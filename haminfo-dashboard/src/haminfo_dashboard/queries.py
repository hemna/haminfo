# haminfo_dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, distinct, and_, text

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo_dashboard.utils import (
    get_country_from_callsign,
    get_country_from_coords,
    CALLSIGN_PREFIXES,
    get_state_from_coords,
    normalize_packet_type,
)
from haminfo_dashboard import cache
from haminfo_dashboard.cache import cached

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOG = logging.getLogger(__name__)

# Feature flag for continuous aggregates
# Set to True after migrations are run and aggregates are populated
USE_CONTINUOUS_AGGREGATES = True

# Tile-based caching constants
TILE_CACHE_TTL = 60  # seconds
MAX_TILES_PER_REQUEST = 100


def get_tile_coords(latitude: float, longitude: float) -> tuple[int, int]:
    """Get tile coordinates for a lat/lon position.

    Tiles are 1° x 1° squares. The tile coordinate is the floor
    of the latitude and longitude.

    Args:
        latitude: Latitude in degrees (-90 to 90).
        longitude: Longitude in degrees (-180 to 180).

    Returns:
        Tuple of (tile_lat, tile_lon) as integers.
    """
    return (math.floor(latitude), math.floor(longitude))


def get_tiles_for_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[tuple[int, int]]:
    """Get all tile coordinates that overlap with a bounding box.

    Args:
        min_lon: Western edge of bbox.
        min_lat: Southern edge of bbox.
        max_lon: Eastern edge of bbox.
        max_lat: Northern edge of bbox.

    Returns:
        List of (tile_lat, tile_lon) tuples, sorted by lat then lon.
    """
    start_lat = math.floor(min_lat)
    end_lat = math.floor(max_lat)
    start_lon = math.floor(min_lon)
    end_lon = math.floor(max_lon)

    tiles = []
    for lat in range(start_lat, end_lat + 1):
        for lon in range(start_lon, end_lon + 1):
            tiles.append((lat, lon))

    return tiles


def query_tile_from_db(
    session: Session,
    tile_lat: int,
    tile_lon: int,
    hours: int,
    station_type: str,
) -> list[dict[str, Any]]:
    """Query database for stations within a single tile.

    Returns the most recent packet per callsign within the tile bounds.

    Args:
        session: Database session.
        tile_lat: Tile latitude (floor of actual lat).
        tile_lon: Tile longitude (floor of actual lon).
        hours: Hours of history to include.
        station_type: Optional packet type filter (empty string for all).

    Returns:
        List of compact station dicts.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build filters for the tile
    filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude >= tile_lat,
        APRSPacket.latitude < tile_lat + 1,
        APRSPacket.longitude >= tile_lon,
        APRSPacket.longitude < tile_lon + 1,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    if station_type:
        filters.append(APRSPacket.packet_type == station_type)

    # Query with ordering to get most recent per callsign
    # We'll deduplicate in Python for simplicity
    packets = (
        session.query(APRSPacket)
        .filter(and_(*filters))
        .order_by(APRSPacket.received_at.desc())
        .all()
    )

    # Deduplicate by callsign, keeping most recent
    seen: set[str] = set()
    result = []

    for packet in packets:
        if packet.from_call in seen:
            continue
        seen.add(packet.from_call)

        result.append(
            {
                'callsign': packet.from_call,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'packet_type': packet.packet_type,
                'symbol': packet.symbol,
                'symbol_table': packet.symbol_table,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'received_at': packet.received_at.isoformat()
                if packet.received_at
                else None,
            }
        )

    return result


def get_tile_stations(
    session: Session,
    tile_lat: int,
    tile_lon: int,
    hours: int,
    station_type: str,
) -> list[dict[str, Any]]:
    """Get stations for a tile, using cache when available.

    Args:
        session: Database session.
        tile_lat: Tile latitude coordinate.
        tile_lon: Tile longitude coordinate.
        hours: Hours of history.
        station_type: Packet type filter (empty string for all).

    Returns:
        List of station dicts.
    """
    cache_key = f'map:tile:{hours}:{station_type}:{tile_lat}:{tile_lon}'

    # Try cache first
    try:
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            LOG.debug(f'Tile cache hit: {cache_key}')
            return cached_data
    except Exception as e:
        LOG.warning(f'Cache read failed for {cache_key}: {e}')

    # Cache miss - query database
    LOG.debug(f'Tile cache miss: {cache_key}')
    stations = query_tile_from_db(session, tile_lat, tile_lon, hours, station_type)

    # Store in cache
    try:
        cache.set(cache_key, stations, ttl=TILE_CACHE_TTL)
    except Exception as e:
        LOG.warning(f'Cache write failed for {cache_key}: {e}')

    return stations


def query_bbox_from_db(
    session: Session,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    hours: int,
    station_type: str,
    max_rows: int = 20000,
) -> list[dict[str, Any]]:
    """Query database for stations within a bounding box.

    Returns the most recent packet per callsign within the bbox.
    This is used for bulk loading when many tiles have cache misses.

    Args:
        session: Database session.
        min_lon: Western edge.
        min_lat: Southern edge.
        max_lon: Eastern edge.
        max_lat: Northern edge.
        hours: Hours of history to include.
        station_type: Optional packet type filter (empty string for all).
        max_rows: Maximum rows to fetch from DB. Limits query time for large
            bboxes. Ordered by received_at DESC so most recent packets are
            returned. Default 20000 (enough for ~2000+ unique stations).

    Returns:
        List of compact station dicts.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build filters for the bbox
    filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude >= min_lat,
        APRSPacket.latitude <= max_lat,
        APRSPacket.longitude >= min_lon,
        APRSPacket.longitude <= max_lon,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    if station_type:
        filters.append(APRSPacket.packet_type == station_type)

    # Query with ordering to get most recent per callsign
    # LIMIT prevents scanning entire table for very large bboxes
    packets = (
        session.query(APRSPacket)
        .filter(and_(*filters))
        .order_by(APRSPacket.received_at.desc())
        .limit(max_rows)
        .all()
    )

    # Deduplicate by callsign, keeping most recent
    seen: set[str] = set()
    result = []

    for packet in packets:
        if packet.from_call in seen:
            continue
        seen.add(packet.from_call)

        result.append(
            {
                'callsign': packet.from_call,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'packet_type': packet.packet_type,
                'symbol': packet.symbol,
                'symbol_table': packet.symbol_table,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'received_at': packet.received_at.isoformat()
                if packet.received_at
                else None,
            }
        )

    return result


