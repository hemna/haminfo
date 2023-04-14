import click
import datetime
import json
import logging as python_logging
import signal
import sys
import time

from oslo_config import cfg
from oslo_log import log as logging
import sqlalchemy

import paho.mqtt.client as mqtt
import haminfo
from haminfo import utils, threads, log
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)


grp = cfg.OptGroup('mqtt')
cfg.CONF.register_group(grp)
mqtt_opts = [
    cfg.StrOpt('host_ip',
               default='0.0.0.0',
               help='The hostname/ip address to listen on'
               ),
    cfg.IntOpt('host_port',
               default=80,
               help='The port to listen on for requests'
               ),
    cfg.StrOpt('user',
               default=None,
               help='The mqtt username to use'
               ),
    cfg.StrOpt('password',
               default=None,
               help="the mqtt password"),
    cfg.StrOpt('topic',
               default="aprs/weather",
               help="The MQTT Topic to subscribe for messages")
]
CONF.register_opts(mqtt_opts, group="mqtt")


def signal_handler(sig, frame):
    click.echo("signal_handler: called")
    threads.MyThreadList().stop_all()
    if "subprocess" not in str(frame):
        LOG.info(
            "Ctrl+C, Sending all threads exit! Can take up to 10 seconds {}".format(
                datetime.datetime.now(),
            ),
        )
        time.sleep(1.5)


# Class to read from the mqtt queue and dump the packets in to the DB.
class MQTTThread(threads.MyThread):
    client = None
    session = None
    counter = 0

    def __init__(self, session=None):
        super().__init__("MQTTThread")
        self.setup()
        self.session = session

    def setup(self):
        LOG.info("Creating MQTT Client")
        self.client = mqtt.Client(client_id="Haminfo")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.connect(CONF.mqtt.host_ip, CONF.mqtt.host_port)
        if CONF.mqtt.user:
            self.client.username_pw_set(
                username=CONF.mqtt.user,
                password=CONF.mqtt.password
            )
        else:
            LOG.info("Not using username/password to auth with MQTT")

    def on_disconnect(self, client, userdata, rc):
        LOG.info("client disconnected ok")

    def on_connect(self, client, userdata, flags, rc):
        LOG.info(
            f"Connected to mqtt://{CONF.mqtt.host_ip}:{CONF.mqtt.host_port}/{CONF.mqtt.topic} ({rc})"
        )
        client.subscribe(CONF.mqtt.topic)

    def on_message(self, client, userdata, msg):
        self.counter += 1
        aprs_data = json.loads(msg.payload)
        # We got a message, lets build the DB model object and insert it.
        try:
            station = WeatherStation.find_station_by_callsign(
                self.session,
                aprs_data["from_call"]
            )
        except sqlalchemy.exc.DatabaseError as ex:
            LOG.error(ex)
            return

        if not station:
            station = WeatherStation.from_json(aprs_data)
            if station:
                self.session.add(station)
                try:
                    self.session.commit()
                except Exception as ex:
                    self.session.rollback()
                    LOG.error(ex)
                    LOG.warning(f"Failed for report {aprs_data}")
                    return
            else:
                # Failed to get station from json
                return
        report = WeatherReport.from_json(aprs_data)
        station.reports.append(report)
        # LOG.debug(f"station reports {station.reports}")
        try:
            self.session.commit()
        except Exception as ex:
            self.session.rollback()
            LOG.error(ex)
            LOG.warning(f"Failed for report {aprs_data}")

        if self.counter % 50 == 0:
            LOG.debug(f"Report counter:{self.counter}")
            #LOG.debug(f"Station {repr(station)}")
            LOG.debug(f"Report({station.callsign}):  {repr(report)}")

    def stop(self):
        LOG.info(__class__.__name__+" Stop")
        self.thread_stop = True
        if self.client:
            self.client.loop_stop()
            LOG.info("Disconnect from MQTT")
            self.client.disconnect()

    def loop(self):
        if self.client:
            LOG.info("Waiting on mqtt packets....")
            self.client.loop_forever(timeout=1)
        return True


@click.command()
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
@click.option(
    "-c",
    "--config-file",
    "config_file",
    show_default=True,
    default=utils.DEFAULT_CONFIG_FILE,
    help="The aprsd config file to use for options.",
)
@click.option(
    "--loglevel",
    "log_level",
    default="INFO",
    show_default=True,
    type=click.Choice(
        ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        case_sensitive=False,
    ),
    show_choices=True,
    help="The log level to use for aprsd.log",
)
@click.version_option()
def main(disable_spinner, config_file, log_level):
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)

    python_logging.captureWarnings(True)
    log.setup_logging()

    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__} ')
    # Dump out the config options read from config file
    CONF.log_opt_values(LOG, logging.DEBUG)

    db_session = db.setup_session()
    session = db_session()

    keepalive = threads.KeepAliveThread()
    keepalive.start()

    mqtt_thread = MQTTThread(session)
    LOG.info("Starting MQTT thread")
    mqtt_thread.start()
    mqtt_thread.join()
    LOG.info("Waiting for keepalive thread to quit")
    keepalive.join()





if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
