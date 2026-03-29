# Map Tile-Based Caching Design

**Date:** 2026-03-29  
**Status:** Approved  
**Author:** Claude (AI Assistant)

## Overview

Implement tile-based caching for the APRS map endpoint using memcached to improve performance while maintaining data freshness. The world is divided into 1°×1° tiles, each cached independently with a 60-second TTL.

## Problem Statement

The current map API (`/api/dashboard/map/stations`) queries PostgreSQL directly on every request, even for the same geographic area. This results in:

- ~500ms latency per request
- Unnecessary database load for repeated queries
- No benefit from spatial locality (adjacent users querying similar areas)

## Goals

1. Reduce map load latency for cached regions to <50ms
2. Maintain data freshness within 60 seconds
3. Limit memcached memory usage (bounded, predictable)
4. Transparent to clients (no API changes)

## Non-Goals

- Real-time (<1s) data freshness
- Caching trail data (too memory-intensive)
- Client-side changes

## Design

### Tile System

Each tile is identified by integer coordinates derived from floor(lat) and floor(lon):

```
tile_lat = floor(latitude)   # -90 to 89
tile_lon = floor(longitude)  # -180 to 179
```

Example: A station at `45.523, -122.676` (Portland, OR) falls in tile `(45, -123)`.

### Cache Key Structure

```
map:tile:{hours}:{type}:{tile_lat}:{tile_lon}

Examples:
  map:tile:1::45:-123        # 1-hour, all types, Portland area
  map:tile:24:weather:45:-123  # 24-hour, weather only
```

Parameters:
- `hours`: 1, 2, 6, or 24
- `type`: empty string for all, or "position", "weather"
- `tile_lat`/`tile_lon`: integer tile coordinates

### Request Flow

```
1. Client Request
   GET /api/dashboard/map/stations?bbox=-123,45,-121,46&hours=1

2. Calculate Tiles
   Tiles: [(45,-123), (45,-122), (46,-123), (46,-122)]

3. Fetch Each Tile
   For each tile:
     - Check memcached
     - Hit: use cached data
     - Miss: query DB, cache result

4. Merge & Filter
   - Combine all tile data
   - Dedupe by callsign (keep most recent)
   - Filter to exact bbox bounds
   - Apply limit

5. Return GeoJSON
```

### Cache Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| TTL | 60 seconds | Balance freshness vs cache hit rate |
| Max tiles per request | 100 | Prevent abuse from huge bbox |
| Serialization | JSON (compact dicts) | Simple, debuggable |

### Database Query (per tile)

```sql
SELECT DISTINCT ON (from_call)
    from_call, latitude, longitude, packet_type,
    symbol, symbol_table, speed, course, altitude,
    comment, received_at
FROM aprs_packet
WHERE received_at >= NOW() - INTERVAL '{hours} hours'
  AND latitude >= {tile_lat} AND latitude < {tile_lat + 1}
  AND longitude >= {tile_lon} AND longitude < {tile_lon + 1}
  AND latitude IS NOT NULL AND longitude IS NOT NULL
ORDER BY from_call, received_at DESC
```

### Error Handling

**Cache failures:** Log and fall through to database query. System continues working if memcached is down.

**Large bbox protection:** If bbox spans >100 tiles, truncate to center tiles and log warning.

### Memory Budget

- Worst case: ~360 active tiles × 4 time windows × 2 types = ~2,880 keys
- At ~50KB per tile average = ~144MB theoretical max
- Realistic: ~25-50MB for typical APRS activity patterns

## Components to Implement

### New Functions in `queries.py`

1. **`get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat)`**
   - Calculate tile coordinates covering a bbox
   - Returns list of (tile_lat, tile_lon) tuples

2. **`get_tile_stations(tile_lat, tile_lon, hours, station_type)`**
   - Fetch single tile with cache lookup
   - Returns list of station dicts

3. **`query_tile_from_db(tile_lat, tile_lon, hours, station_type)`**
   - Database query for one tile
   - Returns compact station dicts (not ORM objects)

4. **`get_map_stations_tiled(bbox, hours, station_type, limit)`**
   - Orchestrates tile fetching, merging, filtering
   - Main entry point for API

### API Changes in `api.py`

Update `api_map_stations()` to use `get_map_stations_tiled()` when bbox is provided, falling back to existing `get_map_stations_fast()` otherwise.

## Performance Expectations

| Scenario | Before | After |
|----------|--------|-------|
| First request (cold cache) | ~500ms | ~500ms |
| Subsequent requests (warm cache) | ~500ms | ~10-50ms |
| Adjacent user same area | ~500ms | ~10-50ms (cache hit) |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Cache stampede on expiry | Short TTL (60s) limits impact; could add jitter |
| Memory growth | TTL-based eviction; bounded key space |
| Stale data | 60s max staleness is acceptable for map view |

## Alternatives Considered

1. **Global dataset caching**: Cache entire station set per time window. Rejected: higher memory, doesn't scale.

2. **Split fresh/cached**: Cache excludes last 5 min, query fresh separately. Rejected: more complex, marginal benefit.

3. **WebSocket overlay**: Short TTL + push new packets. Considered for future enhancement.

## Success Criteria

- [ ] Map loads in <100ms for cached regions
- [ ] Memory usage stays under 100MB
- [ ] No visible data staleness issues reported
- [ ] Graceful degradation when memcached unavailable
