# API Contract: Location API

**Feature**: 001-aprs-position-reports
**Date**: 2026-03-09

## Endpoint 1: aprs.fi-Compatible Location Query

This endpoint mimics the aprs.fi API format to serve as a drop-in replacement
for the `aprsd-locationdata-plugin` and `aprsd-location-plugin`.

### Request

```
GET /api/get?what=loc&apikey={API_KEY}&format=json&name={CALLSIGN}
```

**Query Parameters**:

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `what` | Yes | String | MUST be `"loc"` (only location queries supported) |
| `apikey` | Yes | String | API key for authentication |
| `format` | No | String | Response format. Only `"json"` supported (default) |
| `name` | Yes | String | Callsign(s), comma-separated. Max 20. Case-insensitive. |

### Response: Success (200)

```json
{
  "command": "get",
  "result": "ok",
  "what": "loc",
  "found": 1,
  "entries": [
    {
      "name": "W3ADO-1",
      "type": "l",
      "time": "1741500000",
      "lasttime": "1741500030",
      "lat": "39.95230",
      "lng": "-75.16520",
      "altitude": "15",
      "course": "180",
      "speed": "0",
      "symbol": "/#",
      "srccall": "W3ADO-1",
      "dstcall": "APRS",
      "comment": "Philadelphia APRS",
      "path": "WIDE1-1,WIDE2-2,qAR,W3ADO"
    }
  ]
}
```

**Response Fields (per entry)**:

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Callsign (uppercase) |
| `type` | String | `"l"` (position), `"o"` (object), `"i"` (item) |
| `time` | String | Packet timestamp as Unix epoch seconds |
| `lasttime` | String | Last received timestamp as Unix epoch seconds |
| `lat` | String | Latitude in decimal degrees |
| `lng` | String | Longitude in decimal degrees |
| `altitude` | String | Altitude in meters (`"0"` if unknown) |
| `course` | String | Course in degrees (`"0"` if unknown) |
| `speed` | String | Speed in km/h (`"0"` if unknown) |
| `symbol` | String | APRS symbol (table char + symbol char) |
| `srccall` | String | Source callsign (uppercase) |
| `dstcall` | String | Destination callsign (uppercase) |
| `comment` | String | Position comment (may be empty) |
| `path` | String | Digipeater path (may be empty) |

### Response: Not Found (200)

When no matching callsign has position data:

```json
{
  "command": "get",
  "result": "ok",
  "what": "loc",
  "found": 0,
  "entries": []
}
```

### Response: Error (200)

Errors return HTTP 200 with `result: "fail"` (matching aprs.fi behavior):

```json
{
  "command": "get",
  "result": "fail",
  "description": "missing parameter: name"
}
```

**Error conditions**:
- Missing `name` parameter
- Missing or invalid `apikey`
- `what` parameter is not `"loc"`
- More than 20 callsigns requested
- `format` is not `"json"`

---

## Endpoint 2: Native Haminfo Location Query

This endpoint uses haminfo's standard API conventions (JSON structure with
`data`/`error`/`meta` fields, `X-Api-Key` header auth).

### Request

```
GET /api/v1/location?callsign={CALLSIGN}
```

**Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `X-Api-Key` | Yes | API key for authentication |

**Query Parameters**:

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `callsign` | Yes | String | Callsign(s), comma-separated. Max 20. Case-insensitive. |

### Response: Success (200)

```json
{
  "data": [
    {
      "callsign": "W3ADO-1",
      "latitude": 39.9523,
      "longitude": -75.1652,
      "altitude": 15.0,
      "course": 180,
      "speed": 0.0,
      "symbol": "/#",
      "to_call": "APRS",
      "comment": "Philadelphia APRS",
      "path": "WIDE1-1,WIDE2-2,qAR,W3ADO",
      "timestamp": "2026-03-09T12:00:00Z",
      "received_at": "2026-03-09T12:00:30Z",
      "packet_type": "position"
    }
  ],
  "meta": {
    "found": 1,
    "requested": ["W3ADO-1"]
  },
  "error": null
}
```

### Response: Not Found (200)

```json
{
  "data": [],
  "meta": {
    "found": 0,
    "requested": ["NONEXIST"]
  },
  "error": null
}
```

### Response: Validation Error (400)

```json
{
  "data": null,
  "meta": null,
  "error": {
    "code": "INVALID_PARAM",
    "message": "Missing required parameter: callsign"
  }
}
```

### Response: Authentication Error (401)

```json
{
  "data": null,
  "meta": null,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

---

## Endpoint 3: APRS Packet Stats (Enhancement to existing /stats)

Extends the existing `/stats` endpoint to include APRS packet statistics.

### Request

```
GET /stats
```

### Response: Success (200)

```json
{
  "repeaters": 42000,
  "weather_stations": 1200,
  "aprs_packets": {
    "total": 500000,
    "position": 350000,
    "weather": 80000,
    "message": 40000,
    "other": 30000,
    "unique_callsigns": 5000,
    "last_24h": 25000
  }
}
```

---

## Authentication

### aprs.fi-Compatible Endpoint (`/api/get`)

Accepts API key as query parameter `apikey` to match aprs.fi's interface.
Internally maps to the same validation as the `X-Api-Key` header.

### Native Endpoint (`/api/v1/location`)

Uses the existing `X-Api-Key` header authentication via the `require_appkey`
decorator, consistent with all other haminfo API endpoints.

---

## Rate Limits

No rate limiting in initial implementation. The existing architecture does
not implement rate limiting. This may be added in a future iteration if
needed.

---

## Caching

Position query results are cached per callsign for 60 seconds using the
existing dogpile.cache infrastructure (memcached backend). Cache key format:
`position:{CALLSIGN}`.

Cache is shared between both endpoints - a query via `/api/get` warms
the cache for `/api/v1/location` and vice versa.
