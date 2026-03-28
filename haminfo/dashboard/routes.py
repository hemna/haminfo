# haminfo/dashboard/routes.py
"""Dashboard page routes."""

from flask import render_template, request, redirect, url_for
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
    # Handle search redirect
    search_query = request.args.get('q')
    if search_query:
        return redirect(url_for('dashboard.station', callsign=search_query))

    return render_template('station.html', callsign=callsign)
