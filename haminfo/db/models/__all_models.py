# Add all your SQLAlchemy models here.
# This allows you to import just this file
# whenever you need to work with your models
# (like creating tables or for migrations)

from haminfo.db.models.station import Station  # noqa
from haminfo.db.models.request import Request  # noqa
from haminfo.db.models.request import WXRequest  # noqa
from haminfo.db.models.weather_report import WeatherStation  # noqa
from haminfo.db.models.weather_report import WeatherReport  # noqa
