# Geographic Filtering for Countries Page

## Problem Statement

The current Countries Page uses callsign prefix matching to determine a station's country, but this is fundamentally unreliable for APRS:
- Objects like "HAMLTN", "WINLINK", "ISS" don't follow callsign conventions
- Stations can operate from different countries than their license indicates
- Mobile stations cross borders

GPS coordinates from APRS position reports are the only reliable way to determine location.

## Solution Overview

Implement geographic filtering using PostGIS reverse geocoding with an application-level cache for performance.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Incoming Packet                          │
│                    (lat, lon from APRS)                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Location Cache Lookup                        │
│            Grid-based: round(lat, 1), round(lon, 1)             │
│                    ~11km resolution                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
               Cache Hit              Cache Miss
                    │                       │
                    ▼                       ▼
           ┌───────────────┐    ┌─────────────────────────┐
           │ Return cached │    │   PostGIS Query         │
           │ country_code  │    │   ST_Contains()         │
           └───────────────┘    │   against boundaries    │
                    │           └─────────────────────────┘
                    │                       │
                    │                       ▼
                    │           ┌─────────────────────────┐
                    │           │   Cache result          │
                    │           │   (grid cell → country) │
                    │           └─────────────────────────┘
                    │                       │
                    └───────────┬───────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Broadcast to Country Room                       │
│                   (e.g., "country_US")                          │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Database: Boundary Tables

**Table: `countries`**
```sql
CREATE TABLE countries (
    id SERIAL PRIMARY KEY,
    iso_a2 CHAR(2) NOT NULL,        -- ISO 3166-1 alpha-2 code
    iso_a3 CHAR(3),                  -- ISO 3166-1 alpha-3 code
    name VARCHAR(100) NOT NULL,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
);

CREATE INDEX idx_countries_geom ON countries USING GIST (geom);
CREATE UNIQUE INDEX idx_countries_iso_a2 ON countries (iso_a2);
```

**Table: `us_states`**
```sql
CREATE TABLE us_states (
    id SERIAL PRIMARY KEY,
    state_code CHAR(2) NOT NULL,     -- USPS abbreviation (CA, TX, etc.)
    name VARCHAR(100) NOT NULL,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
);

CREATE INDEX idx_us_states_geom ON us_states USING GIST (geom);
CREATE UNIQUE INDEX idx_us_states_code ON us_states (state_code);
```

**Data Source:** Natural Earth 1:10m Admin 0 Countries and Admin 1 States/Provinces
- Download: https://www.naturalearthdata.com/downloads/10m-cultural-vectors/
- Files: `ne_10m_admin_0_countries.shp`, `ne_10m_admin_1_states_provinces.shp`

### 2. Application: Location Cache

**Module: `haminfo_dashboard/geo_cache.py`**

```python
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
from collections import OrderedDict
import threading

@dataclass
class LocationInfo:
    country_code: Optional[str]  # ISO 3166-1 alpha-2 (e.g., "US")
    state_code: Optional[str]    # For US locations only (e.g., "CA")

class GeoCache:
    """Thread-safe LRU cache for geographic lookups."""
    
    def __init__(self, max_size: int = 100_000, grid_resolution: float = 0.1):
        self._cache: OrderedDict[Tuple[float, float], LocationInfo] = OrderedDict()
        self._max_size = max_size
        self._resolution = grid_resolution
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}
    
    def _grid_key(self, lat: float, lon: float) -> Tuple[float, float]:
        """Round coordinates to grid resolution (~11km at 0.1°)."""
        return (
            round(lat / self._resolution) * self._resolution,
            round(lon / self._resolution) * self._resolution
        )
    
    def get(self, lat: float, lon: float) -> Optional[LocationInfo]:
        """Get cached location info, or None if not cached."""
        key = self._grid_key(lat, lon)
        with self._lock:
            if key in self._cache:
                self._stats["hits"] += 1
                self._cache.move_to_end(key)  # LRU update
                return self._cache[key]
            self._stats["misses"] += 1
            return None
    
    def put(self, lat: float, lon: float, info: LocationInfo) -> None:
        """Cache location info for coordinates."""
        key = self._grid_key(lat, lon)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # Remove oldest
                self._cache[key] = info
    
    def warm_from_db(self, session, hours: int = 24) -> int:
        """Pre-populate cache from recent packets with positions."""
        # Query distinct grid cells from recent packets
        # For each, do reverse geocode and cache
        pass  # Implementation in next section
    
    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                **self._stats,
                "size": len(self._cache),
                "hit_rate": self._stats["hits"] / max(1, self._stats["hits"] + self._stats["misses"])
            }

# Global instance
geo_cache = GeoCache()
```

### 3. Reverse Geocoding Function

**In `geo_cache.py`:**

