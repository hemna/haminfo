# Map Tile-Based Caching Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement tile-based memcached caching for the APRS map API to reduce latency from ~500ms to <50ms for cached regions.

**Architecture:** Divide the world into 1°×1° tiles, cache each tile independently with 60-second TTL. When a bbox request comes in, calculate overlapping tiles, fetch from cache (or DB on miss), merge and filter to exact bbox.

**Tech Stack:** Python 3.10+, Flask, SQLAlchemy, pylibmc (memcached), pytest

**Spec:** `docs/superpowers/specs/2026-03-29-map-tile-caching-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `haminfo-dashboard/src/haminfo_dashboard/queries.py` | Add tile query functions |
| `haminfo-dashboard/src/haminfo_dashboard/cache.py` | Already exists - use as-is |
| `haminfo-dashboard/src/haminfo_dashboard/api.py` | Update to use tiled queries |
| `haminfo-dashboard/tests/test_tile_cache.py` | New test file for tile caching |

---

## Chunk 1: Tile Calculation Functions

### Task 1: Add tile calculation helper functions

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py` (add at top after imports)
- Create: `haminfo-dashboard/tests/test_tile_cache.py`

- [ ] **Step 1: Write tests for tile coordinate calculation**

Create `haminfo-dashboard/tests/test_tile_cache.py`:

```python
# tests/test_tile_cache.py
"""Tests for tile-based map caching."""

import pytest


class TestGetTileCoords:
    """Tests for get_tile_coords function."""

    def test_positive_coords(self):
        """Test tile coords for positive lat/lon."""
        from haminfo_dashboard.queries import get_tile_coords
        
        # Portland, OR: 45.523, -122.676 -> tile (45, -123)
        assert get_tile_coords(45.523, -122.676) == (45, -123)

    def test_negative_coords(self):
        """Test tile coords for negative lat/lon."""
        from haminfo_dashboard.queries import get_tile_coords
        
        # Buenos Aires: -34.6, -58.4 -> tile (-35, -59)
        assert get_tile_coords(-34.6, -58.4) == (-35, -59)

    def test_exact_boundary(self):
        """Test coords exactly on tile boundary."""
        from haminfo_dashboard.queries import get_tile_coords
        
        # Exactly 45.0, -123.0 -> tile (45, -123)
        assert get_tile_coords(45.0, -123.0) == (45, -123)

    def test_near_zero(self):
        """Test coords near zero."""
        from haminfo_dashboard.queries import get_tile_coords
        
        # London area: 51.5, -0.1 -> tile (51, -1)
        assert get_tile_coords(51.5, -0.1) == (51, -1)
        # Just east of prime meridian
        assert get_tile_coords(51.5, 0.1) == (51, 0)


class TestGetTilesForBbox:
    """Tests for get_tiles_for_bbox function."""

    def test_single_tile(self):
        """Test bbox within single tile."""
        from haminfo_dashboard.queries import get_tiles_for_bbox
        
        # Small bbox within Portland tile
        tiles = get_tiles_for_bbox(-122.8, 45.4, -122.5, 45.6)
        assert tiles == [(45, -123)]

    def test_multiple_tiles(self):
        """Test bbox spanning multiple tiles."""
        from haminfo_dashboard.queries import get_tiles_for_bbox
        
        # 2x2 tile area
        tiles = get_tiles_for_bbox(-123.5, 45.2, -121.5, 46.8)
        assert set(tiles) == {(45, -124), (45, -123), (45, -122),
                              (46, -124), (46, -123), (46, -122)}

    def test_bbox_order(self):
        """Test tiles are returned in consistent order."""
        from haminfo_dashboard.queries import get_tiles_for_bbox
        
        tiles = get_tiles_for_bbox(-123.0, 45.0, -121.0, 46.0)
        # Should be sorted by lat, then lon
        assert tiles == [(45, -123), (45, -122), (46, -123), (46, -122)]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py -v
```

Expected: FAIL with "cannot import name 'get_tile_coords'"

- [ ] **Step 3: Implement tile calculation functions**

Add to `haminfo-dashboard/src/haminfo_dashboard/queries.py` after the imports section (around line 20):

