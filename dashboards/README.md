# Grafana Dashboards for HamInfo

This directory contains Grafana dashboard JSON files for visualizing data from the HamInfo database.

## Dashboards

1. **stations-dashboard.json** - Dashboard for repeater stations
   - Total stations count
   - Stations by frequency band, state, country
   - Operational status distribution
   - Feature distribution (ARES, RACES, SKYWARN, etc.)
   - Stations added over time

2. **weather-stations-dashboard.json** - Dashboard for weather stations
   - Total weather stations count
   - Stations by country
   - Top stations by report count
   - Weather reports over time
   - Average temperature and humidity by station

3. **weather-reports-dashboard.json** - Dashboard for weather reports
   - Total weather reports count
   - Temperature, humidity, pressure over time
   - Wind speed and gusts
   - Rainfall metrics (1h, 24h)
   - Reports per hour

4. **aprs-packet-dashboard.json** - Dashboard for APRS packets
   - Total packets and recent activity
   - Packets by type (weather, position, message, etc.)
   - Top callsigns
   - Packets received over time
   - Packet format distribution

5. **request-dashboard.json** - Dashboard for API requests
   - Total requests and recent activity
   - Requests over time
   - Requests by band and filter
   - Top requesting callsigns
   - Request count distribution

6. **wx-request-dashboard.json** - Dashboard for weather API requests
   - Total weather requests and recent activity
   - Requests over time
   - Top requesting callsigns
   - Average stations per request

## Setup Instructions

### 1. Install Grafana

Follow the [Grafana installation guide](https://grafana.com/docs/grafana/latest/setup-grafana/installation/) for your platform.

### 2. Install SQLite Datasource Plugin

These dashboards use SQLite as the datasource. Install the SQLite plugin:

```bash
grafana-cli plugins install frser-sqlite-datasource
```

Or install via Grafana UI: Configuration → Plugins → Search for "SQLite" → Install

### 3. Configure SQLite Datasource

1. Go to Configuration → Data Sources → Add data source
2. Select "SQLite"
3. Configure:
   - **Name**: `haminfo` (must match the datasource UID in the dashboards)
   - **Path**: Path to your HamInfo SQLite database file
   - **Path Type**: File
4. Click "Save & Test"

### 4. Import Dashboards

#### Option A: Via Grafana UI

1. Go to Dashboards → Import
2. Click "Upload JSON file"
3. Select one of the dashboard JSON files from this directory
4. Review the import settings
5. Click "Import"

#### Option B: Via Grafana API

```bash
# Set your Grafana API key and URL
export GRAFANA_API_KEY="your-api-key"
export GRAFANA_URL="http://localhost:3000"

# Import each dashboard
for dashboard in *.json; do
  curl -X POST \
    -H "Authorization: Bearer $GRAFANA_API_KEY" \
    -H "Content-Type: application/json" \
    -d @$dashboard \
    "$GRAFANA_URL/api/dashboards/db"
done
```

#### Option C: Copy to Grafana Dashboards Directory

```bash
# Copy dashboards to Grafana's provisioning directory
cp *.json /etc/grafana/provisioning/dashboards/

# Or on macOS with Homebrew
cp *.json /usr/local/share/grafana/dashboards/
```

Then restart Grafana.

## Database Schema Notes

The dashboards assume the following table names:
- `station` (not `stations`)
- `weather_station` (not `weather_stations`)
- `weather_report` (not `weather_reports`)
- `aprs_packet`
- `request`
- `wx_request`

If your database uses different table names, you'll need to update the SQL queries in the dashboard JSON files.

## Customization

All dashboards are editable in Grafana. You can:
- Modify time ranges
- Add or remove panels
- Change visualization types
- Adjust refresh intervals
- Add variables for filtering

## Troubleshooting

### "Datasource not found" error

Make sure the datasource UID in Grafana matches `haminfo` (as configured in the dashboards). You can change the datasource UID in the dashboard JSON files if needed.

### SQL errors

- Verify your database file path is correct
- Check that the table names match your schema
- Ensure SQLite plugin has read permissions to the database file

### No data showing

- Check that your database contains data
- Verify the time range in the dashboard
- Check Grafana logs for SQL errors

## Dashboard Refresh

All dashboards are configured to refresh every 30 seconds. You can adjust this in the dashboard settings or in the JSON files (change the `refresh` field).

## Time Range

Default time range is set to "Last 7 days". You can change this in the dashboard or modify the `time.from` field in the JSON files.