```python
from sqlalchemy import text

def reverse_geocode(session, lat: float, lon: float) -> LocationInfo:
    """
    Look up country (and state if US) for coordinates using PostGIS.
    Returns LocationInfo with country_code and optional state_code.
    """
    # First check countries
    country_query = text("""
        SELECT iso_a2 
        FROM countries 
        WHERE ST_Contains(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))
        LIMIT 1
    """)
    
    result = session.execute(country_query, {"lat": lat, "lon": lon}).fetchone()
    
    if not result:
        return LocationInfo(country_code=None, state_code=None)
    
    country_code = result[0]
    state_code = None
    
    # If US, also check state
    if country_code == "US":
        state_query = text("""
            SELECT state_code 
            FROM us_states 
            WHERE ST_Contains(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))
            LIMIT 1
        """)
        state_result = session.execute(state_query, {"lat": lat, "lon": lon}).fetchone()
        if state_result:
            state_code = state_result[0]
    
    return LocationInfo(country_code=country_code, state_code=state_code)


def get_location_info(session, lat: float, lon: float) -> LocationInfo:
    """
    Get location info with caching.
    Checks cache first, falls back to PostGIS query.
    """
    # Check cache
    cached = geo_cache.get(lat, lon)
    if cached is not None:
        return cached
    
    # Cache miss - query PostGIS
    info = reverse_geocode(session, lat, lon)
    
    # Cache result (even if None - negative caching for ocean/invalid coords)
    geo_cache.put(lat, lon, info)
    
    return info
```

### 4. Cache Warm-up

**In `geo_cache.py`:**

```python
def warm_cache(session, hours: int = 24) -> dict:
    """
    Pre-populate cache from recent packets with distinct grid cells.
    Called on application startup.
    """
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Get distinct grid cells from recent packets
    # Using 0.1 degree resolution
    grid_query = text("""
        SELECT DISTINCT 
            ROUND(latitude::numeric, 1) as grid_lat,
            ROUND(longitude::numeric, 1) as grid_lon
        FROM aprs_packet
        WHERE created_at > :cutoff
          AND latitude IS NOT NULL 
          AND longitude IS NOT NULL
          AND latitude BETWEEN -90 AND 90
          AND longitude BETWEEN -180 AND 180
    """)
    
    grid_cells = session.execute(grid_query, {"cutoff": cutoff}).fetchall()
    
    populated = 0
    errors = 0
    
    for grid_lat, grid_lon in grid_cells:
        try:
            lat = float(grid_lat)
            lon = float(grid_lon)
            info = reverse_geocode(session, lat, lon)
            geo_cache.put(lat, lon, info)
            populated += 1
        except Exception as e:
            errors += 1
            # Log but continue
    
    return {
        "grid_cells_found": len(grid_cells),
        "populated": populated,
        "errors": errors,
        "cache_size": geo_cache.stats["size"]
    }
```

### 5. Integration Points

#### 5.1 WebSocket Broadcast (`websocket.py`)

Update `broadcast_packet()` to use geographic lookup:

```python
from .geo_cache import get_location_info, geo_cache

def broadcast_packet(packet_data):
    """Broadcast packet to appropriate rooms based on geography."""
    
    # Always broadcast to main live feed
    socketio.emit("new_packet", packet_data, room="live_feed")
    
    # Geographic filtering for country/state rooms
    lat = packet_data.get("latitude")
    lon = packet_data.get("longitude")
    
    if lat is not None and lon is not None:
        try:
            with get_db_session() as session:
                info = get_location_info(session, lat, lon)
                
                if info.country_code:
                    # Broadcast to country room
                    socketio.emit("new_packet", packet_data, room=f"country_{info.country_code}")
                    
                    # If US, also broadcast to state room
                    if info.state_code:
                        socketio.emit("new_packet", packet_data, room=f"state_{info.state_code}")
        except Exception as e:
            # Log error but don't fail the broadcast
            current_app.logger.error(f"Geo lookup failed: {e}")
```

#### 5.2 Application Startup (`__init__.py`)

Initialize cache on startup:

```python
def create_app():
    app = Flask(__name__)
    # ... existing setup ...
    
    with app.app_context():
        from .geo_cache import warm_cache, geo_cache
        from .database import get_session
        
        try:
            with get_session() as session:
                stats = warm_cache(session, hours=24)
                app.logger.info(f"Geo cache warmed: {stats}")
        except Exception as e:
            app.logger.warning(f"Geo cache warm-up failed: {e}")
    
    return app
```

#### 5.3 Query Functions (`queries.py`)

Update country queries to use geographic aggregation:

```python
def get_all_countries_breakdown(session, hours: int = 24) -> list:
    """
    Get packet counts by country using geographic lookup.
    Uses cached reverse geocoding for efficiency.
    """
    # Option A: Aggregate from packets with cached lookups
    # Option B: Spatial join in SQL (slower but accurate for historical)
    
    # For dashboard display, use spatial join for accuracy:
    query = text("""
        SELECT 
            c.iso_a2 as country_code,
            c.name as country_name,
            COUNT(DISTINCT p.from_callsign) as unique_stations,
            COUNT(*) as packet_count
        FROM aprs_packet p
        JOIN countries c ON ST_Contains(c.geom, p.location::geometry)
        WHERE p.created_at > NOW() - INTERVAL ':hours hours'
          AND p.latitude IS NOT NULL
        GROUP BY c.iso_a2, c.name
        ORDER BY packet_count DESC
    """)
    
    return session.execute(query, {"hours": hours}).fetchall()
```

