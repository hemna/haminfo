# haminfo_dashboard/routes.py
"""Dashboard page routes."""

from flask import render_template, request, redirect, url_for, Blueprint

dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static',
)


@dashboard_bp.app_template_filter('format_number')
def format_number(value):
    """Format number with thousand separators."""
    try:
        return '{:,}'.format(int(value))
    except (ValueError, TypeError):
        return value


@dashboard_bp.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard/index.html')


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
