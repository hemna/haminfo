"""MQTT ingestion module for APRS and weather data.

.. deprecated::
    This module filename contains a typo ('injest' instead of 'ingest').
    It will be renamed to 'mqtt_ingest.py' in a future release.
    Please update any direct imports when this migration occurs.
"""

import click
import datetime
import json
import queue
import signal
import threading
import time

from cachetools import cached, TTLCache
from geopy.geocoders import Nominatim
from oslo_config import cfg
from oslo_log import log as logging
from loguru import logger
import paho.mqtt.client as mqtt

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils, threads
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo.db.models.aprs_packet import APRSPacket

from aprsd.packets import core
from aprsd.packets.core import WeatherPacket


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


def signal_handler(sig, frame):
    click.echo('signal_handler: called')
    threads.MyThreadList().stop_all()
    if 'subprocess' not in str(frame):
        LOG.info(
            'Ctrl+C, Sending all threads exit! Can take up to 10 seconds {}'.format(
                datetime.datetime.now(),
            ),
        )
        time.sleep(1.5)


@cached(cache=TTLCache(maxsize=640 * 1024, ttl=300))
def get_location(coordinates):
    nom = Nominatim(user_agent='haminfo')
    location = None
    try:
        location = nom.geocode(
            coordinates,
            language='en',
            addressdetails=True,
        )
    except Exception:
        LOG.error(f'Failed to get location for {coordinates}')
        location = None
    return location


class APRSPacketFilter:
    """Filter that writes packets to the database aprs_packets table."""

    def filter(self, packet):
        if not isinstance(packet, core.Packet):
            return None


class WeatherPacketFilter:
    """Filter that processes weather packets and saves them to the database."""

    def __init__(self, session, stats, stats_lock, reports):
        """Initialize the weather packet filter with database session and stats."""
        self.session = session
        self.stats = stats
        self.stats_lock = stats_lock
        self.reports = reports

    def filter(self, packet):
        """Process weather packet: find/create station, create report, and save to DB."""
        # Check if this is a weather packet
        if not isinstance(packet, WeatherPacket):
            return packet

        # Convert aprsd packet to dict for database operations
        try:
            if hasattr(packet, 'to_dict'):
                aprs_data = packet.to_dict()
            else:
                # Fallback to to_json() and parse
                aprs_data_json = packet.to_json()
                aprs_data = (
                    json.loads(aprs_data_json)
                    if isinstance(aprs_data_json, str)
                    else aprs_data_json
                )
        except Exception as ex:
            LOG.error(f'Failed to convert aprsd packet to dict: {ex}')
            return None

        # Build the DB model object and insert it
        station = None
        try:
            station = WeatherStation.find_station_by_callsign(
                self.session, aprs_data['from_call']
            )
        except Exception as ex:
            LOG.error(f'Failed to find station {aprs_data["from_call"]}')
            LOG.exception(ex)
            pass

        if not station:
            LOG.info(f"Didn't find station {aprs_data['from_call']}")
            station = WeatherStation.from_json(aprs_data)
            if station:
                # Get the country code
                coordinates = f'{station.latitude:0.6f}, {station.longitude:0.6f}'
                location = get_location(coordinates)
                if location and hasattr(location, 'raw'):
                    address = location.raw.get('address')
                    if address:
                        station.country_code = address['country_code']
                    else:
                        LOG.error(f'Failed to find address for {coordinates}')
                try:
                    self.session.add(station)
                    self.session.commit()
                except Exception as ex:
                    self.session.rollback()
                    LOG.error(
                        'Failed getting/creating station for '
                        f'report {aprs_data["from_call"]}'
                    )
                    LOG.error(ex.__cause__)
                    return None
            else:
                # Failed to get station from json
                LOG.warning('Failed to get station from json.')
                return None

        try:
            report = WeatherReport.from_json(aprs_data, station.id)
        except Exception as ex:
            LOG.error(aprs_data)
            LOG.error('Failed to create WeatherReport because')
            LOG.exception(ex)
            return None

        try:
            # Make sure there is valid data to add to the DB
            if report.is_valid():
                self.reports.append(report)
                with self.stats_lock:
                    self.stats['report_counter'] = (
                        self.stats.get('report_counter', 0) + 1
                    )
                return packet
            else:
                return None
        except ValueError as ex:
            self.session.rollback()
            LOG.exception(ex)
            LOG.error(report)
            return None
        except Exception as ex:
            self.session.rollback()
            LOG.error(f'Failed to add_wx_report {report}')
            LOG.error(ex)
            return None


