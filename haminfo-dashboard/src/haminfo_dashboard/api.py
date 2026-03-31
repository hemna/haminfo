# haminfo_dashboard/api.py
"""Dashboard JSON API endpoints."""

from __future__ import annotations

from flask import jsonify, request, render_template

from haminfo.db.db import setup_session
from haminfo_dashboard.routes import dashboard_bp
from haminfo_dashboard.utils import get_states_for_country
from haminfo_dashboard.queries import (
    get_dashboard_stats,
    get_top_stations,
    get_country_breakdown,
    get_hourly_distribution,
    get_recent_packets,
    get_weather_stations,
    get_weather_countries,
    get_station_detail,
    get_map_stations,
    get_station_weather_reports,
)
from haminfo_dashboard.state_queries import (
    get_state_stations,
    compute_state_aggregates,
    get_state_trends,
    detect_state_alerts,
)


def _get_session():
    """Get a database session."""
    session_factory = setup_session()
    return session_factory()


# Stats endpoints
@dashboard_bp.route('/api/dashboard/stats')
def api_stats():
    """Dashboard statistics - returns HTMX partial."""
    session = _get_session()
    try:
        stats = get_dashboard_stats(session)
        return render_template('dashboard/partials/stats_cards.html', stats=stats)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/stats/json')
def api_stats_json():
    """Dashboard statistics - returns JSON."""
    session = _get_session()
    try:
        stats = get_dashboard_stats(session)
        return jsonify(stats)
    finally:
        session.close()


# Top stations endpoints
@dashboard_bp.route('/api/dashboard/top-stations')
def api_top_stations():
    """Top stations by packet count - returns HTMX partial."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        stations = get_top_stations(session, limit=limit)
        return render_template(
            'dashboard/partials/top_stations.html', stations=stations
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/top-stations/json')
def api_top_stations_json():
    """Top stations by packet count - returns JSON."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        stations = get_top_stations(session, limit=limit)
        return jsonify(stations)
    finally:
        session.close()


# Country breakdown endpoints
@dashboard_bp.route('/api/dashboard/countries')
def api_countries():
    """Country breakdown - returns HTMX partial."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        countries = get_country_breakdown(session, limit=limit)
        return render_template('dashboard/partials/countries.html', countries=countries)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/countries/json')
def api_countries_json():
    """Country breakdown - returns JSON."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        countries = get_country_breakdown(session, limit=limit)
        return jsonify(countries)
    finally:
        session.close()


# Hourly distribution endpoint (JSON only for charts)
@dashboard_bp.route('/api/dashboard/hourly')
def api_hourly():
    """Hourly packet distribution - returns JSON for chart."""
    session = _get_session()
    try:
        distribution = get_hourly_distribution(session)
        return jsonify(distribution)
    finally:
        session.close()


# Recent packets endpoint
@dashboard_bp.route('/api/dashboard/packets')
def api_packets():
    """Recent packets - returns JSON."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        callsign = request.args.get('callsign')
        country = request.args.get('country')
        packets = get_recent_packets(
            session,
            limit=limit,
            offset=offset,
            callsign=callsign,
            country=country,
        )
        return jsonify(packets)
    finally:
        session.close()


# Weather stations endpoints
@dashboard_bp.route('/api/dashboard/weather/stations')
def api_weather_stations():
    """Weather stations - returns HTMX partial."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        country = request.args.get('country')
        state = request.args.get('state')
        search = request.args.get('search')
        has_recent_data = request.args.get('has_recent_data', '').lower() in (
            'true',
            '1',
            'yes',
        )

        stations = get_weather_stations(
            session,
            limit=limit,
            offset=offset,
            country=country if country else None,
            state=state if state else None,
            has_recent_data=has_recent_data,
            search=search if search else None,
        )
        return render_template(
            'dashboard/partials/weather_grid.html', stations=stations
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/weather/stations/json')
def api_weather_stations_json():
    """Weather stations - returns JSON."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        country = request.args.get('country')
        state = request.args.get('state')
        search = request.args.get('search')
        has_recent_data = request.args.get('has_recent_data', '').lower() in (
            'true',
            '1',
            'yes',
        )

        stations = get_weather_stations(
            session,
            limit=limit,
            offset=offset,
            country=country if country else None,
            state=state if state else None,
            has_recent_data=has_recent_data,
            search=search if search else None,
        )
        return jsonify(stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/weather/states/<country>')
def api_weather_states(country: str):
    """Get list of states/provinces for a country - returns JSON.

    Only supports US, CA, AU countries.
    """
    states = get_states_for_country(country.upper())
    return jsonify([{'code': code, 'name': name} for code, name in states])


@dashboard_bp.route('/api/dashboard/weather/countries')
def api_weather_countries():
    """Get list of countries with weather stations - returns JSON."""
    session = _get_session()
    try:
        countries = get_weather_countries(session)
        return jsonify(countries)
    finally:
        session.close()


# Station detail endpoints
@dashboard_bp.route('/api/dashboard/station/<callsign>')
def api_station_detail(callsign: str):
    """Station detail - returns HTMX partial."""
    session = _get_session()
    try:
        station = get_station_detail(session, callsign)
        if not station:
            return render_template(
                'dashboard/partials/station_not_found.html', callsign=callsign
            ), 404
        return render_template(
            'dashboard/partials/station_detail.html', station=station
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/station/<callsign>/json')
def api_station_detail_json(callsign: str):
    """Station detail - returns JSON."""
    session = _get_session()
    try:
        station = get_station_detail(session, callsign)
        if not station:
            return jsonify({'error': 'Station not found', 'callsign': callsign}), 404
        return jsonify(station)
    finally:
        session.close()


# Station packets endpoint (HTMX partial)
@dashboard_bp.route('/api/dashboard/station/<callsign>/packets')
def api_station_packets(callsign: str):
    """Station packets - returns HTMX partial."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        packets = get_recent_packets(
            session, limit=limit, offset=offset, callsign=callsign
        )
        return render_template(
            'dashboard/partials/packets_table.html', packets=packets, callsign=callsign
        )
    finally:
        session.close()