def get_map_stations_tiled(
    session: Session,
    bbox: tuple[float, float, float, float],
    hours: int,
    station_type: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Get map stations using tile-based caching.

    Calculates tiles overlapping the bbox, checks cache for each tile,
    then does a single DB query for all uncached tiles. Results are
    cached per-tile for future requests.

    Args:
        session: Database session.
        bbox: Bounding box (min_lon, min_lat, max_lon, max_lat).
        hours: Hours of history.
        station_type: Packet type filter (empty string for all).
        limit: Maximum stations to return.

    Returns:
        List of station dicts sorted by recency.
    """
    min_lon, min_lat, max_lon, max_lat = bbox

    # Get tiles for bbox
    tiles = get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat)

    # Limit tiles to prevent abuse
    if len(tiles) > MAX_TILES_PER_REQUEST:
        LOG.warning(
            f'Bbox too large: {len(tiles)} tiles, limiting to {MAX_TILES_PER_REQUEST}'
        )
        tiles = tiles[:MAX_TILES_PER_REQUEST]

    # Check cache for each tile, collect cached data and uncached tiles
    all_stations: dict[str, dict[str, Any]] = {}
    uncached_tiles: list[tuple[int, int]] = []

    for tile_lat, tile_lon in tiles:
        cache_key = f'map:tile:{hours}:{station_type}:{tile_lat}:{tile_lon}'
        try:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                # Cache hit - add to results
                for station in cached_data:
                    callsign = station['callsign']
                    if callsign not in all_stations:
                        all_stations[callsign] = station
                    elif station.get('received_at', '') > all_stations[callsign].get(
                        'received_at', ''
                    ):
                        all_stations[callsign] = station
            else:
                uncached_tiles.append((tile_lat, tile_lon))
        except Exception as e:
            LOG.warning(f'Cache read failed for {cache_key}: {e}')
            uncached_tiles.append((tile_lat, tile_lon))

    # If there are uncached tiles, do ONE database query for the whole bbox
    # (or the uncached portion) and then cache per-tile
    if uncached_tiles:
        LOG.debug(f'Cache miss for {len(uncached_tiles)} tiles, querying DB')

        # Query the entire bbox in one go (faster than N separate queries)
        db_stations = query_bbox_from_db(
            session, min_lon, min_lat, max_lon, max_lat, hours, station_type
        )

        # Organize stations by tile for caching
        tiles_data: dict[tuple[int, int], list[dict[str, Any]]] = {
            t: [] for t in uncached_tiles
        }

        for station in db_stations:
            tile_coord = get_tile_coords(station['latitude'], station['longitude'])

            # Add to all_stations
            callsign = station['callsign']
            if callsign not in all_stations:
                all_stations[callsign] = station
            elif station.get('received_at', '') > all_stations[callsign].get(
                'received_at', ''
            ):
                all_stations[callsign] = station

            # Add to tile bucket for caching (only for uncached tiles)
            if tile_coord in tiles_data:
                tiles_data[tile_coord].append(station)

        # Cache each tile's data
        for (tile_lat, tile_lon), tile_stations in tiles_data.items():
            cache_key = f'map:tile:{hours}:{station_type}:{tile_lat}:{tile_lon}'
            try:
                cache.set(cache_key, tile_stations, ttl=TILE_CACHE_TTL)
            except Exception as e:
                LOG.warning(f'Cache write failed for {cache_key}: {e}')

    # Filter to exact bbox
    result = [
        s
        for s in all_stations.values()
        if (
            min_lat <= s['latitude'] <= max_lat and min_lon <= s['longitude'] <= max_lon
        )
    ]

    # Sort by recency and apply limit
    result.sort(key=lambda s: s.get('received_at', ''), reverse=True)

    return result[:limit]


@cached('dashboard:stats', ttl=30)
def get_dashboard_stats(session: Session) -> dict[str, Any]:
    """Get summary statistics for dashboard.

    Args:
        session: Database session.

    Returns:
        Dict with total_packets_24h, unique_stations, countries, weather_stations.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_dashboard_stats_from_aggregates(session)
    return _get_dashboard_stats_from_raw(session)


def _get_dashboard_stats_from_aggregates(session: Session) -> dict[str, Any]:
    """Get dashboard stats from continuous aggregates (fast)."""
    result = session.execute(
        text("""
        SELECT
            COALESCE(SUM(packet_count), 0) as total_packets,
            COALESCE(SUM(unique_stations), 0) as unique_stations,
            COALESCE(SUM(unique_prefixes), 0) as unique_prefixes
        FROM aprs_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
    """)
    ).fetchone()

    # Weather stations still from regular query
    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0

    # Count unique countries from weather stations
    countries = (
        session.query(func.count(distinct(WeatherStation.country_code)))
        .filter(WeatherStation.country_code.isnot(None))
        .scalar()
        or 0
    )

    return {
        'total_packets_24h': int(result.total_packets) if result else 0,
        'unique_stations': int(result.unique_stations) if result else 0,
        'countries': countries,
        'weather_stations': weather_stations,
    }


def _get_dashboard_stats_from_raw(session: Session) -> dict[str, Any]:
    """Get dashboard stats from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Count packets in last 24 hours
    total_packets = (
        session.query(func.count(APRSPacket.from_call))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    # Count unique stations in last 24 hours
    unique_stations = (
        session.query(func.count(distinct(APRSPacket.from_call)))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    # Count unique countries from weather stations
    countries = (
        session.query(func.count(distinct(WeatherStation.country_code)))
        .filter(WeatherStation.country_code.isnot(None))
        .scalar()
        or 0
    )

    # Count weather stations
    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0

    return {
        'total_packets_24h': total_packets,
        'unique_stations': unique_stations,
        'countries': countries,
        'weather_stations': weather_stations,
    }


@cached('dashboard:top_stations:{limit}')
def get_top_stations(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get top stations by packet count in the last 24 hours.

    Args:
        session: Database session.
        limit: Maximum number of stations to return.

    Returns:
        List of dicts with callsign, count, and country info.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_top_stations_from_aggregates(session, limit)
    return _get_top_stations_from_raw(session, limit)


def _get_top_stations_from_aggregates(
    session: Session, limit: int
) -> list[dict[str, Any]]:
    """Get top stations from continuous aggregates (fast)."""
    results = session.execute(
        text("""
        SELECT from_call, SUM(packet_count) as total_count
        FROM aprs_station_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY from_call
        ORDER BY total_count DESC
        LIMIT :limit
    """),
        {'limit': limit},
    ).fetchall()

    stations = []
    for row in results:
        country_info = get_country_from_callsign(row.from_call)
        stations.append(
            {
                'callsign': row.from_call,
                'count': int(row.total_count),
                'country_code': country_info[0] if country_info else None,
                'country_name': country_info[1] if country_info else None,
            }
        )

    return stations


def _get_top_stations_from_raw(session: Session, limit: int) -> list[dict[str, Any]]:
    """Get top stations from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    results = (
        session.query(
            APRSPacket.from_call,
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(APRSPacket.from_call)
        .order_by(func.count(APRSPacket.from_call).desc())
        .limit(limit)
        .all()
    )

    stations = []
    for callsign, count in results:
        country_info = get_country_from_callsign(callsign)
        stations.append(
            {
                'callsign': callsign,
                'count': count,
                'country_code': country_info[0] if country_info else None,
                'country_name': country_info[1] if country_info else None,
            }
        )

    return stations


@cached('dashboard:countries:{limit}')
def get_country_breakdown(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get packet count breakdown by country.

    Args:
        session: Database session.
        limit: Maximum number of countries to return.

    Returns:
        List of dicts with country_code, country_name, count.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_country_breakdown_from_aggregates(session, limit)
    return _get_country_breakdown_from_raw(session, limit)


def _get_country_breakdown_from_aggregates(
    session: Session, limit: int
) -> list[dict[str, Any]]:
    """Get country breakdown from continuous aggregates (fast)."""
    prefix_counts = session.execute(
        text("""
        SELECT prefix, SUM(packet_count) as count
        FROM aprs_prefix_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY prefix
    """)
    ).fetchall()

    country_counts: dict[tuple[str, str], int] = {}
    unknown_count = 0

    for row in prefix_counts:
        prefix = row.prefix
        count = int(row.count)
        if not prefix:
            unknown_count += count
            continue
        country_info = None
        if len(prefix) >= 2:
            country_info = CALLSIGN_PREFIXES.get(prefix[:2])
        if not country_info and len(prefix) >= 1:
            country_info = CALLSIGN_PREFIXES.get(prefix[:1])

        if country_info:
            key = country_info
            country_counts[key] = country_counts.get(key, 0) + count
        else:
            unknown_count += count

    result = [
        {'country_code': code, 'country_name': name, 'count': cnt}
        for (code, name), cnt in country_counts.items()
    ]
    result.sort(key=lambda x: x['count'], reverse=True)

    return result[:limit]


def _get_country_breakdown_from_raw(
    session: Session, limit: int
) -> list[dict[str, Any]]:
    """Get country breakdown from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get counts grouped by first 1-2 characters of callsign (prefix)
    prefix_counts = (
        session.query(
            func.substring(APRSPacket.from_call, 1, 2).label('prefix'),
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(func.substring(APRSPacket.from_call, 1, 2))
        .all()
    )

    # Aggregate by country using prefix mapping
    country_counts: dict[tuple[str, str], int] = {}
    unknown_count = 0

    for prefix, count in prefix_counts:
        if not prefix:
            unknown_count += count
            continue
        # Try 2-char prefix first, then 1-char
        country_info = None
        if len(prefix) >= 2:
            country_info = CALLSIGN_PREFIXES.get(prefix[:2])
        if not country_info and len(prefix) >= 1:
            country_info = CALLSIGN_PREFIXES.get(prefix[:1])

        if country_info:
            key = country_info
            country_counts[key] = country_counts.get(key, 0) + count
        else:
            unknown_count += count

    # Convert to list and sort
    result = [
        {
            'country_code': code,
            'country_name': name,
            'count': cnt,
        }
        for (code, name), cnt in country_counts.items()
    ]
    result.sort(key=lambda x: x['count'], reverse=True)

    return result[:limit]


@cached('dashboard:hourly', ttl=300)
def get_hourly_distribution(session: Session) -> dict[str, list]:
    """Get packet count distribution by hour of day.

    Args:
        session: Database session.

    Returns:
        Dict with 'labels' (hour strings) and 'values' (counts) arrays.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_hourly_distribution_from_aggregates(session)
    return _get_hourly_distribution_from_raw(session)


def _get_hourly_distribution_from_aggregates(session: Session) -> dict[str, list]:
    """Get hourly distribution from continuous aggregates (fast)."""
    # Use bucket + 1 hour to include buckets where any part falls within 24h window
    # This prevents gaps when the current time is past the hour mark
    # e.g., at 18:11, we want to include yesterday's 18:00 bucket
    hourly_counts = session.execute(
        text("""
        SELECT EXTRACT(hour FROM bucket)::integer as hour, SUM(packet_count) as count
        FROM aprs_stats_hourly
        WHERE bucket + INTERVAL '1 hour' > NOW() - INTERVAL '24 hours'
          AND bucket < NOW()
        GROUP BY EXTRACT(hour FROM bucket)
    """)
    ).fetchall()

    hour_map = {}
    for row in hourly_counts:
        if row.hour is not None:
            hour_map[row.hour] = int(row.count)

    labels = [f'{h:02d}:00' for h in range(24)]
    values = [hour_map.get(h, 0) for h in range(24)]

    return {'labels': labels, 'values': values}


def _get_hourly_distribution_from_raw(session: Session) -> dict[str, list]:
    """Get hourly distribution from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get dialect to use appropriate function
    dialect = session.bind.dialect.name if session.bind else 'postgresql'

    if dialect == 'sqlite':
        hour_expr = func.strftime('%H', APRSPacket.received_at)
    else:
        hour_expr = func.extract('hour', APRSPacket.received_at)

    hourly_counts = (
        session.query(
            hour_expr.label('hour'),
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(hour_expr)
        .all()
    )

    # Create dict from results
    hour_map = {}
    for hour, count in hourly_counts:
        if hour is not None:
            hour_map[int(hour)] = count

    # Build complete 24-hour arrays
    labels = [f'{h:02d}:00' for h in range(24)]
    values = [hour_map.get(h, 0) for h in range(24)]

    return {
        'labels': labels,
        'values': values,
    }


def get_recent_packets(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    callsign: Optional[str] = None,
    country: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get recent packets with optional filters.

    Note: Not cached because it's used for live data and has many param combinations.

    Args:
        session: Database session.
        limit: Maximum number of packets to return.
        offset: Number of packets to skip.
        callsign: Filter by callsign (partial match).
        country: Filter by country code.

    Returns:
        List of packet dicts.
    """
    query = session.query(APRSPacket).order_by(APRSPacket.received_at.desc())

    if callsign:
        query = query.filter(APRSPacket.from_call.ilike(f'%{callsign}%'))

    packets = query.offset(offset).limit(limit if not country else limit * 3).all()

    result = []
    for packet in packets:
        if country:
            country_info = get_country_from_callsign(packet.from_call)
            if not country_info or country_info[0] != country:
                continue

        country_info = get_country_from_callsign(packet.from_call)
        result.append(
            {
                'from_call': packet.from_call,
                'to_call': packet.to_call,
                'path': packet.path,
                'packet_type': normalize_packet_type(
                    packet.packet_type,
                    packet.latitude,
                    packet.longitude,
                    packet.raw,
                ),
                'received_at': packet.received_at.isoformat()
                if packet.received_at
                else None,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'raw': packet.raw,
                'country_code': country_info[0] if country_info else None,
                'country_name': country_info[1] if country_info else None,
            }
        )

        if len(result) >= limit:
            break

    return result


@cached(
    'dashboard:wx_stations:{limit}:{offset}:{country}:{state}:{has_recent_data}:{search}'
)
def get_weather_stations(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    country: Optional[str] = None,
    state: Optional[str] = None,
    has_recent_data: bool = False,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get weather stations with their latest reports.

    Args:
        session: Database session.
        limit: Maximum number of stations to return.
        offset: Number of stations to skip.
        country: Filter by country code.
        state: Filter by state/province code (US, CA, AU only).
        has_recent_data: Only return stations with reports in last 24h.
        search: Filter by callsign (partial match, case-insensitive).

    Returns:
        List of weather station dicts with latest report data.
    """
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    query = session.query(WeatherStation).order_by(WeatherStation.callsign)

    # Apply callsign search filter at DB level for efficiency
    if search:
        query = query.filter(WeatherStation.callsign.ilike(f'%{search}%'))

    stations_list = query.all()

    result = []
    for station in stations_list:
        report_query = session.query(WeatherReport).filter(
            WeatherReport.weather_station_id == station.id
        )

        if has_recent_data:
            report_query = report_query.filter(WeatherReport.time >= last_24h)

        latest_report = report_query.order_by(WeatherReport.time.desc()).first()

        # Skip stations with no reports at all
        if not latest_report:
            continue

        # Get country from coordinates first (more reliable for weather stations)
        # Fall back to callsign prefix if coords don't match any country
        country_info = get_country_from_coords(station.latitude, station.longitude)
        if not country_info:
            country_info = get_country_from_callsign(station.callsign)

        if country:
            if not country_info or country_info[0] != country:
                continue

        # Get state info for supported countries
        state_info = None
        if country_info and country_info[0] in ('US', 'CA', 'AU'):
            state_info = get_state_from_coords(
                station.latitude, station.longitude, country_info[0]
            )

        # Filter by state if specified
        if state:
            if not state_info or state_info[0] != state:
                continue

        station_dict = {
            'id': station.id,
            'callsign': station.callsign,
            'latitude': station.latitude,
            'longitude': station.longitude,
            'comment': station.comment,
            'country_code': country_info[0] if country_info else None,
            'country_name': country_info[1] if country_info else None,
            'state_code': state_info[0] if state_info else None,
            'state_name': state_info[1] if state_info else None,
        }

        station_dict['latest_report'] = {
            'time': latest_report.time.isoformat() if latest_report.time else None,
            'temperature': latest_report.temperature,
            'humidity': latest_report.humidity,
            'pressure': latest_report.pressure,
            'wind_speed': latest_report.wind_speed,
            'wind_direction': latest_report.wind_direction,
        }

        result.append(station_dict)

        if len(result) >= limit + offset:
            break

    return result[offset : offset + limit]


@cached('dashboard:wx_countries')
def get_weather_countries(session: Session) -> list[dict[str, Any]]:
    """Get list of countries that have weather stations with reports.

    Args:
        session: Database session.

    Returns:
        List of dicts with country_code, country_name, count.
    """
    # Only get stations that have at least one weather report
    from sqlalchemy import exists

    stations = (
        session.query(
            WeatherStation.callsign, WeatherStation.latitude, WeatherStation.longitude
        )
        .filter(exists().where(WeatherReport.weather_station_id == WeatherStation.id))
        .all()
    )

    country_counts: dict[tuple[str, str], int] = {}

    for callsign, lat, lon in stations:
        # Get country from coordinates first (more reliable)
        # Fall back to callsign prefix if coords don't match
        country_info = get_country_from_coords(lat, lon)
        if not country_info:
            country_info = get_country_from_callsign(callsign)
        if country_info:
            key = country_info
            country_counts[key] = country_counts.get(key, 0) + 1

    result = [
        {
            'country_code': code,
            'country_name': name,
            'count': cnt,
        }
        for (code, name), cnt in country_counts.items()
    ]
    result.sort(key=lambda x: x['count'], reverse=True)

    return result


@cached('dashboard:station:{callsign}')
def get_station_detail(session: Session, callsign: str) -> Optional[dict[str, Any]]:
    """Get detailed information about a station.

    Args:
        session: Database session.
        callsign: Station callsign.

    Returns:
        Dict with station details or None if not found.
    """
    callsign_upper = callsign.upper()

    latest_packet = (
        session.query(APRSPacket)
        .filter(APRSPacket.from_call == callsign_upper)
        .order_by(APRSPacket.received_at.desc())
        .first()
    )

    # Also get the most recent packet WITH position data in the database
    # This handles cases where the latest packet is telemetry/message/status
    # but older packets have valid position information
    latest_position_packet = (
        session.query(APRSPacket)
        .filter(
            APRSPacket.from_call == callsign_upper,
            APRSPacket.latitude.isnot(None),
            APRSPacket.longitude.isnot(None),
        )
        .order_by(APRSPacket.received_at.desc())
        .first()
    )

    # If no position packet found in DB, try parsing recent raw packets with aprslib
    # This handles cases where Rust ingest didn't extract position (e.g., objects)
    parsed_position = None
    if not latest_position_packet:
        # Get a few recent packets to try parsing (not just the latest)
        recent_packets = (
            session.query(APRSPacket)
            .filter(APRSPacket.from_call == callsign_upper)
            .order_by(APRSPacket.received_at.desc())
            .limit(20)
            .all()
        )

        for packet in recent_packets:
            if not packet.raw:
                continue
            try:
                import aprslib

                parsed = aprslib.parse(packet.raw)

                # Only accept position from formats that actually contain position
                # Reject telemetry and other non-position formats
                fmt = parsed.get('format', '')
                if fmt in ('telemetry', 'telemetry-message', 'message', 'status'):
                    continue

                lat = parsed.get('latitude')
                lon = parsed.get('longitude')

                # Validate coordinates are within valid ranges
                # Also reject coordinates that are suspiciously close to 0,0 or poles
                if lat is not None and lon is not None:
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                    # Reject coordinates above 85° latitude (likely parsing errors)
                    if abs(lat) > 85:
                        continue
                    # Reject 0,0 (null island - usually parsing error)
                    if lat == 0 and lon == 0:
                        continue

                    parsed_position = {
                        'latitude': lat,
                        'longitude': lon,
                        'altitude': parsed.get('altitude'),
                        'speed': parsed.get('speed'),
                        'course': parsed.get('course'),
                        'received_at': packet.received_at,
                    }
                    break  # Found valid position, stop searching
            except Exception:
                continue

    if not latest_packet:
        # Fall back to weather station table - some weather stations
        # may not have APRS packets but exist in WeatherStation table
        # Use case-insensitive match since callsigns may be stored with mixed case
        weather_station = (
            session.query(WeatherStation)
            .filter(func.upper(WeatherStation.callsign) == callsign_upper)
            .first()
        )
        if weather_station:
            # Return minimal station info from weather station
            country_info = get_country_from_coords(
                weather_station.latitude, weather_station.longitude
            )
            if not country_info:
                country_info = get_country_from_callsign(callsign)

            # Get weather report count
            report_count = (
                session.query(func.count(WeatherReport.id))
                .filter(WeatherReport.weather_station_id == weather_station.id)
                .scalar()
                or 0
            )

            return {
                'callsign': weather_station.callsign,
                'last_seen': None,
                'latitude': weather_station.latitude,
                'longitude': weather_station.longitude,
                'altitude': None,
                'speed': None,
                'course': None,
                'symbol': '_',  # Weather station symbol
                'symbol_table': '/',
                'comment': weather_station.comment,
                'packets_24h': 0,
                'packets_7d': 0,
                'packets_total': report_count,  # Use weather report count
                'first_seen': None,
                'packet_types': {'weather': report_count},
                'country_code': country_info[0] if country_info else None,
                'country_name': country_info[1] if country_info else None,
                'is_weather_station': True,
            }
        return None

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Count packets in last 24 hours
    packets_24h = (
        session.query(func.count('*'))
        .select_from(APRSPacket)
        .filter(
            APRSPacket.from_call == callsign_upper,
            APRSPacket.received_at >= last_24h,
        )
        .scalar()
        or 0
    )

    # Count packets in last 7 days
    packets_7d = (
        session.query(func.count('*'))
        .select_from(APRSPacket)
        .filter(
            APRSPacket.from_call == callsign_upper,
            APRSPacket.received_at >= last_7d,
        )
        .scalar()
        or 0
    )

    # Count total packets
    packets_total = (
        session.query(func.count('*'))
        .select_from(APRSPacket)
        .filter(APRSPacket.from_call == callsign_upper)
        .scalar()
        or 0
    )

    # Get first seen date
    first_packet = (
        session.query(APRSPacket.received_at)
        .filter(APRSPacket.from_call == callsign_upper)
        .order_by(APRSPacket.received_at.asc())
        .first()
    )
    first_seen = first_packet[0].strftime('%Y-%m-%d') if first_packet else None

    type_counts = (
        session.query(
            APRSPacket.packet_type,
            func.count(APRSPacket.packet_type).label('count'),
        )
        .filter(
            APRSPacket.from_call == callsign_upper,
            APRSPacket.received_at >= last_24h,
        )
        .group_by(APRSPacket.packet_type)
        .all()
    )
    packet_types = {ptype or 'unknown': count for ptype, count in type_counts}

    # Determine position data source (in priority order):
    # 1. DB packet with position data
    # 2. Parsed position from raw packet
    # 3. Latest packet (which may have None lat/lon)
    if latest_position_packet:
        lat = latest_position_packet.latitude
        lon = latest_position_packet.longitude
        alt = latest_position_packet.altitude
        spd = latest_position_packet.speed
        crs = latest_position_packet.course
        pos_last_seen = (
            latest_position_packet.received_at.isoformat()
            if latest_position_packet.received_at
            else None
        )
    elif parsed_position:
        lat = parsed_position['latitude']
        lon = parsed_position['longitude']
        alt = parsed_position['altitude']
        spd = parsed_position['speed']
        crs = parsed_position['course']
        pos_last_seen = (
            parsed_position['received_at'].isoformat()
            if parsed_position['received_at']
            else None
        )
    else:
        lat = latest_packet.latitude
        lon = latest_packet.longitude
        alt = latest_packet.altitude
        spd = latest_packet.speed
        crs = latest_packet.course
        pos_last_seen = None

    # Get country - prefer coords lookup over callsign prefix
    country_info = None
    if lat is not None and lon is not None:
        country_info = get_country_from_coords(lat, lon)
    if not country_info:
        country_info = get_country_from_callsign(callsign)

    # Get state for US stations
    state_info = None
    if country_info and country_info[0] == 'US' and lat is not None and lon is not None:
        state_info = get_state_from_coords(lat, lon, 'US')

    return {
        'callsign': latest_packet.from_call,
        'last_seen': latest_packet.received_at.isoformat()
        if latest_packet.received_at
        else None,
        'latitude': lat,
        'longitude': lon,
        'altitude': alt,
        'speed': spd,
        'course': crs,
        'symbol': latest_packet.symbol,
        'symbol_table': latest_packet.symbol_table,
        'comment': latest_packet.comment,
        'packets_24h': packets_24h,
        'packets_7d': packets_7d,
        'packets_total': packets_total,
        'first_seen': first_seen,
        'packet_types': packet_types,
        'country_code': country_info[0] if country_info else None,
        'country_name': country_info[1] if country_info else None,
        'position_last_seen': pos_last_seen,
        'state_code': state_info[0] if state_info else None,
        'state_name': state_info[1] if state_info else None,
    }


def get_station_weather_reports(
    session: Session,
    callsign: str,
    limit: int = 20,
) -> Optional[dict[str, Any]]:
    """Get weather reports for a station.

    Args:
        session: Database session.
        callsign: Station callsign.
        limit: Maximum number of reports to return.

    Returns:
        Dict with station info and weather reports, or None if not a weather station.
    """
    # Check if this callsign is a weather station
    # Use case-insensitive match since callsigns may be stored with mixed case
    station = (
        session.query(WeatherStation)
        .filter(func.upper(WeatherStation.callsign) == callsign.upper())
        .first()
    )

    if not station:
        return None

    # Get recent weather reports
    reports = (
        session.query(WeatherReport)
        .filter(WeatherReport.weather_station_id == station.id)
        .order_by(WeatherReport.time.desc())
        .limit(limit)
        .all()
    )

    country_info = get_country_from_callsign(callsign)

    return {
        'station': {
            'id': station.id,
            'callsign': station.callsign,
            'latitude': station.latitude,
            'longitude': station.longitude,
            'comment': station.comment,
            'country_code': country_info[0] if country_info else None,
            'country_name': country_info[1] if country_info else None,
        },
        'reports': [
            {
                'time': report.time.isoformat() if report.time else None,
                # Convert temperature from Fahrenheit (DB storage) to Celsius (display)
                'temperature': (report.temperature - 32) * 5 / 9
                if report.temperature is not None
                else None,
                'humidity': report.humidity,
                'pressure': report.pressure,
                'wind_speed': report.wind_speed,
                'wind_direction': report.wind_direction,
                'wind_gust': report.wind_gust,
                'rain_1h': report.rain_1h,
                'rain_24h': report.rain_24h,
                'rain_since_midnight': report.rain_since_midnight,
            }
            for report in reports
        ],
        'report_count': len(reports),
    }


@cached('dashboard:map:{bbox}:{station_type}:{limit}')
def get_map_stations(
    session: Session,
    bbox: Optional[tuple[float, float, float, float]] = None,
    station_type: Optional[str] = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Get stations for map display with optional bounding box filter.

    Args:
        session: Database session.
        bbox: Optional bounding box (min_lon, min_lat, max_lon, max_lat).
        station_type: Optional packet type filter.
        limit: Maximum number of stations to return.

    Returns:
        List of station dicts with position data.
    """
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Build base filters for the subquery
    subq_filters = [
        APRSPacket.received_at >= last_24h,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    # If filtering by station type, include it in subquery
    # This ensures we find the latest packet OF THAT TYPE for each station
    if station_type:
        subq_filters.append(APRSPacket.packet_type == station_type)

    latest_subq = (
        session.query(
            APRSPacket.from_call,
            func.max(APRSPacket.received_at).label('max_received'),
        )
        .filter(*subq_filters)
        .group_by(APRSPacket.from_call)
        .subquery()
    )

    query = session.query(APRSPacket).join(
        latest_subq,
        (APRSPacket.from_call == latest_subq.c.from_call)
        & (APRSPacket.received_at == latest_subq.c.max_received),
    )

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        query = query.filter(
            APRSPacket.longitude >= min_lon,
            APRSPacket.longitude <= max_lon,
            APRSPacket.latitude >= min_lat,
            APRSPacket.latitude <= max_lat,
        )

    # Also filter main query by station_type to match the subquery
    if station_type:
        query = query.filter(APRSPacket.packet_type == station_type)

    packets = query.limit(limit).all()

    result = []
    for packet in packets:
        country_info = get_country_from_callsign(packet.from_call)
        result.append(
            {
                'callsign': packet.from_call,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'packet_type': packet.packet_type,
                'symbol': packet.symbol,
                'symbol_table': packet.symbol_table,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'last_seen': packet.received_at.isoformat()
                if packet.received_at
                else None,
                'country_code': country_info[0] if country_info else None,
            }
        )

    return result


def get_map_stations_fast(
    session: Session,
    bbox: Optional[tuple[float, float, float, float]] = None,
    station_type: Optional[str] = None,
    hours: int = 24,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Get stations for map display using a fast query (no trails).

    This is optimized for quick initial load - it fetches recent packets
    and deduplicates by callsign in Python, which is much faster than
    the GROUP BY subquery approach for large datasets.

    Args:
        session: Database session.
        bbox: Optional bounding box (min_lon, min_lat, max_lon, max_lat).
        station_type: Optional packet type filter.
        hours: Number of hours of history to include.
        limit: Maximum number of unique stations to return.

    Returns:
        List of station dicts with position data (no trails).
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build filters - query recent packets directly, ordered by time desc
    filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    if station_type:
        filters.append(APRSPacket.packet_type == station_type)

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        filters.extend(
            [
                APRSPacket.longitude >= min_lon,
                APRSPacket.longitude <= max_lon,
                APRSPacket.latitude >= min_lat,
                APRSPacket.latitude <= max_lat,
            ]
        )

    # Fetch more packets than needed, then deduplicate
    # This is faster than GROUP BY for getting first N unique stations
    packets = (
        session.query(APRSPacket)
        .filter(*filters)
        .order_by(APRSPacket.received_at.desc())
        .limit(limit * 10)  # Fetch extra to ensure we get enough unique
        .all()
    )

    # Deduplicate by callsign, keeping the most recent packet
    seen_callsigns: set[str] = set()
    result = []

    for packet in packets:
        if packet.from_call in seen_callsigns:
            continue
        seen_callsigns.add(packet.from_call)

        country_info = get_country_from_callsign(packet.from_call)
        result.append(
            {
                'callsign': packet.from_call,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'packet_type': packet.packet_type,
                'symbol': packet.symbol,
                'symbol_table': packet.symbol_table,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'last_seen': packet.received_at.isoformat()
                if packet.received_at
                else None,
                'country_code': country_info[0] if country_info else None,
                'trail': [],  # No trails in fast mode
            }
        )

        if len(result) >= limit:
            break

    return result


def count_map_stations(
    session: Session,
    bbox: Optional[tuple[float, float, float, float]] = None,
    station_type: Optional[str] = None,
    hours: int = 24,
) -> int:
    """Count unique stations in the map view area.

    Args:
        session: Database session.
        bbox: Optional bounding box (min_lon, min_lat, max_lon, max_lat).
        station_type: Optional packet type filter.
        hours: Number of hours of history to include.

    Returns:
        Count of unique stations.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build filters
    filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    if station_type:
        filters.append(APRSPacket.packet_type == station_type)

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        filters.extend(
            [
                APRSPacket.longitude >= min_lon,
                APRSPacket.longitude <= max_lon,
                APRSPacket.latitude >= min_lat,
                APRSPacket.latitude <= max_lat,
            ]
        )

    count = (
        session.query(func.count(distinct(APRSPacket.from_call)))
        .filter(*filters)
        .scalar()
        or 0
    )

    return count


def get_map_stations_with_trails(
    session: Session,
    bbox: Optional[tuple[float, float, float, float]] = None,
    station_type: Optional[str] = None,
    hours: int = 1,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get stations for map display with position trails.

    Args:
        session: Database session.
        bbox: Optional bounding box (min_lon, min_lat, max_lon, max_lat).
        station_type: Optional packet type filter.
        hours: Number of hours of history to include (1, 2, 6, 24).
        limit: Maximum number of stations to return.
        offset: Number of stations to skip (for pagination).

    Returns:
        List of station dicts with position data and trail coordinates.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # First get the unique stations with their latest position in the bbox
    subq_filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]

    if station_type:
        subq_filters.append(APRSPacket.packet_type == station_type)

    # Subquery to find latest packet per station
    latest_subq = (
        session.query(
            APRSPacket.from_call,
            func.max(APRSPacket.received_at).label('max_received'),
        )
        .filter(*subq_filters)
        .group_by(APRSPacket.from_call)
        .subquery()
    )

    # Get latest packet for each station
    query = session.query(APRSPacket).join(
        latest_subq,
        (APRSPacket.from_call == latest_subq.c.from_call)
        & (APRSPacket.received_at == latest_subq.c.max_received),
    )

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        query = query.filter(
            APRSPacket.longitude >= min_lon,
            APRSPacket.longitude <= max_lon,
            APRSPacket.latitude >= min_lat,
            APRSPacket.latitude <= max_lat,
        )

    if station_type:
        query = query.filter(APRSPacket.packet_type == station_type)

    # Apply pagination - order by callsign for consistent pagination
    query = query.order_by(APRSPacket.from_call)
    latest_packets = query.offset(offset).limit(limit).all()

    # Get callsigns of stations in view
    callsigns = [p.from_call for p in latest_packets]

    if not callsigns:
        return []

    # Now get all positions for these stations within the time window
    # to build trails
    trail_query = (
        session.query(
            APRSPacket.from_call,
            APRSPacket.latitude,
            APRSPacket.longitude,
            APRSPacket.received_at,
            APRSPacket.speed,
        )
        .filter(
            APRSPacket.from_call.in_(callsigns),
            APRSPacket.received_at >= since,
            APRSPacket.latitude.isnot(None),
            APRSPacket.longitude.isnot(None),
        )
        .order_by(APRSPacket.from_call, APRSPacket.received_at)
        .all()
    )

    # Group trail points by callsign
    trails_by_callsign: dict[str, list[tuple[float, float, str]]] = {}
    for row in trail_query:
        callsign = row.from_call
        if callsign not in trails_by_callsign:
            trails_by_callsign[callsign] = []
        trails_by_callsign[callsign].append(
            (
                row.longitude,
                row.latitude,
                row.received_at.isoformat() if row.received_at else None,
            )
        )

    # Build result with latest position and trail
    result = []
    for packet in latest_packets:
        country_info = get_country_from_callsign(packet.from_call)
        trail = trails_by_callsign.get(packet.from_call, [])

        result.append(
            {
                'callsign': packet.from_call,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'packet_type': packet.packet_type,
                'symbol': packet.symbol,
                'symbol_table': packet.symbol_table,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'last_seen': packet.received_at.isoformat()
                if packet.received_at
                else None,
                'country_code': country_info[0] if country_info else None,
                'trail': trail
                if len(trail) > 1
                else [],  # Only include if multiple points
            }
        )

    return result
