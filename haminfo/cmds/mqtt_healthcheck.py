import click
import datetime
import json
import logging as python_logging
import os
import signal
import sys
import time

from geopy.geocoders import Nominatim
from oslo_config import cfg
from oslo_log import log as logging
import paho.mqtt.client as mqtt

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils, threads, log
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def mqtt_healthcheck(ctx):
    """MQTT healthcheck."""
    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__} ')
    # Dump out the config options read from config file
    # CONF.log_opt_values(LOG, logging.DEBUG)

    now = datetime.datetime.now()

    try:
        modify_time = os.path.getmtime(CONF.mqtt.keepalive_file)
        modify_date = datetime.datetime.fromtimestamp(modify_time)
        max_timeout = {"hours": 0.0, "minutes": 15, "seconds": 0}
        max_delta = datetime.timedelta(**max_timeout)
        diff = now - modify_date
        if diff > max_delta:
            LOG.error(f"Healthcheck file is old! {CONF.mqtt.keepalive_file} : {diff}")
            sys.exit(-1)
        else:
            LOG.info(f"Healthcheck file age {diff}")
    except Exception as ex:
        LOG.error(f"Failed: {ex}")
        sys.exit(-1)

    # try and read the keep alive json file
    try:
        fp = open(CONF.mqtt.keepalive_file)
        keepalive_data = json.load(fp)
        LOG.info(keepalive_data)
        fp.close()
    except Exception:
        LOG.error(f"Failed to read/parse the keepalive file {CONF.mqtt.keepalive_file}")
        sys.exit(-1)

    if "threads" in keepalive_data:
        for thread in keepalive_data["threads"]:
            if not keepalive_data["threads"][thread]:
                LOG.error(f"Thread {thread} is not running")
                sys.exit(-1)

    return 0