class InjestPacketFilter:
    """Filter that injests packets into the database."""

    def filter(self, packet):
        return packet


class APRSPacketProcessorThread(threads.MyThread):
    """Thread that processes all APRS packets from a queue.

    Supports staggered batch saving to reduce DB contention when multiple
    processor threads run in parallel. Each thread can have a different
    batch_save_threshold based on its thread_index.
    """

    # Base batch size - threads will save at BASE + (thread_index * STAGGER)
    BASE_BATCH_SIZE = 200
    BATCH_STAGGER = 25  # Stagger by 25 packets per thread

    def __init__(self, packet_queue, session, stats, stats_lock, thread_index=0):
        super().__init__('APRSPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session = session
        self.stats = stats
        self.stats_lock = stats_lock
        self.aprs_packets = []
        self.thread_index = thread_index
        # Stagger batch save thresholds: thread 0=200, thread 1=225, thread 2=250, etc.
        self.batch_save_threshold = self.BASE_BATCH_SIZE + (
            thread_index * self.BATCH_STAGGER
        )
        LOG.info(
            f'Thread {thread_index}: batch_save_threshold = {self.batch_save_threshold}'
        )

    def loop(self):
        try:
            # Get aprsd packet object from queue with timeout
            aprsd_packet = self.packet_queue.get(timeout=1.0)

            # Convert aprsd packet to dict for database operations
            try:
                if hasattr(aprsd_packet, 'to_dict'):
                    aprs_data = aprsd_packet.to_dict()
                else:
                    # Fallback to to_json() and parse
                    aprs_data_json = aprsd_packet.to_json()
                    aprs_data = (
                        json.loads(aprs_data_json)
                        if isinstance(aprs_data_json, str)
                        else aprs_data_json
                    )
            except Exception as ex:
                LOG.error(f'Failed to convert aprsd packet to dict: {ex}')
                return True

            # Track unique callsigns
            from_call = aprs_data.get('from_call')
            if from_call:
                with self.stats_lock:
                    if 'unique_callsigns' not in self.stats:
                        self.stats['unique_callsigns'] = set()
                    self.stats['unique_callsigns'].add(from_call)

            # Create APRSPacket record for every packet received
            try:
                aprs_packet = APRSPacket.from_json(aprs_data)
                self.aprs_packets.append(aprs_packet)

                with self.stats_lock:
                    self.stats['packet_counter'] = (
                        self.stats.get('packet_counter', 0) + 1
                    )

                    # Track packet type from aprsd packet object
                    packet_type = getattr(aprsd_packet, 'packet_type', None)
                    if not packet_type:
                        packet_type = (
                            getattr(aprs_packet, 'packet_type', None) or 'unknown'
                        )

                    if 'packet_types' not in self.stats:
                        self.stats['packet_types'] = {}
                    self.stats['packet_types'][packet_type] = (
                        self.stats['packet_types'].get(packet_type, 0) + 1
                    )
            except Exception as ex:
                LOG.error(f'Failed to create APRSPacket from JSON: {ex}')
                LOG.debug(f'Packet data: {aprs_data}')
                with self.stats_lock:
                    if 'packet_types' not in self.stats:
                        self.stats['packet_types'] = {}
                    self.stats['packet_types']['failed'] = (
                        self.stats['packet_types'].get('failed', 0) + 1
                    )

            # Save packets periodically
            self._save_packets_if_needed()

            # Print stats periodically
            with self.stats_lock:
                counter = self.stats.get('packet_counter', 0)
            if counter % 500 == 0:
                self._print_stats()

            if counter % 25 == 0:
                LOG.debug(f'Packet Counter: {counter}')

        except queue.Empty:
            # Timeout - check if we should save any pending packets
            self._save_packets_if_needed()
            return True
        except Exception as ex:
            LOG.error(f'Error processing APRS packet: {ex}')
            LOG.exception(ex)
            return True

        return True

    def _save_packets_if_needed(self):
        """Save APRSPackets to database if we've accumulated enough.

        Uses staggered threshold based on thread_index to avoid all threads
        saving simultaneously and causing DB contention.
        """
        if len(self.aprs_packets) >= self.batch_save_threshold:
            try:
                packets_to_save = len(self.aprs_packets)
                LOG.info(
                    f'[T{self.thread_index}] Saving {packets_to_save} APRS packets to DB.'
                )
                tic = time.perf_counter()
                self.session.bulk_save_objects(self.aprs_packets)
                self.session.commit()
                toc = time.perf_counter()

                with self.stats_lock:
                    self.stats['packets_saved'] = (
                        self.stats.get('packets_saved', 0) + packets_to_save
                    )

                LOG.info(
                    f'[T{self.thread_index}] Time to save APRS packets = {toc - tic:0.4f}'
                )
                self.aprs_packets = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f'[T{self.thread_index}] Failed to save APRS packets: {ex}')
                LOG.exception(ex)
                # Drop the packets to avoid memory issues
                self.aprs_packets = []

    def _print_stats(self):
        """Print statistics about processed packets."""
        with self.stats_lock:
            packet_counter = self.stats.get('packet_counter', 0)
            packets_saved = self.stats.get('packets_saved', 0)
            unique_callsigns = len(self.stats.get('unique_callsigns', set()))
            packet_types = self.stats.get('packet_types', {})
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
            for packet_type, count in sorted_types:
                percentage = (count / packet_counter * 100) if packet_counter > 0 else 0
                packet_type_str = f'{packet_type:20s}'
                count_str = f'{count:6d}'
                percentage_str = f'{percentage:5.1f}%'
                color_tag = (
                    'green' if count > 100 else 'yellow' if count > 10 else 'red'
                )
                logger.opt(colors=True).info(
                    f'  <cyan>{packet_type_str}</cyan>: <{color_tag}>{count_str}</{color_tag}> (<magenta>{percentage_str}</magenta>)'
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
                    f'Uptime: <cyan>{elapsed:.0f}</cyan> seconds (<cyan>{elapsed / 60:.1f}</cyan> minutes)'
                )

        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')

    def _cleanup(self):
        """Save any remaining packets before stopping."""
        if self.aprs_packets:
            try:
                packets_to_save = len(self.aprs_packets)
                LOG.info(
                    f'[T{self.thread_index}] Saving {packets_to_save} remaining APRS packets before shutdown.'
                )
                self.session.bulk_save_objects(self.aprs_packets)
                self.session.commit()

                with self.stats_lock:
                    self.stats['packets_saved'] = (
                        self.stats.get('packets_saved', 0) + packets_to_save
                    )

                self.aprs_packets = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(
                    f'[T{self.thread_index}] Failed to save remaining APRS packets: {ex}'
                )
                LOG.exception(ex)


