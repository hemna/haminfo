# haminfo/dashboard/api.py
"""Dashboard JSON API endpoints."""

from flask import jsonify
from haminfo.dashboard import dashboard_bp


@dashboard_bp.route('/api/dashboard/stats')
def api_stats():
    """Dashboard statistics."""
    return jsonify(
        {
            'total_packets_24h': 0,
            'unique_stations': 0,
            'countries': 0,
            'weather_stations': 0,
        }
    )
