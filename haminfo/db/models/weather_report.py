import sqlalchemy as sa
from geoalchemy2 import Geography

from haminfo.db.models.modelbase import ModelBase


class WeatherReport(ModelBase):
    __tablename__ = 'weather_report'

    id = sa.Column(sa.Integer, sa.Sequence('weather_report_id_seq'),
                   primary_key=True)
    callsign = sa.Column(sa.String, primary_key=True)
    latitude = sa.Column(sa.Float, nullable=False)
    longitude = sa.Column(sa.Float, nullable=False)
    location = sa.Column(Geography('POINT'))
