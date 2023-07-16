from __future__ import annotations
from datetime import datetime
import time
from typing import List

from oslo_log import log as logging
import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import relationship
from sqlalchemy.exc import NoResultFound

from haminfo.db import caching_query
from haminfo.db.models.modelbase import ModelBase
from haminfo import utils


LOG = logging.getLogger(utils.DOMAIN)


class WeatherStation(ModelBase):
    __tablename__ = 'weather_station'

    id = sa.Column(sa.Integer,
                   sa.Sequence('weather_station_id_seq'), primary_key=True,
                   unique=True)
    callsign = sa.Column(sa.String, primary_key=True, unique=True)
    latitude = sa.Column(sa.Float, nullable=False)
    longitude = sa.Column(sa.Float, nullable=False)
    location = sa.Column(Geography('POINT'))
    comment = sa.Column(sa.String)
    symbol = sa.Column(sa.CHAR)
    symbol_table = sa.Column(sa.CHAR)
    country_code = sa.Column(sa.String)
    reports: Mapped[List["WeatherReport"]] = relationship(
        order_by="desc(WeatherReport.time)",
        back_populates="weather_station", cascade="all, delete")

    @staticmethod
    def find_station_by_callsign(session, callsign):
        callsign = callsign.replace('\x00', '')
        try:
            station = session.query(
                WeatherStation
            ).options(
                caching_query.FromCache('default')
            ).filter(
                WeatherStation.callsign == callsign
            ).one()
            return station
        except NoResultFound:
            LOG.info(f'Failed to find station "{callsign}"')
            return None

    @staticmethod
    def from_json(station_json):
        if not station_json.get('latitude', None):
            # LOG.warning(f"Station {station_json}")
            return None
        if not station_json.get('longitude', None):
            # LOG.warning(f"Station {station_json}")
            return None

        station = WeatherStation(
            callsign=station_json["from_call"].replace('\x00', ''),
            latitude=station_json["latitude"],
            longitude=station_json["longitude"],
            location="POINT({} {})".format(
                station_json['longitude'],
                station_json['latitude']
            ),
            comment=station_json.get("comment", None).replace('\x00', ''),
            symbol=station_json.get("symbol", "_").replace('\x00', ''),
            symbol_table=station_json.get('symbol_table', '/').replace('\x00', ''),
        )
        return station

    def to_dict(self):
        return {
            "id": self.id,
            "callsign": self.callsign,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "symbol": self.symbol,
            "symbol_table": self.symbol_table,
            "comment": self.comment
        }

    def __repr__(self):
        return (
            f"<WeatherStation(ID={self.id}, callsign='{self.callsign}',"
            f"lat={self.latitude}, "
            f"long={self.longitude}, "
            f"Comment='{self.comment}', "
            f"Symbol='{self.symbol}', "
            f"SymbolTable='{self.symbol_table}' "
            ")>"
        )


class WeatherReport(ModelBase):
    __tablename__ = 'weather_report'

    id = sa.Column(sa.Integer, sa.Sequence('weather_report_id_seq'),
                   primary_key=True, unique=True)
    weather_station_id = sa.Column(sa.Integer, sa.ForeignKey("weather_station.id"))
    weather_station = relationship("WeatherStation", back_populates="reports")
    temperature = sa.Column(sa.Float(decimal_return_scale=2))
    humidity = sa.Column(sa.Integer)
    pressure = sa.Column(sa.Float(decimal_return_scale=2))
    wind_direction = sa.Column(sa.Integer)
    wind_speed = sa.Column(sa.Float(decimal_return_scale=3))
    wind_gust = sa.Column(sa.Float(decimal_return_scale=4))
    rain_1h = sa.Column(sa.Float(decimal_return_scale=2))
    rain_24h = sa.Column(sa.Float(decimal_return_scale=2))
    rain_since_midnight = sa.Column(sa.Float(decimal_return_scale=2))
    time = sa.Column(sa.DateTime)
    raw_report = sa.Column(sa.String)

    def to_dict(self):
        return {
            "temperature": self.temperature,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "wind_direction": self.wind_direction,
            "wind_gust": self.wind_gust,
            "rain_1h": self.rain_1h,
            "rain_24h": self.rain_24h,
            "rain_since_midnight": self.rain_since_midnight,
            "time": f"{self.time}",
            "raw_report": self.raw_report
        }

    def __repr__(self):
        return (
            f"<WeatherReport(time='{self.time}', "
            f"Station ID={self.weather_station_id}, "
            f"Temperature={self.temperature}, "
            f"Pressure={self.pressure}, "
            f"rain_since_midnight={self.rain_since_midnight}, "
            f"rain_24h={self.rain_24h}, "
            f"rain_1h={self.rain_1h}, "
            f"wind_gust={self.wind_gust}, "
            f"wind_direction={self.wind_direction}, "
            f"wind_speed={self.wind_speed}, "
            f"raw_report='{self.raw_report}', "
            f"Station={self.weather_station} "
            ")>"
        )

    @staticmethod
    def from_json(station_json, station_id):

        ts_str = station_json.get('timestamp', None)
        if not ts_str:
            ts_str = time.time()

        report_time = str(datetime.fromtimestamp(ts_str))
        temperature = station_json.get("temperature", 0)
        wind_speed = station_json.get("wind_speed", 0.00)
        wind_direction = station_json.get("wind_direction", 0)
        humidity = station_json.get("humidity", 0)
        pressure = station_json.get("pressure", 0)
        wind_gust = station_json.get("wind_gust", 0.00)
        rain_1h = station_json.get("rain_1h", 0.00)
        rain_24h = station_json.get("rain_24h", 0.00)
        rain_since_midnight = station_json.get("rain_since_midnight", 0.00)
        raw_report = station_json.get("raw").replace('\x00', '')
        #if "weather" in station_json:
        #    temperature = station_json["weather"].get("temperature", temperature)
        #    wind_speed = station_json["weather"].get(
        #        "wind_speed", wind_speed
        #    )
        #    humidity = station_json["weather"].get(
        #        "humidity", humidity
        #    )
        #    pressure = station_json["weather"].get(
        #        "pressure", pressure
        #    )
        #    wind_direction = station_json["weather"].get(
        #        "wind_direction", wind_direction
        #    )
        #    wind_gust = station_json["weather"].get(
        #        "wind_gust", wind_gust
        #    )
        #    rain_1h = station_json["weather"].get(
        #        "rain_1h", rain_1h
        #    )
        #    rain_24h = station_json["weather"].get(
        #        "rain_24h", rain_24h
        #    )
        #    rain_since_midnight = station_json["weather"].get(
        #        "rain_since_midnight", rain_since_midnight
        #    )

        return WeatherReport(
            time=report_time,
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            wind_direction=wind_direction,
            wind_speed=wind_speed,
            wind_gust=wind_gust,
            rain_1h=rain_1h,
            rain_24h=rain_24h,
            rain_since_midnight=rain_since_midnight,
            raw_report=raw_report,
            weather_station_id=station_id
        )

    def is_valid(self):
        """Make sure the report has good data."""

        # One common issue is there is no data at all
        # in which case the report will have 0 for all measurements
        if (
            self.temperature == 0 and
            self.humidity == 0 and
            self.pressure == 0 and
            self.wind_direction == 0 and
            self.wind_speed == 0 and
            self.wind_gust == 0 and
            self.rain_since_midnight == 0 and
            self.rain_24h == 0 and
            self.rain_1h == 0
        ):
            # all values are 0
            return False

        else:
            return True
