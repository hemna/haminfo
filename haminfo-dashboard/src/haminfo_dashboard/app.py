# haminfo_dashboard/app.py
"""Flask application factory for dashboard."""

from __future__ import annotations

import os
import sys
from flask import Flask

from haminfo_dashboard.routes import dashboard_bp
from haminfo_dashboard import api  # noqa: F401 - Import to register API routes on blueprint
from haminfo_dashboard.websocket import init_socketio
from haminfo_dashboard import cache
from haminfo_dashboard.utils import get_packet_human_info, get_packet_addressee


def create_app(config_file: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_file: Path to haminfo config file for database connection.

    Returns:
        Configured Flask application.
    """
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )

    # Basic Flask config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # Load haminfo config for database if provided
    if config_file:
        _load_haminfo_config(config_file)
        _init_cache()
        _warm_cache()

    # Register blueprint at root (dashboard is the main app)
    app.register_blueprint(dashboard_bp)

    # Register template globals
    app.jinja_env.globals['get_packet_human_info'] = get_packet_human_info
    app.jinja_env.globals['get_packet_addressee'] = get_packet_addressee

    # Initialize SocketIO
    init_socketio(app)

    return app


def _load_haminfo_config(config_file: str) -> None:
    """Load haminfo oslo.config configuration.

    This sets up the database connection string used by haminfo.db.
    Opts are registered at module import time in haminfo.db.db.

    Args:
        config_file: Path to haminfo config file.
    """
    from oslo_config import cfg

    # Import db module to trigger opt registration at module level
    from haminfo.db import db  # noqa: F401

    CONF = cfg.CONF

    # Load config file (opts already registered by db module import)
    CONF(
        args=[],
        default_config_files=[config_file],
    )


def _init_cache() -> None:
    """Initialize memcached connection using config."""
    from oslo_config import cfg

    CONF = cfg.CONF

    memcached_url = getattr(CONF.memcached, 'url', None)
    expire_time = getattr(CONF.memcached, 'expire_time', 300)

    cache.init_cache(memcached_url, ttl=expire_time)


def _warm_cache() -> None:
    """Pre-populate cache with expensive queries on startup.

    This ensures the home page loads quickly on first request.
    """
    from haminfo.db.db import setup_session
    from haminfo_dashboard.queries import (
        get_dashboard_stats,
        get_top_stations,
        get_country_breakdown,
        get_hourly_distribution,
    )

    print('Warming cache with dashboard stats...', file=sys.stderr, flush=True)

    try:
        session_factory = setup_session()
        session = session_factory()

        # Pre-cache the main dashboard queries
        get_dashboard_stats(session)
        print('  - Dashboard stats cached', file=sys.stderr, flush=True)

        get_top_stations(session, limit=10)
        print('  - Top stations cached', file=sys.stderr, flush=True)

        get_country_breakdown(session, limit=10)
        print('  - Country breakdown cached', file=sys.stderr, flush=True)

        get_hourly_distribution(session)
        print('  - Hourly distribution cached', file=sys.stderr, flush=True)

        session.close()
        print('Cache warming complete', file=sys.stderr, flush=True)
    except Exception as e:
        print(f'Cache warming failed: {e}', file=sys.stderr, flush=True)
        import traceback

        traceback.print_exc()
