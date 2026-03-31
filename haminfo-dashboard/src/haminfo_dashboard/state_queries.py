# haminfo_dashboard/state_queries.py
"""Database queries for state weather dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from haminfo_dashboard.cache import cached

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOG = logging.getLogger(__name__)


# Alert thresholds (from spec)
ALERT_THRESHOLDS = {
    'high_wind': {'wind_speed': 40, 'level': 'warning'},
    'extreme_wind': {'wind_speed': 60, 'wind_gust': 75, 'level': 'severe'},
    'extreme_heat': {'temperature': 100, 'level': 'warning'},
    'extreme_cold': {'temperature': 10, 'level': 'warning'},  # Below this
    'heavy_rain': {'rain_1h': 1.0, 'level': 'warning'},
}


@cached('state_stations:{state_code}', ttl=300)
def get_state_stations(session: Session, state_code: str) -> list[dict[str, Any]]:
    """Get all weather stations in a state with their latest readings.

    Args:
        session: Database session
        state_code: Two-letter state code (e.g., 'VA')

    Returns:
        List of station dicts with latest weather data
    """
    state_code = state_code.upper()

    query = text("""
        SELECT ws.callsign, ws.latitude, ws.longitude, ws.comment,
               ws.symbol, ws.symbol_table,
               wr.temperature, wr.humidity, wr.pressure,
               wr.wind_speed, wr.wind_gust, wr.wind_direction,
               wr.rain_1h, wr.time as last_report
        FROM weather_station ws
        JOIN LATERAL (
            SELECT * FROM weather_report 
            WHERE weather_station_id = ws.id 
            ORDER BY time DESC LIMIT 1
        ) wr ON true
        WHERE ws.state = :state_code 
          AND ws.country_code = 'US'
    """)

    result = session.execute(query, {'state_code': state_code})
    return [dict(row) for row in result.mappings().all()]


def compute_state_aggregates(stations: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics from station list.

    Args:
        stations: List of station dicts with weather readings

    Returns:
        Dict with avg/min/max for temp, humidity, pressure, wind
    """
    if not stations:
        return {
            'station_count': 0,
            'avg_temp': None,
            'min_temp': None,
            'max_temp': None,
            'avg_humidity': None,
            'min_humidity': None,
            'max_humidity': None,
            'avg_pressure': None,
            'min_pressure': None,
            'max_pressure': None,
            'avg_wind': None,
            'max_wind': None,
        }

    def safe_values(key: str) -> list[float]:
        """Extract non-None values for a key."""
        return [s[key] for s in stations if s.get(key) is not None]

    def safe_avg(values: list[float]) -> float | None:
        """Compute average, returning None if empty."""
        return sum(values) / len(values) if values else None

    temps = safe_values('temperature')
    humidities = safe_values('humidity')
    pressures = safe_values('pressure')
    winds = safe_values('wind_speed')
    gusts = safe_values('wind_gust')

    return {
        'station_count': len(stations),
        'avg_temp': safe_avg(temps),
        'min_temp': min(temps) if temps else None,
        'max_temp': max(temps) if temps else None,
        'avg_humidity': safe_avg(humidities),
        'min_humidity': min(humidities) if humidities else None,
        'max_humidity': max(humidities) if humidities else None,
        'avg_pressure': safe_avg(pressures),
        'min_pressure': min(pressures) if pressures else None,
        'max_pressure': max(pressures) if pressures else None,
        'avg_wind': safe_avg(winds),
        'max_wind': max(gusts) if gusts else (max(winds) if winds else None),
    }


