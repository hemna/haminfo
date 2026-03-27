"""Packet processor threads for MQTT ingestion.

These threads consume packets from queues and process them
for storage in the database.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert


from haminfo import threads
from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.mqtt.filters import WeatherPacketFilter, _convert_packet_to_dict

# Batch size for bulk database operations
BATCH_SIZE = 500
# How often to print stats (every N packets)
STATS_INTERVAL = 500


class APRSPacketProcessorThread(threads.MyThread):
    """Thread that processes all APRS packets from a queue.

    Accumulates packets and saves them in batches to the database
    for better write performance.

    Supports staggered batch saving to reduce DB contention when multiple
    processor threads run in parallel. Each thread can have a different
    batch_save_threshold based on its thread_index.
    """

    # Stagger increment per thread (e.g., thread 0=500, thread 1=525, etc.)
    BATCH_STAGGER = 25

    def __init__(
        self,
        packet_queue: queue.Queue,
        session_factory: Any,
        stats: dict,
        stats_lock: threading.Lock,
        thread_index: int = 0,
    ):
        super().__init__('APRSPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session_factory = session_factory
        self.stats = stats
        self.stats_lock = stats_lock
        self.aprs_packets: list[APRSPacket] = []
        self.thread_index = thread_index
        # Stagger batch save thresholds: thread 0=500, thread 1=525, thread 2=550, etc.
        self.batch_save_threshold = BATCH_SIZE + (thread_index * self.BATCH_STAGGER)
        logger.info(
            f'[T{thread_index}] APRSPacketProcessorThread initialized with '
            f'batch_save_threshold={self.batch_save_threshold}'
        )

    def loop(self) -> bool:
        try:
            aprsd_packet = self.packet_queue.get(timeout=1.0)

            aprs_data = _convert_packet_to_dict(aprsd_packet)
            if aprs_data is None:
                return True

            # Track unique callsigns
            from_call = aprs_data.get('from_call')
            if from_call:
                with self.stats_lock:
                    if 'unique_callsigns' not in self.stats:
                        self.stats['unique_callsigns'] = set()
                    self.stats['unique_callsigns'].add(from_call)

            # Create APRSPacket record
            try:
                aprs_packet = APRSPacket.from_json(aprs_data)
                self.aprs_packets.append(aprs_packet)

                with self.stats_lock:
                    self.stats['packet_counter'] = (
                        self.stats.get('packet_counter', 0) + 1
                    )

                    packet_type = (
                        getattr(aprsd_packet, 'packet_type', None)
                        or getattr(aprs_packet, 'packet_type', None)
                        or 'unknown'
                    )
                    if 'packet_types' not in self.stats:
                        self.stats['packet_types'] = {}
                    self.stats['packet_types'][packet_type] = (
                        self.stats['packet_types'].get(packet_type, 0) + 1
                    )
            except Exception as ex:
                logger.error(f'Failed to create APRSPacket from JSON: {ex}')
                logger.debug(f'Packet data: {aprs_data}')
                with self.stats_lock:
                    if 'packet_types' not in self.stats:
                        self.stats['packet_types'] = {}
                    self.stats['packet_types']['failed'] = (
                        self.stats['packet_types'].get('failed', 0) + 1
                    )

            self._save_packets_if_needed()

            # Print detailed stats periodically (every STATS_INTERVAL packets)
            with self.stats_lock:
                counter = self.stats.get('packet_counter', 0)
            if counter % STATS_INTERVAL == 0:
                self._print_stats()

        except queue.Empty:
            self._save_packets_if_needed()
            return True
        except Exception as ex:
            logger.error(f'Error processing APRS packet: {ex}')
            logger.exception(ex)
            return True

        return True

    def _save_packets_if_needed(self) -> None:
        """Save APRSPackets to database if we've accumulated enough.

        Uses INSERT ... ON CONFLICT DO NOTHING to handle duplicate
        (from_call, timestamp) keys gracefully.
        Gets a fresh session from the factory for each batch to avoid
        stale connection issues.

        Uses staggered threshold based on thread_index to avoid all threads
        saving simultaneously and causing DB contention.
        """
        if len(self.aprs_packets) < self.batch_save_threshold:
            return

        # Get a fresh session for this batch
        session = self.session_factory()
        try:
            packets_to_save = len(self.aprs_packets)
            logger.info(
                f'[T{self.thread_index}] Saving {packets_to_save} APRS packets to DB.'
            )
            tic = time.perf_counter()

            # Convert ORM objects to dicts for bulk insert
            packet_dicts = []
            for pkt in self.aprs_packets:
                packet_dicts.append(
                    {
                        'from_call': pkt.from_call,
                        'to_call': pkt.to_call,
                        'path': pkt.path,
                        'timestamp': pkt.timestamp,
                        'received_at': pkt.received_at,
                        'raw': pkt.raw,
                        'packet_type': pkt.packet_type,
                        'latitude': pkt.latitude,
                        'longitude': pkt.longitude,
                        'location': pkt.location,
                        'altitude': pkt.altitude,
                        'course': pkt.course,
                        'speed': pkt.speed,
                        'symbol': pkt.symbol,
                        'symbol_table': pkt.symbol_table,
                        'comment': pkt.comment,
                    }
                )

            # Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING
            stmt = pg_insert(APRSPacket).values(packet_dicts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['from_call', 'timestamp']
            )
            result = session.execute(stmt)
            session.commit()

            # rowcount shows how many were actually inserted (not duplicates)
            actual_inserted = result.rowcount
            toc = time.perf_counter()

            with self.stats_lock:
                self.stats['packets_saved'] = (
                    self.stats.get('packets_saved', 0) + actual_inserted
                )

            if actual_inserted < packets_to_save:
                logger.info(
                    f'[T{self.thread_index}] Inserted {actual_inserted}/{packets_to_save} packets '
                    f'({packets_to_save - actual_inserted} duplicates skipped) '
                    f'in {toc - tic:0.4f}s'
                )
            else:
                logger.info(
                    f'[T{self.thread_index}] Time to save APRS packets = {toc - tic:0.4f}s'
                )
            # Only clear on success — failed batches will be retried
            self.aprs_packets = []
        except Exception as ex:
            session.rollback()
            logger.error(f'[T{self.thread_index}] Failed to save APRS packets: {ex}')
            logger.exception(ex)
        finally:
            # Always close the session to return connection to pool
            session.close()

    def _print_stats(self) -> None:
        """Print statistics about processed packets."""
        with self.stats_lock:
            packet_counter = self.stats.get('packet_counter', 0)
            packets_saved = self.stats.get('packets_saved', 0)
            unique_callsigns = len(self.stats.get('unique_callsigns', set()))
            packet_types = self.stats.get('packet_types', {}).copy()
            start_time = self.stats.get('start_time')

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
            f'Packets pending save: <yellow>{len(self.aprs_packets)}</yellow>'
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
        if not self.aprs_packets:
            return

        session = self.session_factory()
        try:
            packets_to_save = len(self.aprs_packets)
            logger.info(
                f'[T{self.thread_index}] Saving {packets_to_save} remaining APRS packets before shutdown.'
            )
            session.bulk_save_objects(self.aprs_packets)
            session.commit()
            with self.stats_lock:
                self.stats['packets_saved'] = (
                    self.stats.get('packets_saved', 0) + packets_to_save
                )
            self.aprs_packets = []
        except Exception as ex:
            session.rollback()
            logger.error(
                f'[T{self.thread_index}] Failed to save remaining APRS packets: {ex}'
            )
            logger.exception(ex)
        finally:
            session.close()


class WeatherPacketProcessorThread(threads.MyThread):
    """Thread that processes weather packets from a queue.

    Uses WeatherPacketFilter to handle station lookup/creation
    and report generation.
    """

    def __init__(
        self,
        packet_queue: queue.Queue,
        session_factory: Any,
        stats: dict,
        stats_lock: threading.Lock,
    ):
        super().__init__('WeatherPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session_factory = session_factory
        self.stats = stats
        self.stats_lock = stats_lock
        self.reports: list = []
        self.weather_filter = WeatherPacketFilter(
            session_factory, stats, stats_lock, self.reports
        )

    def loop(self) -> bool:
        try:
            aprsd_packet = self.packet_queue.get(timeout=1.0)
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

        session = self.session_factory()
        try:
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
            session.rollback()
            logger.error(f'ValueError saving weather reports: {ex}')
            for r in self.reports:
                if hasattr(r, 'raw_report') and r.raw_report and '\x00' in r.raw_report:
                    logger.error(f'Null char found in report: {r}')
        except Exception as ex:
            session.rollback()
            logger.error(f'Failed to save weather reports: {ex}')
            logger.exception(ex)
        finally:
            session.close()

    def _cleanup(self) -> None:
        """Save any remaining weather reports before stopping."""
        if not self.reports:
            return

        session = self.session_factory()
        try:
            count = len(self.reports)
            logger.info(f'Saving {count} remaining weather reports before shutdown.')
            session.bulk_save_objects(self.reports)
            session.commit()
            self.reports.clear()
        except Exception as ex:
            session.rollback()
            logger.error(f'Failed to save remaining weather reports: {ex}')
            logger.exception(ex)
        finally:
            session.close()
