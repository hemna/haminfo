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

from loguru import logger
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

    db_session = db.setup_session()
    session = db_session()

    # Create queue for packet processing
    packet_queue = queue.Queue(maxsize=5000)

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

    # Create processor threads
    aprs_processor = APRSPacketProcessorThread(
        packet_queue,
        session,
        stats,
        stats_lock,
    )
    weather_processor = WeatherPacketProcessorThread(
        packet_queue,
        session,
        stats,
        stats_lock,
    )
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

    # Wait for MQTT thread (runs until stopped)
    mqtt_thread.join()

    # Stop processor threads
    LOG.info('Stopping processor threads')
    aprs_processor.stop()
    weather_processor.stop()
    aprs_processor.join(timeout=5)
    weather_processor.join(timeout=5)

    LOG.info('Waiting for keepalive thread to quit')
    keepalive.join()


# Backward compatibility alias
wx_mqtt_injest = wx_mqtt_ingest
