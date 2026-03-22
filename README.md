# Haminfo

[![Build Status](https://github.com/hemna/haminfo/actions/workflows/build.yml/badge.svg)](https://github.com/hemna/haminfo/actions/workflows/build.yml)
[![Docker Image](https://github.com/hemna/haminfo/actions/workflows/docker-image.yml/badge.svg)](https://github.com/hemna/haminfo/actions/workflows/docker-image.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A comprehensive ham radio information service providing REST APIs for querying repeaters, weather stations, and APRS packet data. Built with Python, Flask, PostgreSQL/PostGIS, and Docker.

## Features

- **Repeater Database** - Query 40,000+ repeaters from [RepeaterBook](https://repeaterbook.com) with automatic monthly updates
- **Geospatial Queries** - Find nearest repeaters or weather stations to any location using PostGIS
- **APRS Integration** - Real-time APRS packet ingestion via MQTT with position tracking
- **Weather Stations** - Track APRS weather stations and their reports
- **aprs.fi Compatible API** - Drop-in replacement for aprs.fi location queries
- **MCP Server** - AI agent access to the database via Model Context Protocol
- **Docker Deployment** - Production-ready Docker Compose setup with automatic migrations

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/hemna/haminfo.git
cd haminfo/docker

# Copy and edit the environment file
cp env.example .env
vim .env  # Set your passwords and API keys

# Copy and edit the config file
cp haminfo.conf.example data/config/haminfo.conf
vim data/config/haminfo.conf

# Start the services
docker compose up -d

# Initialize with repeater data (first time only)
docker compose exec haminfo_api haminfo rb fetch-all-repeaters --force
```

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[test]"

# Set up PostgreSQL with PostGIS
# (See Database Setup section below)

# Run the API
haminfo_api --config haminfo.conf
```

## Configuration

Haminfo uses [oslo.config](https://docs.openstack.org/oslo.config/latest/) for configuration. Create a config file at `~/.config/haminfo/haminfo.conf` or specify with `--config`.

### Minimal Configuration

```ini
[database]
connection = postgresql://haminfo:password@localhost:5432/haminfo

[web]
host_ip = 0.0.0.0
host_port = 8081
api_key = YOUR_API_KEY_HERE

[memcached]
url = 127.0.0.1:11211
```

### Generate an API Key

```bash
haminfo generate-token
# Output: Generated API key: Abc123...
# Add this to your config file under [web] api_key
```

### Full Configuration Reference

<details>
<summary>Click to expand full configuration options</summary>

```ini
[DEFAULT]
trace_enabled = false

[database]
# PostgreSQL connection URL (required)
connection = postgresql://user:pass@host:5432/haminfo
# Enable SQL query debugging
debug = false

[memcached]
# Memcached server URL
url = 127.0.0.1:11211
# Cache expiration time in seconds
expire_time = 300

[web]
# IP address to bind to
host_ip = 0.0.0.0
# Port to listen on
host_port = 8081
# API key for authentication (required)
api_key = YOUR_API_KEY
# Sentry error tracking
sentry_enable = false
sentry_url = https://xxx@sentry.io/xxx

[mqtt]
# MQTT broker for APRS packet ingestion
host_ip = mqtt.example.com
host_port = 1883
user = haminfo
password = mqtt_password
topic = aprs/weather
keepalive_file = /tmp/haminfo_mqtt_keepalive.json

[repeaterbook]
# RepeaterBook API token (get from repeaterbook.com)
api_token = app_xxxxx

[logging]
logfile = /var/log/haminfo/haminfo.log
log_level = INFO
enable_console_stdout = true
```

</details>

## API Reference

All endpoints require authentication via the `X-Api-Key` header unless noted otherwise.

### Find Nearest Repeaters

```bash
curl -X POST http://localhost:8081/nearest \
  -H "X-Api-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 38.9072,
    "lon": -77.0369,
    "count": 5,
    "band": "2m",
    "filters": "dmr,echolink"
  }'
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | float | Yes | Latitude (-90 to 90) |
| `lon` | float | Yes | Longitude (-180 to 180) |
| `count` | int | No | Number of results (1-100, default 1) |
| `band` | string | No | Filter by band: `6m`, `2m`, `1.25m`, `70cm`, `33cm`, `23cm` |
| `filters` | string | No | Comma-separated: `ares`, `races`, `skywarn`, `allstar`, `echolink`, `irlp`, `wires`, `fm`, `dmr`, `dstar` |

**Response:**
```json
[
  {
    "callsign": "W3ABC",
    "frequency": "146.8200",
    "offset": "-0.6000",
    "uplink_tone": "100.0",
    "downlink_tone": "100.0",
    "state": "Virginia",
    "county": "Fairfax",
    "nearest_city": "Falls Church",
    "distance": "5234.50",
    "distance_units": "meters",
    "degrees": 45,
    "direction": "NE",
    "fm_analog": true,
    "dmr": false,
    "dstar": false,
    "echolink_node": true,
    "operational_status": "On-air"
  }
]
```

### Find Nearest Weather Stations

```bash
curl -X POST http://localhost:8081/wxnearest \
  -H "X-Api-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"lat": 38.9072, "lon": -77.0369, "count": 3}'
```

**Response includes latest weather report:**
```json
[
  {
    "callsign": "EW1234",
    "latitude": 38.91,
    "longitude": -77.04,
    "distance": "1234.50",
    "direction": "N",
    "report": {
      "temperature": 72.5,
      "humidity": 65,
      "pressure": 1013.25,
      "wind_direction": 180,
      "wind_speed": 5.5,
      "wind_gust": 12.0,
      "rain_1h": 0.0,
      "rain_24h": 0.25,
      "time": "2024-03-22T10:30:00Z"
    }
  }
]
```

### APRS Location Query (aprs.fi Compatible)

```bash
curl "http://localhost:8081/api/get?apikey=YOUR_KEY&what=loc&name=W3ABC,K4XYZ"
```

**Response (aprs.fi format):**
```json
{
  "command": "get",
  "result": "ok",
  "what": "loc",
  "found": 2,
  "entries": [
    {
      "name": "W3ABC",
      "type": "l",
      "time": "1711111111",
      "lat": "38.90000",
      "lng": "-77.00000",
      "altitude": "100",
      "course": "90",
      "speed": "5",
      "comment": "Mobile"
    }
  ]
}
```

### Other Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/test` | Yes | Health check, returns version |
| `GET` | `/stats` | No | APRS packet statistics |
| `POST` | `/stations` | No | Query by callsigns or repeater IDs |
| `GET` | `/wxstations` | Yes | List all weather stations |
| `GET` | `/wxstation_report?wx_station_id=123` | Yes | Get weather report |
| `GET` | `/api/v1/location?callsign=W3ABC` | Yes | Native location query |

## CLI Commands

### Database Management

```bash
# Initialize database schema (first time)
haminfo db schema-init

# Run migrations
haminfo db schema-upgrade

# Check schema version
haminfo db schema-version

# Clone data from production to development
haminfo db clone-from "postgresql://user:pass@prod-host/haminfo" --force

# Clean old data
haminfo db clean-wx-reports      # Delete weather reports > 14 days
haminfo db clean-aprs-packets    # Delete APRS packets > 30 days
```

### RepeaterBook Data

```bash
# Fetch all USA repeaters
haminfo rb fetch-usa-repeaters

# Fetch worldwide repeaters
haminfo rb fetch-all-repeaters

# Dry run (don't save to database)
haminfo rb fetch-usa-repeaters --fetch-only
```

### Services

```bash
# Start MQTT ingestion
haminfo wx-mqtt-ingest

# Check MQTT health
haminfo mqtt-healthcheck

# Start MCP server (for AI agents)
haminfo mcp-server
```

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `haminfo_api` | 8081 | REST API server |
| `haminfo_db` | 5432 | PostgreSQL with PostGIS |
| `haminfo_memcached` | 11211 | Query caching |
| `mqtt_ingest` | - | APRS packet ingestion |
| `haminfo_cron` | - | Scheduled maintenance tasks |
| `haminfo_adminer` | 8066 | Database admin UI |

### Scheduled Tasks

| Schedule | Task |
|----------|------|
| Monthly (1st) | Refresh repeater data from RepeaterBook |
| Weekly (Sunday) | Clean old weather reports |

## Database Schema

Haminfo uses PostgreSQL with the PostGIS extension for geospatial queries.

### Main Tables

- **station** - Repeater information (40,000+ records)
- **weather_station** - APRS weather stations
- **weather_report** - Weather observations
- **aprs_packet** - APRS packet history
- **request** / **wx_request** - API request logging

### Geospatial Features

All location data uses PostGIS `Geography(POINT)` types for accurate distance calculations:

```sql
-- Find repeaters within 50km
SELECT callsign, frequency,
       ST_Distance(location, ST_MakePoint(-77.0, 38.9)::geography) as distance
FROM station
WHERE ST_DWithin(location, ST_MakePoint(-77.0, 38.9)::geography, 50000)
ORDER BY distance;
```

## MCP Server (AI Integration)

Haminfo includes an MCP server for AI agent database access with built-in SQL injection protection.

```bash
# Start the MCP server
haminfo mcp-server
```

### Available Tools

| Tool | Description |
|------|-------------|
| `query_data` | Execute validated SELECT queries |
| `query_stations` | Query repeaters with filters |
| `query_weather_stations` | Query weather stations |
| `query_weather_reports` | Query weather reports |
| `query_aprs_packets` | Query APRS packets |

### Security Features

- Only SELECT queries allowed
- Table allowlist enforcement
- Maximum 1000 results per query
- Subquery and dangerous pattern detection

## Development

### Running Tests

```bash
# Install test dependencies
pip install -e ".[test]"

# Run all tests
pytest

# Run with coverage
pytest --cov=haminfo

# Lint check
ruff check .
```

### Database Setup (Local)

```bash
# Create PostgreSQL database with PostGIS
createdb haminfo
psql haminfo -c "CREATE EXTENSION postgis;"

# Initialize schema
haminfo db schema-init

# Load test data
haminfo rb fetch-usa-repeaters --fetch-only  # Dry run first
haminfo rb fetch-usa-repeaters
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Run linting (`ruff check .`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [RepeaterBook](https://repeaterbook.com) for the repeater database
- [APRSD](https://github.com/craigerl/aprsd) for APRS packet handling
- [PostGIS](https://postgis.net/) for geospatial queries

## Author

**Walter A. Boring IV (WB4BOR)**
- GitHub: [@hemna](https://github.com/hemna)
- Email: waboring@hemna.com
