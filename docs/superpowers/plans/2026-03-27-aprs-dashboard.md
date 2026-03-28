# APRS Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time APRS statistics dashboard with live traffic feed, weather reports, station map, and callsign lookup.

**Architecture:** Extend existing Flask app with Jinja2 templates, HTMX for dynamic updates, Flask-SocketIO for WebSocket live feed, Chart.js for visualizations, and Leaflet for maps. All data served from existing PostgreSQL/PostGIS haminfo database.

**Tech Stack:** Flask, Jinja2, HTMX, Flask-SocketIO, Chart.js, Leaflet, PostgreSQL/PostGIS

**Spec:** `docs/superpowers/specs/2026-03-27-aprs-dashboard-design.md`

**Note:** API endpoints use `/api/dashboard/*` prefix (deviation from spec's `/api/*`) for cleaner namespacing with existing haminfo API routes.

---

## File Structure

```
haminfo/
  templates/
    dashboard/
      base.html              # Dark theme base with nav, HTMX, SocketIO
      index.html             # Main dashboard page
      weather.html           # Weather stations page
      map.html               # Interactive map page
      station.html           # Station lookup page
      partials/
        stats_cards.html     # Stats cards (HTMX partial)
        live_feed.html       # Live feed container
        hourly_chart.html    # Chart container
        top_stations.html    # Leaderboard (HTMX partial)
        countries.html       # Countries breakdown (HTMX partial)
        weather_grid.html    # Weather station cards (HTMX partial)
        station_detail.html  # Station info (HTMX partial)
        packets_table.html   # Packets table (HTMX partial)
  static/
    css/
      dashboard.css          # Dark theme styles
    js/
      dashboard.js           # WebSocket client, charts init
  dashboard/
    __init__.py              # Blueprint registration
    routes.py                # Page routes (/, /weather, /map, /station)
    api.py                   # JSON API endpoints
    websocket.py             # SocketIO event handlers
    queries.py               # Database query helpers
    utils.py                 # Callsign prefix lookup, formatting
tests/
  test_dashboard_api.py      # API endpoint tests
  test_dashboard_queries.py  # Query helper tests
  test_dashboard_utils.py    # Utility function tests
```

---

## Chunk 1: Foundation (Dependencies, Blueprint, Base Template)

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add flask-socketio and gevent to dependencies**

Open `pyproject.toml` and add to the `dependencies` array:

```toml
    "flask-socketio>=5.3.0",
    "python-socketio>=5.10.0",
    "gevent>=24.2.1",
    "gevent-websocket>=0.10.1",
```

- [ ] **Step 2: Install dependencies**

Run: `cd ~/devel/mine/hamradio/haminfo && uv sync`
Expected: Dependencies installed successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add flask-socketio and gevent for websocket support"
```

---

### Task 2: Create Dashboard Blueprint Structure

**Files:**
- Create: `haminfo/dashboard/__init__.py`
- Create: `haminfo/dashboard/routes.py`
- Create: `haminfo/dashboard/api.py`
- Create: `haminfo/dashboard/queries.py`
- Create: `haminfo/dashboard/utils.py`
- Create: `haminfo/dashboard/websocket.py`

- [ ] **Step 1: Create dashboard package init**

```python
# haminfo/dashboard/__init__.py
"""APRS Dashboard blueprint."""

from flask import Blueprint

dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='../templates/dashboard',
    static_folder='../static',
    static_url_path='/static'
)

from haminfo.dashboard import routes  # noqa: F401, E402
from haminfo.dashboard import api  # noqa: F401, E402
```

- [ ] **Step 2: Create routes placeholder**

```python
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
```

- [ ] **Step 3: Create API placeholder**

```python
# haminfo/dashboard/api.py
"""Dashboard JSON API endpoints."""

from flask import jsonify
from haminfo.dashboard import dashboard_bp


@dashboard_bp.route('/api/dashboard/stats')
def api_stats():
    """Dashboard statistics."""
    return jsonify({
        'total_packets_24h': 0,
        'unique_stations': 0,
        'countries': 0,
        'weather_stations': 0,
    })
```

- [ ] **Step 4: Create queries placeholder**

```python
# haminfo/dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_dashboard_stats(session: Session) -> dict:
    """Get summary statistics for dashboard."""
    return {
        'total_packets_24h': 0,
        'unique_stations': 0,
        'countries': 0,
        'weather_stations': 0,
    }
```

- [ ] **Step 5: Create utils placeholder**

```python
# haminfo/dashboard/utils.py
"""Utility functions for dashboard."""

from __future__ import annotations

# Callsign prefix to country mapping (common prefixes)
CALLSIGN_PREFIXES = {
    '9M': ('MY', 'Malaysia'),
    '9W': ('MY', 'Malaysia'),
    'VK': ('AU', 'Australia'),
    'ZL': ('NZ', 'New Zealand'),
    'JA': ('JP', 'Japan'),
    'JH': ('JP', 'Japan'),
    'JR': ('JP', 'Japan'),
    'HL': ('KR', 'South Korea'),
    'BV': ('TW', 'Taiwan'),
    'W': ('US', 'United States'),
    'K': ('US', 'United States'),
    'N': ('US', 'United States'),
    'AA': ('US', 'United States'),
    'AB': ('US', 'United States'),
    'AC': ('US', 'United States'),
    'AD': ('US', 'United States'),
    'AE': ('US', 'United States'),
    'AF': ('US', 'United States'),
    'AG': ('US', 'United States'),
    'AI': ('US', 'United States'),
    'AJ': ('US', 'United States'),
    'AK': ('US', 'United States'),
    'AL': ('US', 'United States'),
    'VE': ('CA', 'Canada'),
    'VA': ('CA', 'Canada'),
    'G': ('GB', 'United Kingdom'),
    'M': ('GB', 'United Kingdom'),
    '2E': ('GB', 'United Kingdom'),
    'F': ('FR', 'France'),
    'DL': ('DE', 'Germany'),
    'DO': ('DE', 'Germany'),
    'PA': ('NL', 'Netherlands'),
    'PD': ('NL', 'Netherlands'),
    'I': ('IT', 'Italy'),
    'EA': ('ES', 'Spain'),
    'OH': ('FI', 'Finland'),
    'SM': ('SE', 'Sweden'),
    'LA': ('NO', 'Norway'),
    'OZ': ('DK', 'Denmark'),
    'SP': ('PL', 'Poland'),
    'OK': ('CZ', 'Czech Republic'),
    'HA': ('HU', 'Hungary'),
    'YO': ('RO', 'Romania'),
    'LZ': ('BG', 'Bulgaria'),
    'UR': ('UA', 'Ukraine'),
    'UT': ('UA', 'Ukraine'),
    'UA': ('RU', 'Russia'),
    'RV': ('RU', 'Russia'),
    'RU': ('RU', 'Russia'),
}


def get_country_from_callsign(callsign: str) -> tuple[str, str] | None:
    """Extract country code and name from callsign prefix.
    
    Args:
        callsign: Ham radio callsign (e.g., '9M2PJU-9')
        
    Returns:
        Tuple of (country_code, country_name) or None if unknown
    """
    if not callsign:
        return None
    
    # Remove SSID suffix
    base_call = callsign.split('-')[0].upper()
    
    # Try progressively shorter prefixes (longest match wins)
    for length in range(min(3, len(base_call)), 0, -1):
        prefix = base_call[:length]
        if prefix in CALLSIGN_PREFIXES:
            return CALLSIGN_PREFIXES[prefix]
    
    return None


def format_packet_summary(packet: dict) -> str:
    """Format packet data for live feed display."""
    packet_type = packet.get('packet_type', 'unknown')
    from_call = packet.get('from_call', '?')
    
    if packet_type == 'position':
        lat = packet.get('latitude', 0)
        lon = packet.get('longitude', 0)
        speed = packet.get('speed')
        if speed:
            return f"{from_call} → Position {lat:.4f}, {lon:.4f} @ {speed}km/h"
        return f"{from_call} → Position {lat:.4f}, {lon:.4f}"
    elif packet_type == 'weather':
        temp = packet.get('temperature')
        humid = packet.get('humidity')
        return f"{from_call} → WX Temp:{temp}°C Humid:{humid}%"
    elif packet_type == 'status':
        status = packet.get('status', '')[:50]
        return f"{from_call} → Status \"{status}\""
    elif packet_type == 'message':
        to_call = packet.get('to_call', '?')
        return f"{from_call} → Message to {to_call}"
    else:
        return f"{from_call} → {packet_type}"
```

- [ ] **Step 6: Create websocket placeholder**

```python
# haminfo/dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations
from flask_socketio import SocketIO, emit, join_room, leave_room

socketio: SocketIO | None = None


def init_socketio(app):
    """Initialize SocketIO with Flask app."""
    global socketio
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
    register_handlers()
    return socketio


