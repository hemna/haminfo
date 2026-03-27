import datetime
import json
import logging
import time
import tracemalloc

from loguru import logger
from oslo_config import cfg

from haminfo.threads import MyThread, MyThreadList
from haminfo import utils


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)

# Minimum packets expected per minute during normal operation
# APRS-IS typically sends 30-90 packets/second, so 60s * 20 = 1200 minimum
MIN_PACKETS_PER_INTERVAL = 100  # Very conservative - if we get less, something is wrong
STALE_CONNECTION_INTERVALS = (
    2  # Number of intervals with no packets before marking unhealthy
)


class KeepAliveThread(MyThread):
    cntr = 0

    def __init__(self):
        tracemalloc.start()
        super().__init__('KeepAlive')
        self.data = {
            'threads': {},
            'packets': {
                'total_received': 0,
                'total_saved': 0,
                'last_interval_received': 0,
                'last_interval_saved': 0,
            },
            'mqtt': {
                'connected': False,
                'subscribed': False,
            },
        }
        self._dump_keepalive()
        self.report_counter = 0
        self.last_packet_count = 0
        self.last_saved_count = 0
        self.zero_packet_intervals = 0  # Track consecutive intervals with no packets

    def _dump_keepalive(self):
        try:
            max_timeout = {'hours': 0.0, 'minutes': 2, 'seconds': 0}
            self.max_delta = datetime.timedelta(**max_timeout)
            self.data['update_at'] = str(datetime.datetime.now())
            LOG.debug(self.data)
            fp = open(CONF.mqtt.keepalive_file, 'w+')
            json.dump(self.data, fp)
            fp.close()
        except Exception as ex:
            LOG.error(f'Failed to write keepalive file {str(ex)}')

    def loop(self):
        if self.cntr % 60 == 0:
            thread_list = MyThreadList()

            # Log packet statistics from stats dict
            stats = None
            stats_lock = None
            mqtt_thread = None
            for thread in thread_list.threads_list:
                if hasattr(thread, 'stats') and hasattr(thread, 'stats_lock'):
                    stats = thread.stats
                    stats_lock = thread.stats_lock
                if thread.__class__.__name__ == 'MQTTThread':
                    mqtt_thread = thread

            if stats and stats_lock:
                with stats_lock:
                    packet_count = stats.get('packet_counter', 0)
                    saved_count = stats.get('packets_saved', 0)
                    unique_calls = len(stats.get('unique_callsigns', set()))

                # Calculate packets received in the last interval
                packets_this_interval = packet_count - self.last_packet_count
                saved_this_interval = saved_count - self.last_saved_count

                logger.info(
                    f'Packets: {packets_this_interval} received, '
                    f'{saved_this_interval} saved in last 60s | '
                    f'Total: {packet_count} received, {saved_count} saved | '
                    f'Unique callsigns: {unique_calls}'
                )

                # Track zero-packet intervals
                if packets_this_interval == 0 and self.last_packet_count > 0:
                    self.zero_packet_intervals += 1
                    logger.warning(
                        f'No packets received this interval '
                        f'({self.zero_packet_intervals} consecutive)'
                    )
                else:
                    self.zero_packet_intervals = 0

                # Update packet stats in keepalive data
                self.data['packets'] = {
                    'total_received': packet_count,
                    'total_saved': saved_count,
                    'last_interval_received': packets_this_interval,
                    'last_interval_saved': saved_this_interval,
                    'zero_intervals': self.zero_packet_intervals,
                }

                self.last_packet_count = packet_count
                self.last_saved_count = saved_count

            # Get MQTT connection state
            if mqtt_thread:
                self.data['mqtt'] = {
                    'connected': getattr(mqtt_thread, 'connected', False),
                    'subscribed': getattr(mqtt_thread, 'subscribed', False),
                    'last_message_age': (
                        time.time() - mqtt_thread.last_message_time
                        if hasattr(mqtt_thread, 'last_message_time')
                        else -1
                    ),
                }

            # Check thread health
            thread_out = []
            all_alive = True
            for thread in thread_list.threads_list:
                thread_name = thread.__class__.__name__
                alive = thread.is_alive()
                if thread_name == 'MQTTThread':
                    # Also check MQTT-specific health
                    if not getattr(thread, 'connected', False):
                        alive = False
                    elif not getattr(thread, 'subscribed', False):
                        alive = False
                    elif (
                        hasattr(thread, 'client')
                        and thread.client
                        and hasattr(thread.client, '_connection_closed')
                        and thread.client._connection_closed()
                    ):
                        alive = False
                self.data['threads'][thread_name] = alive

                thread_out.append(f'{thread_name}:{alive}')
                if not alive:
                    all_alive = False
                    LOG.error(f'Thread {thread}')

            # Mark unhealthy if no packets for multiple intervals
            if self.zero_packet_intervals >= STALE_CONNECTION_INTERVALS:
                all_alive = False
                LOG.error(
                    f'No packets for {self.zero_packet_intervals} intervals - '
                    f'marking unhealthy'
                )
                self.data['threads']['PacketFlow'] = False
            else:
                self.data['threads']['PacketFlow'] = True

            # Only log thread status if there's a problem
            if not all_alive:
                LOG.warning('Thread status: ' + '  '.join(thread_out))

        self.cntr += 1
        # every 1 minutes
        if self.cntr % 60 == 0:
            # update the keepalive file
            self._dump_keepalive()
        time.sleep(1)
        return True
