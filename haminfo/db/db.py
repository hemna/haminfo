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
from haminfo.db.models.aprs_packet import APRSPacket
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
# Global session factory (avoid recreating engine on every call)
_session_factory: Optional[scoped_session] = None


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
    Returns the cached session factory on subsequent calls.
    """
    global cache, _session_factory
    if _session_factory is not None:
        return _session_factory
    regions = _create_cache_regions()
    engine = get_engine()
    _session_factory = scoped_session(sessionmaker(bind=engine))
    cache = caching_query.ORMCache(regions)
    cache.listen_on_session(_session_factory)
    return _session_factory


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
        .filter(WeatherStation.callsign == callsign)
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
    # Invalidate all cached request queries regardless of page size
    cache.cache_regions['default'].invalidate(hard=False)


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

    filter_parts = []
    if freq_band:
        filter_parts.append(Station.freq_band == freq_band)

    if filters:
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
    # Invalidate all cached wx request queries regardless of page size
    cache.cache_regions['default'].invalidate(hard=False)


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


def clean_empty_wx_stations(session: Session) -> int:
    """Delete weather stations that have no reports.

    Args:
        session: Database session.

    Returns:
        Number of stations deleted.
    """
    LOG.info('Cleaning up weather stations with no reports')

    # Find stations with no reports using a NOT EXISTS subquery
    # This is more efficient than loading all stations and checking reports
    from sqlalchemy import exists, select

    # Subquery to check if a station has any reports
    has_reports = (
        select(WeatherReport.id)
        .where(WeatherReport.weather_station_id == WeatherStation.id)
        .exists()
    )

    # Delete stations that have no reports
    deleted = (
        session.query(WeatherStation)
        .filter(~has_reports)
        .delete(synchronize_session='fetch')
    )
    session.commit()

    LOG.info(f'Deleted {deleted} empty weather stations')
    return deleted


def find_latest_positions_by_callsigns(
    session: Session,
    callsigns: list[str],
) -> list[APRSPacket]:
    """Find the most recent position-bearing packet for each callsign.

    Uses a subquery with group_by and max(timestamp) to find the latest
    position packet per callsign. This is portable across database backends
    (works with both PostgreSQL and SQLite for testing).

    Args:
        session: Database session.
        callsigns: List of callsigns to query (will be uppercased).

    Returns:
        List of APRSPacket instances, one per found callsign,
        each being the most recent packet with position data.
    """
    if not callsigns:
        return []

    # Normalize callsigns to uppercase
    upper_callsigns = [cs.upper() for cs in callsigns]

    # Subquery: find the max timestamp per callsign for packets with positions
    latest_subq = (
        session.query(
            APRSPacket.from_call,
            func.max(APRSPacket.timestamp).label('max_ts'),
        )
        .filter(
            func.upper(APRSPacket.from_call).in_(upper_callsigns),
            APRSPacket.latitude.isnot(None),
            APRSPacket.longitude.isnot(None),
        )
        .group_by(APRSPacket.from_call)
        .subquery()
    )

    # Main query: join back to get the full packet row
    results = (
        session.query(APRSPacket)
        .options(caching_query.FromCache('default'))
        .join(
            latest_subq,
            (APRSPacket.from_call == latest_subq.c.from_call)
            & (APRSPacket.timestamp == latest_subq.c.max_ts),
        )
        .filter(
            APRSPacket.latitude.isnot(None),
            APRSPacket.longitude.isnot(None),
        )
        .all()
    )

    return results


def find_latest_position_by_callsign(
    session: Session,
    callsign: str,
) -> Optional[APRSPacket]:
    """Find the most recent position-bearing packet for a single callsign.

    Convenience wrapper around find_latest_positions_by_callsigns().

    Args:
        session: Database session.
        callsign: Callsign to query (will be uppercased).

    Returns:
        The most recent APRSPacket with position data, or None if not found.
    """
    results = find_latest_positions_by_callsigns(session, [callsign])
    return results[0] if results else None


def clean_aprs_packets(session: Session, days: int = 30) -> int:
    """Delete APRS packets older than the specified number of days.

    Args:
        session: Database session.
        days: Number of days of data to retain (default 30).

    Returns:
        Number of packets deleted.
    """
    LOG.info(f'Cleaning up APRS packets older than {days} days')
    count = (
        session.query(APRSPacket)
        .filter(APRSPacket.received_at < datetime.utcnow() - timedelta(days=days))
        .delete()
    )
    session.commit()
    LOG.info(f'Deleted {count} old APRS packets')
    return count


def get_aprs_packet_stats(session: Session) -> dict[str, Any]:
    """Get statistics about APRS packets in the database.

    Args:
        session: SQLAlchemy database session.

    Returns:
        Dict with total count, counts per packet_type, unique callsign
        count, and last-24-hour packet count.
    """
    total = session.query(APRSPacket).count()

    # Count by packet type
    type_counts = (
        session.query(
            APRSPacket.packet_type,
            func.count(APRSPacket.id),
        )
        .group_by(APRSPacket.packet_type)
        .all()
    )
    type_dict: dict[str, int] = {}
    for ptype, cnt in type_counts:
        key = ptype if ptype else 'unknown'
        type_dict[key] = cnt

    unique_callsigns = (
        session.query(func.count(sqlalchemy.distinct(APRSPacket.from_call))).scalar()
        or 0
    )

    last_24h = (
        session.query(APRSPacket)
        .filter(APRSPacket.received_at >= datetime.utcnow() - timedelta(hours=24))
        .count()
    )

    return {
        'total': total,
        'position': type_dict.get('position', 0),
        'weather': type_dict.get('weather', 0),
        'message': type_dict.get('message', 0),
        'other': sum(
            v
            for k, v in type_dict.items()
            if k not in ('position', 'weather', 'message')
        ),
        'unique_callsigns': unique_callsigns,
        'last_24h': last_24h,
    }
