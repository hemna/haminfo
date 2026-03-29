# haminfo_dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, distinct

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo_dashboard.utils import (
    get_country_from_callsign,
    get_country_from_coords,
    CALLSIGN_PREFIXES,
    get_state_from_coords,
)
from haminfo_dashboard.cache import cached

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@cached('dashboard:stats', ttl=300)
def get_dashboard_stats(session: Session) -> dict[str, Any]:
    """Get summary statistics for dashboard.

    Args:
        session: Database session.

    Returns:
        Dict with total_packets_24h, unique_stations, countries, weather_stations.
    """
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
    countries = (
        session.query(func.count(distinct(func.substring(APRSPacket.from_call, 1, 2))))
        .filter(APRSPacket.received_at >= last_24h)
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

    if not latest_packet:
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
        'packets_24h': packets_24h,
        'packets_7d': packets_7d,
        'packets_total': packets_total,
        'first_seen': first_seen,
        'packet_types': packet_types,
        'country_code': country_info[0] if country_info else None,
        'country_name': country_info[1] if country_info else None,
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
    station = (
        session.query(WeatherStation)
        .filter(WeatherStation.callsign == callsign.upper())
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
                'temperature': report.temperature,
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
