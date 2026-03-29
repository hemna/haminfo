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
        has_recent_data = request.args.get('has_recent_data', '').lower() in ('true', '1', 'yes')
        
        stations = get_weather_stations(
            session,
            limit=limit,
            offset=offset,
            country=country if country else None,
            state=state if state else None,
            has_recent_data=has_recent_data,
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
        has_recent_data = request.args.get('has_recent_data', '').lower() in ('true', '1', 'yes')
        
        stations = get_weather_stations(
            session,
            limit=limit,
            offset=offset,
            country=country if country else None,
            state=state if state else None,
            has_recent_data=has_recent_data,
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


# Map stations endpoint (GeoJSON)
@dashboard_bp.route('/api/dashboard/map/stations')
def api_map_stations():
    """Map stations - returns GeoJSON FeatureCollection."""
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

        station_type = request.args.get('type')
        limit = request.args.get('limit', 1000, type=int)

        stations = get_map_stations(
            session,
            bbox=bbox,
            station_type=station_type,
            limit=limit,
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
                        'last_seen': station.get('last_seen'),
                        'country_code': station.get('country_code'),
                    },
                }
                features.append(feature)

        geojson = {
            'type': 'FeatureCollection',
            'features': features,
        }
        return jsonify(geojson)
    finally:
        session.close()
