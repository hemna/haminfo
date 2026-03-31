# State Weather Dashboard Design Specification

**Date**: 2026-03-31  
**Status**: Draft  
**Author**: Claude + User collaboration

## Overview

A statewide weather trend dashboard providing operational awareness, trend analysis, and alert detection for APRS weather stations organized by US state and other country subdivisions.

## Goals

1. **Operational Awareness**: See current weather conditions across a state at a glance
2. **Trend Analysis**: Track how weather patterns change over the last 24 hours
3. **Alert Detection**: Surface severe weather thresholds and regional patterns on the dashboard

## Non-Goals

- Push notifications or APRS message delivery (alerts are dashboard-only)
- User preferences or saved states
- Historical data beyond 24 hours
- Mobile app (web dashboard only)

## Schema Changes

### Add `state` Column

```sql
ALTER TABLE weather_station ADD COLUMN state VARCHAR(10);
CREATE INDEX idx_weather_station_state ON weather_station(state);
CREATE INDEX idx_weather_station_country_state ON weather_station(country_code, state);
```

**Column Values**:
- US: Two-letter state codes (`VA`, `CA`, `TX`)
- Canada: Province codes (`ON`, `BC`, `QC`)
- Australia: State codes (`NSW`, `VIC`, `QLD`)
- Other countries: NULL (can be populated later)

### Backfill Strategy

1. Query stations where `state IS NULL` and lat/lon are valid
2. Call OpenCage API with coordinates (already integrated in project)
3. Extract state/province from `components.state_code` or `components.state`
4. Update in batches of 100 with rate limiting (OpenCage free tier: 2,500 requests/day)
5. Log failures for manual review
6. If rate limit hit, sleep until next day or prompt to continue manually

**Error Handling**:
- API timeout: Retry up to 3 times with exponential backoff
- Invalid response: Log and skip station, continue with next
- Rate limit exceeded: Save progress, exit with message to resume later

### On-Insert Geocoding

When a new weather station is created with `state IS NULL`, geocode via OpenCage and populate the column. This happens in `haminfo/db/models/weather_station.py` or the ingestion code that creates stations.

**Error Handling**:
- If OpenCage unavailable, leave `state` as NULL (non-blocking)
- Log failures; periodic batch job can retry NULLs later

## Route Structure

| Route | Purpose |
|-------|---------|
| `/weather/states` | Landing page with clickable US map |
| `/weather/state/<state_code>` | State dashboard (e.g., `/weather/state/VA`) |
| `/api/dashboard/state/<state_code>` | State data JSON API |
| `/api/dashboard/state/<state_code>/stations` | Stations list HTMX partial |
| `/api/dashboard/state/<state_code>/summary` | Summary cards HTMX partial |
| `/api/dashboard/state/<state_code>/alerts` | Alerts banner HTMX partial |
| `/api/dashboard/state/<state_code>/trends` | Trend data JSON for charts |

**URL Behavior**:
- State codes uppercase in URLs
- Case-insensitive matching (redirect `va` → `VA`)
- Invalid codes show "State not found" with link to map

## Navigation Integration

- **Main nav**: Add "States" link next to "Weather"
- **Weather page**: Add "View by State" link
- **Station detail page**: Add "View [State Name] Weather" link when station has state

## States Landing Page (`/weather/states`)

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: "Weather by State"                                     │
│  Subtitle: "Select a state to view detailed weather conditions" │
├─────────────────────────────────────────────────────────────────┤
│                    INTERACTIVE US MAP                           │
│                    (hover for info, click to drill)             │
│                                                                 │
│  Legend: [●] Has stations  [○] No stations                      │
├─────────────────────────────────────────────────────────────────┤
│  QUICK STATS                                                    │
│  Total US Stations: 1,623 │ States with coverage: 48            │
├─────────────────────────────────────────────────────────────────┤
│  STATES WITH ACTIVE ALERTS                                      │
│  ⚠️ Texas (3) - High wind warnings                              │
│  ⚠️ Florida (2) - Heavy rain                                    │
├─────────────────────────────────────────────────────────────────┤
│  ALL STATES (sortable table)                                    │
│  State | Stations | Avg Temp | Alerts                           │
└─────────────────────────────────────────────────────────────────┘
```

### Map Behavior

- SVG map with each state as a clickable path
- **Hover**: Tooltip with state name, station count, avg temp
- **Click**: Navigate to `/weather/state/{code}`
- **Coloring**: Green gradient by station count; alert states get orange/red border

## State Dashboard (`/weather/state/<code>`)

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: "Virginia Weather"                                     │
│  Subtitle: "47 stations • Last updated 2 min ago"               │
│  [Back to States Map]                                           │
├─────────────────────────────────────────────────────────────────┤
│  ALERTS BANNER (if any active)                                  │
│  ⚠️ High Wind Warning: 3 stations reporting >50mph gusts        │
├───────────────────────────────────┬─────────────────────────────┤
│                                   │  SUMMARY CARDS              │
│      STATE MAP                    │  Temp: 72°F (Hi:85 Lo:58)   │
│      (stations as markers)        │  Humidity: 65% (45-89%)     │
│      • colored by temp            │  Pressure: 1018mb ↑rising   │
│      • click for popup            │  Wind: 8mph (Max: 32)       │
├───────────────────────────────────┴─────────────────────────────┤
│  TREND CHARTS (24h)                                             │
│  [Temperature] [Pressure] [Wind] [Humidity]                     │
│  (line charts with avg/min/max bands)                           │
├─────────────────────────────────────────────────────────────────┤
│  STATION LIST (sortable table)                                  │
│  Callsign | Temp | Humidity | Pressure | Wind | Last Report     │
└─────────────────────────────────────────────────────────────────┘
```