```python
# Tile-based caching constants
TILE_CACHE_TTL = 60  # seconds
MAX_TILES_PER_REQUEST = 100


def get_tile_coords(latitude: float, longitude: float) -> tuple[int, int]:
    """Get tile coordinates for a lat/lon position.
    
    Tiles are 1° x 1° squares. The tile coordinate is the floor
    of the latitude and longitude.
    
    Args:
        latitude: Latitude in degrees (-90 to 90).
        longitude: Longitude in degrees (-180 to 180).
        
    Returns:
        Tuple of (tile_lat, tile_lon) as integers.
    """
    import math
    return (math.floor(latitude), math.floor(longitude))


def get_tiles_for_bbox(
    min_lon: float,
    min_lat: float, 
    max_lon: float,
    max_lat: float,
) -> list[tuple[int, int]]:
    """Get all tile coordinates that overlap with a bounding box.
    
    Args:
        min_lon: Western edge of bbox.
        min_lat: Southern edge of bbox.
        max_lon: Eastern edge of bbox.
        max_lat: Northern edge of bbox.
        
    Returns:
        List of (tile_lat, tile_lon) tuples, sorted by lat then lon.
    """
    import math
    
    start_lat = math.floor(min_lat)
    end_lat = math.floor(max_lat)
    start_lon = math.floor(min_lon)
    end_lon = math.floor(max_lon)
    
    tiles = []
    for lat in range(start_lat, end_lat + 1):
        for lon in range(start_lon, end_lon + 1):
            tiles.append((lat, lon))
    
    return tiles
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetTileCoords -v
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetTilesForBbox -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py haminfo-dashboard/tests/test_tile_cache.py
git commit -m "feat: add tile coordinate calculation functions for map caching"
```

---

## Chunk 2: Tile Query and Cache Functions

### Task 2: Add tile-specific database query function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py`
- Modify: `haminfo-dashboard/tests/test_tile_cache.py`

- [ ] **Step 1: Write test for query_tile_from_db**

Add to `haminfo-dashboard/tests/test_tile_cache.py`:

```python
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestQueryTileFromDb:
    """Tests for query_tile_from_db function."""

    def test_returns_station_dicts(self):
        """Test that query returns compact station dicts."""
        from haminfo_dashboard.queries import query_tile_from_db
        
        # Create mock packet
        mock_packet = MagicMock()
        mock_packet.from_call = 'N0CALL'
        mock_packet.latitude = 45.5
        mock_packet.longitude = -122.6
        mock_packet.packet_type = 'position'
        mock_packet.symbol = '>'
        mock_packet.symbol_table = '/'
        mock_packet.speed = 55.0
        mock_packet.course = 180
        mock_packet.altitude = 100.0
        mock_packet.comment = 'Test station'
        mock_packet.received_at = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_packet]
        
        result = query_tile_from_db(mock_session, 45, -123, 1, '')
        
        assert len(result) == 1
        assert result[0]['callsign'] == 'N0CALL'
        assert result[0]['latitude'] == 45.5
        assert result[0]['longitude'] == -122.6
        assert 'received_at' in result[0]

    def test_filters_by_tile_bounds(self):
        """Test that query filters to tile boundaries."""
        from haminfo_dashboard.queries import query_tile_from_db
        
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        
        query_tile_from_db(mock_session, 45, -123, 1, '')
        
        # Verify filter was called (we can't easily check the exact args)
        assert mock_session.query.return_value.filter.called
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestQueryTileFromDb -v
```

Expected: FAIL with "cannot import name 'query_tile_from_db'"

- [ ] **Step 3: Implement query_tile_from_db**

Add to `haminfo-dashboard/src/haminfo_dashboard/queries.py` after the tile calculation functions:

```python
def query_tile_from_db(
    session: Session,
    tile_lat: int,
    tile_lon: int,
    hours: int,
    station_type: str,
) -> list[dict[str, Any]]:
    """Query database for stations within a single tile.
    
    Returns the most recent packet per callsign within the tile bounds.
    
    Args:
        session: Database session.
        tile_lat: Tile latitude (floor of actual lat).
        tile_lon: Tile longitude (floor of actual lon).
        hours: Hours of history to include.
        station_type: Optional packet type filter (empty string for all).
        
    Returns:
        List of compact station dicts.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    
    # Build filters for the tile
    filters = [
        APRSPacket.received_at >= since,
        APRSPacket.latitude >= tile_lat,
        APRSPacket.latitude < tile_lat + 1,
        APRSPacket.longitude >= tile_lon,
        APRSPacket.longitude < tile_lon + 1,
        APRSPacket.latitude.isnot(None),
        APRSPacket.longitude.isnot(None),
    ]
    
    if station_type:
        filters.append(APRSPacket.packet_type == station_type)
    
    # Query with ordering to get most recent per callsign
    # We'll deduplicate in Python for simplicity
    packets = (
        session.query(APRSPacket)
        .filter(and_(*filters))
        .order_by(APRSPacket.received_at.desc())
        .all()
    )
    
    # Deduplicate by callsign, keeping most recent
    seen: set[str] = set()
    result = []
    
    for packet in packets:
        if packet.from_call in seen:
            continue
        seen.add(packet.from_call)
        
        result.append({
            'callsign': packet.from_call,
            'latitude': packet.latitude,
            'longitude': packet.longitude,
            'packet_type': packet.packet_type,
            'symbol': packet.symbol,
            'symbol_table': packet.symbol_table,
            'speed': packet.speed,
            'course': packet.course,
            'altitude': packet.altitude,
            'comment': packet.comment,
            'received_at': packet.received_at.isoformat() if packet.received_at else None,
        })
    
    return result
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestQueryTileFromDb -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py haminfo-dashboard/tests/test_tile_cache.py
git commit -m "feat: add query_tile_from_db for single tile database queries"
```

