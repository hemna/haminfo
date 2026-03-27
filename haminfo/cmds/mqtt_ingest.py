"""CLI command for MQTT APRS packet ingestion.

This module provides the CLI entry point for starting the MQTT
ingestion service. The actual implementation is in the haminfo.mqtt package.
"""

from __future__ import annotations

import click
import datetime
import queue
import signal
import threading
import time

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils, threads
from haminfo.db import db
from haminfo.mqtt import (
    MQTTThread,
    APRSPacketProcessorThread,
    WeatherPacketProcessorThread,
)

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


def signal_handler(sig, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    click.echo('signal_handler: called')
    threads.MyThreadList().stop_all()
    if 'subprocess' not in str(frame):
        LOG.info(
            f'Ctrl+C, Sending all threads exit! '
            f'Can take up to 10 seconds {datetime.datetime.now()}'
        )
        time.sleep(1.5)


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def wx_mqtt_ingest(ctx):
    """Ingest APRSD Weather packets from an MQTT queue."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__}')
    CONF.log_opt_values(LOG, logging.DEBUG)

    # Check for stats_only mode
    stats_only = CONF.mqtt.stats_only
    if stats_only:
        LOG.warning('=' * 60)
        LOG.warning('STATS-ONLY MODE: Packets will NOT be saved to database!')
        LOG.warning('=' * 60)

    # Get session factory - processors will create their own sessions
    session_factory = db.setup_session()

    # Get processor count from config
    processor_count = CONF.mqtt.processor_count
    LOG.info(f'Starting {processor_count} parallel APRS packet processor threads')

    # Create N APRS queues + 1 weather queue
    aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
    weather_queue = queue.Queue(maxsize=5000)

    # Shared stats dictionary and lock for thread-safe access
    stats_lock = threading.Lock()
    stats = {
        'start_time': time.time(),
        'packet_counter': 0,
        'packets_saved': 0,
        'report_counter': 0,
        'packet_types': {},
        'unique_callsigns': set(),
    }

    # Create N APRS processor threads with staggered batch thresholds
    aprs_processors = []
    for i in range(processor_count):
        processor = APRSPacketProcessorThread(
            aprs_queues[i],
            session_factory,
            stats,
            stats_lock,
            thread_index=i,  # Pass index for staggered batch saves
            stats_only=stats_only,
        )
        processor.name = f'APRSPacketProcessorThread-{i}'
        aprs_processors.append(processor)

    # Single weather processor
    weather_processor = WeatherPacketProcessorThread(
        weather_queue,
        session_factory,
        stats,
        stats_lock,
        stats_only=stats_only,
    )

    # MQTT thread gets all queues: [aprs_0, ..., aprs_N-1, weather]
    all_queues = aprs_queues + [weather_queue]
    mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

    # Start all threads
    keepalive = threads.KeepAliveThread()
    keepalive.start()

    for processor in aprs_processors:
        LOG.info(f'Starting {processor.name}')
        processor.start()

    LOG.info('Starting weather packet processor thread')
    weather_processor.start()

    LOG.info('Starting MQTT thread')
    mqtt_thread.start()

    # Wait for MQTT thread (runs until stopped)
    mqtt_thread.join()

    # Graceful shutdown - stop all processor threads
    LOG.info('Stopping processor threads')
    for processor in aprs_processors:
        processor.stop()
    weather_processor.stop()

    # Wait for processors to finish
    for processor in aprs_processors:
        processor.join(timeout=5)
    weather_processor.join(timeout=5)

    LOG.info('Waiting for keepalive thread to quit')
    keepalive.stop()
    keepalive.join()


# Backward compatibility alias
wx_mqtt_injest = wx_mqtt_ingest
