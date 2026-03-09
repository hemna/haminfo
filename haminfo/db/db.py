"""Database operations for haminfo.

Provides functions for querying and managing ham radio repeater,
weather station, and APRS data in the PostGIS database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import md5
from typing import Any, Optional

from oslo_config import cfg
from oslo_log import log as logging

from dogpile.cache.region import make_region
import sqlalchemy
from sqlalchemy import create_engine, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker, Session, Query

from haminfo.db import caching_query
from haminfo.db.models.station import Station
from haminfo.db.models.modelbase import ModelBase
from haminfo.db.models.request import Request, WXRequest
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo import utils


LOG = logging.getLogger(utils.DOMAIN)
CONF = cfg.CONF

grp = cfg.OptGroup('database')
cfg.CONF.register_group(grp)
database_opts = [
    cfg.StrOpt(
        'connection',
        help='The SQLAlchemy connection string to use to connect to the database.',
        secret=True,
    ),
    cfg.BoolOpt('debug', default=False, help='Enable SQL query debugging'),
]

CONF.register_opts(database_opts, group='database')

memcached_opts = [
    cfg.StrOpt('url', help='The memcached connection string to use.', secret=True),
    cfg.IntOpt(
        'expire_time',
        help='The time the cache data is valid for. Default is 5 minutes',
        default=300,
        secret=True,
    ),
]
CONF.register_opts(memcached_opts, group='memcached')

# Mapping of human filter string to db column name
STATION_FEATURES: dict[str, str] = {
    'ares': 'ares',
    'races': 'races',
    'skywarn': 'skywarn',
    'allstar': 'allstar_node',
    'echolink': 'echolink_node',
    'irlp': 'irlp_node',
    'wires': 'wires_node',
    'fm': 'fm_analog',
    'dmr': 'dmr',
    'dstar': 'dstar',
}

# Global cache object
cache: Optional[caching_query.ORMCache] = None


def init_db_schema(engine: Any) -> None:
    """Initialize (recreate) all database tables.

    Warning: This drops all existing data!
    """
    LOG.info('Dropping all tables')
    ModelBase.metadata.drop_all(engine)
    LOG.info('Creating all tables')
    ModelBase.metadata.create_all(engine)


def md5_key_mangler(key: str) -> str:
    """Convert cache keys to md5 hashes for memcached compatibility."""
    return md5(key.encode('ascii')).hexdigest()


def _create_cache_regions() -> dict[str, Any]:
    """Create dogpile cache regions.

    Uses memcached if configured, otherwise falls back to in-memory cache.
    """
    regions = {}
    memcached_url = CONF.memcached.url

    if memcached_url:
        regions['default'] = make_region(key_mangler=md5_key_mangler).configure(
            'dogpile.cache.pylibmc',
            expiration_time=CONF.memcached.expire_time,
            arguments={'url': [memcached_url]},
        )
    else:
        LOG.warning('memcached.url not configured, using memory cache backend')
        regions['default'] = make_region(key_mangler=md5_key_mangler).configure(
            'dogpile.cache.memory',
            expiration_time=CONF.memcached.expire_time,
        )
    return regions


def get_engine() -> Any:
    """Create and return a SQLAlchemy engine."""
    engine = create_engine(
        CONF.database.connection,
        echo=CONF.database.debug,
    )
    return engine


def setup_session() -> scoped_session:
    """Set up and return a scoped database session factory.

    Also initializes the cache system if not already done.
    """
    global cache
    regions = _create_cache_regions()
    engine = get_engine()
    session = scoped_session(sessionmaker(bind=engine))
    cache = caching_query.ORMCache(regions)
    cache.listen_on_session(session)
    return session


def delete_USA_state_repeaters(state: str, session: Session) -> None:  # noqa: N802
    """Delete all repeaters for a given US state."""
    stmt = (
        sqlalchemy.delete(Station)
        .where(Station.state == state)
        .execution_options(synchronize_session='fetch')
    )
    session.execute(stmt)


def log_request(session: Session, params: dict, results: list[dict]) -> None:
    """Log a nearest-repeater request to the database."""
    r = Request.from_json(params)
    LOG.info(r)
    stations = []
    station_ids = []
    for result in results:
        stations.append(result['callsign'])
        station_ids.append(str(result['id']))

    LOG.info(f'Station_ids {station_ids}')
    r.stations = ','.join(stations)
    r.repeater_ids = ','.join(station_ids)
    try:
        session.add(r)
        session.commit()
        invalidate_requests_cache(session)
    except SQLAlchemyError as ex:
        session.rollback()
        LOG.error(f'Failed to log request: {ex}')


def log_wx_request(session: Session, params: dict, results: list[dict]) -> None:
    """Log a nearest-weather-station request to the database."""
    r = WXRequest.from_json(params)
    LOG.info(r)
    callsigns = []
    station_ids = []
    for result in results:
        callsigns.append(result['callsign'])
        station_ids.append(str(result['id']))

    LOG.info(f'wx_station_ids {station_ids}')
    r.station_callsigns = ','.join(callsigns)
    r.wx_station_ids = ','.join(station_ids)
    try:
        session.add(r)
        session.commit()
        invalidate_wxrequests_cache(session)
    except SQLAlchemyError as ex:
        session.rollback()
        LOG.error(f'Failed to log wx request: {ex}')


def find_stations_by_callsign(session: Session, stations: list[str]) -> Query:
    """Find stations by callsign."""
    query = (
        session.query(Station)
        .options(caching_query.FromCache('default'))
        .filter(Station.callsign.in_(tuple(stations)))
    )
    return query


def find_stations_by_ids(session: Session, repeater_ids: list[int]) -> Query:
    """Find stations by their database IDs."""
    query = (
        session.query(Station)
        .options(caching_query.FromCache('default'))
        .filter(Station.id.in_(tuple(repeater_ids)))
    )
    return query


def find_wx_stations(session: Session) -> Query:
    """Get all weather stations."""
    query = session.query(WeatherStation)
    return query


def find_wx_station_by_callsign(session: Session, callsign: str) -> Query:
    """Find weather stations by callsign."""
    query = (
        session.query(WeatherStation)
        .options(caching_query.FromCache('default'))
        .filter(WeatherStation.callsign.in_(tuple(callsign)))
    )
    return query


def get_wx_station_report(
    session: Session,
    wx_station_id: int,
) -> Optional[WeatherReport]:
    """Find the latest weather report for a station."""
    query = (
        session.query(WeatherReport)
        .options(caching_query.FromCache('default'))
        .filter(WeatherReport.weather_station_id == wx_station_id)
        .order_by(WeatherReport.time.desc())
        .first()
    )
    return query


def add_wx_report(session: Session, report: WeatherReport) -> None:
    """Insert a weather report into the database."""
    raw_report = report.raw_report or ''
    stmt = sqlalchemy.insert(WeatherReport).values(
        weather_station_id=report.weather_station_id,
        temperature=report.temperature,
        humidity=report.humidity,
        pressure=report.pressure,
        wind_direction=report.wind_direction,
        wind_speed=report.wind_speed,
        wind_gust=report.wind_gust,
        rain_1h=report.rain_1h,
        rain_24h=report.rain_24h,
        rain_since_midnight=report.rain_since_midnight,
        time=report.time,
        raw_report=raw_report.rstrip('\x00'),
    )
    session.execute(stmt)


def find_requests(session: Session, number: Optional[int] = None) -> Query:
    """Find API request log entries, most recent first."""
    query = (
        session.query(Request)
        .options(caching_query.FromCache('default'))
        .order_by(Request.id.desc())
    )
    if number:
        query = query.limit(number)
    return query


def invalidate_requests_cache(session: Session) -> None:
    """Invalidate cached request queries."""
    global cache
    if cache is None:
        return

    LOG.info('Invalidate requests cache')
    for limit in (25, 50, None):
        q = session.query(Request).order_by(Request.id.desc())
        if limit:
            q = q.limit(limit)
        cache.invalidate(q, {}, caching_query.FromCache('default'))


def find_nearest_to(
    session: Session,
    lat: float,
    lon: float,
    freq_band: str = '2m',
    limit: int = 1,
    filters: Optional[list[str]] = None,
) -> Query:
    """Find the nearest repeaters to a given lat/lon.

    Args:
        session: Database session.
        lat: Latitude.
        lon: Longitude.
        freq_band: Frequency band to filter by (e.g. '2m', '70cm').
        limit: Maximum number of results.
        filters: Optional list of feature filters (e.g. 'ares', 'dmr').

    Returns:
        Query yielding (Station, distance_meters, bearing_radians) tuples.
    """
    poi = f'SRID=4326;POINT({lon} {lat})'
    poi_point = func.ST_Point(lon, lat)
    LOG.info(f'Band: {freq_band}  Limit: {limit}  Filters: {filters}')

    filter_parts = [Station.freq_band == freq_band]

    if filters:
        filter_parts = []
        for f in filters:
            LOG.info(f"Add filter '{f}'")
            if f in STATION_FEATURES:
                col_name = STATION_FEATURES[f]
                filter_parts.append(getattr(Station, col_name) == True)  # noqa: E712

    query = (
        session.query(
            Station,
            func.ST_Distance(Station.location, poi).label('distance'),
            func.ST_Azimuth(poi_point, func.ST_Point(Station.long, Station.lat)).label(
                'bearing'
            ),
        )
        .filter(*filter_parts)
        .order_by(Station.location.distance_centroid(poi))
        .limit(limit)
    )

    return query


def find_wxnearest_to(
    session: Session,
    lat: float,
    lon: float,
    limit: int = 1,
) -> Query:
    """Find the nearest weather stations to a given lat/lon.

    Args:
        session: Database session.
        lat: Latitude.
        lon: Longitude.
        limit: Maximum number of results.

    Returns:
        Query yielding (WeatherStation, distance_meters, bearing_radians) tuples.
    """
    poi = f'SRID=4326;POINT({lon} {lat})'
    poi_point = func.ST_Point(lon, lat)

    query = (
        session.query(
            WeatherStation,
            func.ST_Distance(WeatherStation.location, poi).label('distance'),
            func.ST_Azimuth(
                poi_point,
                func.ST_Point(WeatherStation.longitude, WeatherStation.latitude),
            ).label('bearing'),
        )
        .order_by(WeatherStation.location.distance_centroid(poi))
        .limit(limit)
    )

    return query


def find_wxrequests(session: Session, number: Optional[int] = None) -> Query:
    """Find weather request log entries, most recent first."""
    query = (
        session.query(WXRequest)
        .options(caching_query.FromCache('default'))
        .order_by(WXRequest.id.desc())
    )
    if number:
        query = query.limit(number)
    return query


def invalidate_wxrequests_cache(session: Session) -> None:
    """Invalidate cached weather request queries."""
    global cache
    if cache is None:
        return

    LOG.info('Invalidate wx requests cache')
    for limit in (25, 50, None):
        q = session.query(WXRequest).order_by(WXRequest.id.desc())
        if limit:
            q = q.limit(limit)
        cache.invalidate(q, {}, caching_query.FromCache('default'))


def get_num_repeaters_in_db(session: Any) -> int:
    """Get the total number of repeaters in the database."""
    rows = session.query(Station).count()
    return rows


def clean_weather_reports(session: Session) -> None:
    """Delete weather reports older than 14 days."""
    LOG.info('Cleaning up old weather reports')
    session.query(WeatherReport).filter(
        WeatherReport.time < func.now() - timedelta(days=14)
    ).delete()
    session.commit()


def clean_empty_wx_stations(session: Session) -> None:
    """Delete weather stations that have no reports."""
    LOG.info('Cleaning up weather stations with no reports')