# Station weather reports endpoints
@dashboard_bp.route('/api/dashboard/station/<callsign>/weather')
def api_station_weather(callsign: str):
    """Station weather reports - returns HTMX partial."""
    session = _get_session()
    try:
        # Default to 50 for better graph visualization
        limit = request.args.get('limit', 50, type=int)
        weather_data = get_station_weather_reports(session, callsign, limit=limit)
        if not weather_data:
            return '', 204  # No content - not a weather station
        return render_template(
            'dashboard/partials/weather_reports_table.html', weather_data=weather_data
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/station/<callsign>/weather/json')
def api_station_weather_json(callsign: str):
    """Station weather reports - returns JSON."""
    session = _get_session()
    try:
        limit = request.args.get('limit', 20, type=int)
        weather_data = get_station_weather_reports(session, callsign, limit=limit)
        if not weather_data:
            return jsonify(
                {'error': 'Not a weather station', 'callsign': callsign}
            ), 404
        return jsonify(weather_data)
    finally:
        session.close()


# Map stations endpoint (GeoJSON)
@dashboard_bp.route('/api/dashboard/map/stations')
def api_map_stations():
    """Map stations - returns GeoJSON FeatureCollection.

    Uses tile-based caching when bbox is provided for better performance.
    Falls back to fast query when no bbox is provided.

    Supports two modes:
    - fast=true (default): Quick load without trails
    - fast=false: Full load with trails (slower but complete)
    """
    from haminfo_dashboard.queries import (
        get_map_stations_fast,
        get_map_stations_tiled,
        get_map_stations_with_trails,
    )

    session = _get_session()
    try:
        # Parse bbox parameter (min_lon,min_lat,max_lon,max_lat)
        bbox_str = request.args.get('bbox')
        bbox = None
        if bbox_str:
            try:
                parts = [float(x) for x in bbox_str.split(',')]
                if len(parts) == 4:
                    bbox = tuple(parts)
            except ValueError:
                pass

        station_type = request.args.get('type', '')
        limit = request.args.get('limit', 500, type=int)
        offset = request.args.get('offset', 0, type=int)
        hours = request.args.get('hours', 24, type=int)
        # Fast mode: skip trails for quick initial load
        fast_mode = request.args.get('fast', 'true').lower() == 'true'

        # Clamp hours to valid range
        if hours not in (1, 2, 6, 24):
            hours = 24

        # Clamp limit to reasonable range
        limit = min(max(limit, 100), 2000)

        # Use tile-based caching when bbox is provided (most common case)
        if bbox and fast_mode:
            stations = get_map_stations_tiled(
                session,
                bbox=bbox,
                hours=hours,
                station_type=station_type,
                limit=limit,
            )
        elif fast_mode:
            # No bbox - use fast query without caching
            stations = get_map_stations_fast(
                session,
                bbox=bbox,
                station_type=station_type,
                hours=hours,
                limit=limit,
            )
        else:
            # Full query with trails (slower)
            stations = get_map_stations_with_trails(
                session,
                bbox=bbox,
                station_type=station_type,
                hours=hours,
                limit=limit,
                offset=offset,
            )

        # Convert to GeoJSON FeatureCollection
        features = []
        for station in stations:
            if station.get('latitude') and station.get('longitude'):
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [station['longitude'], station['latitude']],
                    },
                    'properties': {
                        'callsign': station['callsign'],
                        'packet_type': station.get('packet_type'),
                        'symbol': station.get('symbol'),
                        'symbol_table': station.get('symbol_table'),
                        'speed': station.get('speed'),
                        'course': station.get('course'),
                        'altitude': station.get('altitude'),
                        'comment': station.get('comment'),
                        'last_seen': station.get('last_seen')
                        or station.get('received_at'),
                        'country_code': station.get('country_code'),
                        'trail': station.get('trail', []),
                    },
                }
                features.append(feature)

        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'mode': 'fast' if fast_mode else 'full',
        }

        return jsonify(geojson)
    finally:
        session.close()


# State weather dashboard endpoints


@dashboard_bp.route('/api/dashboard/state/<state_code>/summary')
def api_state_summary(state_code: str):
    """State summary cards - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        summary = compute_state_aggregates(stations)
        return render_template(
            'dashboard/partials/state_summary.html',
            summary=summary,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/summary/json')
def api_state_summary_json(state_code: str):
    """State summary - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        summary = compute_state_aggregates(stations)
        return jsonify(summary)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/stations')
def api_state_stations(state_code: str):
    """State stations list - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        return render_template(
            'dashboard/partials/state_stations_table.html',
            stations=stations,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/stations/json')
def api_state_stations_json(state_code: str):
    """State stations - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        return jsonify(stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/alerts')
def api_state_alerts(state_code: str):
    """State alerts banner - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        alerts = detect_state_alerts(stations)
        return render_template(
            'dashboard/partials/state_alerts.html',
            alerts=alerts,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/alerts/json')
def api_state_alerts_json(state_code: str):
    """State alerts - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        alerts = detect_state_alerts(stations)
        return jsonify(alerts)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/trends')
def api_state_trends(state_code: str):
    """State 24h trend data - returns JSON for Chart.js."""
    session = _get_session()
    try:
        trends = get_state_trends(session, state_code)
        return jsonify(trends)
    finally:
        session.close()