---

### Task 3: Add get_tile_stations with caching

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py`
- Modify: `haminfo-dashboard/tests/test_tile_cache.py`

- [ ] **Step 1: Write tests for get_tile_stations**

Add to `haminfo-dashboard/tests/test_tile_cache.py`:

```python
class TestGetTileStations:
    """Tests for get_tile_stations with caching."""

    @patch('haminfo_dashboard.queries.cache')
    def test_returns_cached_data_on_hit(self, mock_cache):
        """Test cache hit returns cached data without DB query."""
        from haminfo_dashboard.queries import get_tile_stations
        
        cached_data = [{'callsign': 'CACHED', 'latitude': 45.5}]
        mock_cache.get.return_value = cached_data
        
        mock_session = MagicMock()
        result = get_tile_stations(mock_session, 45, -123, 1, '')
        
        assert result == cached_data
        mock_session.query.assert_not_called()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_tile_from_db')
    def test_queries_db_on_cache_miss(self, mock_query, mock_cache):
        """Test cache miss queries DB and stores result."""
        from haminfo_dashboard.queries import get_tile_stations
        
        mock_cache.get.return_value = None
        db_data = [{'callsign': 'FRESH', 'latitude': 45.5}]
        mock_query.return_value = db_data
        
        mock_session = MagicMock()
        result = get_tile_stations(mock_session, 45, -123, 1, '')
        
        assert result == db_data
        mock_query.assert_called_once()
        mock_cache.set.assert_called_once()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_tile_from_db')
    def test_cache_key_format(self, mock_query, mock_cache):
        """Test cache key includes all parameters."""
        from haminfo_dashboard.queries import get_tile_stations
        
        mock_cache.get.return_value = None
        mock_query.return_value = []
        
        mock_session = MagicMock()
        get_tile_stations(mock_session, 45, -123, 1, 'weather')
        
        # Verify cache key format
        cache_key = mock_cache.get.call_args[0][0]
        assert 'map:tile:1:weather:45:-123' == cache_key
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetTileStations -v
```

Expected: FAIL with "cannot import name 'get_tile_stations'"

- [ ] **Step 3: Implement get_tile_stations**

Add to `haminfo-dashboard/src/haminfo_dashboard/queries.py` after query_tile_from_db:

```python
def get_tile_stations(
    session: Session,
    tile_lat: int,
    tile_lon: int,
    hours: int,
    station_type: str,
) -> list[dict[str, Any]]:
    """Get stations for a tile, using cache when available.
    
    Args:
        session: Database session.
        tile_lat: Tile latitude coordinate.
        tile_lon: Tile longitude coordinate.
        hours: Hours of history.
        station_type: Packet type filter (empty string for all).
        
    Returns:
        List of station dicts.
    """
    from haminfo_dashboard import cache
    
    cache_key = f"map:tile:{hours}:{station_type}:{tile_lat}:{tile_lon}"
    
    # Try cache first
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            LOG.debug(f"Tile cache hit: {cache_key}")
            return cached
    except Exception as e:
        LOG.warning(f"Cache read failed for {cache_key}: {e}")
    
    # Cache miss - query database
    LOG.debug(f"Tile cache miss: {cache_key}")
    stations = query_tile_from_db(session, tile_lat, tile_lon, hours, station_type)
    
    # Store in cache
    try:
        cache.set(cache_key, stations, ttl=TILE_CACHE_TTL)
    except Exception as e:
        LOG.warning(f"Cache write failed for {cache_key}: {e}")
    
    return stations
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetTileStations -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py haminfo-dashboard/tests/test_tile_cache.py
git commit -m "feat: add get_tile_stations with memcached caching"
```

---

## Chunk 3: Main Tiled Query Function

### Task 4: Add get_map_stations_tiled orchestration function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py`
- Modify: `haminfo-dashboard/tests/test_tile_cache.py`

