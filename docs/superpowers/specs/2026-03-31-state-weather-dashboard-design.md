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
4. Update in batches of 100 with rate limiting
5. Log failures for manual review

### On-Insert Geocoding

When a new weather station is created with `state IS NULL`, geocode via OpenCage and populate the column. This happens in the station creation flow.

## Route Structure

| Route | Purpose |
|-------|---------|
| `/weather/states` | Landing page with clickable US map |
| `/weather/state/<state_code>` | State dashboard (e.g., `/weather/state/VA`) |

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
- Auto-refresh every 5 minutes via HTMX polling

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

```sql
SELECT 
    AVG(temperature) as avg_temp,
    MIN(temperature) as min_temp, 
    MAX(temperature) as max_temp,
    AVG(humidity) as avg_humidity,
    AVG(pressure) as avg_pressure,
    AVG(wind_speed) as avg_wind,
    MAX(wind_speed) as max_wind,
    MAX(wind_gust) as max_gust
FROM latest_readings_for_state(:state_code)
```

### 24h Trend Data

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