def register_handlers():
    """Register SocketIO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        join_room('live_feed')
        emit('status', {'connected': True})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        leave_room('live_feed')
    
    @socketio.on('filter')
    def handle_filter(data):
        """Handle filter change from client."""
        country = data.get('country')
        # Store filter preference in session or handle accordingly
        emit('filter_applied', {'country': country})


def broadcast_packet(packet_data: dict):
    """Broadcast new packet to all connected clients."""
    if socketio:
        socketio.emit('packet', packet_data, room='live_feed')
```

- [ ] **Step 7: Commit**

```bash
git add haminfo/dashboard/
git commit -m "feat(dashboard): create blueprint structure with placeholders"
```

---

### Task 3: Register Blueprint in Flask App

**Files:**
- Modify: `haminfo/flask.py`

- [ ] **Step 1: Import and register dashboard blueprint**

First, examine the structure of `haminfo/flask.py` to find the correct insertion point:

Run: `grep -n "def create_app\|app = Flask\|@app.route" ~/devel/mine/hamradio/haminfo/haminfo/flask.py | head -20`

Then add the imports near the top of the file (with other imports):

```python
from haminfo.dashboard import dashboard_bp
from haminfo.dashboard.websocket import init_socketio
```

And add blueprint registration after app is created (likely after `app = Flask(...)` or inside `create_app()`):

```python
app.register_blueprint(dashboard_bp)

# After app configuration, initialize socketio:
socketio = init_socketio(app)
```

- [ ] **Step 2: Verify app starts**

Run: `cd ~/devel/mine/hamradio/haminfo && python -c "from haminfo.flask import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add haminfo/flask.py
git commit -m "feat(dashboard): register dashboard blueprint in flask app"
```

---

### Task 4: Create Base Template

**Files:**
- Create: `haminfo/templates/dashboard/base.html`

- [ ] **Step 1: Create templates directory**

```bash
mkdir -p ~/devel/mine/hamradio/haminfo/haminfo/templates/dashboard/partials
```

- [ ] **Step 2: Create base template with dark theme**

```html
<!-- haminfo/templates/dashboard/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}APRS Dashboard{% endblock %}</title>
    
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    
    <!-- Socket.IO -->
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    
    {% block head_extra %}{% endblock %}
    
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-card: #16213e;
            --bg-card-hover: #1a2744;
            --border-color: #2a2a4e;
            --text-primary: #fff;
            --text-secondary: #888;
            --text-muted: #666;
            --accent-green: #0f0;
            --accent-cyan: #0ff;
            --accent-yellow: #ff0;
            --accent-magenta: #f0f;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        /* Header */
        .header {
            background: var(--bg-card);
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        
        .logo {
            color: var(--accent-green);
            font-weight: bold;
            font-size: 18px;
            text-decoration: none;
        }
        
        .nav {
            display: flex;
            gap: 8px;
        }
        
        .nav a {
            color: var(--text-secondary);
            text-decoration: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 13px;
            transition: all 0.2s;
        }
        
        .nav a:hover {
            color: var(--text-primary);
            background: var(--bg-card-hover);
        }
        
        .nav a.active {
            color: #000;
            background: var(--accent-green);
        }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .live-indicator {
            color: var(--accent-green);
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .live-indicator::before {
            content: '●';
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* Content */
        .content {
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* Cards */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
        }
        
        .card-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .card-title {
            font-size: 13px;
            font-weight: 600;
        }
        
        .card-body {
            padding: 16px;
        }
        
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 4px;
        }
        
        .stat-label {
            color: var(--text-secondary);
            font-size: 12px;
        }
        
        .stat-card.green .stat-value { color: var(--accent-green); }
        .stat-card.cyan .stat-value { color: var(--accent-cyan); }
        .stat-card.yellow .stat-value { color: var(--accent-yellow); }
        .stat-card.magenta .stat-value { color: var(--accent-magenta); }
        
        /* Grid layouts */
        .grid-2x2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
        }
        
        /* Form elements */
        select, input[type="text"] {
            background: var(--bg-card-hover);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 13px;
        }
        
        select:focus, input:focus {
            outline: none;
            border-color: var(--accent-green);
        }
        
        button {
            background: var(--accent-green);
            color: #000;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 13px;
            cursor: pointer;
            font-weight: 500;
        }
        
        button:hover {
            opacity: 0.9;
        }
        
        /* Live feed */
        .live-feed {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .live-feed-item {
            padding: 8px;
            border-bottom: 1px solid var(--border-color);
        }
        
        .live-feed-item:last-child {
            border-bottom: none;
        }
        
        .live-feed-item.position { color: var(--accent-green); }
        .live-feed-item.weather { color: var(--accent-cyan); }
        .live-feed-item.status { color: var(--accent-yellow); }
        .live-feed-item.message { color: var(--text-primary); }
        
        /* Responsive */
        @media (max-width: 1024px) {
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .grid-2x2 { grid-template-columns: 1fr; }
            .grid-3 { grid-template-columns: 1fr; }
        }
        
        @media (max-width: 640px) {
            .stats-grid { grid-template-columns: 1fr; }
            .header { flex-direction: column; gap: 12px; }
            .header-left { flex-direction: column; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-left">
            <a href="{{ url_for('dashboard.index') }}" class="logo">📡 APRS Dashboard</a>
            <nav class="nav">
                <a href="{{ url_for('dashboard.index') }}" class="{{ 'active' if request.endpoint == 'dashboard.index' else '' }}">Home</a>
                <a href="{{ url_for('dashboard.weather') }}" class="{{ 'active' if request.endpoint == 'dashboard.weather' else '' }}">Weather</a>
                <a href="{{ url_for('dashboard.map_view') }}" class="{{ 'active' if request.endpoint == 'dashboard.map_view' else '' }}">Map</a>
                <a href="{{ url_for('dashboard.station', callsign='lookup') }}" class="{{ 'active' if request.endpoint == 'dashboard.station' else '' }}">Lookup</a>
            </nav>
        </div>
        <div class="header-right">
            {% block header_right %}
            <select id="country-filter">
                <option value="">All Countries</option>
            </select>
            <div class="live-indicator">LIVE</div>
            {% endblock %}
        </div>
    </header>
    
    <main class="content">
        {% block content %}{% endblock %}
    </main>
    
    <script>
        // Initialize Socket.IO connection
        const socket = io();
        
        socket.on('connect', () => {
            console.log('Connected to live feed');
        });
        
        socket.on('disconnect', () => {
            console.log('Disconnected from live feed');
        });
        
        socket.on('packet', (data) => {
            // Handle incoming packet - override in page-specific JS
            if (typeof handlePacket === 'function') {
                handlePacket(data);
            }
        });
        
        // Country filter handler
        document.getElementById('country-filter')?.addEventListener('change', (e) => {
            socket.emit('filter', { country: e.target.value });
        });
    </script>
    
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add haminfo/templates/
git commit -m "feat(dashboard): add base template with dark theme and navigation"
```

---

### Task 5: Create Main Dashboard Template

**Files:**
- Create: `haminfo/templates/dashboard/index.html`

- [ ] **Step 1: Create index template**

```html
<!-- haminfo/templates/dashboard/index.html -->
{% extends "base.html" %}

{% block title %}APRS Dashboard - Home{% endblock %}

{% block content %}
<!-- Stats Cards -->
<div class="stats-grid" 
     hx-get="{{ url_for('dashboard.api_stats') }}" 
     hx-trigger="load, every 30s"
     hx-swap="innerHTML">
    <div class="stat-card green">
        <div class="stat-value">--</div>
        <div class="stat-label">Total Packets (24h)</div>
    </div>
    <div class="stat-card cyan">
        <div class="stat-value">--</div>
        <div class="stat-label">Unique Stations</div>
    </div>
    <div class="stat-card yellow">
        <div class="stat-value">--</div>
        <div class="stat-label">Countries</div>
    </div>
    <div class="stat-card magenta">
        <div class="stat-value">--</div>
        <div class="stat-label">Weather Stations</div>
    </div>
</div>

<!-- Main Grid -->
<div class="grid-2x2">
    <!-- Live Feed -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Live Traffic</span>
            <span class="live-indicator">streaming</span>
        </div>
        <div class="card-body">
            <div id="live-feed" class="live-feed">
                <div class="live-feed-item" style="color: var(--text-muted);">
                    Waiting for packets...
                </div>
            </div>
        </div>
    </div>
    
    <!-- Hourly Chart -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Hourly Distribution</span>
        </div>
        <div class="card-body">
            <canvas id="hourly-chart" height="200"></canvas>
        </div>
    </div>
    
    <!-- Top Stations -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Top Stations (24h)</span>
        </div>
        <div class="card-body"
             hx-get="{{ url_for('dashboard.api_top_stations') }}"
             hx-trigger="load, every 60s"
             hx-swap="innerHTML">
            <div style="color: var(--text-muted);">Loading...</div>
        </div>
    </div>
    
    <!-- Countries -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Countries</span>
        </div>
        <div class="card-body"
             hx-get="{{ url_for('dashboard.api_countries') }}"
             hx-trigger="load, every 60s"
             hx-swap="innerHTML">
            <div style="color: var(--text-muted);">Loading...</div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    const MAX_FEED_ITEMS = 50;
    const feedContainer = document.getElementById('live-feed');
    
    function handlePacket(packet) {
        const item = document.createElement('div');
        item.className = 'live-feed-item ' + (packet.packet_type || 'unknown');
        item.textContent = packet.summary || JSON.stringify(packet);
        
        // Remove "waiting" message if present
        const waiting = feedContainer.querySelector('[style*="text-muted"]');
        if (waiting) waiting.remove();
        
        // Add to top
        feedContainer.insertBefore(item, feedContainer.firstChild);
        
        // Trim old items
        while (feedContainer.children.length > MAX_FEED_ITEMS) {
            feedContainer.removeChild(feedContainer.lastChild);
        }
    }
    
    // Initialize hourly chart
    fetch('{{ url_for("dashboard.api_hourly") }}')
        .then(r => r.json())
        .then(data => {
            new Chart(document.getElementById('hourly-chart'), {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.values,
                        backgroundColor: '#0f0',
                        borderRadius: 4,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { 
                            grid: { color: '#2a2a4e' },
                            ticks: { color: '#888' }
                        },
                        y: { 
                            grid: { color: '#2a2a4e' },
                            ticks: { color: '#888' }
                        }
                    }
                }
            });
        });
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/templates/dashboard/index.html
git commit -m "feat(dashboard): add main dashboard template with live feed and charts"
```

---

### Task 6: Create Stats Partial Template

**Files:**
- Create: `haminfo/templates/dashboard/partials/stats_cards.html`

- [ ] **Step 1: Create stats partial for HTMX**

```html
<!-- haminfo/templates/dashboard/partials/stats_cards.html -->
<div class="stat-card green">
    <div class="stat-value">{{ stats.total_packets_24h | default(0) | int | format_number }}</div>
    <div class="stat-label">Total Packets (24h)</div>
</div>
<div class="stat-card cyan">
    <div class="stat-value">{{ stats.unique_stations | default(0) | int | format_number }}</div>
    <div class="stat-label">Unique Stations</div>
</div>
<div class="stat-card yellow">
    <div class="stat-value">{{ stats.countries | default(0) | int }}</div>
    <div class="stat-label">Countries</div>
</div>
<div class="stat-card magenta">
    <div class="stat-value">{{ stats.weather_stations | default(0) | int }}</div>
    <div class="stat-label">Weather Stations</div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/templates/dashboard/partials/stats_cards.html
git commit -m "feat(dashboard): add stats cards partial template"
```

---

## Chunk 2: Database Queries and API Endpoints

### Task 7: Write Tests for Query Helpers

**Files:**
- Create: `tests/test_dashboard_queries.py`

**Note:** Tests use existing fixtures from `tests/conftest.py` (`db_session`, `app`, `client`).

- [ ] **Step 1: Create query helper tests**

```python
# tests/test_dashboard_queries.py
"""Tests for dashboard query helpers.