- [ ] **Step 1: Write tests for get_map_stations_tiled**

Add to `haminfo-dashboard/tests/test_tile_cache.py`:

```python
class TestGetMapStationsTiled:
    """Tests for get_map_stations_tiled orchestration."""

    @patch('haminfo_dashboard.queries.get_tile_stations')
    def test_fetches_all_tiles(self, mock_get_tile):
        """Test that all overlapping tiles are fetched."""
        from haminfo_dashboard.queries import get_map_stations_tiled
        
        mock_get_tile.return_value = []
        mock_session = MagicMock()
        
        # 2x2 tile area
        get_map_stations_tiled(
            mock_session,
            bbox=(-123.5, 45.2, -121.5, 46.8),
            hours=1,
            station_type='',
            limit=500,
        )
        
        # Should fetch 6 tiles (3 lon x 2 lat)
        assert mock_get_tile.call_count == 6

    @patch('haminfo_dashboard.queries.get_tile_stations')
    def test_deduplicates_by_callsign(self, mock_get_tile):
        """Test that duplicate callsigns are deduplicated."""
        from haminfo_dashboard.queries import get_map_stations_tiled
        
        # Same station appears in two tiles
        mock_get_tile.side_effect = [
            [{'callsign': 'N0CALL', 'latitude': 45.5, 'longitude': -122.5, 
              'received_at': '2026-03-29T12:00:00'}],
            [{'callsign': 'N0CALL', 'latitude': 45.5, 'longitude': -122.5,
              'received_at': '2026-03-29T11:00:00'}],  # Older
        ]
        mock_session = MagicMock()
        
        result = get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -121.0, 46.0),
            hours=1,
            station_type='',
            limit=500,
        )
        
        # Should have only one station (most recent)
        assert len(result) == 1
        assert result[0]['callsign'] == 'N0CALL'

    @patch('haminfo_dashboard.queries.get_tile_stations')
    def test_filters_to_exact_bbox(self, mock_get_tile):
        """Test that results are filtered to exact bbox."""
        from haminfo_dashboard.queries import get_map_stations_tiled
        
        # Station outside exact bbox but inside tile
        mock_get_tile.return_value = [
            {'callsign': 'INSIDE', 'latitude': 45.5, 'longitude': -122.5,
             'received_at': '2026-03-29T12:00:00'},
            {'callsign': 'OUTSIDE', 'latitude': 45.1, 'longitude': -122.9,
             'received_at': '2026-03-29T12:00:00'},  # Outside bbox
        ]
        mock_session = MagicMock()
        
        result = get_map_stations_tiled(
            mock_session,
            bbox=(-122.7, 45.4, -122.3, 45.7),  # Tight bbox
            hours=1,
            station_type='',
            limit=500,
        )
        
        assert len(result) == 1
        assert result[0]['callsign'] == 'INSIDE'

    @patch('haminfo_dashboard.queries.get_tile_stations')
    def test_respects_limit(self, mock_get_tile):
        """Test that limit is applied to results."""
        from haminfo_dashboard.queries import get_map_stations_tiled
        
        # Return many stations
        mock_get_tile.return_value = [
            {'callsign': f'CALL{i}', 'latitude': 45.5, 'longitude': -122.5,
             'received_at': f'2026-03-29T{12-i:02d}:00:00'}
            for i in range(10)
        ]
        mock_session = MagicMock()
        
        result = get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -122.0, 46.0),
            hours=1,
            station_type='',
            limit=3,
        )
        
        assert len(result) == 3

    @patch('haminfo_dashboard.queries.get_tile_stations')
    def test_limits_tiles_per_request(self, mock_get_tile):
        """Test that too many tiles are truncated."""
        from haminfo_dashboard.queries import get_map_stations_tiled, MAX_TILES_PER_REQUEST
        
        mock_get_tile.return_value = []
        mock_session = MagicMock()
        
        # Request huge bbox that would span many tiles
        get_map_stations_tiled(
            mock_session,
            bbox=(-180.0, -90.0, 180.0, 90.0),  # Whole world
            hours=1,
            station_type='',
            limit=500,
        )
        
        # Should be capped at MAX_TILES_PER_REQUEST
        assert mock_get_tile.call_count <= MAX_TILES_PER_REQUEST
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetMapStationsTiled -v
```

