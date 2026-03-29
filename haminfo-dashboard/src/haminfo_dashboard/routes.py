# haminfo_dashboard/routes.py
"""Dashboard page routes."""

from flask import render_template, request, redirect, url_for, Blueprint

from haminfo.db.db import setup_session
from haminfo_dashboard.queries import (
    get_dashboard_stats,
    get_hourly_distribution,
    get_top_stations,
    get_country_breakdown,
)

dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static',
)


def _get_session():
    """Get a database session."""
    session_factory = setup_session()
    return session_factory()


@dashboard_bp.app_template_filter('format_number')
def format_number(value):
    """Format number with thousand separators."""
    try:
        return '{:,}'.format(int(value))
    except (ValueError, TypeError):
        return value


@dashboard_bp.route('/')
def index():
    """Main dashboard page with pre-loaded cached stats."""
    session = _get_session()
    try:
        # Pre-load all data from cache for instant display
        stats = get_dashboard_stats(session)
        hourly = get_hourly_distribution(session)
        top_stations = get_top_stations(session, limit=10)
        countries = get_country_breakdown(session, limit=10)
        return render_template(
            'dashboard/index.html',
            stats=stats,
            hourly=hourly,
            top_stations=top_stations,
            countries=countries,
        )
    finally:
        session.close()


@dashboard_bp.route('/weather')
def weather():
    """Weather stations page."""
    return render_template('dashboard/weather.html')


@dashboard_bp.route('/map')
def map_view():
    """Station map page."""
    return render_template('dashboard/map.html')


@dashboard_bp.route('/station/<callsign>')
def station(callsign: str):
    """Station lookup page."""
    # Handle search redirect
    search_query = request.args.get('q')
    if search_query:
        return redirect(url_for('dashboard.station', callsign=search_query))

    return render_template('dashboard/station.html', callsign=callsign)
