# Weather Station History API

## Overview

Expose an API endpoint to fetch historical weather data for graphing. Supports date range queries with hourly aggregation, field selection, and flexible station identification.

## Problem Statement

- Weather website needs to render graphs of historical weather data
- Need to query data between date ranges for specific fields (temperature, etc.)
- Current API only returns latest report per station, not historical data

## Solution: Hourly Aggregated History Endpoint

### Endpoint Definition

**Endpoint:** `GET /api/v1/wx/history`

**Authentication:** API key via `X-Api-Key` header

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `station_id` | integer | One required | Weather station ID |
| `callsign` | string | One required | Station callsign (e.g., "W1RCY") |
| `start` | string | Yes | Start time (ISO 8601) |
| `end` | string | Yes | End time (ISO 8601) |
| `fields` | string | Yes | Comma-separated field names |

**Valid fields:** `temperature`, `humidity`, `pressure`, `wind_speed`, `wind_direction`, `wind_gust`, `rain_1h`, `rain_24h`, `rain_since_midnight`

### Response Format

**Success (200 OK):**

```json
{
  "station_id": 21285,
  "callsign": "W1RCY",
  "start": "2026-03-20T00:00:00Z",
  "end": "2026-03-21T00:00:00Z",
  "interval": "1h",
  "fields": ["temperature"],
  "history": [
    {"time": "2026-03-20T00:00:00Z", "temperature": -1.2},
    {"time": "2026-03-20T01:00:00Z", "temperature": -0.8},
    {"time": "2026-03-20T02:00:00Z", "temperature": -0.5}
  ],
  "count": 3
}
```

**Error (4xx):**

```json
{
  "error": "Date range exceeds maximum of 30 days",
  "field": "start/end"
}
```

### Validation Rules

| Rule | Constraint |
|------|------------|
| Date range | `end - start` ≤ 30 days |
| Date order | `start` must be before `end` |
| Station lookup | Resolve callsign to station_id; 404 if not found |
| Fields | At least one valid field required |
| Timestamps | Valid ISO 8601; UTC assumed if no timezone |

### Error Handling

| Scenario | Status | Message |
|----------|--------|---------|
| Missing station_id and callsign | 400 | "Either 'station_id' or 'callsign' is required" |
| Station not found | 404 | "Weather station not found" |
| Missing start/end | 400 | "Both 'start' and 'end' are required" |
| Invalid timestamp | 400 | "Invalid timestamp format for 'start'" |
| Range > 30 days | 400 | "Date range exceeds maximum of 30 days" |
| start >= end | 400 | "'start' must be before 'end'" |
| Missing fields | 400 | "At least one valid field is required" |
| Invalid field | 400 | "Invalid field: 'foo'. Valid fields: ..." |
| No data in range | 200 | Empty `history` array |

### Database Query

Uses TimescaleDB `time_bucket` for efficient aggregation:

```sql
SELECT 
    time_bucket('1 hour', time) AS bucket,
    AVG(temperature) AS temperature,
    AVG(humidity) AS humidity
FROM weather_report
WHERE weather_station_id = :station_id
  AND time >= :start
  AND time < :end
GROUP BY bucket
ORDER BY bucket ASC
```

## OpenAPI Documentation

**New requirement:** Expose `/openapi.json` documenting all haminfo APIs.

**Approach:** Auto-generate using `apispec` library with code annotations.

**New endpoints:**

- `GET /openapi.json` - OpenAPI 3.0 specification (no auth)
- `GET /docs` - Swagger UI (optional)

**Documented endpoints:**

- All existing endpoints (nearest, wxnearest, wxstations, etc.)
- New `/api/v1/wx/history` endpoint

## Implementation Plan

### Files to Modify

| File | Changes |
|------|---------|
| `haminfo/flask.py` | Add `wx_history()`, OpenAPI annotations, `/openapi.json` route |
| `haminfo/db/db.py` | Add `get_wx_history()` with TimescaleDB query |
| `pyproject.toml` | Add `apispec`, `apispec-webframeworks` dependencies |

### New Validation Helpers

- `validate_iso_timestamp()` - Parse ISO 8601 timestamps
- `validate_fields()` - Validate field names

### No Database Migrations Required

Uses existing `weather_report` TimescaleDB hypertable.

## Testing Strategy

- Unit tests for validation helpers
- Integration tests for endpoint with test database
- Test cases: valid queries, all error conditions, empty results, edge cases (exactly 30 days)