### Interactivity

- Map markers clickable → popup with station details + link to station page
- Summary cards show tooltip with which station has min/max
- Auto-refresh via HTMX polling:
  - Summary cards: `hx-get="/api/dashboard/state/{code}/summary" hx-trigger="every 5m" hx-swap="innerHTML"`
  - Alerts banner: `hx-get="/api/dashboard/state/{code}/alerts" hx-trigger="every 2m" hx-swap="innerHTML"`
  - Station list: `hx-get="/api/dashboard/state/{code}/stations" hx-trigger="every 5m" hx-swap="innerHTML"`

### Empty State Handling

- **No stations in state**: Show message "No APRS weather stations found in [State]. Check back later or view nearby states."
- **Station exists but no recent data**: Show station on map with "No recent data" indicator

## Alert Detection

### Severe Weather Thresholds (Individual Station)

| Condition | Threshold | Level |
|-----------|-----------|-------|
| High Wind | Sustained > 40 mph | Warning |
| Extreme Wind | Sustained > 60 mph or Gust > 75 mph | Severe |
| Extreme Heat | > 100°F (38°C) | Warning |
| Extreme Cold | < 10°F (-12°C) | Warning |
| Rapid Pressure Drop | > 6 mbar in 3 hours | Warning |
| Heavy Rain | > 1 inch in 1 hour | Warning |

### Regional Patterns (Multiple Stations)

| Pattern | Criteria | Alert |
|---------|----------|-------|
| Widespread Wind | 3+ stations within 50mi reporting > 40 mph | Regional Wind Alert |
| Heat Wave | 5+ stations > 95°F | Heat Advisory |
| Cold Snap | 5+ stations < 20°F | Cold Advisory |
| Storm Front | 3+ stations with pressure drop > 4 mbar/3hr | Storm Approaching |

**Regional Pattern Detection Algorithm**:

For distance-based patterns (e.g., "within 50mi"), use PostGIS:

```sql
-- Find clusters of stations with high wind
WITH high_wind_stations AS (
    SELECT ws.id, ws.callsign, ws.location, wr.wind_speed
    FROM weather_station ws
    JOIN weather_report wr ON wr.weather_station_id = ws.id
    WHERE ws.state = :state_code
      AND wr.time > NOW() - INTERVAL '1 hour'
      AND wr.wind_speed > 40
)
SELECT a.callsign, COUNT(b.id) as nearby_count
FROM high_wind_stations a
JOIN high_wind_stations b 
  ON ST_DWithin(a.location, b.location, 80467)  -- 50 miles in meters
  AND a.id != b.id
GROUP BY a.id, a.callsign
HAVING COUNT(b.id) >= 2  -- 3+ total including self
```

For count-based patterns (heat wave, cold snap), simple aggregation suffices.

### Processing

1. On page load, query last 3 hours of data for state's stations
2. Check individual thresholds
3. Check regional patterns (group nearby stations)
4. Aggregate and rank alerts (Severe > Warning > Advisory)
5. Display in banner; highlight affected stations on map

Alerts are computed fresh on each page load—no persistence required.

## Data Queries

### State Stations with Latest Readings

```sql
SELECT ws.*, wr.temperature, wr.humidity, wr.pressure, 
       wr.wind_speed, wr.wind_gust, wr.wind_direction,
       wr.rain_1h, wr.time as last_report
FROM weather_station ws
JOIN LATERAL (
    SELECT * FROM weather_report 
    WHERE weather_station_id = ws.id 
    ORDER BY time DESC LIMIT 1
) wr ON true
WHERE ws.state = :state_code AND ws.country_code = 'us'
```