Uses existing db_session fixture from tests/conftest.py.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from haminfo.dashboard.queries import (
    get_dashboard_stats,
    get_top_stations,
    get_country_breakdown,
    get_hourly_distribution,
    get_recent_packets,
)


class TestGetDashboardStats:
    """Tests for get_dashboard_stats."""
    
    def test_returns_dict_with_required_keys(self, db_session):
        """Stats should include all required keys."""
        result = get_dashboard_stats(db_session)
        
        assert 'total_packets_24h' in result
        assert 'unique_stations' in result
        assert 'countries' in result
        assert 'weather_stations' in result
    
    def test_returns_integers(self, db_session):
        """All stat values should be integers."""
        result = get_dashboard_stats(db_session)
        
        assert isinstance(result['total_packets_24h'], int)
        assert isinstance(result['unique_stations'], int)
        assert isinstance(result['countries'], int)
        assert isinstance(result['weather_stations'], int)


class TestGetTopStations:
    """Tests for get_top_stations."""
    
    def test_returns_list(self, db_session):
        """Should return a list."""
        result = get_top_stations(db_session, limit=10)
        assert isinstance(result, list)
    
    def test_respects_limit(self, db_session):
        """Should not exceed requested limit."""
        result = get_top_stations(db_session, limit=5)
        assert len(result) <= 5


class TestGetCountryBreakdown:
    """Tests for get_country_breakdown."""
    
    def test_returns_list(self, db_session):
        """Should return a list."""
        result = get_country_breakdown(db_session, limit=10)
        assert isinstance(result, list)
    
    def test_entries_have_required_fields(self, db_session):
        """Each entry should have country_code, country_name, count."""
        result = get_country_breakdown(db_session, limit=10)
        for entry in result:
            assert 'country_code' in entry
            assert 'country_name' in entry
            assert 'count' in entry


class TestGetHourlyDistribution:
    """Tests for get_hourly_distribution."""
    
    def test_returns_24_hours(self, db_session):
        """Should return data for 24 hours."""
        result = get_hourly_distribution(db_session)
        assert 'labels' in result
        assert 'values' in result
        assert len(result['labels']) == 24
        assert len(result['values']) == 24


class TestGetRecentPackets:
    """Tests for get_recent_packets."""
    
    def test_returns_list(self, db_session):
        """Should return a list."""
        result = get_recent_packets(db_session, limit=50)
        assert isinstance(result, list)
    
    def test_respects_limit(self, db_session):
        """Should not exceed requested limit."""
        result = get_recent_packets(db_session, limit=10)
        assert len(result) <= 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/devel/mine/hamradio/haminfo && pytest tests/test_dashboard_queries.py -v`
Expected: FAIL (functions not fully implemented)

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_dashboard_queries.py
git commit -m "test(dashboard): add query helper tests"
```

---

### Task 8: Implement Query Helpers

**Files:**
- Modify: `haminfo/dashboard/queries.py`

- [ ] **Step 1: Implement all query functions**

