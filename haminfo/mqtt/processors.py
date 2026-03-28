"""Packet processor threads for MQTT ingestion.

These threads consume packets from queues and process them
for storage in the database.

Optimized for high throughput with:
- Thread-local counters to minimize lock contention
- Direct JSON to dict conversion (skipping ORM object creation)
- PostgreSQL COPY protocol for bulk inserts
- Batch queue draining
"""

from __future__ import annotations

import io
import queue
import threading
import time
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from haminfo import threads
from haminfo.mqtt.filters import WeatherPacketFilter, _convert_packet_to_dict

# Batch size for bulk database operations
BATCH_SIZE = 500
# How often to print stats (every N packets)
STATS_INTERVAL = 500
# How often to flush thread-local stats to shared stats (every N packets)
STATS_FLUSH_INTERVAL = 100


def _prepare_insert_dict(packet_json: dict) -> Optional[dict]:
    """Convert JSON packet data directly to a dict for database insert.

    This bypasses ORM object creation for better performance.
    Replicates the logic from APRSPacket.from_json() but returns a dict.
    """
    # Handle timestamp
    ts_str = packet_json.get('timestamp', None)
    if not ts_str:
        ts_str = time.time()

    if isinstance(ts_str, (int, float)):
        packet_time = datetime.fromtimestamp(ts_str)
    else:
        try:
            packet_time = datetime.fromisoformat(str(ts_str))
        except (ValueError, TypeError):
            packet_time = datetime.utcnow()

    # Extract core fields with null byte sanitization
    from_call = packet_json.get('from_call', '')
    if from_call:
        from_call = from_call.replace('\x00', '')
    if not from_call:
        return None  # from_call is required

    to_call = packet_json.get('to_call', '')
    if to_call:
        to_call = to_call.replace('\x00', '')

    path = packet_json.get('path', '')
    if isinstance(path, list):
        path = ','.join(path)

    raw = packet_json.get('raw', '')
    if raw:
        raw = raw.replace('\x00', '')

    # Extract position data
    latitude = packet_json.get('latitude')
    longitude = packet_json.get('longitude')
    location = None
    if latitude is not None and longitude is not None:
        location = f'POINT({longitude} {latitude})'

    # Extract symbol info
    symbol = packet_json.get('symbol')
    if symbol:
        symbol_str = str(symbol).replace('\x00', '')
        symbol = symbol_str[0] if len(symbol_str) > 0 else None

    symbol_table = packet_json.get('symbol_table')
    if symbol_table:
        symbol_table_str = str(symbol_table).replace('\x00', '')
        symbol_table = symbol_table_str[0] if len(symbol_table_str) > 0 else None

    # Extract comment
    comment = packet_json.get('comment')
    if comment:
        comment = str(comment).replace('\x00', '')

    # Determine packet type based on content
    packet_type = packet_json.get('packet_type')
    if not packet_type:
        if any(
            packet_json.get(f) is not None
            for f in ('temperature', 'humidity', 'pressure')
        ):
            packet_type = 'weather'
        elif packet_json.get('telemetry_analog') or packet_json.get(
            'telemetry_digital'
        ):
            packet_type = 'telemetry'
        elif packet_json.get('object_name'):
            packet_type = 'object'
        elif packet_json.get('message_text'):
            packet_type = 'message'
        elif packet_json.get('status'):
            packet_type = 'status'
        elif packet_json.get('query_type'):
            packet_type = 'query'
        elif latitude is not None and longitude is not None:
            packet_type = 'position'
        else:
            packet_type = 'unknown'

    return {
        'from_call': from_call,
        'to_call': to_call or None,
        'path': path or None,
        'timestamp': packet_time,
        'received_at': datetime.utcnow(),
        'raw': raw,
        'packet_type': packet_type,
        'latitude': latitude,
        'longitude': longitude,
        'location': location,
        'altitude': packet_json.get('altitude'),
        'course': packet_json.get('course'),
        'speed': packet_json.get('speed'),
        'symbol': symbol,
        'symbol_table': symbol_table,
        'comment': comment,
    }