class WeatherPacketProcessorThread(threads.MyThread):
    """Thread that processes weather packets from a queue using WeatherPacketFilter."""

    def __init__(self, packet_queue, session, stats, stats_lock):
        super().__init__('WeatherPacketProcessorThread')
        self.packet_queue = packet_queue
        self.session = session
        self.stats = stats
        self.stats_lock = stats_lock
        self.reports = []
        self.weather_filter = WeatherPacketFilter(
            session, stats, stats_lock, self.reports
        )

    def loop(self):
        try:
            # Get aprsd packet object from queue with timeout
            aprsd_packet = self.packet_queue.get(timeout=1.0)

            # Process weather packet through filter (result ignored, filter modifies self.reports)
            self.weather_filter.filter(aprsd_packet)

            # Save reports periodically
            if len(self.reports) >= 200:
                self._save_reports()

            # Print stats periodically
            with self.stats_lock:
                report_counter = self.stats.get('report_counter', 0)
            if report_counter % 200 == 0 and report_counter > 0:
                self._save_reports()

        except queue.Empty:
            # Timeout - check if we should save any pending reports
            self._save_reports()
            return True
        except Exception as ex:
            LOG.error(f'Error processing weather packet: {ex}')
            LOG.exception(ex)
            return True

        return True

    def _save_reports(self):
        """Save weather reports to database."""
        if not self.reports:
            return

        try:
            LOG.info(f'Saving {len(self.reports)} weather reports to DB.')
            tic = time.perf_counter()
            self.session.bulk_save_objects(self.reports)
            self.session.commit()
            toc = time.perf_counter()
            LOG.warning(f'Time to save weather reports = {toc - tic:0.4f}')
            self.reports = []
        except ValueError as ex:
            self.session.rollback()
            LOG.error(f'Failed for report {self.reports}')
            LOG.exception(ex)
            for r in self.reports:
                if '\x00' in r.raw_report:
                    LOG.error(f'Null char in {r}')
            self.reports = []
        except Exception as ex:
            self.session.rollback()
            LOG.error(f'Failed for report {self.reports}')
            LOG.exception(ex)
            # Just drop all the reports
            self.reports = []

    def _cleanup(self):
        """Save any remaining weather reports before stopping."""
        if self.reports:
            try:
                LOG.info(
                    f'Saving {len(self.reports)} remaining weather reports before shutdown.'
                )
                self.session.bulk_save_objects(self.reports)
                self.session.commit()
                self.reports = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f'Failed to save remaining weather reports: {ex}')
                LOG.exception(ex)