```python
# haminfo/dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, distinct, text
from sqlalchemy.orm import Session

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo.dashboard.utils import get_country_from_callsign

if TYPE_CHECKING:
    pass


def get_dashboard_stats(session: Session) -> dict:
    """Get summary statistics for dashboard.
    
    Returns:
        Dict with total_packets_24h, unique_stations, countries, weather_stations
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    
    # Total packets in last 24h
    total_packets = session.query(func.count(APRSPacket.id)).filter(
        APRSPacket.received_at >= day_ago
    ).scalar() or 0
    
    # Unique stations (from_call) in last 24h
    unique_stations = session.query(
        func.count(distinct(APRSPacket.from_call))
    ).filter(
        APRSPacket.received_at >= day_ago
    ).scalar() or 0
    
    # Get unique callsigns for country count
    callsigns = session.query(distinct(APRSPacket.from_call)).filter(
        APRSPacket.received_at >= day_ago
    ).all()
    
    countries = set()
    for (callsign,) in callsigns:
        country = get_country_from_callsign(callsign)
        if country:
            countries.add(country[0])
    
    # Weather stations count
    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0
    
    return {
        'total_packets_24h': int(total_packets),
        'unique_stations': int(unique_stations),
        'countries': len(countries),
        'weather_stations': int(weather_stations),
    }


def get_top_stations(session: Session, limit: int = 10) -> list[dict]:
    """Get top stations by packet count in last 24h.
    
    Args:
        session: Database session
        limit: Maximum number of stations to return
        
    Returns:
        List of dicts with callsign, count, device
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    
    results = session.query(
        APRSPacket.from_call,
        func.count(APRSPacket.id).label('count')
    ).filter(
        APRSPacket.received_at >= day_ago
    ).group_by(
        APRSPacket.from_call
    ).order_by(
        func.count(APRSPacket.id).desc()
    ).limit(limit).all()
    
    return [
        {
            'callsign': row.from_call,
            'count': row.count,
            'device': None,  # Future enhancement: extract from TOCALL
        }
        for row in results
    ]


def get_country_breakdown(session: Session, limit: int = 10) -> list[dict]:
    """Get packet count breakdown by country.
    
    Args:
        session: Database session
        limit: Maximum number of countries to return
        
    Returns:
        List of dicts with country_code, country_name, count
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    
    # Get all callsigns with their counts
    results = session.query(
        APRSPacket.from_call,
        func.count(APRSPacket.id).label('count')
    ).filter(
        APRSPacket.received_at >= day_ago
    ).group_by(
        APRSPacket.from_call
    ).all()
    
    # Aggregate by country
    country_counts: dict[tuple[str, str], int] = {}
    for row in results:
        country = get_country_from_callsign(row.from_call)
        if country:
            key = country
            country_counts[key] = country_counts.get(key, 0) + row.count
    
    # Sort by count and limit
    sorted_countries = sorted(
        country_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:limit]
    
    return [
        {
            'country_code': code,
            'country_name': name,
            'count': count,
        }
        for (code, name), count in sorted_countries
    ]


def get_hourly_distribution(session: Session) -> dict:
    """Get packet count distribution by hour for last 24h.
    
    Returns:
        Dict with labels (hours) and values (counts)
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    
    # Generate hour labels
    labels = []
    for i in range(24):
        hour = (now - timedelta(hours=23-i)).hour
        labels.append(f"{hour:02d}:00")
    
    # Query hourly counts
    # Note: This query may need adjustment for TimescaleDB
    results = session.query(
        func.date_trunc('hour', APRSPacket.received_at).label('hour'),
        func.count(APRSPacket.id).label('count')
    ).filter(
        APRSPacket.received_at >= day_ago
    ).group_by(
        func.date_trunc('hour', APRSPacket.received_at)
    ).all()
    
    # Map results to hours
    hour_counts = {r.hour.hour: r.count for r in results if r.hour}
    values = [hour_counts.get((now - timedelta(hours=23-i)).hour, 0) for i in range(24)]
    
    return {
        'labels': labels,
        'values': values,
    }


def get_recent_packets(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    callsign: str | None = None,
    country: str | None = None,
) -> list[dict]:
    """Get recent packets with optional filtering.
    
    Args:
        session: Database session
        limit: Maximum number of packets
        offset: Pagination offset
        callsign: Filter by specific callsign
        country: Filter by country code (derived from callsign prefix)
        
    Returns:
        List of packet dicts
    """
    query = session.query(APRSPacket).order_by(
        APRSPacket.received_at.desc()
    )
    
    if callsign:
        query = query.filter(APRSPacket.from_call == callsign)
    
    # Note: Country filtering requires post-processing since it's derived
    
    results = query.offset(offset).limit(limit).all()
    
    packets = []
    for p in results:
        packet_data = {
            'id': p.id,
            'from_call': p.from_call,
            'to_call': p.to_call,
            'packet_type': p.packet_type,
            'received_at': p.received_at.isoformat() if p.received_at else None,
            'latitude': p.latitude,
            'longitude': p.longitude,
            'speed': p.speed,
            'course': p.course,
            'altitude': p.altitude,
        }
        
        # Apply country filter if specified
        if country:
            pkt_country = get_country_from_callsign(p.from_call)
            if not pkt_country or pkt_country[0] != country:
                continue
        
        packets.append(packet_data)
    
    return packets


def get_weather_stations(session: Session, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get weather stations with their latest reports.
    
    Args:
        session: Database session
        limit: Maximum number of stations
        offset: Pagination offset
        
    Returns:
        List of weather station dicts with latest report data
    """
    stations = session.query(WeatherStation).limit(limit).offset(offset).all()
    
    result = []
    for station in stations:
        # Get latest report for this station
        latest_report = session.query(WeatherReport).filter(
            WeatherReport.weather_station_id == station.id
        ).order_by(
            WeatherReport.time.desc()
        ).first()
        
        station_data = {
            'id': station.id,
            'callsign': station.callsign,
            'latitude': station.latitude,
            'longitude': station.longitude,
            'comment': station.comment,
        }
        
        if latest_report:
            station_data.update({
                'temperature': latest_report.temperature,
                'humidity': latest_report.humidity,
                'pressure': latest_report.pressure,
                'wind_speed': latest_report.wind_speed,
                'wind_direction': latest_report.wind_direction,
                'wind_gust': latest_report.wind_gust,
                'rain_1h': latest_report.rain_1h,
                'rain_24h': latest_report.rain_24h,
                'report_time': latest_report.time.isoformat() if latest_report.time else None,
            })
        
        result.append(station_data)
    
    return result


def get_station_detail(session: Session, callsign: str) -> dict | None:
    """Get detailed information about a specific station.
    
    Args:
        session: Database session
        callsign: Station callsign
        
    Returns:
        Station detail dict or None if not found
    """
    # Get latest packet for this station
    latest_packet = session.query(APRSPacket).filter(
        APRSPacket.from_call == callsign
    ).order_by(
        APRSPacket.received_at.desc()
    ).first()
    
    if not latest_packet:
        return None
    
    # Get first packet for this station
    first_packet = session.query(APRSPacket).filter(
        APRSPacket.from_call == callsign
    ).order_by(
        APRSPacket.received_at.asc()
    ).first()
    
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    
    # Packet counts
    packets_24h = session.query(func.count(APRSPacket.id)).filter(
        APRSPacket.from_call == callsign,
        APRSPacket.received_at >= day_ago
    ).scalar() or 0
    
    packets_7d = session.query(func.count(APRSPacket.id)).filter(
        APRSPacket.from_call == callsign,
        APRSPacket.received_at >= week_ago
    ).scalar() or 0
    
    packets_total = session.query(func.count(APRSPacket.id)).filter(
        APRSPacket.from_call == callsign
    ).scalar() or 0
    
    country = get_country_from_callsign(callsign)
    
    return {
        'callsign': callsign,
        'country_code': country[0] if country else None,
        'country_name': country[1] if country else None,
        'latitude': latest_packet.latitude,
        'longitude': latest_packet.longitude,
        'altitude': latest_packet.altitude,
        'speed': latest_packet.speed,
        'course': latest_packet.course,
        'symbol': latest_packet.symbol if hasattr(latest_packet, 'symbol') else None,
        'symbol_table': latest_packet.symbol_table if hasattr(latest_packet, 'symbol_table') else None,
        'last_seen': latest_packet.received_at.isoformat() if latest_packet.received_at else None,
        'first_seen': first_packet.received_at.isoformat() if first_packet and first_packet.received_at else None,
        'packets_24h': packets_24h,
        'packets_7d': packets_7d,
        'packets_total': packets_total,
    }


def get_map_stations(
    session: Session,
    bbox: tuple[float, float, float, float] | None = None,
    station_type: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Get stations for map display.
    
    Args:
        session: Database session
        bbox: Bounding box (min_lon, min_lat, max_lon, max_lat)
        station_type: Filter by type ('position', 'weather', 'digipeater')
        limit: Maximum number of stations
        
    Returns:
        List of station dicts with location and type
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    
    # Get distinct stations with their latest position
    subquery = session.query(
        APRSPacket.from_call,
        func.max(APRSPacket.received_at).label('max_time')
    ).filter(
        APRSPacket.received_at >= day_ago,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ).group_by(APRSPacket.from_call).subquery()
    
    query = session.query(APRSPacket).join(
        subquery,
        (APRSPacket.from_call == subquery.c.from_call) &
        (APRSPacket.received_at == subquery.c.max_time)
    )
    
    if station_type:
        query = query.filter(APRSPacket.packet_type == station_type)
    
    results = query.limit(limit).all()
    
    stations = []
    for p in results:
        # Apply bbox filter if specified
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (min_lon <= p.longitude <= max_lon and min_lat <= p.latitude <= max_lat):
                continue
        
        stations.append({
            'callsign': p.from_call,
            'latitude': p.latitude,
            'longitude': p.longitude,
            'packet_type': p.packet_type,
            'speed': p.speed,
            'last_seen': p.received_at.isoformat() if p.received_at else None,
        })
    
    return stations
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd ~/devel/mine/hamradio/haminfo && pytest tests/test_dashboard_queries.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add haminfo/dashboard/queries.py
git commit -m "feat(dashboard): implement database query helpers"
```

---

### Task 9: Write Tests for Utils

**Files:**
- Create: `tests/test_dashboard_utils.py`

- [ ] **Step 1: Create utils tests**

