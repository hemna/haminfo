# haminfo_dashboard/app.py
"""Flask application factory for dashboard."""

from __future__ import annotations

import os
from flask import Flask

from haminfo_dashboard.routes import dashboard_bp
from haminfo_dashboard.websocket import init_socketio


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

    # Register blueprint at root (dashboard is the main app)
    app.register_blueprint(dashboard_bp)

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
