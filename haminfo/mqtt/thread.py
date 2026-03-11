"""MQTT connection thread for APRS packet ingestion.

Manages the connection to an MQTT broker and routes incoming
packets to processing queues.
"""

from __future__ import annotations

import datetime
import json
import queue
import threading
import time
from typing import Any, Optional

from loguru import logger
from oslo_config import cfg
import paho.mqtt.client as mqtt

from aprsd.packets import core

from haminfo import threads

CONF = cfg.CONF

# Connection health check settings
CONNECTION_CHECK_INTERVAL = 5  # seconds
MESSAGE_TIMEOUT = 300  # seconds (5 minutes)
MAX_RECONNECT_DELAY = 60  # seconds
INITIAL_RECONNECT_DELAY = 1  # seconds


class MQTTThread(threads.MyThread):
    """Thread that manages the MQTT connection and routes packets.

    Connects to an MQTT broker, subscribes to a topic, and routes
    incoming APRS packets to a processing queue. Includes automatic
    reconnection with exponential backoff.
    """

    def __init__(
        self,
        packet_queues: list[queue.Queue] | queue.Queue,
        stats: dict,
        stats_lock: threading.Lock,
    ):
        super().__init__('MQTTThread')
        # Support single queue (backward compat) or list of queues (fan-out)
        if isinstance(packet_queues, queue.Queue):
            self.packet_queues = [packet_queues]
        else:
            self.packet_queues = list(packet_queues)
        # Keep backward-compat attribute for stats reporting
        self.packet_queue = self.packet_queues[0]
        self.stats = stats
        self.stats_lock = stats_lock

        self.client: Optional[mqtt.Client] = None
        self.counter: int = 0
        self.start_time: float = time.time()
        self.last_stats_time: float = self.start_time

        # Connection state
        self.connected: bool = False
        self.connection_attempts: int = 0
        self.last_connection_check: float = 0
        self.reconnect_delay: float = INITIAL_RECONNECT_DELAY
        self.last_message_time: float = time.time()
        self.reconnecting: bool = False
        self.reconnect_lock = threading.Lock()

        # KeepAliveThread compatibility attributes
        self.packet_counter: int = 0
        self.packets_saved: int = 0
        self.report_counter: int = 0

        logger.info('MQTTThread initialized')
        self._connect()

    def _update_stats_attributes(self) -> None:
        """Sync thread attributes from shared stats dict."""
        with self.stats_lock:
            self.packet_counter = self.stats.get('packet_counter', 0)
            self.packets_saved = self.stats.get('packets_saved', 0)
            self.report_counter = self.stats.get('report_counter', 0)

    def _connect(self) -> None:
        """Connect to MQTT broker with error handling."""
        try:
            logger.info('Creating MQTT Client')
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
                    username=CONF.mqtt.user,
                    password=CONF.mqtt.password,
                )
            else:
                logger.info('Not using username/password for MQTT auth')

            logger.info(
                f'Connecting to MQTT broker at '
                f'{CONF.mqtt.host_ip}:{CONF.mqtt.host_port}'
            )
            self.client.connect(
                CONF.mqtt.host_ip,
                CONF.mqtt.host_port,
                keepalive=60,
            )
            self.client.loop_start()
            self.connection_attempts += 1
            time.sleep(0.5)

        except (ConnectionError, OSError) as ex:
            logger.error(f'Network error connecting to MQTT broker: {ex}')
            self.connected = False
            self.client = None
        except Exception as ex:
            logger.error(f'Failed to create/connect MQTT client: {ex}')
            self.connected = False
            self.client = None

    def _reconnect(self) -> None:
        """Reconnect to MQTT broker with exponential backoff."""
        with self.reconnect_lock:
            if self.thread_stop or self.reconnecting:
                return
            self.reconnecting = True

        try:
            if self.client:
                try:
                    logger.info('Disconnecting existing client before reconnect')
                    self.client.loop_stop()
                    time.sleep(0.5)
                except Exception as ex:
                    logger.warning(f'Error stopping client loop: {ex}')
                try:
                    self.client.disconnect()
                except Exception as ex:
                    logger.warning(f'Error disconnecting client: {ex}')
                finally:
                    self.client = None

            self.connected = False

            delay = min(self.reconnect_delay, MAX_RECONNECT_DELAY)
            logger.info(
                f'Waiting {delay}s before reconnecting '
                f'(attempt {self.connection_attempts})'
            )

            # Sleep in small increments to check for shutdown
            slept = 0.0
            while slept < delay and not self.thread_stop:
                time.sleep(min(1.0, delay - slept))
                slept += 1.0

            if self.thread_stop:
                return

            self.reconnect_delay = min(self.reconnect_delay * 2, MAX_RECONNECT_DELAY)
            self._connect()
        finally:
            with self.reconnect_lock:
                self.reconnecting = False

    def _check_connection_health(self) -> None:
        """Periodically verify the MQTT connection is healthy."""
        current_time = time.time()

        if current_time - self.last_connection_check < CONNECTION_CHECK_INTERVAL:
            return
        self.last_connection_check = current_time

        if self.reconnecting:
            return

        if not self.client:
            logger.warning('MQTT client is None, reconnecting...')
            self._reconnect()
            return

        if not self.connected:
            logger.warning('MQTT client not connected, reconnecting...')
            self._reconnect()
            return

        # Check if the network loop thread is alive
        try:
            if (
                hasattr(self.client, '_thread')
                and self.client._thread
                and not self.client._thread.is_alive()
            ):
                logger.warning('MQTT network loop not running, reconnecting...')
                self._reconnect()
                return
        except AttributeError:
            pass
        except Exception as ex:
            logger.warning(f'Error checking connection health: {ex}')
            self._reconnect()
            return

        # Check for message timeout (stale connection)
        time_since_start = current_time - self.start_time
        if time_since_start > 60:  # Only check after 1 minute of runtime
            time_since_last = current_time - self.last_message_time
            if time_since_last > MESSAGE_TIMEOUT:
                logger.warning(
                    f'No messages for {time_since_last:.0f}s '
                    f'(timeout: {MESSAGE_TIMEOUT}s), reconnecting...'
                )
                self._reconnect()

    # --- MQTT Callbacks ---

    def on_connect_fail(self, client: Any, userdata: Any) -> None:
        """Called when connection attempt fails."""
        logger.error('MQTT connection failed')
        self.connected = False

    def on_disconnect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        """Called when client disconnects from broker."""
        if rc == 0:
            logger.info('MQTT client disconnected cleanly')
        else:
            logger.warning(
                f'MQTT client disconnected unexpectedly (rc={rc}, flags={flags})'
            )
        self.connected = False
        if rc != 0:
            self.reconnect_delay = INITIAL_RECONNECT_DELAY

    def on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any,
    ) -> None:
        """Called when client connects to broker."""
        if rc == 0:
            logger.info(
                f'Connected to mqtt://{CONF.mqtt.host_ip}:{CONF.mqtt.host_port}'
                f'/{CONF.mqtt.topic} (rc={rc})'
            )
            self.connected = True
            self.connection_attempts = 0
            self.reconnect_delay = INITIAL_RECONNECT_DELAY
            self.last_message_time = time.time()
            try:
                client.subscribe(CONF.mqtt.topic)
                logger.info(f'Subscribed to topic: {CONF.mqtt.topic}')
            except Exception as ex:
                logger.error(f'Failed to subscribe to {CONF.mqtt.topic}: {ex}')
                self.connected = False
        else:
            logger.error(f'Failed to connect to MQTT broker (rc={rc})')
            self.connected = False

    def on_message(
        self,
        client: Any,
        userdata: Any,
        msg: Any,
    ) -> None:
        """Called when a message is received from MQTT."""
        try:
            self.counter += 1
            self.last_message_time = time.time()

            raw_payload = msg.payload.decode('utf-8').replace('\x00', '')
            aprs_data_raw = json.loads(raw_payload)
            logger.debug(f'Raw packet data: {aprs_data_raw}')

            try:
                aprsd_packet = core.factory(aprs_data_raw)
            except Exception as ex:
                logger.error(f'Failed to create aprsd packet: {ex}')
                logger.debug(f'Packet data: {aprs_data_raw}')
                return

            if aprsd_packet:
                for pq in self.packet_queues:
                    try:
                        pq.put_nowait(aprsd_packet)
                    except queue.Full:
                        logger.warning('Packet queue is full, dropping packet')

            # Periodic stats
            current_time = time.time()
            if self.counter % 500 == 0 or (current_time - self.last_stats_time) >= 60:
                self._print_stats()
                self.last_stats_time = current_time
                self._update_stats_attributes()

            # Update stats periodically for other threads to access
            if self.counter % 100 == 0:
                self._update_stats_attributes()
        except Exception as ex:
            logger.error(f'Error processing MQTT message: {ex}')
            logger.exception(ex)

    def _print_stats(self) -> None:
        """Print ingestion statistics with colored output."""
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
            f'Total packets from MQTT: <green>{self.counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Total packets processed: <green>{packet_counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Total packets saved: <green>{packets_saved}</green>'
        )
        logger.opt(colors=True).info(
            f'Packets in queue: <yellow>{self.packet_queue.qsize()}</yellow>'
        )
        logger.opt(colors=True).info(
            f'Weather reports: <green>{report_counter}</green>'
        )
        logger.opt(colors=True).info(
            f'Unique callsigns: <cyan>{unique_callsigns}</cyan>'
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
                    f'  <cyan>{ptype:20s}</cyan>: '
                    f'<{color}>{count:6d}</{color}> '
                    f'(<magenta>{pct:5.1f}%</magenta>)'
                )

        if self.start_time and self.counter > 0:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                rate = self.counter / elapsed
                save_rate = packets_saved / elapsed if packets_saved > 0 else 0
                logger.opt(colors=True).info('')
                logger.opt(colors=True).info(
                    f'Ingestion rate: <green>{rate:.2f}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Save rate: <green>{save_rate:.2f}</green> packets/second'
                )
                logger.opt(colors=True).info(
                    f'Uptime: <cyan>{elapsed:.0f}</cyan>s '
                    f'(<cyan>{elapsed / 60:.1f}</cyan> min)'
                )

        logger.opt(colors=True).info(f'<cyan>{separator}</cyan>')

    def stop(self) -> None:
        """Stop the MQTT thread and clean up."""
        logger.info('MQTTThread stopping')
        self.thread_stop = True
        self._print_stats()

        if self.client:
            try:
                self.client.loop_stop()
                logger.info('Stopped MQTT network loop')
            except Exception as ex:
                logger.warning(f'Error stopping MQTT loop: {ex}')
            try:
                self.client.disconnect()
                logger.info('Disconnected from MQTT')
            except Exception as ex:
                logger.warning(f'Error disconnecting MQTT client: {ex}')

    def loop(self) -> bool:
        """Main loop: check connection health."""
        try:
            self._check_connection_health()

            if not self.client or not self.connected:
                time.sleep(1)
                return True

            time.sleep(1)
        except Exception as ex:
            logger.error(f'Error in MQTT loop: {ex}')
            if self.client:
                try:
                    self.client.loop_stop()
                except Exception as stop_ex:
                    logger.debug(f'Error stopping MQTT loop during recovery: {stop_ex}')
            self._reconnect()

        return True