class APRSPacketProcessorThread(threads.MyThread):
    """Thread that processes all APRS packets from a queue.

    Optimized for high throughput:
    - Uses thread-local counters to minimize lock contention
    - Converts JSON directly to insert dicts (no ORM objects)
    - Uses PostgreSQL COPY protocol for bulk inserts
    - Batches stats updates

    Supports staggered batch saving to reduce DB contention when multiple
    processor threads run in parallel. Each thread can have a different
    batch_save_threshold based on its thread_index.

    When stats_only=True, packets are processed for statistics but not
    saved to the database. This is useful for measuring MQTT ingestion
    throughput independent of database performance.
    """

    # Stagger increment per thread (e.g., thread 0=500, thread 1=525, etc.)
    BATCH_STAGGER = 25

    # Columns for COPY protocol (must match table order)
    COPY_COLUMNS = [
        'from_call',
        'to_call',
        'path',
        'timestamp',
        'received_at',
        'raw',
        'packet_type',
        'latitude',
        'longitude',
        'location',
        'altitude',
        'course',
        'speed',
        'symbol',
        'symbol_table',
        'comment',
    ]

    def __init__(
        self,
        packet_queue: queue.Queue,
        session_factory: Any,
        stats: dict,
        stats_lock: threading.Lock,
        thread_index: int = 0,
        stats_only: bool = False,
    ):
        super().__init__('APRSPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session_factory = session_factory
        self.stats = stats
        self.stats_lock = stats_lock
        self.packet_dicts: list[dict] = []  # Store dicts directly, not ORM objects
        self.thread_index = thread_index
        self.stats_only = stats_only
        # Stagger batch save thresholds
        self.batch_save_threshold = BATCH_SIZE + (thread_index * self.BATCH_STAGGER)

        # Thread-local counters to minimize lock contention
        self._local_packet_count = 0
        self._local_packets_saved = 0
        self._local_callsigns: set = set()
        self._local_packet_types: dict = {}
        self._last_stats_flush = 0

        # Initialize per-thread pending count in shared stats (one-time lock)
        with self.stats_lock:
            if 'pending_per_thread' not in self.stats:
                self.stats['pending_per_thread'] = {}
            self.stats['pending_per_thread'][thread_index] = 0

        mode = (
            'STATS-ONLY mode'
            if stats_only
            else f'batch_save_threshold={self.batch_save_threshold}'
        )
        logger.info(
            f'[T{thread_index}] APRSPacketProcessorThread initialized with {mode}'
        )

    def _flush_local_stats(self) -> None:
        """Flush thread-local counters to shared stats dict.

        Called periodically to minimize lock contention while keeping
        shared stats reasonably up-to-date.
        """
        if self._local_packet_count == 0:
            return

        with self.stats_lock:
            self.stats['packet_counter'] = (
                self.stats.get('packet_counter', 0) + self._local_packet_count
            )
            self.stats['packets_saved'] = (
                self.stats.get('packets_saved', 0) + self._local_packets_saved
            )
            self.stats['pending_per_thread'][self.thread_index] = len(self.packet_dicts)

            # Merge callsigns
            if 'unique_callsigns' not in self.stats:
                self.stats['unique_callsigns'] = set()
            self.stats['unique_callsigns'].update(self._local_callsigns)

            # Merge packet types
            if 'packet_types' not in self.stats:
                self.stats['packet_types'] = {}
            for ptype, count in self._local_packet_types.items():
                self.stats['packet_types'][ptype] = (
                    self.stats['packet_types'].get(ptype, 0) + count
                )

        # Reset local counters
        self._local_packet_count = 0
        self._local_packets_saved = 0
        self._local_callsigns.clear()
        self._local_packet_types.clear()
        self._last_stats_flush = time.time()

    def loop(self) -> bool:
        try:
            aprsd_packet = self.packet_queue.get(timeout=0.5)  # Reduced timeout

            aprs_data = _convert_packet_to_dict(aprsd_packet)
            if aprs_data is None:
                return True

            # Convert directly to insert dict (skip ORM object)
            packet_dict = _prepare_insert_dict(aprs_data)
            if packet_dict is None:
                return True

            self.packet_dicts.append(packet_dict)

            # Update thread-local counters (no lock!)
            from_call = packet_dict.get('from_call')
            if from_call:
                self._local_callsigns.add(from_call)

            self._local_packet_count += 1

            packet_type = packet_dict.get('packet_type', 'unknown')
            self._local_packet_types[packet_type] = (
                self._local_packet_types.get(packet_type, 0) + 1
            )

            # Periodically flush stats to shared dict
            if self._local_packet_count >= STATS_FLUSH_INTERVAL:
                self._flush_local_stats()

            self._save_packets_if_needed()

            # Only thread 0 prints stats
            if self.thread_index == 0:
                with self.stats_lock:
                    counter = self.stats.get('packet_counter', 0)
                if counter % STATS_INTERVAL == 0 and counter > 0:
                    self._print_stats()

        except queue.Empty:
            # Flush stats on idle
            if self._local_packet_count > 0:
                self._flush_local_stats()
            self._save_packets_if_needed()
            return True
        except Exception as ex:
            logger.error(f'Error processing APRS packet: {ex}')
            logger.exception(ex)
            return True

        return True

    def _save_packets_if_needed(self) -> None:
        """Save packets to database if we've accumulated enough.

        Uses PostgreSQL COPY protocol for maximum throughput.
        Falls back to INSERT on COPY failure.
        """
        if len(self.packet_dicts) < self.batch_save_threshold:
            return

        # In stats_only mode, just discard packets and update stats
        if self.stats_only:
            packets_discarded = len(self.packet_dicts)
            self._local_packets_saved += packets_discarded
            logger.debug(
                f'[T{self.thread_index}] STATS-ONLY: Discarded {packets_discarded} packets (no DB write)'
            )
            self.packet_dicts = []
            return

        packets_to_save = len(self.packet_dicts)
        logger.info(
            f'[T{self.thread_index}] Saving {packets_to_save} APRS packets to DB.'
        )
        tic = time.perf_counter()

        # Try COPY protocol first (fastest)
        actual_inserted = self._save_with_copy()

        if actual_inserted < 0:
            # COPY failed, fall back to INSERT
            actual_inserted = self._save_with_insert()

        toc = time.perf_counter()

        if actual_inserted >= 0:
            self._local_packets_saved += actual_inserted

            if actual_inserted < packets_to_save:
                logger.info(
                    f'[T{self.thread_index}] Inserted {actual_inserted}/{packets_to_save} packets '
                    f'({packets_to_save - actual_inserted} duplicates skipped) '
                    f'in {toc - tic:0.4f}s'
                )
            else:
                logger.info(
                    f'[T{self.thread_index}] Saved {actual_inserted} packets in {toc - tic:0.4f}s'
                )
            self.packet_dicts = []

    def _save_with_copy(self) -> int:
        """Save packets using PostgreSQL COPY protocol.

        Returns number of rows inserted, or -1 on failure.
        COPY doesn't support ON CONFLICT, so we use a temp table approach.
        """
        session = None
        try:
            session = self.session_factory()
            conn = session.connection()
            raw_conn = conn.connection.dbapi_connection

            # Create TEXT format buffer for COPY (not CSV - simpler escaping)
            # TEXT format uses tab delimiter, \N for NULL, and backslash escaping
            buffer = io.StringIO()

            for pkt in self.packet_dicts:
                row = []
                for col in self.COPY_COLUMNS:
                    val = pkt.get(col)
                    if val is None:
                        row.append('\\N')  # NULL in TEXT COPY format
                    elif isinstance(val, datetime):
                        row.append(val.isoformat())
                    else:
                        # Escape special characters for TEXT COPY format
                        val_str = str(val)
                        # Order matters: escape backslash first, then others
                        val_str = val_str.replace('\\', '\\\\')
                        val_str = val_str.replace('\t', '\\t')
                        val_str = val_str.replace('\n', '\\n')
                        val_str = val_str.replace('\r', '\\r')
                        row.append(val_str)
                buffer.write('\t'.join(row) + '\n')

            buffer.seek(0)

            # Use temp table + INSERT ... ON CONFLICT for deduplication
            with raw_conn.cursor() as cur:
                # Create temp table with location as TEXT (not geography)
                # so we can COPY WKT strings and convert during INSERT
                cur.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS aprs_packet_staging (
                        from_call VARCHAR(20),
                        to_call VARCHAR(20),
                        path VARCHAR(255),
                        timestamp TIMESTAMP,
                        received_at TIMESTAMP,
                        raw TEXT,
                        packet_type VARCHAR(50),
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        location TEXT,
                        altitude REAL,
                        course REAL,
                        speed REAL,
                        symbol CHAR(1),
                        symbol_table CHAR(1),
                        comment TEXT
                    ) ON COMMIT DROP
                """)

                # COPY into temp table using TEXT format (not CSV)
                cur.copy_expert(
                    f'COPY aprs_packet_staging ({",".join(self.COPY_COLUMNS)}) FROM STDIN',
                    buffer,
                )

                # INSERT from temp to real table with conflict handling
                # Convert location TEXT to geography using ST_GeogFromText
                cur.execute("""
                    INSERT INTO aprs_packet (
                        from_call, to_call, path, timestamp, received_at, raw,
                        packet_type, latitude, longitude, location, altitude,
                        course, speed, symbol, symbol_table, comment
                    )
                    SELECT from_call, to_call, path, timestamp, received_at, raw,
                           packet_type, latitude, longitude, 
                           CASE WHEN location IS NOT NULL AND location != '' 
                                THEN ST_GeogFromText(location) 
                                ELSE NULL END,
                           altitude, course, speed, symbol, symbol_table, comment
                    FROM aprs_packet_staging
                    ON CONFLICT (from_call, timestamp) DO NOTHING
                """)
                actual_inserted = cur.rowcount

            raw_conn.commit()
            return actual_inserted

        except Exception as ex:
            logger.warning(f'[T{self.thread_index}] COPY failed, will try INSERT: {ex}')
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
            return -1
        finally:
            if session is not None:
                session.close()

    def _save_with_insert(self) -> int:
        """Save packets using INSERT ... ON CONFLICT (fallback method)."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from haminfo.db.models.aprs_packet import APRSPacket

        session = None
        try:
            session = self.session_factory()

            stmt = pg_insert(APRSPacket).values(self.packet_dicts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['from_call', 'timestamp']
            )
            result = session.execute(stmt)
            session.commit()

            return result.rowcount

        except Exception as ex:
            if session is not None:
                session.rollback()
            logger.error(f'[T{self.thread_index}] Failed to save APRS packets: {ex}')
            logger.exception(ex)
            return 0
        finally:
            if session is not None:
                session.close()

    def _print_stats(self) -> None:
        """Print statistics about processed packets.

        Only called by thread 0 to avoid duplicate output.
        Shows aggregated stats from all processor threads.
        """
        # Ensure local stats are flushed before printing
        self._flush_local_stats()

        with self.stats_lock:
            packet_counter = self.stats.get('packet_counter', 0)
            packets_saved = self.stats.get('packets_saved', 0)
            unique_callsigns = len(self.stats.get('unique_callsigns', set()))
            packet_types = self.stats.get('packet_types', {}).copy()
            start_time = self.stats.get('start_time')
            pending_per_thread = self.stats.get('pending_per_thread', {})
            total_pending = sum(pending_per_thread.values())

        separator = '=' * 80
        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')
        logger.opt(colors=True).info(
            '<bold><cyan>APRS Packet Processing Statistics</cyan></bold>'
        )
        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')
        logger.opt(colors=True).info(
            f'Total packets processed: <green>{packet_counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Total packets saved to database: <green>{packets_saved}</green>'
        )
        logger.opt(colors=True).info(
            f'Packets pending save (all threads): <yellow>{total_pending}</yellow>'
        )
        logger.opt(colors=True).info(
            f'Unique callsigns seen: <cyan>{unique_callsigns}</cyan>'
        )

        if packet_types:
            logger.opt(colors=True).info('')
            logger.opt(colors=True).info('<bold>Packet Type Breakdown:</bold>')
            sorted_types = sorted(
                packet_types.items(), key=lambda x: x[1], reverse=True
            )
            for ptype, count in sorted_types:
                pct = (count / packet_counter * 100) if packet_counter > 0 else 0
                color = 'green' if count > 100 else 'yellow' if count > 10 else 'red'
                logger.opt(colors=True).info(
                    f'  <cyan>{ptype:20s}</cyan>: <{color}>{count:6d}</{color}>'
                    f' (<magenta>{pct:5.1f}%</magenta>)'
                )

        if start_time and packet_counter > 0:
            elapsed = time.time() - start_time
            if elapsed > 0:
                rate = packet_counter / elapsed
                save_rate = packets_saved / elapsed if packets_saved > 0 else 0
                logger.opt(colors=True).info('')
                logger.opt(colors=True).info(
                    f'Average processing rate: <green>{rate:.2f}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Average save rate: <green>{save_rate:.2f}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Uptime: <cyan>{elapsed:.0f}</cyan> seconds '
                    f'(<cyan>{elapsed / 60:.1f}</cyan> minutes)'
                )

        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')

    def _cleanup(self) -> None:
        """Save any remaining packets before stopping."""
        # Flush local stats
        self._flush_local_stats()

        if not self.packet_dicts:
            return

        # In stats_only mode, just discard remaining packets
        if self.stats_only:
            count = len(self.packet_dicts)
            logger.info(
                f'[T{self.thread_index}] STATS-ONLY: Discarding {count} remaining packets on shutdown'
            )
            self.packet_dicts = []
            return

        # Force save remaining packets
        packets_to_save = len(self.packet_dicts)
        logger.info(
            f'[T{self.thread_index}] Saving {packets_to_save} remaining APRS packets before shutdown.'
        )

        actual_inserted = self._save_with_copy()
        if actual_inserted < 0:
            actual_inserted = self._save_with_insert()

        if actual_inserted >= 0:
            with self.stats_lock:
                self.stats['packets_saved'] = (
                    self.stats.get('packets_saved', 0) + actual_inserted
                )
            self.packet_dicts = []


class WeatherPacketProcessorThread(threads.MyThread):
    """Thread that processes weather packets from a queue.

    Uses WeatherPacketFilter to handle station lookup/creation
    and report generation.

    When stats_only=True, packets are processed for statistics but not
    saved to the database.
    """

    def __init__(
        self,
        packet_queue: queue.Queue,
        session_factory: Any,
        stats: dict,
        stats_lock: threading.Lock,
        stats_only: bool = False,
    ):
        super().__init__('WeatherPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session_factory = session_factory
        self.stats = stats
        self.stats_lock = stats_lock
        self.stats_only = stats_only
        self.reports: list = []
        self.weather_filter = WeatherPacketFilter(
            session_factory, stats, stats_lock, self.reports, stats_only=stats_only
        )
        if stats_only:
            logger.info('WeatherPacketProcessorThread initialized in STATS-ONLY mode')

    def loop(self) -> bool:
        try:
            aprsd_packet = self.packet_queue.get(timeout=0.5)  # Reduced timeout
            self.weather_filter.filter(aprsd_packet)

            if len(self.reports) >= BATCH_SIZE:
                self._save_reports()

        except queue.Empty:
            self._save_reports()
            return True
        except Exception as ex:
            logger.error(f'Error processing weather packet: {ex}')
            logger.exception(ex)
            return True

        return True

    def _save_reports(self) -> None:
        """Save weather reports to database."""
        if not self.reports:
            return

        # In stats_only mode, just discard reports
        if self.stats_only:
            count = len(self.reports)
            logger.debug(
                f'STATS-ONLY: Discarding {count} weather reports (no DB write)'
            )
            self.reports.clear()
            return

        session = None
        try:
            session = self.session_factory()
            count = len(self.reports)
            logger.info(f'Saving {count} weather reports to DB.')
            tic = time.perf_counter()
            session.bulk_save_objects(self.reports)
            session.commit()
            toc = time.perf_counter()
            logger.info(f'Time to save weather reports = {toc - tic:0.4f}s')
            # Only clear on success — failed batches will be retried
            self.reports.clear()
        except ValueError as ex:
            if session is not None:
                session.rollback()
            logger.error(f'ValueError saving weather reports: {ex}')
            for r in self.reports:
                if hasattr(r, 'raw_report') and r.raw_report and '\x00' in r.raw_report:
                    logger.error(f'Null char found in report: {r}')
        except Exception as ex:
            if session is not None:
                session.rollback()
            logger.error(f'Failed to save weather reports: {ex}')
            logger.exception(ex)
        finally:
            if session is not None:
                session.close()

    def _cleanup(self) -> None:
        """Save any remaining weather reports before stopping."""
        if not self.reports:
            return

        # In stats_only mode, just discard remaining reports
        if self.stats_only:
            count = len(self.reports)
            logger.info(
                f'STATS-ONLY: Discarding {count} remaining weather reports on shutdown'
            )
            self.reports.clear()
            return

        session = None
        try:
            session = self.session_factory()
            count = len(self.reports)
            logger.info(f'Saving {count} remaining weather reports before shutdown.')
            session.bulk_save_objects(self.reports)
            session.commit()
            self.reports.clear()
        except Exception as ex:
            if session is not None:
                session.rollback()
            logger.error(f'Failed to save remaining weather reports: {ex}')
            logger.exception(ex)
        finally:
            if session is not None:
                session.close()
