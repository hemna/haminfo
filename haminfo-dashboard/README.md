# haminfo-dashboard

APRS-IS Network Statistics Dashboard - a web interface for viewing real-time APRS packet statistics, weather reports, station locations, and network activity.

## Features

- **Live Dashboard**: Real-time packet counts, active stations, countries
- **Weather Page**: Weather station reports with temperature, wind, pressure data
- **Map View**: Leaflet-based map showing station locations
- **Station Lookup**: Search and view individual station details

## Installation

```bash
# Install with pip (from the haminfo monorepo)
pip install -e ./haminfo-dashboard

# Or with uv
uv pip install -e ./haminfo-dashboard
```

## Configuration

The dashboard uses the same configuration as haminfo. Set the database connection in your haminfo config file:

```ini
[database]
connection = postgresql://user:pass@localhost/haminfo
```

## Running

```bash
# Development
haminfo-dashboard --config /path/to/haminfo.conf

# Production (with gunicorn + gevent for WebSocket support)
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    -w 1 -b 0.0.0.0:5001 \
    "haminfo_dashboard.app:create_app()"
```

## Architecture

This is a separate deployable service that:
- Connects directly to the haminfo PostgreSQL database (read-only)
- Imports DB models from the `haminfo` package
- Runs independently from the haminfo API service

## Tech Stack

- Flask + Jinja2 templates
- HTMX for dynamic updates
- Flask-SocketIO for WebSocket live feed
- Chart.js for visualizations
- Leaflet for maps
- Dark theme UI
