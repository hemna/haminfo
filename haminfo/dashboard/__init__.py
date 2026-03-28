"""APRS Dashboard blueprint."""

from flask import Blueprint

dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='../templates/dashboard',
    static_folder='../static',
    static_url_path='/static',
)


@dashboard_bp.app_template_filter('format_number')
def format_number(value):
    """Format number with thousand separators."""
    try:
        return '{:,}'.format(int(value))
    except (ValueError, TypeError):
        return value


from haminfo.dashboard import routes  # noqa: F401, E402
from haminfo.dashboard import api  # noqa: F401, E402
