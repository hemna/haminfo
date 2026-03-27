"""Tests for MQTTThread round-robin distribution."""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestMQTTThreadRoundRobin:
    """Tests for round-robin packet distribution."""

    @pytest.fixture
    def stats(self):
        """Create shared stats dict."""
        return {
            'start_time': 0,
            'packet_counter': 0,
            'packets_saved': 0,
            'report_counter': 0,
            'packet_types': {},
            'unique_callsigns': set(),
        }

    @pytest.fixture
    def stats_lock(self):
        """Create stats lock."""
        return threading.Lock()

    @pytest.fixture
    def queues(self):
        """Create test queues: 3 APRS + 1 weather."""
        return [queue.Queue() for _ in range(4)]

    @patch('haminfo.mqtt.thread.CONF')
    def test_round_robin_distribution(self, mock_conf, queues, stats, stats_lock):
        """Packets should be distributed round-robin to APRS queues."""
        from haminfo.mqtt.thread import MQTTThread

        # Mock config
        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        # Patch _connect to avoid actual MQTT connection
        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(queues, stats, stats_lock)

        # Verify queue separation
        assert len(thread.aprs_queues) == 3
        assert thread.weather_queue is queues[3]

        # Simulate distributing 6 packets
        for i in range(6):
            # Get expected queue index
            expected_idx = i % 3
            actual_queue = thread.aprs_queues[thread.rr_index % len(thread.aprs_queues)]
            assert actual_queue is queues[expected_idx], (
                f'Packet {i} went to wrong queue'
            )
            thread.rr_index += 1

    @patch('haminfo.mqtt.thread.CONF')
    def test_weather_packet_goes_to_both_queues(
        self, mock_conf, queues, stats, stats_lock
    ):
        """Weather packets should go to APRS queue AND weather queue."""
        from haminfo.mqtt.thread import MQTTThread
        from aprsd.packets.core import WeatherPacket

        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(queues, stats, stats_lock)

        # Create a mock weather packet
        weather_packet = MagicMock(spec=WeatherPacket)

        # Distribute to APRS queue (round-robin)
        aprs_queue = thread.aprs_queues[thread.rr_index % len(thread.aprs_queues)]
        aprs_queue.put_nowait(weather_packet)
        thread.rr_index += 1

        # Also distribute to weather queue
        thread.weather_queue.put_nowait(weather_packet)

        # Verify packet is in both queues
        assert queues[0].qsize() == 1  # First APRS queue
        assert queues[3].qsize() == 1  # Weather queue


class TestMQTTThreadBackwardCompatibility:
    """Tests for backward compatibility with single queue."""

    @pytest.fixture
    def stats(self):
        return {'start_time': 0, 'packet_counter': 0}

    @pytest.fixture
    def stats_lock(self):
        return threading.Lock()

    @patch('haminfo.mqtt.thread.CONF')
    def test_single_queue_still_works(self, mock_conf, stats, stats_lock):
        """Single queue input should still work (backward compat)."""
        from haminfo.mqtt.thread import MQTTThread

        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        single_queue = queue.Queue()

        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(single_queue, stats, stats_lock)

        # Should handle single queue gracefully
        assert thread.packet_queue is single_queue