```python
# tests/test_dashboard_utils.py
"""Tests for dashboard utility functions."""

import pytest

from haminfo.dashboard.utils import (
    get_country_from_callsign,
    format_packet_summary,
)


class TestGetCountryFromCallsign:
    """Tests for get_country_from_callsign."""
    
    def test_malaysian_callsign(self):
        """Should recognize Malaysian callsigns."""
        assert get_country_from_callsign('9M2PJU') == ('MY', 'Malaysia')
        assert get_country_from_callsign('9M2PJU-9') == ('MY', 'Malaysia')
        assert get_country_from_callsign('9W2ABC') == ('MY', 'Malaysia')
    
    def test_us_callsigns(self):
        """Should recognize US callsigns."""
        assert get_country_from_callsign('W1AW') == ('US', 'United States')
        assert get_country_from_callsign('K1ABC') == ('US', 'United States')
        assert get_country_from_callsign('N0CALL') == ('US', 'United States')
        assert get_country_from_callsign('AA1BB') == ('US', 'United States')
    
    def test_australian_callsign(self):
        """Should recognize Australian callsigns."""
        assert get_country_from_callsign('VK3ABC') == ('AU', 'Australia')
    
    def test_japanese_callsign(self):
        """Should recognize Japanese callsigns."""
        assert get_country_from_callsign('JA1ABC') == ('JP', 'Japan')
        assert get_country_from_callsign('JH1XYZ') == ('JP', 'Japan')
    
    def test_removes_ssid(self):
        """Should handle SSID suffix."""
        assert get_country_from_callsign('9M2PJU-15') == ('MY', 'Malaysia')
    
    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert get_country_from_callsign('9m2pju') == ('MY', 'Malaysia')
    
    def test_unknown_prefix(self):
        """Should return None for unknown prefixes."""
        assert get_country_from_callsign('ZZ9ABC') is None
    
    def test_empty_callsign(self):
        """Should handle empty/None callsign."""
        assert get_country_from_callsign('') is None
        assert get_country_from_callsign(None) is None


class TestFormatPacketSummary:
    """Tests for format_packet_summary."""
    
    def test_position_packet(self):
        """Should format position packets."""
        packet = {
            'from_call': '9M2PJU-9',
            'packet_type': 'position',
            'latitude': 3.1234,
            'longitude': 101.4567,
        }
        result = format_packet_summary(packet)
        assert '9M2PJU-9' in result
        assert 'Position' in result
        assert '3.1234' in result
    
    def test_position_with_speed(self):
        """Should include speed if present."""
        packet = {
            'from_call': '9M2PJU-9',
            'packet_type': 'position',
            'latitude': 3.1234,
            'longitude': 101.4567,
            'speed': 45,
        }
        result = format_packet_summary(packet)
        assert '45km/h' in result
    
    def test_weather_packet(self):
        """Should format weather packets."""
        packet = {
            'from_call': 'VK3RWX',
            'packet_type': 'weather',
            'temperature': 25,
            'humidity': 78,
        }
        result = format_packet_summary(packet)
        assert 'VK3RWX' in result
        assert 'WX' in result
        assert '25°C' in result
    
    def test_status_packet(self):
        """Should format status packets."""
        packet = {
            'from_call': 'W1AW',
            'packet_type': 'status',
            'status': 'QRV on 144.390',
        }
        result = format_packet_summary(packet)
        assert 'W1AW' in result
        assert 'Status' in result
    
    def test_message_packet(self):
        """Should format message packets."""
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'message',
            'to_call': 'W1AW',
        }
        result = format_packet_summary(packet)
        assert 'N0CALL' in result
        assert 'Message to W1AW' in result
```

- [ ] **Step 2: Run tests**

Run: `cd ~/devel/mine/hamradio/haminfo && pytest tests/test_dashboard_utils.py -v`
Expected: PASS (utils already implemented)

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard_utils.py
git commit -m "test(dashboard): add utils tests"
```

---

### Task 10: Implement API Endpoints

**Files:**
- Modify: `haminfo/dashboard/api.py`

- [ ] **Step 1: Implement all API endpoints**

```python
# haminfo/dashboard/api.py
"""Dashboard JSON API endpoints."""

from flask import jsonify, request, render_template
from haminfo.dashboard import dashboard_bp
from haminfo.dashboard.queries import (
    get_dashboard_stats,
    get_top_stations,
    get_country_breakdown,
    get_hourly_distribution,
    get_recent_packets,
    get_weather_stations,
    get_station_detail,
    get_map_stations,
)
from haminfo.db.models.db_session import get_session


def get_db_session():
    """Get database session."""
    return get_session()


@dashboard_bp.route('/api/dashboard/stats')
def api_stats():
    """Dashboard statistics - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        stats = get_dashboard_stats(session)
        return render_template('partials/stats_cards.html', stats=stats)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/stats/json')
def api_stats_json():
    """Dashboard statistics as JSON."""
    session = get_db_session()
    try:
        stats = get_dashboard_stats(session)
        return jsonify(stats)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/top-stations')
def api_top_stations():
    """Top stations leaderboard - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        stations = get_top_stations(session, limit=min(limit, 50))
        return render_template('partials/top_stations.html', stations=stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/top-stations/json')
def api_top_stations_json():
    """Top stations leaderboard as JSON."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        stations = get_top_stations(session, limit=min(limit, 50))
        return jsonify(stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/countries')
def api_countries():
    """Country breakdown - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        countries = get_country_breakdown(session, limit=min(limit, 50))
        return render_template('partials/countries.html', countries=countries)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/countries/json')
def api_countries_json():
    """Country breakdown as JSON."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 10, type=int)
        countries = get_country_breakdown(session, limit=min(limit, 50))
        return jsonify(countries)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/hourly')
def api_hourly():
    """Hourly distribution data for chart."""
    session = get_db_session()
    try:
        data = get_hourly_distribution(session)
        return jsonify(data)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/packets')
def api_packets():
    """Recent packets list."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        callsign = request.args.get('callsign')
        country = request.args.get('country')
        
        packets = get_recent_packets(
            session,
            limit=min(limit, 100),
            offset=offset,
            callsign=callsign,
            country=country,
        )
        return jsonify(packets)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/weather/stations')
def api_weather_stations():
    """Weather stations list - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        stations = get_weather_stations(session, limit=min(limit, 100), offset=offset)
        return render_template('partials/weather_grid.html', stations=stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/weather/stations/json')
def api_weather_stations_json():
    """Weather stations list as JSON."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        stations = get_weather_stations(session, limit=min(limit, 100), offset=offset)
        return jsonify(stations)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/station/<callsign>')
def api_station_detail(callsign: str):
    """Station detail - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        detail = get_station_detail(session, callsign)
        if not detail:
            return render_template('partials/station_detail.html', station=None, error='Station not found')
        return render_template('partials/station_detail.html', station=detail)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/station/<callsign>/json')
def api_station_detail_json(callsign: str):
    """Station detail as JSON."""
    session = get_db_session()
    try:
        detail = get_station_detail(session, callsign)
        if not detail:
            return jsonify({'error': 'Station not found'}), 404
        return jsonify(detail)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/station/<callsign>/packets')
def api_station_packets(callsign: str):
    """Station packet history - returns HTML partial for HTMX."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        packets = get_recent_packets(session, limit=min(limit, 100), offset=offset, callsign=callsign)
        return render_template('partials/packets_table.html', packets=packets)
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/map/stations')
def api_map_stations():
    """Stations for map display as GeoJSON."""
    session = get_db_session()
    try:
        limit = request.args.get('limit', 1000, type=int)
        station_type = request.args.get('type')
        
        # Parse bbox if provided
        bbox = None
        bbox_param = request.args.get('bbox')
        if bbox_param:
            try:
                parts = [float(x) for x in bbox_param.split(',')]
                if len(parts) == 4:
                    bbox = tuple(parts)
            except ValueError:
                pass
        
        stations = get_map_stations(
            session,
            bbox=bbox,
            station_type=station_type,
            limit=min(limit, 5000),
        )
        
        # Convert to GeoJSON FeatureCollection
        features = [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [s['longitude'], s['latitude']],
                },
                'properties': {
                    'callsign': s['callsign'],
                    'packet_type': s['packet_type'],
                    'speed': s['speed'],
                    'last_seen': s['last_seen'],
                },
            }
            for s in stations
            if s['latitude'] and s['longitude']
        ]
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
        })
    finally:
        session.close()
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/dashboard/api.py
git commit -m "feat(dashboard): implement API endpoints"
```

---

### Task 11: Write API Endpoint Tests

**Files:**
- Create: `tests/test_dashboard_api.py`

**Note:** Tests use existing `app` and `client` fixtures from `tests/conftest.py`.

- [ ] **Step 1: Create API tests**

```python
# tests/test_dashboard_api.py
"""Tests for dashboard API endpoints.

Uses existing app/client fixtures from tests/conftest.py.
"""

import pytest


# Use existing client fixture from conftest.py - no need for custom fixture


class TestStatsEndpoint:
    """Tests for /api/dashboard/stats endpoint."""
    
    def test_stats_returns_200(self, client):
        """Should return 200 OK."""
        response = client.get('/api/dashboard/stats/json')
        assert response.status_code == 200
    
    def test_stats_returns_json(self, client):
        """Should return JSON with required fields."""
        response = client.get('/api/dashboard/stats/json')
        data = response.get_json()
        
        assert 'total_packets_24h' in data
        assert 'unique_stations' in data
        assert 'countries' in data
        assert 'weather_stations' in data


class TestTopStationsEndpoint:
    """Tests for /api/dashboard/top-stations endpoint."""
    
    def test_top_stations_returns_200(self, client):
        """Should return 200 OK."""
        response = client.get('/api/dashboard/top-stations/json')
        assert response.status_code == 200
    
    def test_top_stations_returns_list(self, client):
        """Should return a list."""
        response = client.get('/api/dashboard/top-stations/json')
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_top_stations_respects_limit(self, client):
        """Should respect limit parameter."""
        response = client.get('/api/dashboard/top-stations/json?limit=5')
        data = response.get_json()
        assert len(data) <= 5


class TestCountriesEndpoint:
    """Tests for /api/dashboard/countries endpoint."""
    
    def test_countries_returns_200(self, client):
        """Should return 200 OK."""
        response = client.get('/api/dashboard/countries/json')
        assert response.status_code == 200
    
    def test_countries_returns_list(self, client):
        """Should return a list."""
        response = client.get('/api/dashboard/countries/json')
        data = response.get_json()
        assert isinstance(data, list)