@cached('state_trends:{state_code}', ttl=300)
def get_state_trends(session: Session, state_code: str) -> dict[str, Any]:
    """Get 24-hour trend data for a state.

    Returns hourly aggregates for temperature, pressure, humidity, wind.
    Uses TimescaleDB time_bucket for efficient bucketing.

    Args:
        session: Database session
        state_code: Two-letter state code

    Returns:
        Dict with labels and data arrays for Chart.js
    """
    state_code = state_code.upper()

    query = text("""
        SELECT 
            time_bucket('1 hour', wr.time) as hour,
            AVG(wr.temperature) as avg_temp,
            MIN(wr.temperature) as min_temp,
            MAX(wr.temperature) as max_temp,
            AVG(wr.pressure) as avg_pressure,
            AVG(wr.humidity) as avg_humidity,
            AVG(wr.wind_speed) as avg_wind
        FROM weather_report wr
        JOIN weather_station ws ON wr.weather_station_id = ws.id
        WHERE ws.state = :state_code 
          AND ws.country_code = 'US'
          AND wr.time > NOW() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY hour
    """)

    result = session.execute(query, {'state_code': state_code})
    rows = [dict(row) for row in result.mappings().all()]

    # Format for Chart.js
    labels = [row['hour'].strftime('%H:%M') for row in rows]

    return {
        'labels': labels,
        'temperature': {
            'avg': [row['avg_temp'] for row in rows],
            'min': [row['min_temp'] for row in rows],
            'max': [row['max_temp'] for row in rows],
        },
        'pressure': {
            'avg': [row['avg_pressure'] for row in rows],
        },
        'humidity': {
            'avg': [row['avg_humidity'] for row in rows],
        },
        'wind': {
            'avg': [row['avg_wind'] for row in rows],
        },
    }


def detect_state_alerts(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect severe weather alerts from station data.

    Checks individual station thresholds. Regional patterns (multiple
    stations) are handled separately if needed.

    Args:
        stations: List of station dicts with weather readings

    Returns:
        List of alert dicts with type, level, message, affected_stations
    """
    if not stations:
        return []

    alerts = []

    # Track affected stations by alert type
    high_wind_stations = []
    extreme_wind_stations = []
    extreme_heat_stations = []
    extreme_cold_stations = []
    heavy_rain_stations = []

    for station in stations:
        callsign = station.get('callsign', 'Unknown')
        wind_speed = station.get('wind_speed') or 0
        wind_gust = station.get('wind_gust') or 0
        temp = station.get('temperature')
        rain_1h = station.get('rain_1h') or 0

        # Extreme wind (supersedes high wind)
        if wind_speed > 60 or wind_gust > 75:
            extreme_wind_stations.append(callsign)
        elif wind_speed > 40:
            high_wind_stations.append(callsign)

        # Temperature extremes
        if temp is not None:
            if temp > 100:
                extreme_heat_stations.append(callsign)
            elif temp < 10:
                extreme_cold_stations.append(callsign)

        # Heavy rain
        if rain_1h > 1.0:
            heavy_rain_stations.append(callsign)

    # Build alert list (severe first)
    if extreme_wind_stations:
        alerts.append(
            {
                'type': 'extreme_wind',
                'level': 'severe',
                'message': f'Extreme wind: {len(extreme_wind_stations)} station(s) reporting >60mph sustained or >75mph gusts',
                'affected_stations': extreme_wind_stations,
            }
        )

    if high_wind_stations:
        alerts.append(
            {
                'type': 'high_wind',
                'level': 'warning',
                'message': f'High wind warning: {len(high_wind_stations)} station(s) reporting >40mph sustained',
                'affected_stations': high_wind_stations,
            }
        )

    if extreme_heat_stations:
        alerts.append(
            {
                'type': 'extreme_heat',
                'level': 'warning',
                'message': f'Extreme heat: {len(extreme_heat_stations)} station(s) reporting >100°F',
                'affected_stations': extreme_heat_stations,
            }
        )

    if extreme_cold_stations:
        alerts.append(
            {
                'type': 'extreme_cold',
                'level': 'warning',
                'message': f'Extreme cold: {len(extreme_cold_stations)} station(s) reporting <10°F',
                'affected_stations': extreme_cold_stations,
            }
        )

    if heavy_rain_stations:
        alerts.append(
            {
                'type': 'heavy_rain',
                'level': 'warning',
                'message': f'Heavy rain: {len(heavy_rain_stations)} station(s) reporting >1" in 1 hour',
                'affected_stations': heavy_rain_stations,
            }
        )

    return alerts