Expected: FAIL with "cannot import name 'get_map_stations_tiled'"

- [ ] **Step 3: Implement get_map_stations_tiled**

Add to `haminfo-dashboard/src/haminfo_dashboard/queries.py` after get_tile_stations:

```python
def get_map_stations_tiled(
    session: Session,
    bbox: tuple[float, float, float, float],
    hours: int,
    station_type: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Get map stations using tile-based caching.
    
    Calculates tiles overlapping the bbox, fetches each tile (from cache
    or DB), merges results, deduplicates by callsign, filters to exact
    bbox, and applies limit.
    
    Args:
        session: Database session.
        bbox: Bounding box (min_lon, min_lat, max_lon, max_lat).
        hours: Hours of history.
        station_type: Packet type filter (empty string for all).
        limit: Maximum stations to return.
        
    Returns:
        List of station dicts sorted by recency.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    
    # Get tiles for bbox
    tiles = get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat)
    
    # Limit tiles to prevent abuse
    if len(tiles) > MAX_TILES_PER_REQUEST:
        LOG.warning(f"Bbox too large: {len(tiles)} tiles, limiting to {MAX_TILES_PER_REQUEST}")
        tiles = tiles[:MAX_TILES_PER_REQUEST]
    
    # Fetch all tiles
    all_stations: dict[str, dict[str, Any]] = {}
    
    for tile_lat, tile_lon in tiles:
        tile_data = get_tile_stations(session, tile_lat, tile_lon, hours, station_type)
        
        for station in tile_data:
            callsign = station['callsign']
            # Keep most recent if duplicate
            if callsign not in all_stations:
                all_stations[callsign] = station
            else:
                existing_time = all_stations[callsign].get('received_at', '')
                new_time = station.get('received_at', '')
                if new_time > existing_time:
                    all_stations[callsign] = station
    
    # Filter to exact bbox
    result = [
        s for s in all_stations.values()
        if (min_lat <= s['latitude'] <= max_lat and
            min_lon <= s['longitude'] <= max_lon)
    ]
    
    # Sort by recency and apply limit
    result.sort(key=lambda s: s.get('received_at', ''), reverse=True)
    
    return result[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestGetMapStationsTiled -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py haminfo-dashboard/tests/test_tile_cache.py
git commit -m "feat: add get_map_stations_tiled orchestration function"
```

---

## Chunk 4: API Integration

### Task 5: Update API to use tiled queries

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/api.py:308-404`

- [ ] **Step 1: Write test for API integration**

Add to `haminfo-dashboard/tests/test_tile_cache.py`:

```python
class TestApiMapStationsIntegration:
    """Integration tests for map stations API with caching."""

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.queries.get_map_stations_tiled')
    @patch('haminfo_dashboard.queries.get_map_stations_fast')
    def test_uses_tiled_query_when_bbox_provided(
        self, mock_fast, mock_tiled, mock_get_session, client
    ):
        """Test that tiled query is used when bbox is provided."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_tiled.return_value = []
        
        response = client.get('/api/dashboard/map/stations?bbox=-123,45,-122,46&hours=1')
        
        assert response.status_code == 200
        mock_tiled.assert_called_once()
        mock_fast.assert_not_called()

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.queries.get_map_stations_tiled')
    @patch('haminfo_dashboard.queries.get_map_stations_fast')
    def test_falls_back_to_fast_when_no_bbox(
        self, mock_fast, mock_tiled, mock_get_session, client
    ):
        """Test that fast query is used when no bbox."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_fast.return_value = []
        
        response = client.get('/api/dashboard/map/stations?hours=1')
        
        assert response.status_code == 200
        mock_fast.assert_called_once()
        mock_tiled.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestApiMapStationsIntegration -v
