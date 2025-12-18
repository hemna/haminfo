import click
import datetime
import json
import signal
import time

from cachetools import cached, TTLCache
from geopy.geocoders import Nominatim
from oslo_config import cfg
from oslo_log import log as logging
from loguru import logger
import paho.mqtt.client as mqtt

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils, threads
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo.db.models.aprs_packet import APRSPacket

from aprsd.packets.core import factory, WeatherPacket


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

@cached(cache=TTLCache(maxsize=640*1024, ttl=300))
def get_location(coordinates):
    nom = Nominatim(user_agent="haminfo")
    location = None
    try:
        location = nom.geocode(
            coordinates,
            language="en",
            addressdetails=True,
        )
    except Exception as ex:
        LOG.error(f"Failed to get location for {coordinates}")
        location = None
    return location


# Class to read from the mqtt queue and dump the packets in to the DB.
class MQTTThread(threads.MyThread):
    client = None
    session = None
    counter = 0
    reports = []
    report_counter = 0
    aprs_packets = []
    packet_counter = 0
    packets_saved = 0
    packet_types = {}  # Track packet types
    last_stats_time = None
    start_time = None

    def __init__(self, session=None):
        super().__init__("MQTTThread")
        self.setup()
        self.session = session
        self.start_time = time.time()
        self.last_stats_time = self.start_time
        self.unique_callsigns = set()  # Track unique callsigns seen
        LOG.info(f"MQTTThread initialized with session: {self.session}")
        LOG.info(f"Creating Nominatim instance")
        #self.nominate = Nominatim(user_agent="haminfo")
        #LOG.info(f"Nominatim instance created: {self.nominate}")

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
        aprs_data_raw = json.loads(msg.payload.decode('utf-8').replace('\x00', ''))

        # First convert to aprsd packet object using factory
        # Since packets are added to MQTT with packet.to_json(), they're already serialized
        # WeatherPacket._translate() expects a 'weather' dict, so create one if missing
        aprs_data_prep = aprs_data_raw.copy()
        if '_type' in aprs_data_prep and aprs_data_prep.get('_type') == 'WeatherPacket':
            # WeatherPacket._translate() expects a 'weather' dict with weather fields
            # When serialized with to_json(), fields are at top level, so we need to nest them
            if 'weather' not in aprs_data_prep:
                weather_fields = [
                    'temperature', 'humidity', 'pressure', 'wind_direction', 'wind_speed',
                    'wind_gust', 'rain_1h', 'rain_24h', 'rain_since_midnight',
                    'solar_radiation', 'uv_index', 'luminosity', 'snow', 'speed', 'course'
                ]
                weather_dict = {}
                for field in weather_fields:
                    if field in aprs_data_prep:
                        weather_dict[field] = aprs_data_prep[field]
                # Always create weather dict for WeatherPacket, even if empty
                aprs_data_prep['weather'] = weather_dict

        aprsd_packet = None
        aprs_data = aprs_data_raw  # Default to raw data
        try:
            aprsd_packet = factory(aprs_data_prep)
            # Convert aprsd packet to dict for APRSPacket creation
            if hasattr(aprsd_packet, 'to_dict'):
                aprs_data = aprsd_packet.to_dict()
            else:
                # Fallback to to_json() and parse
                aprs_data_json = aprsd_packet.to_json()
                aprs_data = json.loads(aprs_data_json) if isinstance(aprs_data_json, str) else aprs_data_json
        except KeyError as ex:
            # Handle case where _type class is not found in globals or weather dict missing
            if str(ex) == "'weather'":
                LOG.debug(f"Weather packet missing 'weather' dict, using raw data: {aprs_data_raw.get('from_call', 'unknown')}")
            else:
                LOG.error(f"Failed to convert to aprsd packet object - class not found: {ex}")
                LOG.debug(f"Packet _type: {aprs_data_raw.get('_type', 'unknown')}")
            # Try to process without factory - use raw data
            aprs_data = aprs_data_raw
            self.packet_types["failed"] = self.packet_types.get("failed", 0) + 1
        except Exception as ex:
            LOG.error(f"Failed to convert to aprsd packet object: {ex}")
            LOG.exception(ex)
            LOG.debug(f"Packet data: {aprs_data_raw}")
            # Try to process without factory - use raw data
            aprs_data = aprs_data_raw
            self.packet_types["failed"] = self.packet_types.get("failed", 0) + 1

        # Track unique callsigns
        from_call = aprs_data.get('from_call') or aprs_data_raw.get('from_call')
        if from_call:
            self.unique_callsigns.add(from_call)

        # Create APRSPacket record for every packet received
        try:
            aprs_packet = APRSPacket.from_json(aprs_data)
            self.aprs_packets.append(aprs_packet)
            self.packet_counter += 1

            # Track packet type from aprsd packet object
            packet_type = aprsd_packet.packet_type or aprs_packet.packet_type or "unknown"
            self.packet_types[packet_type] = self.packet_types.get(packet_type, 0) + 1
        except Exception as ex:
            LOG.error(f"Failed to create APRSPacket from JSON: {ex}")
            LOG.debug(f"Packet data: {aprs_data}")
            # Track failed packets
            self.packet_types["failed"] = self.packet_types.get("failed", 0) + 1
            # Continue processing even if APRSPacket creation fails

        # Check if this is a weather packet using the aprsd packet object (if available)
        # Otherwise check packet_type field in the data
        is_weather = False
        if aprsd_packet:
            is_weather = isinstance(aprsd_packet, WeatherPacket)
        else:
            # Fallback: check packet_type in the data
            packet_type = aprs_data.get('packet_type', '').lower()
            is_weather = packet_type in ('weather', 'wx') or (
                aprs_data.get('temperature') is not None or
                aprs_data.get('humidity') is not None or
                aprs_data.get('pressure') is not None
            )

        if not is_weather:
            # Still save APRSPacket, but skip weather report processing
            self._save_packets_if_needed()
            return

        # We got a weather packet, lets build the DB model object and insert it.
        station = None
        try:
            station = WeatherStation.find_station_by_callsign(
                self.session,
                aprs_data["from_call"]
            )
        except Exception as ex:
            LOG.error(f"Failed to find station {aprs_data['from_call']}")
            LOG.exception(ex)
            pass

        if not station:
            LOG.info(f"Didn't find station {aprs_data['from_call']}")
            station = WeatherStation.from_json(aprs_data)
            if station:
                # Get the country code
                coordinates = f"{station.latitude:0.6f}, {station.longitude:0.6f}"
                location = get_location(coordinates)
                if location and hasattr(location, "raw"):
                    address = location.raw.get("address")
                    if address:
                        station.country_code = address["country_code"]
                    else:
                        LOG.error(f"Failed to find address for {coordinates}")
                try:
                    self.session.add(station)
                    self.session.commit()
                except Exception as ex:
                    self.session.rollback()
                    LOG.error("Failed getting/creating station for "
                              f"report {aprs_data['from_call']}")
                    LOG.error(ex.__cause__)
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

        # Print stats periodically (every 500 packets or every 60 seconds)
        current_time = time.time()
        if self.counter % 500 == 0 or (current_time - self.last_stats_time) >= 60:
            self._print_stats()
            self.last_stats_time = current_time

        if self.counter % 25 == 0:
            LOG.debug(f"Loop counter:{self.counter}  "
                      f"Report Counter:{self.report_counter}  "
                      f"Packet Counter:{self.packet_counter}")

        if self.counter % 200 == 0:
            LOG.debug(report)
            try:
                LOG.info(f"Saving {len(self.reports)} weather reports to DB.")
                tic = time.perf_counter()
                self.session.bulk_save_objects(self.reports)
                self.session.commit()
                toc = time.perf_counter()
                LOG.warning(f"Time to save weather reports = {toc - tic:0.4f}")
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

        # Save APRSPackets periodically
        self._save_packets_if_needed()

    def _save_packets_if_needed(self):
        """Save APRSPackets to database if we've accumulated enough."""
        if len(self.aprs_packets) >= 200:
            try:
                packets_to_save = len(self.aprs_packets)
                LOG.info(f"Saving {packets_to_save} APRS packets to DB.")
                tic = time.perf_counter()
                self.session.bulk_save_objects(self.aprs_packets)
                self.session.commit()
                toc = time.perf_counter()
                self.packets_saved += packets_to_save
                LOG.info(f"Time to save APRS packets = {toc - tic:0.4f}")
                self.aprs_packets = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f"Failed to save APRS packets: {ex}")
                LOG.exception(ex)
                # Drop the packets to avoid memory issues
                self.aprs_packets = []

    def _print_stats(self):
        """Print statistics about ingested packets using loguru with colors."""
        separator = "=" * 80
        logger.opt(colors=True).info(f"<cyan>{separator}</cyan>")
        logger.opt(colors=True).info("<bold><cyan>MQTT Ingestion Statistics</cyan></bold>")
        logger.opt(colors=True).info(f"<cyan>{separator}</cyan>")
        logger.opt(colors=True).info(
            f"Total packets ingested from MQTT: <green>{self.packet_counter}</green>"
        )
        logger.opt(colors=True).info(
            f"Total packets saved to database: <green>{self.packets_saved}</green>"
        )
        logger.opt(colors=True).info(
            f"Packets pending save: <yellow>{len(self.aprs_packets)}</yellow>"
        )
        logger.opt(colors=True).info(
            f"Weather reports processed: <green>{self.report_counter}</green>"
        )
        logger.opt(colors=True).info(
            f"Weather reports pending save: <yellow>{len(self.reports)}</yellow>"
        )
        logger.opt(colors=True).info(
            f"Unique callsigns seen: <cyan>{len(self.unique_callsigns)}</cyan>"
        )

        if self.packet_types:
            logger.opt(colors=True).info("")
            logger.opt(colors=True).info("<bold>Packet Type Breakdown:</bold>")
            # Sort by count (descending)
            sorted_types = sorted(
                self.packet_types.items(),
                key=lambda x: x[1],
                reverse=True
            )
            for packet_type, count in sorted_types:
                percentage = (count / self.packet_counter * 100) if self.packet_counter > 0 else 0
                # Format values first, then apply colors
                packet_type_str = f"{packet_type:20s}"
                count_str = f"{count:6d}"
                percentage_str = f"{percentage:5.1f}%"
                # Use different colors for different packet types
                color_tag = "green" if count > 100 else "yellow" if count > 10 else "red"
                logger.opt(colors=True).info(
                    f"  <cyan>{packet_type_str}</cyan>: <{color_tag}>{count_str}</{color_tag}> (<magenta>{percentage_str}</magenta>)"
                )

        # Calculate rates if we have timing info
        if self.start_time and self.packet_counter > 0:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                rate = self.packet_counter / elapsed
                save_rate = self.packets_saved / elapsed if self.packets_saved > 0 else 0
                logger.opt(colors=True).info("")
                rate_str = f"{rate:.2f}"
                save_rate_str = f"{save_rate:.2f}"
                elapsed_sec_str = f"{elapsed:.0f}"
                elapsed_min_str = f"{elapsed/60:.1f}"
                logger.opt(colors=True).info(
                    f"Average ingestion rate: <green>{rate_str}</green> packets/second"
                )
                logger.opt(colors=True).info(
                    f"Average save rate: <green>{save_rate_str}</green> packets/second"
                )
                logger.opt(colors=True).info(
                    f"Uptime: <cyan>{elapsed_sec_str}</cyan> seconds (<cyan>{elapsed_min_str}</cyan> minutes)"
                )

        logger.opt(colors=True).info(f"<cyan>{separator}</cyan>")

    def stop(self):
        LOG.info(__class__.__name__+" Stop")
        self.thread_stop = True

        # Print final stats before shutdown
        self._print_stats()

        # Save any remaining packets before stopping
        if self.aprs_packets:
            try:
                packets_to_save = len(self.aprs_packets)
                LOG.info(f"Saving {packets_to_save} remaining APRS packets before shutdown.")
                self.session.bulk_save_objects(self.aprs_packets)
                self.session.commit()
                self.packets_saved += packets_to_save
                self.aprs_packets = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f"Failed to save remaining APRS packets: {ex}")
                LOG.exception(ex)

        # Save any remaining weather reports before stopping
        if self.reports:
            try:
                LOG.info(f"Saving {len(self.reports)} remaining weather reports before shutdown.")
                self.session.bulk_save_objects(self.reports)
                self.session.commit()
                self.reports = []
            except Exception as ex:
                self.session.rollback()
                LOG.error(f"Failed to save remaining weather reports: {ex}")
                LOG.exception(ex)

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
