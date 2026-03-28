# haminfo/dashboard/routes.py
"""Dashboard page routes."""

from flask import render_template
from haminfo.dashboard import dashboard_bp


@dashboard_bp.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@dashboard_bp.route('/weather')
def weather():
    """Weather stations page."""
    return render_template('weather.html')


@dashboard_bp.route('/map')
def map_view():
    """Station map page."""
    return render_template('map.html')


@dashboard_bp.route('/station/<callsign>')
def station(callsign: str):
    """Station lookup page."""
    return render_template('station.html', callsign=callsign)