# Class to read from the mqtt queue and dump the packets in to the DB.
class MQTTThread(threads.MyThread):
    client = None
    counter = 0
    last_stats_time = None
    start_time = None

    def __init__(self, packet_queue, stats, stats_lock):
        super().__init__('MQTTThread')
        self.packet_queue = packet_queue
        self.stats = stats
        self.stats_lock = stats_lock
        self.start_time = time.time()
        self.last_stats_time = self.start_time
        # Expose stats as attributes for KeepAliveThread compatibility
        self._update_stats_attributes()
        # Connection state tracking
        self.connected = False
        self.connection_attempts = 0
        self.last_connection_check = 0
        self.reconnect_delay = 1  # Start with 1 second delay
        self.max_reconnect_delay = 60  # Max 60 seconds between attempts
        self.connection_check_interval = 5  # Check connection every 5 seconds
        self.last_message_time = time.time()  # Track last message received
        self.message_timeout = (
            300  # Consider connection dead if no messages for 5 minutes
        )
        self.reconnecting = False  # Flag to prevent concurrent reconnection attempts
        self.reconnect_lock = threading.Lock()  # Lock for reconnection operations
        LOG.info('MQTTThread initialized')
        self.setup()

    def _update_stats_attributes(self):
        """Update thread attributes from stats dict for KeepAliveThread compatibility."""
        with self.stats_lock:
            self.packet_counter = self.stats.get('packet_counter', 0)
            self.packets_saved = self.stats.get('packets_saved', 0)
            self.report_counter = self.stats.get('report_counter', 0)

    def setup(self):
        self._connect()

    def _connect(self):
        """Connect to MQTT broker with error handling."""
        try:
            LOG.info('Creating MQTT Client')
            # Generate a client id based on date and time.
            client_id = f'Haminfo-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect
            self.client.on_connect_fail = self.on_connect_fail

            if CONF.mqtt.user:
                self.client.username_pw_set(
                    username=CONF.mqtt.user, password=CONF.mqtt.password
                )
            else:
                LOG.info('Not using username/password to auth with MQTT')

            LOG.info(
                f'Connecting to MQTT broker at {CONF.mqtt.host_ip}:{CONF.mqtt.host_port}'
            )
            # Set a connection timeout
            self.client.connect(CONF.mqtt.host_ip, CONF.mqtt.host_port, keepalive=60)
            self.client.loop_start()  # Start the network loop in background
            self.connection_attempts += 1

            # Give connection a moment to establish
            time.sleep(0.5)

        except (ConnectionError, OSError) as ex:
            LOG.error(f'Network error connecting to MQTT broker: {ex}')
            self.connected = False
            self.client = None
        except Exception as ex:
            LOG.error(f'Failed to create/connect MQTT client: {ex}')
            LOG.exception(ex)
            self.connected = False
            self.client = None

    def _reconnect(self):
        """Reconnect to MQTT broker with exponential backoff."""
        # Use lock to prevent concurrent reconnection attempts
        with self.reconnect_lock:
            # Don't reconnect if we're already in the process of reconnecting
            # or if we're shutting down
            if self.thread_stop or self.reconnecting:
                return

            self.reconnecting = True

        try:
            if self.client:
                try:
                    LOG.info('Disconnecting existing client before reconnect')
                    self.client.loop_stop()
                    # Give the loop a moment to stop
                    time.sleep(0.5)
                except Exception as ex:
                    LOG.warning(f'Error stopping client loop: {ex}')
                try:
                    self.client.disconnect()
                except Exception as ex:
                    LOG.warning(f'Error disconnecting client: {ex}')
                finally:
                    self.client = None

            self.connected = False

            # Exponential backoff: wait before reconnecting
            delay = min(self.reconnect_delay, self.max_reconnect_delay)
            LOG.info(
                f'Waiting {delay} seconds before reconnecting (attempt {self.connection_attempts})'
            )

            # Sleep in small increments to check for thread_stop
            slept = 0
            while slept < delay and not self.thread_stop:
                time.sleep(min(1, delay - slept))
                slept += 1

            if self.thread_stop:
                return

            # Increase delay for next attempt (exponential backoff)
            self.reconnect_delay = min(
                self.reconnect_delay * 2, self.max_reconnect_delay
            )

            # Attempt reconnection
            self._connect()
        finally:
            with self.reconnect_lock:
                self.reconnecting = False

    def _check_connection_health(self):
        """Check if MQTT connection is healthy."""
        current_time = time.time()

        # Don't check too frequently
        if current_time - self.last_connection_check < self.connection_check_interval:
            return

        self.last_connection_check = current_time

        # Don't check if we're already reconnecting
        if self.reconnecting:
            return

        # Check if client exists
        if not self.client:
            LOG.warning('MQTT client is None, reconnecting...')
            self._reconnect()
            return

        # Check if we're connected
        if not self.connected:
            LOG.warning('MQTT client not connected, reconnecting...')
            self._reconnect()
            return

        # Check if client's internal state indicates connection
        try:
            # Check if the network loop is running
            if (
                not hasattr(self.client, '_thread')
                or not self.client._thread
                or not self.client._thread.is_alive()
            ):
                LOG.warning('MQTT network loop not running, reconnecting...')
                self._reconnect()
                return

            # Check if we've received messages recently (connection might be dead)
            # Only check this if we've been connected for a while (give it time to receive first message)
            if self.start_time is None:
                return  # Not yet initialized, skip health check

            time_since_start = current_time - self.start_time
            if time_since_start > 60:  # Only check after 1 minute of runtime
                time_since_last_message = current_time - self.last_message_time
                if time_since_last_message > self.message_timeout:
                    LOG.warning(
                        f'No messages received for {time_since_last_message:.0f} seconds '
                        f'(timeout: {self.message_timeout}), reconnecting...'
                    )
                    self._reconnect()
                    return

        except AttributeError:
            # _thread attribute might not exist in some versions
            # Try to ping the broker instead
            try:
                if self.client and self.connected:
                    # Use publish with qos=0 to test connection
                    # This is a lightweight way to check if connection is alive
                    pass  # Skip this check if we can't access _thread
            except Exception:
                pass
        except Exception as ex:
            LOG.warning(f'Error checking connection health: {ex}')
            LOG.exception(ex)
            # If we can't check health, try reconnecting
            self._reconnect()

    def on_connect_fail(self, client, userdata):
        """Called when connection fails."""
        LOG.error('MQTT connection failed')
        self.connected = False
        # Don't reconnect here, let the health check handle it

    def on_disconnect(self, client, userdata, flags, rc, properties=None):
        """Called when client disconnects."""
        if rc == 0:
            LOG.info('MQTT client disconnected cleanly')
        else:
            LOG.warning(
                f'MQTT client disconnected unexpectedly (rc={rc}, flags={flags})'
            )
        self.connected = False

        # If disconnect was unexpected, trigger reconnection
        if rc != 0:
            # Reset reconnect delay on unexpected disconnect
            self.reconnect_delay = 1

    def on_connect(self, client, userdata, flags, rc, properties):
        """Called when client connects to broker."""
        if rc == 0:
            LOG.info(
                f'Connected to mqtt://{CONF.mqtt.host_ip}:{CONF.mqtt.host_port}'
                f'/{CONF.mqtt.topic} (rc={rc})'
            )
            self.connected = True
            self.connection_attempts = 0  # Reset on successful connection
            self.reconnect_delay = 1  # Reset reconnect delay
            self.last_message_time = time.time()  # Reset message timer
            try:
                client.subscribe(CONF.mqtt.topic)
                LOG.info(f'Subscribed to topic: {CONF.mqtt.topic}')
            except Exception as ex:
                LOG.error(f'Failed to subscribe to topic {CONF.mqtt.topic}: {ex}')
                LOG.exception(ex)
                self.connected = False
        else:
            LOG.error(f'Failed to connect to MQTT broker (rc={rc})')
            self.connected = False

    def on_message(self, client, userdata, msg):
        """Called when a message is received."""
        try:
            self.counter += 1
            self.last_message_time = time.time()  # Update last message time
            aprs_data_raw = json.loads(msg.payload.decode('utf-8').replace('\x00', ''))
            LOG.debug(f'Raw packet data: {aprs_data_raw}')

            # Try to convert the packet to an aprsd packet object
            aprsd_packet = None
            try:
                aprsd_packet = core.factory(aprs_data_raw)
            except Exception as ex:
                LOG.error(f'Failed to convert to aprsd packet object: {ex}')
                LOG.debug(f'Packet data: {aprs_data_raw}')
                LOG.exception(ex)
                return False

            # Only put valid aprsd packet objects into the queue
            if aprsd_packet:
                try:
                    self.packet_queue.put_nowait(aprsd_packet)
                except queue.Full:
                    LOG.warning('APRS packet queue is full, dropping packet')

            # Print stats periodically (every 500 packets or every 60 seconds)
            current_time = time.time()
            if self.counter % 500 == 0 or (current_time - self.last_stats_time) >= 60:
                self._print_stats()
                self.last_stats_time = current_time
                # Update attributes for KeepAliveThread compatibility
                self._update_stats_attributes()

            if self.counter % 25 == 0:
                with self.stats_lock:
                    packet_counter = self.stats.get('packet_counter', 0)
                    report_counter = self.stats.get('report_counter', 0)
                # Update attributes for KeepAliveThread compatibility
                self._update_stats_attributes()
                LOG.debug(
                    f'Loop counter:{self.counter}  '
                    f'Report Counter:{report_counter}  '
                    f'Packet Counter:{packet_counter}'
                )
        except Exception as ex:
            LOG.error(f'Error processing MQTT message: {ex}')
            LOG.exception(ex)
            return False

    def _print_stats(self):
        """Print statistics about ingested packets using loguru with colors."""
        with self.stats_lock:
            packet_counter = self.stats.get('packet_counter', 0)
            packets_saved = self.stats.get('packets_saved', 0)
            report_counter = self.stats.get('report_counter', 0)
            unique_callsigns = len(self.stats.get('unique_callsigns', set()))
            packet_types = self.stats.get('packet_types', {}).copy()

        separator = '=' * 80
        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')
        logger.opt(colors=True).info(
            '<bold><cyan>MQTT Ingestion Statistics</cyan></bold>'
        )
        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')
        logger.opt(colors=True).info(
            f'Total packets ingested from MQTT: <green>{self.counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Total packets processed: <green>{packet_counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Total packets saved to database: <green>{packets_saved}</green>'
        )
        logger.opt(colors=True).info(
            f'Packets pending in queue: <yellow>{self.packet_queue.qsize()}</yellow>'
        )
        logger.opt(colors=True).info(
            f'Weather reports processed: <green>{report_counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Unique callsigns seen: <cyan>{unique_callsigns}</cyan>'
        )

        if packet_types:
            logger.opt(colors=True).info('')
            logger.opt(colors=True).info('<bold>Packet Type Breakdown:</bold>')
            # Sort by count (descending)
            sorted_types = sorted(
                packet_types.items(), key=lambda x: x[1], reverse=True
            )
            for packet_type, count in sorted_types:
                percentage = (count / packet_counter * 100) if packet_counter > 0 else 0
                # Format values first, then apply colors
                packet_type_str = f'{packet_type:20s}'
                count_str = f'{count:6d}'
                percentage_str = f'{percentage:5.1f}%'
                # Use different colors for different packet types
                color_tag = (
                    'green' if count > 100 else 'yellow' if count > 10 else 'red'
                )
                logger.opt(colors=True).info(
                    f'  <cyan>{packet_type_str}</cyan>: <{color_tag}>{count_str}</{color_tag}> (<magenta>{percentage_str}</magenta>)'
                )

        # Calculate rates if we have timing info
        if self.start_time and self.counter > 0:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                rate = self.counter / elapsed
                save_rate = packets_saved / elapsed if packets_saved > 0 else 0
                logger.opt(colors=True).info('')
                rate_str = f'{rate:.2f}'
                save_rate_str = f'{save_rate:.2f}'
                elapsed_sec_str = f'{elapsed:.0f}'
                elapsed_min_str = f'{elapsed / 60:.1f}'
                logger.opt(colors=True).info(
                    f'Average ingestion rate: <green>{rate_str}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Average save rate: <green>{save_rate_str}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Uptime: <cyan>{elapsed_sec_str}</cyan> seconds (<cyan>{elapsed_min_str}</cyan> minutes)'
                )

        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')

    def stop(self):
        LOG.info(__class__.__name__ + ' Stop')
        self.thread_stop = True

        # Print final stats before shutdown
        self._print_stats()

        if self.client:
            try:
                self.client.loop_stop()
                LOG.info('Stopping MQTT network loop')
            except Exception as ex:
                LOG.warning(f'Error stopping MQTT loop: {ex}')
            try:
                self.client.disconnect()
                LOG.info('Disconnected from MQTT')
            except Exception as ex:
                LOG.warning(f'Error disconnecting MQTT client: {ex}')

    def loop(self):
        """Main loop that checks connection health and handles reconnection."""
        try:
            # Check connection health periodically
            self._check_connection_health()

            # If we don't have a client or aren't connected, wait a bit before next check
            if not self.client or not self.connected:
                time.sleep(1)
                return True

            # Sleep briefly to avoid tight loop, but allow health checks
            time.sleep(1)

        except Exception as ex:
            LOG.error(f'Error in MQTT loop: {ex}')
            LOG.exception(ex)
            # Try to recover by reconnecting
            if self.client:
                try:
                    self.client.loop_stop()
                except Exception:
                    pass
            self._reconnect()

        return True


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def wx_mqtt_injest(ctx):
    """Injest APRSD Weather packets from an MQTT queue"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__} ')
    # Dump out the config options read from config file
    CONF.log_opt_values(LOG, logging.DEBUG)

    db_session = db.setup_session()
    session = db_session()

    # Create queues for packet processing
    packet_queue = queue.Queue(maxsize=5000)

    # Shared stats dictionary and lock for thread-safe access
    stats_lock = threading.Lock()
    start_time = time.time()
    stats = {
        'start_time': start_time,
        'packet_counter': 0,
        'packets_saved': 0,
        'report_counter': 0,
        'packet_types': {},
        'unique_callsigns': set(),
    }

    # Create processor threads (single-threaded legacy mode, uses thread_index=0)
    aprs_processor = APRSPacketProcessorThread(
        packet_queue, session, stats, stats_lock, thread_index=0
    )

    weather_processor = WeatherPacketProcessorThread(
        packet_queue, session, stats, stats_lock
    )

    # Create MQTT thread
    mqtt_thread = MQTTThread(packet_queue, stats, stats_lock)

    # Start all threads
    keepalive = threads.KeepAliveThread()
    keepalive.start()

    LOG.info('Starting APRS packet processor thread')
    aprs_processor.start()

    LOG.info('Starting weather packet processor thread')
    weather_processor.start()

    LOG.info('Starting MQTT thread')
    mqtt_thread.start()

    # Wait for MQTT thread (it runs until stopped)
    mqtt_thread.join()

    # Stop processor threads
    LOG.info('Stopping processor threads')
    aprs_processor.stop()
    weather_processor.stop()
    aprs_processor.join(timeout=5)
    weather_processor.join(timeout=5)

    LOG.info('Waiting for keepalive thread to quit')
    keepalive.join()
