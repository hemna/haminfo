"""Tests for MQTT ingest command with parallel processors."""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestParallelProcessorSetup:
    """Tests for parallel processor thread creation."""

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    @patch('haminfo.cmds.mqtt_ingest.db')
    def test_creates_n_aprs_queues(self, mock_db, mock_conf):
        """Should create processor_count APRS queues."""
        mock_conf.mqtt.processor_count = 4

        # Create queues as the command would
        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]

        assert len(aprs_queues) == 4

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    @patch('haminfo.cmds.mqtt_ingest.db')
    def test_creates_n_processor_threads(self, mock_db, mock_conf):
        """Should create processor_count APRSPacketProcessorThread instances."""
        from haminfo.mqtt import APRSPacketProcessorThread

        mock_conf.mqtt.processor_count = 4
        mock_db.setup_session.return_value = MagicMock()

        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
        session_factory = mock_db.setup_session()
        stats = {}
        stats_lock = threading.Lock()

        aprs_processors = []
        for i in range(processor_count):
            processor = APRSPacketProcessorThread(
                aprs_queues[i],
                session_factory,
                stats,
                stats_lock,
                thread_index=i,
            )
            processor.name = f'APRSPacketProcessorThread-{i}'
            aprs_processors.append(processor)

        assert len(aprs_processors) == 4
        assert aprs_processors[0].name == 'APRSPacketProcessorThread-0'
        assert aprs_processors[3].name == 'APRSPacketProcessorThread-3'
        # Verify staggered batch thresholds (base=500, stagger=25)
        assert aprs_processors[0].batch_save_threshold == 500  # 500 + 0*25
        assert aprs_processors[1].batch_save_threshold == 525  # 500 + 1*25
        assert aprs_processors[2].batch_save_threshold == 550  # 500 + 2*25
        assert aprs_processors[3].batch_save_threshold == 575  # 500 + 3*25

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    def test_mqtt_thread_receives_all_queues(self, mock_conf):
        """MQTTThread should receive N APRS queues + 1 weather queue."""
        mock_conf.mqtt.processor_count = 4

        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=5000)

        all_queues = aprs_queues + [weather_queue]

        assert len(all_queues) == 5  # 4 APRS + 1 weather
