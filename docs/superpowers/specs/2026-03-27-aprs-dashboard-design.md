# APRS Dashboard Design Specification

## Overview

A web dashboard for displaying APRS-IS network statistics, inspired by [aprsmy.hamradio.my](https://aprsmy.hamradio.my/). The dashboard provides real-time packet monitoring, station statistics, weather reports, and geographic visualization using data from the existing haminfo PostgreSQL/PostGIS database.

## Goals

- Provide real-time visibility into APRS-IS traffic
- Display statistics by callsign, country, and time period
- Show weather station data from APRS weather reports
- Enable station lookup and historical packet viewing
- User-configurable geographic filtering

## Non-Goals

- Admin/authentication functionality (public read-only dashboard)
- Packet injection or APRS-IS gateway features
- Mobile-first design (desktop-primary, responsive secondary)

## Architecture

### Tech Stack

- **Backend**: Extend existing Flask application (`haminfo/flask.py`)
- **Templates**: Jinja2 with server-side rendering
- **Interactivity**: HTMX for partial page updates
- **Real-time**: Flask-SocketIO for WebSocket live feed
- **Charts**: Chart.js for visualizations
- **Maps**: Leaflet with OpenStreetMap tiles
- **Styling**: Custom CSS with dark theme (no framework)

### Data Sources

Existing haminfo database tables:
- `aprs_packet` - APRS packet history (from_call, to_call, packet_type, location, etc.)
- `weather_station` - Weather station metadata (callsign, location, symbol)
- `weather_report` - Weather observations (temperature, humidity, pressure, wind, rain)
- `station` - Repeater database (secondary, for reference)

### URL Structure

| Route | Description |
|-------|-------------|
| `/` | Main dashboard |
| `/weather` | Weather stations page |
| `/map` | Interactive station map |
| `/station/<callsign>` | Station lookup/detail page |
| `/api/ws` | WebSocket endpoint for live feed |

## Pages

### 1. Main Dashboard (`/`)

**Layout**: Dark theme (#1a1a2e background, #16213e cards)

**Header**:
- Logo/title: "APRS Dashboard"
- Navigation: Home | Weather | Map | Lookup
- Country filter dropdown (user-configurable)
- Live indicator

**Stats Row** (4 cards):
- Total Packets (24h) - green accent
- Unique Stations - cyan accent
- Countries - yellow accent
- Weather Stations - magenta accent

**Content Grid** (2x2):

1. **Live Traffic Feed** (WebSocket-powered)
   - Scrolling list of incoming packets
   - Color-coded by packet type (position=green, weather=cyan, status=yellow, message=white)
   - Format: `CALLSIGN -> Type: Summary`
   - Auto-scroll with pause on hover

2. **Hourly Distribution Chart**
   - Bar chart showing packet counts by hour (last 24h)
   - Chart.js with dark theme styling

3. **Top Stations Leaderboard**
   - Top 10 callsigns by packet count (24h)
   - Shows callsign, packet count, device/TOCALL

4. **Countries Breakdown**
   - Top countries by packet count
   - Flag emoji + country name + count
   - Derived from callsign prefix

### 2. Weather Page (`/weather`)

**Stats Row** (3 cards):
- Active Weather Stations count
- Reports (24h) count
- Average Temperature

**Weather Station Grid**:
- Card per station showing:
  - Callsign (linked to lookup page)
  - Last update time
  - Temperature, Humidity (2-column grid)
  - Wind speed/direction, Pressure
  - Rain 1h, Rain 24h
  - Location (city/country)

**Features**:
- Search/filter by callsign
- Sort by last update, temperature, etc.
- HTMX pagination

### 3. Map Page (`/map`)

**Full-width Leaflet map** with:
- Station markers color-coded by type:
  - Green: Position packets
  - Cyan: Weather stations
  - Yellow: Digipeaters
- Click popup showing:
  - Callsign
  - Position (lat/lon)
  - Speed (if mobile)
  - Last update
  - Link to detail page

**Controls**:
- Station type filter dropdown
- Station count display
- Legend (bottom-left)
- Zoom controls

**Data loading**:
- Initial load: stations active in last 24h
- Cluster markers when zoomed out
- HTMX refresh button

### 4. Station Lookup Page (`/station/<callsign>`)

**Header**:
- Search box (pre-filled with current callsign)
- Search button

**Station Header**:
- Large callsign display
- Station type + country flag
- Symbol info (APRS symbol table)
- Last seen / First seen timestamps

**Content Grid** (2 columns):

1. **Current Position Card**:
   - Latitude, Longitude
   - Altitude, Speed, Course
   - Link to view on map

2. **Statistics Card**:
   - Packet counts (24h, 7d, total)
   - Device/TOCALL
   - Path info

3. **Recent Packets Table** (full width):
   - Packet type, summary, timestamp
   - Last 50 packets
   - Pagination via HTMX

## WebSocket Protocol

**Endpoint**: `/api/ws`

**Server -> Client Messages**:
```json
{
  "type": "packet",
  "data": {
    "from_call": "9M2PJU-9",
    "to_call": "APRS",
    "packet_type": "position",
    "summary": "3.1234, 101.4567 @ 48km/h",
    "timestamp": "2026-03-27T12:34:56Z"
  }
}
```

**Client -> Server Messages**:
```json
{
  "type": "filter",
  "country": "MY"
}
```

## API Endpoints (New)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | Dashboard statistics |
| `/api/packets/recent` | GET | Recent packets (paginated) |
| `/api/packets/hourly` | GET | Hourly distribution data |
| `/api/stations/top` | GET | Top stations leaderboard |
| `/api/stations/countries` | GET | Country breakdown |
| `/api/weather/stations` | GET | Weather stations list |
| `/api/weather/reports/<callsign>` | GET | Weather reports for station |
| `/api/map/stations` | GET | Stations for map (GeoJSON) |
| `/api/station/<callsign>` | GET | Station detail |
| `/api/station/<callsign>/packets` | GET | Station packet history |

## Styling

### Color Palette

- Background: `#1a1a2e`
- Card background: `#16213e`
- Card border: `#2a2a4e`
- Primary accent (green): `#0f0` / `#00ff00`
- Secondary accent (cyan): `#0ff` / `#00ffff`
- Tertiary accent (yellow): `#ff0` / `#ffff00`
- Quaternary accent (magenta): `#f0f` / `#ff00ff`
- Text primary: `#fff`
- Text secondary: `#888`
- Text muted: `#666`

### Typography

- Font family: System UI stack
- Monospace for callsigns and packet data
- Stats: 24-28px bold
- Headings: 12-16px bold
- Body: 10-12px

## Dependencies (New)

```
flask-socketio>=5.3.0
python-socketio>=5.10.0
gevent>=23.9.0  # or eventlet
```

Frontend (CDN):
- HTMX 1.9.x
- Chart.js 4.x
- Leaflet 1.9.x

## File Structure

```
haminfo/
  templates/
    dashboard/
      base.html          # Dark theme base template
      index.html         # Main dashboard
      weather.html       # Weather page
      map.html           # Map page
      station.html       # Station lookup
      partials/
        live_feed.html   # HTMX partial
        stats.html       # HTMX partial
        top_stations.html
        countries.html
  static/
    css/
      dashboard.css      # Dark theme styles
    js/
      dashboard.js       # WebSocket client, Chart.js init
  flask.py               # Add new routes (extend existing)
```

## Testing

- Unit tests for new API endpoints
- WebSocket connection tests
- Template rendering tests
- Browser testing for live feed functionality

## Future Considerations

- Mobile-responsive improvements
- Dark/light theme toggle
- Custom time range selection
- Export functionality (CSV/JSON)
- Alerts/notifications for specific callsigns