class TestHourlyEndpoint:
    """Tests for /api/dashboard/hourly endpoint."""
    
    def test_hourly_returns_200(self, client):
        """Should return 200 OK."""
        response = client.get('/api/dashboard/hourly')
        assert response.status_code == 200
    
    def test_hourly_returns_labels_and_values(self, client):
        """Should return labels and values arrays."""
        response = client.get('/api/dashboard/hourly')
        data = response.get_json()
        
        assert 'labels' in data
        assert 'values' in data
        assert len(data['labels']) == 24
        assert len(data['values']) == 24


class TestMapStationsEndpoint:
    """Tests for /api/dashboard/map/stations endpoint."""
    
    def test_map_stations_returns_200(self, client):
        """Should return 200 OK."""
        response = client.get('/api/dashboard/map/stations')
        assert response.status_code == 200
    
    def test_map_stations_returns_geojson(self, client):
        """Should return GeoJSON FeatureCollection."""
        response = client.get('/api/dashboard/map/stations')
        data = response.get_json()
        
        assert data['type'] == 'FeatureCollection'
        assert 'features' in data
        assert isinstance(data['features'], list)


class TestStationDetailEndpoint:
    """Tests for /api/dashboard/station/<callsign> endpoint."""
    
    def test_unknown_station_returns_404(self, client):
        """Should return 404 for unknown callsign."""
        response = client.get('/api/dashboard/station/UNKNOWN123/json')
        assert response.status_code == 404
```

- [ ] **Step 2: Run tests**

Run: `cd ~/devel/mine/hamradio/haminfo && pytest tests/test_dashboard_api.py -v`
Expected: Most tests PASS (some may fail without test data)

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard_api.py
git commit -m "test(dashboard): add API endpoint tests"
```

---

## Chunk 3: Page Templates

### Task 12: Create Partial Templates

**Files:**
- Create: `haminfo/templates/dashboard/partials/top_stations.html`
- Create: `haminfo/templates/dashboard/partials/countries.html`
- Create: `haminfo/templates/dashboard/partials/weather_grid.html`
- Create: `haminfo/templates/dashboard/partials/station_detail.html`
- Create: `haminfo/templates/dashboard/partials/packets_table.html`

- [ ] **Step 1: Create top stations partial**

```html
<!-- haminfo/templates/dashboard/partials/top_stations.html -->
{% if stations %}
<div class="leaderboard">
    {% for station in stations %}
    <div class="leaderboard-item" style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);">
        <span>
            <span style="color:var(--accent-green);margin-right:8px;">{{ loop.index }}.</span>
            <a href="{{ url_for('dashboard.station', callsign=station.callsign) }}" style="color:var(--accent-cyan);text-decoration:none;">{{ station.callsign }}</a>
        </span>
        <span style="color:var(--text-secondary);">{{ station.count }} pkts</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div style="color:var(--text-muted);text-align:center;padding:20px;">No stations found</div>
{% endif %}
```

- [ ] **Step 2: Create countries partial**

```html
<!-- haminfo/templates/dashboard/partials/countries.html -->
{% set country_flags = {
    'US': '🇺🇸', 'MY': '🇲🇾', 'AU': '🇦🇺', 'JP': '🇯🇵', 'GB': '🇬🇧',
    'CA': '🇨🇦', 'DE': '🇩🇪', 'FR': '🇫🇷', 'NL': '🇳🇱', 'IT': '🇮🇹',
    'ES': '🇪🇸', 'SE': '🇸🇪', 'NO': '🇳🇴', 'FI': '🇫🇮', 'DK': '🇩🇰',
    'PL': '🇵🇱', 'CZ': '🇨🇿', 'NZ': '🇳🇿', 'KR': '🇰🇷', 'TW': '🇹🇼',
    'RU': '🇷🇺', 'UA': '🇺🇦', 'HU': '🇭🇺', 'RO': '🇷🇴', 'BG': '🇧🇬',
} %}
{% if countries %}
<div class="country-list">
    {% for country in countries %}
    <div class="country-item" style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);">
        <span>{{ country_flags.get(country.country_code, '🏳️') }} {{ country.country_name }}</span>
        <span style="color:var(--text-secondary);">{{ country.count }}</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div style="color:var(--text-muted);text-align:center;padding:20px;">No data</div>
{% endif %}
```

- [ ] **Step 3: Create weather grid partial**

```html
<!-- haminfo/templates/dashboard/partials/weather_grid.html -->
{% if stations %}
<div class="grid-3">
    {% for station in stations %}
    <div class="card" style="padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <a href="{{ url_for('dashboard.station', callsign=station.callsign) }}" style="color:var(--accent-green);font-weight:bold;text-decoration:none;">{{ station.callsign }}</a>
            {% if station.report_time %}
            <span style="color:var(--text-muted);font-size:11px;">{{ station.report_time | default('--') }}</span>
            {% endif %}
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
            <div><span style="color:var(--text-muted);">Temp:</span> <span style="color:var(--accent-yellow);">{{ station.temperature | default('--') }}°C</span></div>
            <div><span style="color:var(--text-muted);">Humid:</span> <span style="color:var(--accent-cyan);">{{ station.humidity | default('--') }}%</span></div>
            <div><span style="color:var(--text-muted);">Wind:</span> {{ station.wind_speed | default('--') }} km/h</div>
            <div><span style="color:var(--text-muted);">Press:</span> {{ station.pressure | default('--') }} hPa</div>
            <div><span style="color:var(--text-muted);">Rain 1h:</span> {{ station.rain_1h | default('0.0') }} mm</div>
            <div><span style="color:var(--text-muted);">Rain 24h:</span> {{ station.rain_24h | default('0.0') }} mm</div>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div style="color:var(--text-muted);text-align:center;padding:40px;">No weather stations found</div>
{% endif %}
```

- [ ] **Step 4: Create station detail partial**

```html
<!-- haminfo/templates/dashboard/partials/station_detail.html -->
{% if station %}
<div class="grid-2x2">
    <!-- Current Position -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Current Position</span>
        </div>
        <div class="card-body" style="font-size:13px;">
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Latitude:</span>
                <span style="color:var(--accent-cyan);">{{ "%.4f"|format(station.latitude) if station.latitude else '--' }}°</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Longitude:</span>
                <span style="color:var(--accent-cyan);">{{ "%.4f"|format(station.longitude) if station.longitude else '--' }}°</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Altitude:</span>
                <span>{{ station.altitude | default('--') }} m</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Speed:</span>
                <span style="color:var(--accent-yellow);">{{ station.speed | default('--') }} km/h</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Course:</span>
                <span>{{ station.course | default('--') }}°</span>
            </div>
            {% if station.latitude and station.longitude %}
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border-color);">
                <a href="{{ url_for('dashboard.map_view') }}?callsign={{ station.callsign }}" style="color:var(--accent-green);font-size:12px;">View on map →</a>
            </div>
            {% endif %}
        </div>
    </div>
    
    <!-- Statistics -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">Statistics</span>
        </div>
        <div class="card-body" style="font-size:13px;">
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Packets (24h):</span>
                <span style="color:var(--accent-green);">{{ station.packets_24h }}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Packets (7d):</span>
                <span style="color:var(--accent-green);">{{ station.packets_7d }}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">Packets (total):</span>
                <span style="color:var(--accent-green);">{{ station.packets_total }}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;">
                <span style="color:var(--text-muted);">First seen:</span>
                <span>{{ station.first_seen | default('--') }}</span>
            </div>
        </div>
    </div>
</div>
{% elif error %}
<div style="color:var(--accent-yellow);text-align:center;padding:40px;">{{ error }}</div>
{% endif %}
```

- [ ] **Step 5: Create packets table partial**

```html
<!-- haminfo/templates/dashboard/partials/packets_table.html -->
{% if packets %}
<table style="width:100%;font-size:12px;border-collapse:collapse;">
    <thead>
        <tr style="border-bottom:1px solid var(--border-color);">
            <th style="text-align:left;padding:8px;color:var(--text-muted);">Type</th>
            <th style="text-align:left;padding:8px;color:var(--text-muted);">Details</th>
            <th style="text-align:right;padding:8px;color:var(--text-muted);">Time</th>
        </tr>
    </thead>
    <tbody>
        {% for packet in packets %}
        <tr style="border-bottom:1px solid var(--border-color);">
            <td style="padding:8px;">
                <span class="packet-type-{{ packet.packet_type }}" style="color:{% if packet.packet_type == 'position' %}var(--accent-green){% elif packet.packet_type == 'weather' %}var(--accent-cyan){% elif packet.packet_type == 'status' %}var(--accent-yellow){% else %}var(--text-primary){% endif %};">
                    {{ packet.packet_type | capitalize }}
                </span>
            </td>
            <td style="padding:8px;color:var(--text-secondary);font-family:monospace;">
                {% if packet.packet_type == 'position' %}
                {{ "%.4f"|format(packet.latitude) if packet.latitude else '--' }}, {{ "%.4f"|format(packet.longitude) if packet.longitude else '--' }}
                {% if packet.speed %} @ {{ packet.speed }}km/h{% endif %}
                {% else %}
                {{ packet.to_call | default('--') }}
                {% endif %}
            </td>
            <td style="padding:8px;text-align:right;color:var(--text-muted);">{{ packet.received_at | default('--') }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<div style="color:var(--text-muted);text-align:center;padding:20px;">No packets found</div>
{% endif %}
```

