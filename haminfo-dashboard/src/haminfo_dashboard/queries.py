# haminfo_dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional
import time

from sqlalchemy import func, distinct

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo_dashboard.utils import get_country_from_callsign

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Simple time-based cache for expensive queries
_stats_cache: dict[str, Any] = {}
_stats_cache_time: float = 0
_countries_cache: list[dict[str, Any]] = []
_countries_cache_time: float = 0
_top_stations_cache: list[dict[str, Any]] = []
_top_stations_cache_time: float = 0
_hourly_cache: dict[str, list] = {}
_hourly_cache_time: float = 0

CACHE_TTL = 30  # seconds


def get_dashboard_stats(session: Session) -> dict[str, Any]:
    """Get summary statistics for dashboard.

    Results are cached for 30 seconds.

    Args:
        session: Database session.

    Returns:
        Dict with total_packets_24h, unique_stations, countries, weather_stations.
    """
    global _stats_cache, _stats_cache_time

    # Return cached result if fresh
    if _stats_cache and (time.time() - _stats_cache_time) < CACHE_TTL:
        return _stats_cache

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

    # Count unique countries - use substring matching on callsign prefixes
    # This is an approximation but much faster than fetching all callsigns
    # We count distinct first characters as a proxy for country diversity
    countries = (
        session.query(func.count(distinct(func.substring(APRSPacket.from_call, 1, 2))))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    # Count weather stations
    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0

    result = {
        'total_packets_24h': total_packets,
        'unique_stations': unique_stations,
        'countries': countries,
        'weather_stations': weather_stations,
    }

    # Update cache
    _stats_cache = result
    _stats_cache_time = time.time()

    return result


def get_top_stations(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get top stations by packet count in the last 24 hours.

    Results are cached for 30 seconds.

    Args:
        session: Database session.
        limit: Maximum number of stations to return.

    Returns:
        List of dicts with callsign, count, and country info.
    """
    global _top_stations_cache, _top_stations_cache_time

    # Return cached result if fresh
    if _top_stations_cache and (time.time() - _top_stations_cache_time) < CACHE_TTL:
        return _top_stations_cache[:limit]

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

    # Update cache
    _top_stations_cache = stations
    _top_stations_cache_time = time.time()

    return stations


def get_country_breakdown(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get packet count breakdown by country.

    Results are cached for 30 seconds.

    Args:
        session: Database session.
        limit: Maximum number of countries to return.

    Returns:
        List of dicts with country_code, country_name, count.
    """
    global _countries_cache, _countries_cache_time

    # Return cached result if fresh
    if _countries_cache and (time.time() - _countries_cache_time) < CACHE_TTL:
        return _countries_cache[:limit]

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get counts grouped by first 1-2 characters of callsign (prefix)
    # This is done in DB for performance - we then map prefixes to countries
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

    # Update cache
    _countries_cache = result
    _countries_cache_time = time.time()

    return result[:limit]


# Import the prefix mapping for use in get_country_breakdown
from haminfo_dashboard.utils import CALLSIGN_PREFIXES


def get_hourly_distribution(session: Session) -> dict[str, list]:
    """Get packet count distribution by hour of day.

    Results are cached for 30 seconds.

    Args:
        session: Database session.

    Returns:
        Dict with 'labels' (hour strings) and 'values' (counts) arrays.
    """
    global _hourly_cache, _hourly_cache_time

    # Return cached result if fresh
    if _hourly_cache and (time.time() - _hourly_cache_time) < CACHE_TTL:
        return _hourly_cache

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get dialect to use appropriate function
    dialect = session.bind.dialect.name if session.bind else 'postgresql'

    if dialect == 'sqlite':
        # SQLite: use strftime to get hour as string
        hour_expr = func.strftime('%H', APRSPacket.received_at)
    else:
        # PostgreSQL: extract hour from timestamp
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

    # Create dict from results - handle both string (SQLite) and int (PostgreSQL) hours
    hour_map = {}
    for hour, count in hourly_counts:
        if hour is not None:
            hour_map[int(hour)] = count

    # Build complete 24-hour arrays
    labels = [f'{h:02d}:00' for h in range(24)]
    values = [hour_map.get(h, 0) for h in range(24)]

    result = {
        'labels': labels,
        'values': values,
    }

    # Update cache
    _hourly_cache = result
    _hourly_cache_time = time.time()

    return result


def get_recent_packets(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    callsign: Optional[str] = None,
    country: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get recent packets with optional filters.

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

    # Country filtering would require post-filtering since it's derived from callsign
    # For now, we'll handle it in Python if needed
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
                'packet_type': packet.packet_type,
                'received_at': packet.received_at.isoformat()
                if packet.received_at
                else None,
                'latitude': packet.latitude,
                'longitude': packet.longitude,
                'speed': packet.speed,
                'course': packet.course,
                'altitude': packet.altitude,
                'comment': packet.comment,
                'country_code': country_info[0] if country_info else None,
                'country_name': country_info[1] if country_info else None,
            }
        )

        if len(result) >= limit:
            break

    return result


def get_weather_stations(
    session: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get weather stations with their latest reports.

    Args:
        session: Database session.
        limit: Maximum number of stations to return.
        offset: Number of stations to skip.

    Returns:
        List of weather station dicts with latest report data.
    """
    stations = (
        session.query(WeatherStation)
        .order_by(WeatherStation.callsign)
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for station in stations:
        # Get latest report for this station
        latest_report = (
            session.query(WeatherReport)
            .filter(WeatherReport.weather_station_id == station.id)
            .order_by(WeatherReport.time.desc())
            .first()
        )

        country_info = get_country_from_callsign(station.callsign)

        station_dict = {
            'id': station.id,
            'callsign': station.callsign,
            'latitude': station.latitude,
            'longitude': station.longitude,
            'comment': station.comment,
            'country_code': country_info[0] if country_info else None,
            'country_name': country_info[1] if country_info else None,
        }

        if latest_report:
            station_dict['latest_report'] = {
                'time': latest_report.time.isoformat() if latest_report.time else None,
                'temperature': latest_report.temperature,
                'humidity': latest_report.humidity,
                'pressure': latest_report.pressure,
                'wind_speed': latest_report.wind_speed,
                'wind_direction': latest_report.wind_direction,
            }
        else:
            station_dict['latest_report'] = None

        result.append(station_dict)

    return result


def get_station_detail(session: Session, callsign: str) -> Optional[dict[str, Any]]:
    """Get detailed information about a station.

    Args:
        session: Database session.
        callsign: Station callsign.

    Returns:
        Dict with station details or None if not found.
    """
    # Get latest packet from this callsign
    latest_packet = (
        session.query(APRSPacket)
        .filter(APRSPacket.from_call == callsign.upper())
        .order_by(APRSPacket.received_at.desc())
        .first()
    )

    if not latest_packet:
        return None

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get packet count in last 24h
    packet_count = (
        session.query(func.count(APRSPacket.from_call))
        .filter(
            APRSPacket.from_call == callsign.upper(),
            APRSPacket.received_at >= last_24h,
        )
        .scalar()
        or 0
    )

    # Get packet type breakdown
    type_counts = (
        session.query(
            APRSPacket.packet_type,
            func.count(APRSPacket.packet_type).label('count'),
        )
        .filter(
            APRSPacket.from_call == callsign.upper(),
            APRSPacket.received_at >= last_24h,
        )
        .group_by(APRSPacket.packet_type)
        .all()
    )
    packet_types = {ptype or 'unknown': count for ptype, count in type_counts}

    country_info = get_country_from_callsign(callsign)

    return {
        'callsign': latest_packet.from_call,
        'last_seen': latest_packet.received_at.isoformat()
        if latest_packet.received_at
        else None,
        'latitude': latest_packet.latitude,
        'longitude': latest_packet.longitude,
        'altitude': latest_packet.altitude,
        'speed': latest_packet.speed,
        'course': latest_packet.course,
        'symbol': latest_packet.symbol,
        'symbol_table': latest_packet.symbol_table,
        'comment': latest_packet.comment,
        'packet_count_24h': packet_count,
        'packet_types': packet_types,
        'country_code': country_info[0] if country_info else None,
        'country_name': country_info[1] if country_info else None,
    }


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

    # Subquery to get latest packet per callsign
    latest_subq = (
        session.query(
            APRSPacket.from_call,
            func.max(APRSPacket.received_at).label('max_received'),
        )
        .filter(
            APRSPacket.received_at >= last_24h,
            APRSPacket.latitude.isnot(None),
            APRSPacket.longitude.isnot(None),
        )
        .group_by(APRSPacket.from_call)
        .subquery()
    )

    query = session.query(APRSPacket).join(
        latest_subq,
        (APRSPacket.from_call == latest_subq.c.from_call)
        & (APRSPacket.received_at == latest_subq.c.max_received),
    )

    # Apply bbox filter if provided
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        query = query.filter(
            APRSPacket.longitude >= min_lon,
            APRSPacket.longitude <= max_lon,
            APRSPacket.latitude >= min_lat,
            APRSPacket.latitude <= max_lat,
        )

    # Apply type filter if provided
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
