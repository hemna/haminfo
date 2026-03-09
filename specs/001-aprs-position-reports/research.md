# Research: APRS Position Reports API

**Feature**: 001-aprs-position-reports
**Date**: 2026-03-09

## Research Questions & Findings

### 1. What is the aprsd-locationdata-plugin and how does it work?

**Decision**: Build an aprs.fi-compatible API endpoint that serves as a
drop-in replacement for the aprs.fi location API.

**Rationale**: The `aprsd-locationdata-plugin` (hemna/aprsd-locationdata-plugin)
and `aprsd-location-plugin` (hemna/aprsd-location-plugin) both call the same
underlying function: `plugin_utils.get_aprs_fi(api_key, callsign)` from the
APRSD core library. This function makes HTTP GET requests to
`https://api.aprs.fi/api/get?what=loc&apikey=KEY&format=json&name=CALLSIGN`.
By implementing the same URL pattern and response format, haminfo can serve as
a self-hosted replacement requiring only a base URL change in the APRSD
plugin configuration.

**Alternatives considered**:
- Custom APRSD plugin with haminfo-native API: Rejected because it requires
  maintaining a separate plugin and doesn't benefit the broader ecosystem.
- Proxy to aprs.fi with caching: Rejected because the goal is to eliminate
  the aprs.fi dependency entirely using locally-ingested data.

### 2. What is the aprs.fi location API response format?

**Decision**: Implement the exact aprs.fi JSON response schema for the
compatibility endpoint.

**Response format** (from aprs.fi API docs):

```json
{
  "command": "get",
  "result": "ok",
  "what": "loc",
  "found": 1,
  "entries": [
    {
      "name": "OH7RDA",
      "type": "l",
      "time": "1267445689",
      "lasttime": "1270580127",
      "lat": "63.06717",
      "lng": "27.66050",
      "altitude": "100",
      "course": "180",
      "speed": "5.5",
      "symbol": "\\/#",
      "srccall": "OH7RDA",
      "dstcall": "APND12",
      "comment": "/R,W,Wn,Tn Siilinjarvi",
      "path": "WIDE2-2,qAR,OH7AA"
    }
  ]
}
```

**Key field mappings from APRSPacket model**:

| aprs.fi field | APRSPacket column | Notes |
|---------------|-------------------|-------|
| `name` | `from_call` | Uppercase |
| `type` | `packet_type` | Map: "position" -> "l", "object" -> "o", "item" -> "i" |
| `time` | `timestamp` | Unix epoch string |
| `lasttime` | `received_at` | Unix epoch string |
| `lat` | `latitude` | String, decimal degrees |
| `lng` | `longitude` | String, decimal degrees |
| `altitude` | `altitude` | String, meters |
| `course` | `course` | String, degrees |
| `speed` | `speed` | String, km/h |
| `symbol` | `symbol_table` + `symbol` | Concatenated 2-char string |
| `srccall` | `from_call` | Uppercase |
| `dstcall` | `to_call` | Uppercase |
| `comment` | `comment` | Raw string |
| `path` | `path` | Raw string |

**Rationale**: Exact format compatibility means no changes needed in APRSD
plugins. The plugins only need their base URL reconfigured.

### 3. How to query the latest position for a callsign efficiently?

**Decision**: Use PostgreSQL `DISTINCT ON` with `ORDER BY` to get the most
recent position-bearing packet per callsign in a single query.

**Query pattern**:
```sql
SELECT DISTINCT ON (from_call)
    from_call, latitude, longitude, altitude, course, speed,
    symbol, symbol_table, to_call, comment, path, timestamp, received_at
FROM aprs_packet
WHERE from_call IN (:callsigns)
  AND packet_type = 'position'
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL
ORDER BY from_call, timestamp DESC;
```

**Rationale**: PostgreSQL's `DISTINCT ON` is the idiomatic and performant way
to get "the latest row per group" without subqueries or window functions.
The existing index on `(from_call, timestamp)` directly supports this query.

**Alternatives considered**:
- Subquery with `MAX(timestamp)`: More portable but slower and more complex.
- Materialized view of latest positions: Premature optimization; adds schema
  complexity. Can be added later if query latency exceeds 200ms threshold.
- Separate "latest_position" table updated on ingest: Maximum read performance
  but adds write-path complexity and consistency concerns. Deferred to future
  optimization if needed.

### 4. Should we include position data from ALL packet types or only "position" type?

**Decision**: Query `packet_type = 'position'` only for the primary query,
but also include packets where `latitude IS NOT NULL AND longitude IS NOT NULL`
as a fallback option (configurable).

**Rationale**: Weather packets, object packets, and other types can also contain
position data, but the `position` type represents explicit position reports
which are the primary use case for the location plugins. Including all packet
types could return stale weather station positions instead of the station
operator's actual moving position.

### 5. What data retention strategy for APRS packets?

**Decision**: Implement a configurable cleanup command that deletes packets
older than N days (default: 30 days), following the existing pattern of
`clean_weather_reports` (14-day retention).

**Rationale**: APRS position data is time-sensitive. Keeping 30 days of
history provides sufficient lookback for location queries while preventing
unbounded table growth. The `clean_weather_reports` function in `db.py`
(line 377-395) establishes the precedent.

**Alternatives considered**:
- Shorter retention (7 days): Too aggressive for stations that transmit
  infrequently.
- Partitioned tables by date: Good for very high volume but adds schema
  complexity. Deferred to future optimization.

### 6. How should the compatibility endpoint authenticate?

**Decision**: The `/api/get` compatibility endpoint will accept an `apikey`
query parameter (matching aprs.fi's format) which maps to the existing
`X-Api-Key` validation. The native `/api/v1/location` endpoint will use the
standard `X-Api-Key` header.

**Rationale**: The APRSD `plugin_utils.get_aprs_fi()` function passes the
API key as a query parameter (`apikey=KEY`). The compatibility endpoint MUST
accept this format. Internally, both endpoints use the same validation logic.

### 7. Should we support multiple callsigns per query?

**Decision**: Yes, support up to 20 comma-separated callsigns per query
(matching the aprs.fi limit).

**Rationale**: The aprs.fi API supports querying multiple callsigns in a
single request via `name=CALL1,CALL2,...`. The APRSD plugins currently only
query one callsign at a time, but supporting batch queries follows the
aprs.fi contract and enables future optimizations.

### 8. Caching strategy for position queries?

**Decision**: Cache latest-position results per callsign for 60 seconds using
the existing dogpile.cache infrastructure.

**Rationale**: Position data changes relatively slowly (most APRS stations
beacon every 1-10 minutes). A 60-second cache TTL provides a good balance
between data freshness and query performance. The existing caching infrastructure
(memcached via dogpile.cache) is already configured in `db/db.py`.

**Alternatives considered**:
- No caching: Could exceed 200ms latency under load.
- Longer TTL (5 min): Too stale for moving stations.
- Cache invalidation on ingest: Complex and unnecessary given the low-latency
  requirements.