```

Expected: FAIL (tiled not called because API not updated yet)

- [ ] **Step 3: Update API to use tiled queries**

Modify `haminfo-dashboard/src/haminfo_dashboard/api.py` - replace the api_map_stations function (lines 308-404):

```python
@dashboard_bp.route('/api/dashboard/map/stations')
def api_map_stations():
    """Map stations - returns GeoJSON FeatureCollection.

    Uses tile-based caching when bbox is provided for better performance.
    Falls back to fast query when no bbox is provided.
    
    Supports two modes:
    - fast=true (default): Quick load without trails
    - fast=false: Full load with trails (slower but complete)
    """
    from haminfo_dashboard.queries import (
        get_map_stations_fast,
        get_map_stations_tiled,
        get_map_stations_with_trails,
    )

    session = _get_session()
    try:
        # Parse bbox parameter (min_lon,min_lat,max_lon,max_lat)
        bbox_str = request.args.get('bbox')
        bbox = None
        if bbox_str:
            try:
                parts = [float(x) for x in bbox_str.split(',')]
                if len(parts) == 4:
                    bbox = tuple(parts)
            except ValueError:
                pass

        station_type = request.args.get('type', '')
        limit = request.args.get('limit', 500, type=int)
        offset = request.args.get('offset', 0, type=int)
        hours = request.args.get('hours', 24, type=int)
        # Fast mode: skip trails for quick initial load
        fast_mode = request.args.get('fast', 'true').lower() == 'true'

        # Clamp hours to valid range
        if hours not in (1, 2, 6, 24):
            hours = 24

        # Clamp limit to reasonable range
        limit = min(max(limit, 100), 2000)

        # Use tile-based caching when bbox is provided (most common case)
        if bbox and fast_mode:
            stations = get_map_stations_tiled(
                session,
                bbox=bbox,
                hours=hours,
                station_type=station_type,
                limit=limit,
            )
        elif fast_mode:
            # No bbox - use fast query without caching
            stations = get_map_stations_fast(
                session,
                bbox=bbox,
                station_type=station_type,
                hours=hours,
                limit=limit,
            )
        else:
            # Full query with trails (slower)
            stations = get_map_stations_with_trails(
                session,
                bbox=bbox,
                station_type=station_type,
                hours=hours,
                limit=limit,
                offset=offset,
            )

        # Convert to GeoJSON FeatureCollection
        features = []
        for station in stations:
            if station.get('latitude') and station.get('longitude'):
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [station['longitude'], station['latitude']],
                    },
                    'properties': {
                        'callsign': station['callsign'],
                        'packet_type': station.get('packet_type'),
                        'symbol': station.get('symbol'),
                        'symbol_table': station.get('symbol_table'),
                        'speed': station.get('speed'),
                        'course': station.get('course'),
                        'altitude': station.get('altitude'),
                        'comment': station.get('comment'),
                        'last_seen': station.get('last_seen') or station.get('received_at'),
                        'country_code': station.get('country_code'),
                        'trail': station.get('trail', []),
                    },
                }
                features.append(feature)

        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'mode': 'fast' if fast_mode else 'full',
        }

        return jsonify(geojson)
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_tile_cache.py::TestApiMapStationsIntegration -v
```

Expected: PASS

- [ ] **Step 5: Run all tests to ensure no regressions**

```bash
cd haminfo-dashboard && pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/api.py haminfo-dashboard/tests/test_tile_cache.py
git commit -m "feat: integrate tile-based caching into map stations API"
```

---

## Chunk 5: Deploy and Verify

### Task 6: Deploy to production

**Files:** None (deployment only)

- [ ] **Step 1: Push to remote**

```bash
git push origin master
```

- [ ] **Step 2: Deploy to production**

```bash
ssh waboring@cloud.hemna.com "cd ~/docker/haminfo/haminfo-repo && git pull && cd ~/docker/haminfo && docker compose build --no-cache haminfo-dashboard && docker compose up -d haminfo-dashboard"
```

- [ ] **Step 3: Verify deployment**

Test the API with curl:

```bash
curl -s "https://aprs.hemna.com/api/dashboard/map/stations?bbox=-123,45,-122,46&hours=1&limit=10" | jq '.features | length'
```

Expected: Returns a number (count of features)

- [ ] **Step 4: Verify caching is working**

Make two requests and compare timing:

```bash
# First request (cache miss)
time curl -s "https://aprs.hemna.com/api/dashboard/map/stations?bbox=-123,45,-122,46&hours=1" > /dev/null

# Second request (should be cache hit)
time curl -s "https://aprs.hemna.com/api/dashboard/map/stations?bbox=-123,45,-122,46&hours=1" > /dev/null
```

Expected: Second request should be noticeably faster (~10-50ms vs ~500ms)

---

## Success Criteria

- [ ] All unit tests pass (`pytest tests/test_tile_cache.py -v`)
- [ ] No regressions in existing tests (`pytest tests/ -v`)
- [ ] Map loads successfully in browser
- [ ] Cache hits visible in logs (optional: check memcached stats)
- [ ] Second request for same area is faster than first
