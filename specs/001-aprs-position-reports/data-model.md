# Data Model: APRS Position Reports API

**Feature**: 001-aprs-position-reports
**Date**: 2026-03-09

## Existing Entities (No Schema Changes Required)

This feature operates entirely on the **existing** `aprs_packet` table. No
new tables or columns are needed. The ingestion pipeline already stores
position data correctly.

### Entity: APRSPacket (existing)

**Table**: `aprs_packet`
**Model**: `haminfo/db/models/aprs_packet.py`

**Columns relevant to position queries**:

| Column | Type | Indexed | Purpose |
|--------|------|---------|---------|
| `id` | Integer (PK) | Yes (PK) | Auto-increment identifier |
| `from_call` | String | Yes | Source callsign (query key) |
| `to_call` | String | Yes | Destination callsign |
| `path` | String | No | Digipeater path |
| `timestamp` | DateTime | Yes | Packet timestamp |
| `received_at` | DateTime | Yes | Ingestion timestamp |
| `packet_type` | String | Yes | "position", "weather", etc. |
| `latitude` | Float | No | Decimal degrees |
| `longitude` | Float | No | Decimal degrees |
| `location` | Geography('POINT') | Yes (GiST) | PostGIS spatial column |
| `altitude` | Float | No | Meters |
| `course` | Integer | No | Degrees (0-360) |
| `speed` | Float | No | Speed value |
| `symbol` | CHAR | No | APRS symbol character |
| `symbol_table` | CHAR | No | APRS symbol table character |
| `comment` | Text | No | Position comment |

### Query: Latest Position by Callsign

```sql
SELECT DISTINCT ON (from_call)
    id, from_call, to_call, path, timestamp, received_at,
    latitude, longitude, altitude, course, speed,
    symbol, symbol_table, comment, packet_type
FROM aprs_packet
WHERE from_call = ANY(:callsigns)
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL
ORDER BY from_call, timestamp DESC;
```

**Index usage**: Uses the existing index on `from_call` for the WHERE clause
and `timestamp` for the ORDER BY. The `DISTINCT ON` eliminates duplicates
per callsign, returning only the most recent position.

**Note**: This query intentionally does NOT filter by `packet_type = 'position'`
because weather packets, object packets, and others also contain valid position
data. The query returns the most recent packet with position coordinates
regardless of type.

### Query: Nearest APRS Stations to a Point

```sql
SELECT DISTINCT ON (from_call)
    from_call, latitude, longitude, altitude, course, speed,
    symbol, symbol_table, comment, timestamp, received_at,
    ST_Distance(location, :poi) AS distance,
    ST_Azimuth(ST_Point(:lon, :lat), ST_Point(longitude, latitude)) AS bearing
FROM aprs_packet
WHERE latitude IS NOT NULL
  AND longitude IS NOT NULL
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY from_call, timestamp DESC;
```

This is a potential future enhancement (not in initial scope) for spatial
proximity searches.

## Index Assessment

**Existing indexes (sufficient for this feature)**:

| Index | Columns | Supports |
|-------|---------|----------|
| PK | `id` | Direct lookups |
| `ix_aprs_packet_from_call` | `from_call` | Callsign filtering |
| `ix_aprs_packet_timestamp` | `timestamp` | Time ordering |
| `ix_aprs_packet_received_at` | `received_at` | Ingestion time queries |
| `ix_aprs_packet_packet_type` | `packet_type` | Type filtering |
| GiST on `location` | `location` | Spatial queries |

**Potential future index** (add only if performance requires it):
```sql
CREATE INDEX ix_aprs_packet_callsign_position
ON aprs_packet (from_call, timestamp DESC)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
```
This partial index would optimize the "latest position by callsign" query
by pre-filtering to only position-bearing packets.

## Response Model: aprs.fi-Compatible Location Entry

This is not a database entity but a response DTO (Data Transfer Object)
that maps APRSPacket fields to the aprs.fi JSON format.

```python
@dataclass
class AprsFiLocationEntry:
    """Maps APRSPacket fields to aprs.fi location response format."""
    name: str           # from_call (uppercase)
    type: str           # "l" for position, "o" for object, "i" for item
    time: str           # timestamp as Unix epoch string
    lasttime: str       # received_at as Unix epoch string
    lat: str            # latitude as string
    lng: str            # longitude as string
    altitude: str       # altitude as string (default "0")
    course: str         # course as string (default "0")
    speed: str          # speed as string (default "0")
    symbol: str         # symbol_table + symbol (2 chars)
    srccall: str        # from_call (uppercase)
    dstcall: str        # to_call (uppercase)
    comment: str        # comment (raw string)
    path: str           # path (raw string)
```

## Data Flow

```
Existing (no changes):
  APRS-IS --> APRSD --> MQTT --> haminfo MQTT ingest --> aprs_packet table

New (this feature):
  HTTP GET /api/get?what=loc&name=CALLSIGN
    --> validate params
    --> query aprs_packet (latest position per callsign)
    --> transform to aprs.fi JSON format
    --> return response

  HTTP GET /api/v1/location?callsign=CALLSIGN
    --> validate params
    --> query aprs_packet (latest position per callsign)
    --> transform to haminfo native JSON format
    --> return response
```

## Data Retention

A cleanup function will delete packets older than a configurable retention
period (default: 30 days). This follows the pattern of the existing
`clean_weather_reports()` function in `haminfo/db/db.py`.

```sql
DELETE FROM aprs_packet
WHERE received_at < NOW() - INTERVAL ':days days';
```
