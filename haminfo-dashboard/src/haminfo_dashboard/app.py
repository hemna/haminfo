# haminfo_dashboard/app.py
"""Flask application factory for dashboard."""

from __future__ import annotations

import os
import sys
import threading
from flask import Flask, render_template_string, redirect, url_for, jsonify

from haminfo_dashboard.routes import dashboard_bp
from haminfo_dashboard import api  # noqa: F401 - Import to register API routes on blueprint
from haminfo_dashboard.websocket import init_socketio
from haminfo_dashboard import cache
from haminfo_dashboard.utils import get_packet_human_info, get_packet_addressee


# Global startup state
class StartupState:
    """Track application startup progress."""

    def __init__(self):
        self.ready = False
        self.status = 'Initializing...'
        self.progress = 0
        self.total_steps = 5

    def update(self, status: str, step: int):
        self.status = status
        self.progress = int((step / self.total_steps) * 100)

    def set_ready(self):
        self.ready = True
        self.status = 'Ready'
        self.progress = 100


startup_state = StartupState()


# Loading page template
LOADING_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loading - Ham Radio Dashboard</title>
    <style>
        :root {
            --bg-dark: #0a0f1a;
            --bg-card: #111827;
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --accent-green: #10b981;
            --accent-cyan: #22d3ee;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: var(--bg-dark);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .loading-container {
            text-align: center;
            padding: 40px;
        }
        
        .logo {
            font-size: 48px;
            margin-bottom: 20px;
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 16px;
            margin-bottom: 40px;
        }
        
        .progress-container {
            width: 300px;
            height: 8px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            margin: 0 auto 20px;
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-green), var(--accent-cyan));
            border-radius: 4px;
            transition: width 0.3s ease;
            width: {{ progress }}%;
        }
        
        .status {
            color: var(--accent-cyan);
            font-size: 14px;
            font-family: 'Monaco', 'Menlo', monospace;
        }
        
        .dots {
            display: inline-block;
            width: 20px;
            text-align: left;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .pulse {
            animation: pulse 1.5s ease-in-out infinite;
        }
    </style>
</head>
<body>
    <div class="loading-container">
        <div class="logo">📡</div>
        <h1>Ham Radio Dashboard</h1>
        <p class="subtitle">Loading the APRS network...</p>
        
        <div class="progress-container">
            <div class="progress-bar" id="progress"></div>
        </div>
        
        <p class="status">
            <span id="status" class="pulse">{{ status }}</span>
            <span class="dots" id="dots"></span>
        </p>
    </div>
    
    <script>
        // Animate dots
        var dots = '';
        setInterval(function() {
            dots = dots.length >= 3 ? '' : dots + '.';
            document.getElementById('dots').textContent = dots;
        }, 500);
        
        // Poll for ready status
        function checkReady() {
            fetch('/startup-status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    document.getElementById('progress').style.width = data.progress + '%';
                    document.getElementById('status').textContent = data.status;
                    
                    if (data.ready) {
                        window.location.href = '/';
                    } else {
                        setTimeout(checkReady, 500);
                    }
                })
                .catch(function() {
                    setTimeout(checkReady, 1000);
                });
        }
        
        // Start polling after initial render
        setTimeout(checkReady, 500);
    </script>
</body>
</html>
"""


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

    # Add startup status endpoint (always available)
    @app.route('/startup-status')
    def startup_status():
        return jsonify(
            {
                'ready': startup_state.ready,
                'status': startup_state.status,
                'progress': startup_state.progress,
            }
        )

    # Add loading page route
    @app.route('/loading')
    def loading_page():
        if startup_state.ready:
            return redirect('/')
        return render_template_string(
            LOADING_PAGE,
            status=startup_state.status,
            progress=startup_state.progress,
        )

    # Load haminfo config for database if provided
    if config_file:
        _load_haminfo_config(config_file)
        _init_cache()
        # Start cache warming in background thread
        warming_thread = threading.Thread(target=_warm_cache, daemon=True)
        warming_thread.start()

    # Register blueprint at root (dashboard is the main app)
    # Add middleware to redirect to loading page if not ready
    @app.before_request
    def check_startup():
        from flask import request

        # Allow these paths during startup
        allowed = ['/loading', '/startup-status', '/static/']
        if not startup_state.ready:
            for path in allowed:
                if request.path.startswith(path):
                    return None
            return redirect('/loading')
        return None

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

    This runs in a background thread so the app can serve the loading page.
    """
    from haminfo.db.db import setup_session
    from haminfo_dashboard.queries import (
        get_dashboard_stats,
        get_top_stations,
        get_country_breakdown,
        get_hourly_distribution,
    )
    from haminfo_dashboard.geo_cache import warm_cache as warm_geo_cache

    print('Warming cache with dashboard stats...', file=sys.stderr, flush=True)

    try:
        startup_state.update('Connecting to database...', 1)
        session_factory = setup_session()
        session = session_factory()

        # Pre-cache the main dashboard queries
        startup_state.update('Loading dashboard stats...', 2)
        get_dashboard_stats(session)
        print('  - Dashboard stats cached', file=sys.stderr, flush=True)

        startup_state.update('Loading top stations...', 3)
        get_top_stations(session, limit=10)
        print('  - Top stations cached', file=sys.stderr, flush=True)

        get_country_breakdown(session, limit=10)
        print('  - Country breakdown cached', file=sys.stderr, flush=True)

        startup_state.update('Loading hourly distribution...', 4)
        get_hourly_distribution(session)
        print('  - Hourly distribution cached', file=sys.stderr, flush=True)

        # Warm geo cache for reverse geocoding
        startup_state.update('Initializing reverse geocoder...', 5)
        try:
            geo_stats = warm_geo_cache(session, hours=24)
            print(
                f'  - Geo cache warmed: {geo_stats["populated"]} cells, '
                f'{geo_stats["errors"]} errors',
                file=sys.stderr,
                flush=True,
            )
        except Exception as e:
            print(f'  - Geo cache warm-up failed: {e}', file=sys.stderr, flush=True)

        session.close()
        print('Cache warming complete', file=sys.stderr, flush=True)

        # Mark as ready
        startup_state.set_ready()

    except Exception as e:
        print(f'Cache warming failed: {e}', file=sys.stderr, flush=True)
        import traceback

        traceback.print_exc()
        # Still mark as ready so app can try to function
        startup_state.set_ready()
