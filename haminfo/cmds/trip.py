# This file handles the TRIP APRS Service API 
# The TRIP service allows users to create/end a TRIP
# for a ham radio that supports APRS and messaging.

import click
import datetime
import signal
import time
import sys

from cachetools import cached, TTLCache
from geopy.geocoders import Nominatim
from oslo_config import cfg
from oslo_log import log as logging

from flask import Flask
from flask_classful import FlaskView

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils, threads
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


def signal_handler(sig, frame):
    click.echo("signal_handler: called")
    LOG.info(
        f"Ctrl+C, Sending all threads({len(threads.APRSDThreadList())}) exit! "
        f"Can take up to 10 seconds {datetime.datetime.now()}",
    )
    threads.APRSDThreadList().stop_all()
    if "subprocess" not in str(frame):
        time.sleep(1.5)
        stats.stats_collector.collect()
        LOG.info("Telling flask to bail.")
        signal.signal(signal.SIGTERM, sys.exit(0))


def _init_flask():
    return Flask(__name__)




class TripsView(FlaskView):

    def index(self):
        """Return the list of trips."""
        return "entire ass list"

    def get(self, id):
        """Get a specific trip."""
        return "get ass"

    def post(self, id):
        """Create something on a trip"""
        return "post ass"



# main() ###
@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option(
    "-p",
    "--port",
    "port",
    show_default=True,
    default=8100,
    help="Port to listen to web requests.  This overrides the "
    "config.aprsd_webchat_extension.web_port setting.",
)
@click.pass_context
@cli_helper.process_standard_options
def trip(ctx, port):
    """APRS TRIP service API to the DB."""

    app = _init_flask()
    TripsView.register(app)
    app.run(host="0.0.0.0", port=port, debug=True)