- [ ] **Step 6: Commit**

```bash
git add haminfo/templates/dashboard/partials/
git commit -m "feat(dashboard): add partial templates for HTMX"
```

---

### Task 13: Create Weather Page Template

**Files:**
- Create: `haminfo/templates/dashboard/weather.html`

- [ ] **Step 1: Create weather page template**

```html
<!-- haminfo/templates/dashboard/weather.html -->
{% extends "base.html" %}

{% block title %}APRS Dashboard - Weather{% endblock %}

{% block header_right %}
<input type="text" id="weather-search" placeholder="Search station..." style="width:180px;">
{% endblock %}

{% block content %}
<!-- Weather Stats -->
<div class="stats-grid" style="grid-template-columns:repeat(3,1fr);">
    <div class="stat-card cyan">
        <div class="stat-value" id="wx-station-count">--</div>
        <div class="stat-label">Active Stations</div>
    </div>
    <div class="stat-card yellow">
        <div class="stat-value" id="wx-report-count">--</div>
        <div class="stat-label">Reports (24h)</div>
    </div>
    <div class="stat-card green">
        <div class="stat-value" id="wx-avg-temp">--</div>
        <div class="stat-label">Avg Temperature</div>
    </div>
</div>

<!-- Weather Stations Grid -->
<div id="weather-grid"
     hx-get="{{ url_for('dashboard.api_weather_stations') }}"
     hx-trigger="load"
     hx-swap="innerHTML">
    <div style="color:var(--text-muted);text-align:center;padding:40px;">Loading weather stations...</div>
</div>
{% endblock %}

{% block scripts %}
<script>
    // Search functionality
    document.getElementById('weather-search')?.addEventListener('input', (e) => {
        const search = e.target.value.toLowerCase();
        document.querySelectorAll('#weather-grid .card').forEach(card => {
            const callsign = card.querySelector('a')?.textContent.toLowerCase() || '';
            card.style.display = callsign.includes(search) ? '' : 'none';
        });
    });
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/templates/dashboard/weather.html
git commit -m "feat(dashboard): add weather page template"
```

---

### Task 14: Create Map Page Template

**Files:**
- Create: `haminfo/templates/dashboard/map.html`

- [ ] **Step 1: Create map page template**

```html
<!-- haminfo/templates/dashboard/map.html -->
{% extends "base.html" %}

{% block title %}APRS Dashboard - Map{% endblock %}

{% block head_extra %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
    #map {
        height: calc(100vh - 120px);
        width: 100%;
        border-radius: 8px;
        background: var(--bg-card);
    }
    .leaflet-popup-content-wrapper {
        background: var(--bg-card);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
    }
    .leaflet-popup-tip {
        background: var(--bg-card);
    }
    .map-legend {
        position: absolute;
        bottom: 30px;
        left: 10px;
        background: rgba(22,33,62,0.95);
        border-radius: 6px;
        padding: 12px;
        z-index: 1000;
        font-size: 11px;
    }
    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
    }
    .legend-item:last-child {
        margin-bottom: 0;
    }
    .legend-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
    }
</style>
{% endblock %}

{% block header_right %}
<select id="station-type-filter">
    <option value="">All Station Types</option>
    <option value="position">Position Only</option>
    <option value="weather">Weather</option>
</select>
<span id="station-count" style="color:var(--accent-green);font-size:12px;">-- stations</span>
{% endblock %}

{% block content %}
<div style="position:relative;">
    <div id="map"></div>
    <div class="map-legend">
        <div class="legend-item">
            <div class="legend-dot" style="background:var(--accent-green);box-shadow:0 0 6px var(--accent-green);"></div>
            <span style="color:var(--text-secondary);">Position</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background:var(--accent-cyan);box-shadow:0 0 6px var(--accent-cyan);"></div>
            <span style="color:var(--text-secondary);">Weather</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background:var(--accent-yellow);box-shadow:0 0 6px var(--accent-yellow);"></div>
            <span style="color:var(--text-secondary);">Digipeater</span>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    // Initialize map
    const map = L.map('map').setView([3.14, 101.69], 5);  // Default to Malaysia
    
    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
    }).addTo(map);
    
    // Marker colors
    const markerColors = {
        'position': '#0f0',
        'weather': '#0ff',
        'digipeater': '#ff0',
        'default': '#0f0',
    };
    
    // Store markers for filtering
    let markers = [];
    
    function createMarker(feature) {
        const props = feature.properties;
        const coords = feature.geometry.coordinates;
        const color = markerColors[props.packet_type] || markerColors.default;
        
        const marker = L.circleMarker([coords[1], coords[0]], {
            radius: 6,
            fillColor: color,
            color: color,
            weight: 1,
            opacity: 1,
            fillOpacity: 0.8,
        });
        
        marker.bindPopup(`
            <div style="min-width:150px;">
                <div style="color:var(--accent-green);font-weight:bold;margin-bottom:8px;">${props.callsign}</div>
                <div style="font-size:11px;color:var(--text-secondary);">
                    <div>Position: ${coords[1].toFixed(4)}°, ${coords[0].toFixed(4)}°</div>
                    ${props.speed ? `<div>Speed: ${props.speed} km/h</div>` : ''}
                    <div>Last: ${props.last_seen || '--'}</div>
                </div>
                <div style="margin-top:8px;">
                    <a href="/station/${props.callsign}" style="color:var(--accent-cyan);font-size:11px;">View details →</a>
                </div>
            </div>
        `);
        
        marker.stationType = props.packet_type;
        return marker;
    }
    
    function loadStations(type = '') {
        const url = new URL('{{ url_for("dashboard.api_map_stations") }}', window.location.origin);
        if (type) url.searchParams.set('type', type);
        
        fetch(url)
            .then(r => r.json())
            .then(data => {
                // Clear existing markers
                markers.forEach(m => map.removeLayer(m));
                markers = [];
                
                // Add new markers
                data.features.forEach(feature => {
                    const marker = createMarker(feature);
                    marker.addTo(map);
                    markers.push(marker);
                });
                
                document.getElementById('station-count').textContent = `${markers.length} stations`;
            });
    }
    
    // Initial load
    loadStations();
    
    // Filter handler
    document.getElementById('station-type-filter').addEventListener('change', (e) => {
        loadStations(e.target.value);
    });
    
    // Handle callsign from URL
    const urlParams = new URLSearchParams(window.location.search);
    const callsign = urlParams.get('callsign');
    if (callsign) {
        // Zoom to specific station
        fetch(`/api/dashboard/station/${callsign}/json`)
            .then(r => r.json())
            .then(data => {
                if (data.latitude && data.longitude) {
                    map.setView([data.latitude, data.longitude], 12);
                }
            });
    }
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/templates/dashboard/map.html
git commit -m "feat(dashboard): add map page template with Leaflet"
```

---

### Task 15: Create Station Lookup Page Template

**Files:**
- Create: `haminfo/templates/dashboard/station.html`

- [ ] **Step 1: Create station lookup template**

