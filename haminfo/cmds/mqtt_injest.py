import click
import datetime
import json
import signal
import time

from geopy.geocoders import Nominatim
from oslo_config import cfg
from oslo_log import log as logging
import paho.mqtt.client as mqtt

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
    reports = []
    report_counter = 0

    def __init__(self, session=None):
        super().__init__("MQTTThread")
        self.setup()
        self.session = session
        self.nominate = Nominatim(user_agent="haminfo")

    def setup(self):
        self._connect()

    def _connect(self):
        LOG.info("Creating MQTT Client")
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="Haminfo",
        )
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

    def on_disconnect(self, client, userdata, flags, rc, properties):
        LOG.info(f"client disconnected {flags}, {rc}, {properties}")

    def on_connect(self, client, userdata, flags, rc, properties):
        LOG.info(
            f"Connected to mqtt://{CONF.mqtt.host_ip}:{CONF.mqtt.host_port}"
            f"/{CONF.mqtt.topic} ({rc})"
        )
        client.subscribe(CONF.mqtt.topic)

    def on_message(self, client, userdata, msg):
        self.counter += 1
        aprs_data = json.loads(msg.payload.decode('utf-8').replace('\x00', ''))
        # We got a message, lets build the DB model object and insert it.
        station = None
        try:
            station = WeatherStation.find_station_by_callsign(
                self.session,
                aprs_data["from_call"]
            )
        except Exception as ex:
            # LOG.error(f"Failed to find station {aprs_data['from_call']}")
            # LOG.exception(ex)
            pass

        if not station:
            LOG.info(f"Didn't find station {aprs_data['from_call']}")
            station = WeatherStation.from_json(aprs_data)
            if station:
                # Get the country code
                coordinates = f"{station.latitude:0.6f}, {station.longitude:0.6f}"
                location = self.nominate.geocode(
                    coordinates,
                    language="en",
                    addressdetails=True,
                )
                if location and hasattr(location, "raw"):
                    address = location.raw.get("address")
                    if address:
                        station.country_code = address["country_code"]
                    else:
                        LOG.error(f"Failed to find address for {coordinates}")
                try:
                    self.session.add(station)
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    LOG.error("Failed getting/creating station for "
                              f"report {aprs_data}")
                    LOG.error(station)
                    return
            else:
                # Failed to get station from json
                LOG.warning("Failed to get station from json.")
                return

        try:
            report = WeatherReport.from_json(aprs_data, station.id)
        except Exception as ex:
            LOG.error(aprs_data)
            LOG.error("Failed to create WeatherReport because")
            LOG.exception(ex)
            return

        try:
            # Make sure there is valid data to add to the DB
            if report.is_valid():
                self.reports.append(report)
                self.report_counter += 1
                # self.session.add(report)
                # db.add_wx_report(self.session, report)
            else:
                # LOG.info(f"Ignoring report {report}")
                return
        except ValueError as ex:
            self.session.rollback()
            LOG.exception(ex)
            LOG.error(report)
            return
        except Exception as ex:
            self.session.rollback()
            LOG.error("Failed to add_wx_report {report}")
            LOG.error(ex)
            return

        if self.counter % 25 == 0:
            LOG.debug(f"Loop counter:{self.counter}  "
                      f"Report Counter:{self.report_counter}")

        if self.counter % 200 == 0:
            LOG.debug(report)
            try:
                LOG.info(f"Saving {len(self.reports)} to DB.")
                tic = time.perf_counter()
                self.session.bulk_save_objects(self.reports)
                self.session.commit()
                toc = time.perf_counter()
                LOG.warning(f"Time to save = {toc - tic:0.4f}")
                self.reports = []
            except ValueError as ex:
                self.session.rollback()
                LOG.error(f"Failed for report {self.reports}")
                LOG.exception(ex)
                for r in self.reports:
                    if '\x00' in r.raw_report:
                        LOG.error(f"Null char in {r}")
                self.reports = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f"Failed for report {self.reports}")
                LOG.exception(ex)
                # Just drop all the reports
                self.reports = []
            # LOG.debug(f"Station {repr(station)}")
            # LOG.debug(f"Report({station.callsign}[{station.id}]):  {repr(report)}")

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
            try:
                self.client.loop_forever(timeout=1)
            except TimeoutError:
                LOG.warning("Disconnecting from MQTT")
                self.client.disconnect()
                self._connect()
        else:
            LOG.warning("Disconnecting from MQTT")
            self._connect()
        return True


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def wx_mqtt_injest(ctx):
    """Injest APRSD Weather packets from an MQTT queue"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

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