### 6. Data Loading Script

**Script: `scripts/load_natural_earth.py`**

```python
#!/usr/bin/env python3
"""Load Natural Earth boundaries into PostGIS."""

import subprocess
import sys

# Natural Earth 10m data URLs
COUNTRIES_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
STATES_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip"

def load_countries(db_url: str):
    """Load country boundaries."""
    # Download and extract
    # Use ogr2ogr or shp2pgsql to load
    # Extract only needed columns: ISO_A2, ISO_A3, NAME, geometry
    pass

def load_us_states(db_url: str):
    """Load US state boundaries."""
    # Filter to US only from admin_1
    # Extract: postal code, name, geometry
    pass

def create_indexes(db_url: str):
    """Create spatial and lookup indexes."""
    pass

if __name__ == "__main__":
    # Load from environment or argument
    db_url = sys.argv[1] if len(sys.argv) > 1 else os.environ["DATABASE_URL"]
    load_countries(db_url)
    load_us_states(db_url)
    create_indexes(db_url)
    print("Natural Earth data loaded successfully")
```

## Migration Path

### Phase 1: Add Boundary Tables (Non-breaking)
1. Create `countries` and `us_states` tables
2. Load Natural Earth data
3. Verify with test queries

### Phase 2: Add Geo Cache Module (Non-breaking)
1. Add `geo_cache.py` with cache and reverse geocoding
2. Add cache warm-up to app startup
3. Monitor cache hit rates in logs

### Phase 3: Update WebSocket Broadcasting
1. Update `broadcast_packet()` to use geographic lookup
2. Keep existing room structure (`country_XX`)
3. Add state rooms (`state_XX`) for US

### Phase 4: Update Query Functions
1. Update `get_all_countries_breakdown()` to use spatial join
2. Update `get_country_stats()` and `get_country_top_stations()`
3. Remove callsign prefix-based filtering

### Phase 5: Cleanup
1. Remove `get_country_from_callsign()` function
2. Remove callsign prefix constants
3. Update any remaining prefix-based code

## Performance Considerations

### Cache Sizing
- Grid resolution: 0.1° ≈ 11km (balances accuracy vs. cache size)
- Expected unique grid cells: ~25k (based on 24h station data)
- Memory usage: ~100KB for 25k entries
- Max size: 100k entries with LRU eviction

### Query Performance
- Spatial index on `geom` columns enables fast `ST_Contains()` queries
- Single point-in-polygon: ~5-10ms cold, <1ms with PostGIS cache
- Cache hit rate expected: >95% after warm-up (APRS stations are mostly stationary)

### Startup Time
- Cache warm-up: ~10-30 seconds for 25k grid cells
- Can be made async/background if needed

## Monitoring

Add metrics for:
- `geo_cache_hits` / `geo_cache_misses` - cache effectiveness
- `geo_cache_size` - current cache entries
- `geo_lookup_latency_ms` - PostGIS query time on cache miss
- `geo_warmup_duration_s` - startup warm-up time

## Testing

### Unit Tests
- `test_grid_key()` - coordinate rounding
- `test_cache_lru()` - eviction behavior
- `test_reverse_geocode()` - known coordinates

### Integration Tests
- Load test boundaries, verify known points
- Test cache warm-up from real data
- Test WebSocket room routing

### Manual Testing
- Watch country page with live data
- Verify stations appear in correct countries
- Check US state filtering works

## Rollback Plan

If issues arise:
1. Revert `broadcast_packet()` to prefix-based filtering
2. Keep boundary tables (no harm)
3. Disable cache warm-up

Geographic filtering is additive - we can fall back to prefix matching while debugging.

## Open Questions

1. **Ocean/invalid coordinates**: Should we have an "Unknown" category or just exclude?
   - Recommendation: Exclude from country pages, still show in main feed

2. **Border accuracy**: Natural Earth 10m may have small border inaccuracies
   - Acceptable for APRS dashboard purposes
   - Can upgrade to higher resolution if needed

3. **Disputed territories**: Some areas have multiple claims
   - Use Natural Earth's default attribution
   - Not a significant concern for ham radio dashboard

## Appendix: Natural Earth Field Mapping

### Countries (ne_10m_admin_0_countries)
| NE Field | Our Field | Notes |
|----------|-----------|-------|
| ISO_A2 | iso_a2 | 2-letter code |
| ISO_A3 | iso_a3 | 3-letter code |
| NAME | name | Country name |
| geometry | geom | MultiPolygon |

### US States (ne_10m_admin_1_states_provinces, filtered to US)
| NE Field | Our Field | Notes |
|----------|-----------|-------|
| postal | state_code | 2-letter USPS code |
| name | name | State name |
| geometry | geom | MultiPolygon |
