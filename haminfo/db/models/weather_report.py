from __future__ import annotations
from typing import List

import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from haminfo.db.models.modelbase import ModelBase


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
    reports: Mapped[List["WeatherReport"]] = relationship(
        back_populates="weather_station", cascade="all, delete")

class WeatherReport(ModelBase):
    __tablename__ = 'weather_report'

    id = sa.Column(sa.Integer, sa.Sequence('weather_report_id_seq'),
                   primary_key=True, unique=True)
    weather_station_id = sa.Column(sa.Integer, sa.ForeignKey("weather_station.id"))
    weather_station = relationship("WeatherStation", back_populates="reports")
    temperature = sa.Column(sa.Float(decimal_return_scale=2))
    humidity = sa.Column(sa.Integer)
    pressure = sa.Column(sa.Float(decimal_return_scale=2))
    course = sa.Column(sa.Integer)
    wind_speed = sa.Column(sa.Float(decimal_return_scale=3))
    wind_gust = sa.Column(sa.Float(decimal_return_scale=4))
    rain_1h = sa.Column(sa.Float(decimal_return_scale=2))
    rain_24h = sa.Column(sa.Float(decimal_return_scale=2))
    rain_since_midnight = sa.Column(sa.Float(decimal_return_scale=2))
    time = sa.Column(sa.DateTime)