```html
<!-- haminfo/templates/dashboard/station.html -->
{% extends "base.html" %}

{% block title %}APRS Dashboard - {{ callsign }}{% endblock %}

{% block header_right %}
<form action="{{ url_for('dashboard.station', callsign='_') }}" method="get" id="search-form" style="display:flex;gap:8px;">
    <input type="text" name="q" id="callsign-search" placeholder="Search callsign..." value="{{ callsign if callsign != 'lookup' else '' }}" style="width:180px;">
    <button type="submit">Search</button>
</form>
{% endblock %}

{% block content %}
{% if callsign and callsign != 'lookup' %}
<!-- Station Header -->
<div class="card" style="margin-bottom:20px;">
    <div class="card-body" style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
            <div style="color:var(--accent-green);font-size:32px;font-weight:bold;margin-bottom:4px;">{{ callsign }}</div>
            <div id="station-meta" style="color:var(--text-secondary);font-size:13px;">Loading...</div>
        </div>
        <div id="station-status" style="text-align:right;">
            <div style="color:var(--accent-green);font-size:12px;">● Loading...</div>
        </div>
    </div>
</div>

<!-- Station Detail (loaded via HTMX) -->
<div id="station-detail"
     hx-get="{{ url_for('dashboard.api_station_detail', callsign=callsign) }}"
     hx-trigger="load"
     hx-swap="innerHTML">
    <div style="color:var(--text-muted);text-align:center;padding:40px;">Loading station data...</div>
</div>

<!-- Recent Packets -->
<div class="card" style="margin-top:20px;">
    <div class="card-header">
        <span class="card-title">Recent Packets</span>
    </div>
    <div class="card-body"
         hx-get="{{ url_for('dashboard.api_station_packets', callsign=callsign) }}"
         hx-trigger="load"
         hx-swap="innerHTML">
        <div style="color:var(--text-muted);">Loading packets...</div>
    </div>
</div>

{% else %}
<!-- Search Landing -->
<div style="text-align:center;padding:60px 20px;">
    <div style="font-size:48px;margin-bottom:20px;">🔍</div>
    <h2 style="color:var(--text-primary);margin-bottom:12px;">Station Lookup</h2>
    <p style="color:var(--text-secondary);margin-bottom:24px;">Enter a callsign to view station details, location, and packet history.</p>
    <form action="{{ url_for('dashboard.station', callsign='_') }}" method="get" style="display:flex;gap:8px;justify-content:center;">
        <input type="text" name="q" placeholder="Enter callsign (e.g., 9M2PJU-9)" style="width:280px;font-size:16px;padding:12px;">
        <button type="submit" style="padding:12px 24px;font-size:16px;">Search</button>
    </form>
</div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
    // Handle search form
    document.getElementById('search-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        const callsign = document.getElementById('callsign-search').value.trim();
        if (callsign) {
            window.location.href = `/station/${encodeURIComponent(callsign)}`;
        }
    });
    
    {% if callsign and callsign != 'lookup' %}
    // Load station metadata
    fetch('/api/dashboard/station/{{ callsign }}/json')
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                document.getElementById('station-meta').textContent = 'Station not found';
                document.getElementById('station-status').innerHTML = '<div style="color:var(--accent-yellow);">Not found</div>';
            } else {
                const country = data.country_name ? `${data.country_name}` : 'Unknown';
                document.getElementById('station-meta').textContent = `${country}`;
                document.getElementById('station-status').innerHTML = `
                    <div style="color:var(--accent-green);font-size:12px;">● Last seen: ${data.last_seen || '--'}</div>
                    <div style="color:var(--text-muted);font-size:11px;margin-top:4px;">First seen: ${data.first_seen || '--'}</div>
                `;
            }
        });
    {% endif %}
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/templates/dashboard/station.html
git commit -m "feat(dashboard): add station lookup page template"
```

---

### Task 16: Update Routes to Handle Search

**Files:**
- Modify: `haminfo/dashboard/routes.py`

- [ ] **Step 1: Update station route to handle search**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/dashboard/routes.py
git commit -m "feat(dashboard): update routes to handle station search"
```

---

## Chunk 4: WebSocket Integration and Final Polish

### Task 17: Integrate WebSocket with MQTT Ingestion

**Files:**
- Modify: `haminfo/dashboard/websocket.py`
- Modify: `haminfo/mqtt/` (if needed for packet broadcasting)

- [ ] **Step 1: Add packet broadcast hook**

The WebSocket needs to receive packets from the MQTT ingestion process. This can be done by:
1. Adding a callback in the MQTT handler to call `broadcast_packet()`
2. Or polling the database for new packets (simpler but less real-time)

For simplicity, start with database polling:

```python
# haminfo/dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from flask_socketio import SocketIO, emit, join_room, leave_room
import gevent

from haminfo.dashboard.utils import format_packet_summary

socketio: SocketIO | None = None
_poll_greenlet = None
_last_packet_time: datetime | None = None


def init_socketio(app):
    """Initialize SocketIO with Flask app."""
    global socketio
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
    register_handlers()
    return socketio


def register_handlers():
    """Register SocketIO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        join_room('live_feed')
        emit('status', {'connected': True})
        start_polling()
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        leave_room('live_feed')
    
    @socketio.on('filter')
    def handle_filter(data):
        """Handle filter change from client."""
        country = data.get('country')
        emit('filter_applied', {'country': country})


def start_polling():
    """Start background polling for new packets using gevent."""
    global _poll_greenlet
    if _poll_greenlet is None or _poll_greenlet.dead:
        _poll_greenlet = gevent.spawn(poll_packets)


def poll_packets():
    """Poll database for new packets and broadcast."""
    global _last_packet_time
    
    from haminfo.db.models.db_session import get_session
    from haminfo.db.models.aprs_packet import APRSPacket
    
    while True:
        try:
            session = get_session()
            try:
                # Get packets newer than last check
                query = session.query(APRSPacket).order_by(
                    APRSPacket.received_at.desc()
                ).limit(10)
                
                if _last_packet_time:
                    query = query.filter(APRSPacket.received_at > _last_packet_time)
                
                packets = query.all()
                
                for packet in reversed(packets):  # Oldest first
                    packet_data = {
                        'from_call': packet.from_call,
                        'to_call': packet.to_call,
                        'packet_type': packet.packet_type,
                        'latitude': packet.latitude,
                        'longitude': packet.longitude,
                        'speed': packet.speed,
                        'received_at': packet.received_at.isoformat() if packet.received_at else None,
                    }
                    packet_data['summary'] = format_packet_summary(packet_data)
                    broadcast_packet(packet_data)
                    
                    if packet.received_at and (_last_packet_time is None or packet.received_at > _last_packet_time):
                        _last_packet_time = packet.received_at
                
            finally:
                session.close()
        except Exception as e:
            print(f"Polling error: {e}")
        
        time.sleep(2)  # Poll every 2 seconds
        gevent.sleep(2)  # Poll every 2 seconds (gevent-aware)


def broadcast_packet(packet_data: dict):
    """Broadcast new packet to all connected clients."""
    if socketio:
        socketio.emit('packet', packet_data, room='live_feed')
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/dashboard/websocket.py
git commit -m "feat(dashboard): add database polling for live feed"
```

---

### Task 18: Add Template Filter for Number Formatting

**Files:**
- Modify: `haminfo/dashboard/__init__.py`

- [ ] **Step 1: Add Jinja2 filter for number formatting**

```python
# haminfo/dashboard/__init__.py
"""APRS Dashboard blueprint."""

from flask import Blueprint

dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='../templates/dashboard',
    static_folder='../static',
    static_url_path='/static'
)


@dashboard_bp.app_template_filter('format_number')
def format_number(value):
    """Format number with thousand separators."""
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value


from haminfo.dashboard import routes  # noqa: F401, E402
from haminfo.dashboard import api  # noqa: F401, E402
```

- [ ] **Step 2: Commit**

```bash
git add haminfo/dashboard/__init__.py
git commit -m "feat(dashboard): add number formatting template filter"
```

---

### Task 19: Create Static CSS File

**Files:**
- Create: `haminfo/static/css/dashboard.css`

- [ ] **Step 1: Create static directory and CSS file**

```bash
mkdir -p ~/devel/mine/hamradio/haminfo/haminfo/static/css
```

- [ ] **Step 2: Create dashboard.css**

```css
/* haminfo/static/css/dashboard.css */
/* Additional dashboard styles beyond base template */

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}

.live-feed-item {
    animation: fadeIn 0.3s ease-out;
}

/* Leaderboard */
.leaderboard-item:hover {
    background: var(--bg-card-hover);
    margin: 0 -8px;
    padding: 8px;
    border-radius: 4px;
}

/* Weather cards */
.weather-card:hover {
    border-color: var(--accent-green);
    transform: translateY(-2px);
    transition: all 0.2s;
}

/* Map markers pulse */
.leaflet-marker-icon {
    animation: markerPulse 2s infinite;
}

@keyframes markerPulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .card-body {
        padding: 12px;
    }
    
    .stat-value {
        font-size: 24px;
    }
}

/* HTMX loading indicator */
.htmx-request .htmx-indicator {
    opacity: 1;
}

.htmx-indicator {
    opacity: 0;
    transition: opacity 200ms ease-in;
}
```

- [ ] **Step 3: Commit**

```bash
git add haminfo/static/
git commit -m "feat(dashboard): add static CSS file"
```

---

### Task 20: Run Full Test Suite

**Files:** None (verification only)

- [ ] **Step 1: Run all dashboard tests**

Run: `cd ~/devel/mine/hamradio/haminfo && pytest tests/test_dashboard*.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run linting**

Run: `cd ~/devel/mine/hamradio/haminfo && ruff check haminfo/dashboard/`
Expected: No errors (or fix any issues)

- [ ] **Step 3: Test manually**

Run: `cd ~/devel/mine/hamradio/haminfo && python -m haminfo.flask`
Open: http://localhost:5000/
Verify: Dashboard loads with dark theme

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(dashboard): complete APRS dashboard implementation"
```

---

## Summary

This plan implements the APRS Dashboard in 20 tasks across 4 chunks:

1. **Chunk 1 (Tasks 1-6):** Foundation - dependencies, blueprint, base template
2. **Chunk 2 (Tasks 7-11):** Database queries and API endpoints
3. **Chunk 3 (Tasks 12-16):** Page templates (weather, map, station lookup)
4. **Chunk 4 (Tasks 17-20):** WebSocket integration and polish

Each task follows TDD where applicable, with frequent commits for easy rollback.