### State Aggregates (Current)

Computed from the State Stations query result (no separate DB function needed):

```python
# In Python after fetching state stations with latest readings
def compute_state_aggregates(stations):
    temps = [s.temperature for s in stations if s.temperature is not None]
    return {
        'avg_temp': sum(temps) / len(temps) if temps else None,
        'min_temp': min(temps) if temps else None,
        'max_temp': max(temps) if temps else None,
        # ... similar for humidity, pressure, wind
    }
```

### 24h Trend Data

Note: This project uses TimescaleDB (evident from `time_bucket` usage elsewhere and hypertable chunks in weather_report). If TimescaleDB is not available, replace `time_bucket` with `date_trunc('hour', time)`.

```sql
SELECT 
    time_bucket('1 hour', time) as hour,
    AVG(temperature) as avg_temp,
    MIN(temperature) as min_temp,
    MAX(temperature) as max_temp,
    AVG(pressure) as avg_pressure,
    AVG(humidity) as avg_humidity,
    AVG(wind_speed) as avg_wind
FROM weather_report wr
JOIN weather_station ws ON wr.weather_station_id = ws.id
WHERE ws.state = :state_code 
  AND ws.country_code = 'us'
  AND wr.time > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour
```

### Trend Chart Data Contract

The `/api/dashboard/state/<code>/trends` endpoint returns JSON for Chart.js:

```json
{
  "labels": ["00:00", "01:00", "02:00", ...],  // 24 hourly labels
  "temperature": {
    "avg": [65.2, 64.8, 63.1, ...],
    "min": [58.0, 57.2, 55.8, ...],
    "max": [72.1, 71.5, 70.2, ...]
  },
  "pressure": {
    "avg": [1018.2, 1018.5, 1018.8, ...]
  },
  "humidity": {
    "avg": [65, 68, 72, ...]
  },
  "wind": {
    "avg": [8.2, 7.5, 6.8, ...]
  }
}
```

Charts rendered client-side using Chart.js line charts with fill for min/max bands (existing pattern in weather_reports_table.html).

### Caching Strategy

| Data | TTL | Key Pattern |
|------|-----|-------------|
| State station list | 5 min | `state:{code}:stations` |
| Current aggregates | 2 min | `state:{code}:summary` |
| 24h trend data | 5 min | `state:{code}:trends` |
| Alert detection | 2 min | `state:{code}:alerts` |

Uses existing memcached infrastructure with `@cached` decorator.

## Implementation Components

### New Files

| File | Purpose |
|------|---------|
| `queries.py` | Add `get_state_stations`, `get_state_summary`, `get_state_trends`, `detect_state_alerts` |
| `api.py` | Add API routes for state data |
| `routes.py` | Add page routes |
| `templates/dashboard/states.html` | US map landing page |
| `templates/dashboard/state_detail.html` | State dashboard |
| `templates/dashboard/partials/state_map.html` | State map partial |
| `templates/dashboard/partials/state_summary.html` | Summary cards partial |
| `templates/dashboard/partials/state_alerts.html` | Alerts banner partial |
| `templates/dashboard/partials/state_trends.html` | Trend charts partial |
| `templates/dashboard/partials/state_stations_table.html` | Station list |
| `utils.py` | Add geocoding helper, state name lookup |
| `static/us-states.svg` | US map SVG |

### Database Migration

| File | Purpose |
|------|---------|
| `alembic/versions/xxx_add_state_column.py` | Add state column + indexes |

### One-time Scripts

| File | Purpose |
|------|---------|
| `scripts/backfill_station_states.py` | Backfill via OpenCage |

### Modifications to Existing Files

| File | Change |
|------|--------|
| `templates/dashboard/base.html` | Add "States" to nav |
| `templates/dashboard/station.html` | Add "View [State] Weather" link |
| `templates/dashboard/weather.html` | Add "View by State" link |
| Station creation code | Add geocoding on insert |

## Technical Notes

- **Temperature units**: Database stores Fahrenheit; convert to Celsius for display (existing pattern)
- **Map library**: Inline SVG for US map (no external dependencies)
- **Charts**: Chart.js (already used in dashboard)
- **State boundaries**: For the state detail map, use OpenStreetMap embed or Leaflet with state GeoJSON

## Future Considerations

- International region pages (infrastructure supports it)
- Push alerts via APRS messages
- Extended time ranges (7d, 30d)
- Station comparison view
- Export/download functionality
