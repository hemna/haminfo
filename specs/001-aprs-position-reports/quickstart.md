# Quickstart: APRS Position Reports API

**Feature**: 001-aprs-position-reports
**Date**: 2026-03-09

## Prerequisites

1. Haminfo is running with MQTT ingestion active (`haminfo wx-mqtt-ingest`)
2. The `aprs_packet` table is populated with position data
3. An API key is configured in `haminfo.conf` under `[web] api_key`
4. The Flask API server is running (`haminfo_api`)

## Verify Data Exists

Check that APRS packets with position data are being ingested:

```bash
# Connect to the database
psql -h localhost -U haminfo -d haminfo

# Check for position packets
SELECT COUNT(*) FROM aprs_packet
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

# Check recent unique callsigns with positions
SELECT DISTINCT from_call, timestamp
FROM aprs_packet
WHERE latitude IS NOT NULL
ORDER BY timestamp DESC
LIMIT 10;
```

## Query Location via aprs.fi-Compatible API

This endpoint is designed for use with the `aprsd-locationdata-plugin`
and `aprsd-location-plugin`.

### Single Callsign

```bash
curl "http://localhost:8080/api/get?what=loc&apikey=YOUR_KEY&format=json&name=W3ADO-1"
```

Expected response:
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

### Multiple Callsigns

```bash
curl "http://localhost:8080/api/get?what=loc&apikey=YOUR_KEY&format=json&name=W3ADO-1,K3ABC,N0CALL"
```

## Query Location via Native API

This endpoint uses haminfo's standard response format.

```bash
curl -H "X-Api-Key: YOUR_KEY" \
  "http://localhost:8080/api/v1/location?callsign=W3ADO-1"
```

Expected response:
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
      "timestamp": "2026-03-09T12:00:00Z",
      "received_at": "2026-03-09T12:00:30Z"
    }
  ],
  "meta": { "found": 1, "requested": ["W3ADO-1"] },
  "error": null
}
```

## Configure APRSD Plugins

To use haminfo as a replacement for aprs.fi in the APRSD location plugins,
you need to configure the APRSD plugin to point to your haminfo instance.

The APRSD plugins call `plugin_utils.get_aprs_fi()` which constructs:
```
http://api.aprs.fi/api/get?what=loc&apikey=KEY&format=json&name=CALLSIGN
```

To redirect this to haminfo, you have two options:

### Option A: Override in APRSD Plugin Configuration

If the APRSD plugin supports configuring the base URL (check plugin docs),
set it to your haminfo instance:
```
http://your-haminfo-host:8080
```

### Option B: DNS/Reverse Proxy

Configure a reverse proxy or DNS override so that `api.aprs.fi` resolves
to your haminfo instance. The `/api/get` endpoint accepts the same query
parameters.

## Data Cleanup

To prevent unbounded growth of the `aprs_packet` table, run the cleanup
command periodically:

```bash
# Clean packets older than 30 days (default)
haminfo db clean-aprs-packets

# Clean packets older than 7 days
haminfo db clean-aprs-packets --days 7
```

Add to cron for automated cleanup:
```cron
0 3 * * * /path/to/haminfo db clean-aprs-packets --days 30
```

## Troubleshooting

### No position data returned

1. Verify MQTT ingestion is running and processing packets
2. Check that position packets exist:
   ```sql
   SELECT COUNT(*) FROM aprs_packet WHERE packet_type = 'position';
   ```
3. Verify the callsign exists (case-insensitive):
   ```sql
   SELECT DISTINCT from_call FROM aprs_packet
   WHERE UPPER(from_call) = 'W3ADO-1';
   ```

### Slow query performance

1. Verify indexes exist:
   ```sql
   \di aprs_packet*
   ```
2. Check table size:
   ```sql
   SELECT COUNT(*) FROM aprs_packet;
   SELECT pg_size_pretty(pg_total_relation_size('aprs_packet'));
   ```
3. Run cleanup if table is too large
4. Consider adding the partial index from data-model.md
