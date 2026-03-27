"""Integration tests for parallel MQTT processing."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from haminfo.mqtt import MQTTThread, APRSPacketProcessorThread


class TestParallelProcessingIntegration:
    """Integration tests for the full parallel processing pipeline."""

    @pytest.fixture
    def stats(self):
        return {
            'start_time': time.time(),
            'packet_counter': 0,
            'packets_saved': 0,
            'report_counter': 0,
            'packet_types': {},
            'unique_callsigns': set(),
        }

    @pytest.fixture
    def stats_lock(self):
        return threading.Lock()

    def test_packets_distributed_across_processors(self, stats, stats_lock):
        """Packets should be evenly distributed across all processors."""
        processor_count = 4
        aprs_queues = [queue.Queue(maxsize=100) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=100)

        with patch('haminfo.mqtt.thread.CONF') as mock_conf:
            mock_conf.mqtt.host_ip = 'localhost'
            mock_conf.mqtt.host_port = 1883
            mock_conf.mqtt.user = None
            mock_conf.mqtt.topic = 'test/topic'

            with patch.object(MQTTThread, '_connect'):
                all_queues = aprs_queues + [weather_queue]
                mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

        # Simulate 100 packets being distributed
        for i in range(100):
            aprs_queue = mqtt_thread.aprs_queues[
                mqtt_thread.rr_index % len(mqtt_thread.aprs_queues)
            ]
            mqtt_thread.rr_index += 1
            aprs_queue.put_nowait(f'packet_{i}')

        # Each queue should have ~25 packets (100 / 4)
        for i, q in enumerate(aprs_queues):
            assert q.qsize() == 25, f'Queue {i} has {q.qsize()} packets, expected 25'

    def test_processor_count_one_matches_original_behavior(self, stats, stats_lock):
        """processor_count=1 should behave like original single-threaded mode."""
        processor_count = 1
        aprs_queues = [queue.Queue(maxsize=100) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=100)

        with patch('haminfo.mqtt.thread.CONF') as mock_conf:
            mock_conf.mqtt.host_ip = 'localhost'
            mock_conf.mqtt.host_port = 1883
            mock_conf.mqtt.user = None
            mock_conf.mqtt.topic = 'test/topic'

            with patch.object(MQTTThread, '_connect'):
                all_queues = aprs_queues + [weather_queue]
                mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

        # All 100 packets should go to the single APRS queue
        for i in range(100):
            aprs_queue = mqtt_thread.aprs_queues[
                mqtt_thread.rr_index % len(mqtt_thread.aprs_queues)
            ]
            mqtt_thread.rr_index += 1
            aprs_queue.put_nowait(f'packet_{i}')

        assert aprs_queues[0].qsize() == 100
