# Geographic Filtering Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unreliable callsign-prefix country detection with accurate PostGIS reverse geocoding using an in-memory LRU cache.

**Architecture:** Load Natural Earth country/state polygons into PostGIS tables. Application maintains a grid-based LRU cache for fast lookups (~11km resolution). Cache is warmed on startup from recent packets, with lazy population on cache misses via PostGIS `ST_Contains()` queries.

**Tech Stack:** PostgreSQL + PostGIS 3.4, Python (Flask), Natural Earth 10m boundaries, ogr2ogr/shp2pgsql for data loading.

**Spec:** `docs/superpowers/specs/002-geographic-filtering.md`

---

## Chunk 1: Database Schema and Data Loading

### Task 1: Create Alembic Migration for Boundary Tables

**Files:**
- Create: `haminfo/alembic/versions/xxx_add_boundary_tables.py`

- [ ] **Step 1: Generate migration file**

```bash
cd haminfo && alembic revision -m "add_boundary_tables"
```

- [ ] **Step 2: Write migration content**

```python
"""add_boundary_tables

Revision ID: <generated>
Revises: <previous>
Create Date: <auto>
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers
revision = '<generated>'
down_revision = '<previous>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create countries table
    op.create_table(
        'countries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('iso_a2', sa.String(2), nullable=False),
        sa.Column('iso_a3', sa.String(3), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('geom', Geometry('MULTIPOLYGON', srid=4326), nullable=False),
    )
    op.create_index('idx_countries_geom', 'countries', ['geom'], postgresql_using='gist')
    op.create_index('idx_countries_iso_a2', 'countries', ['iso_a2'], unique=True)

    # Create us_states table
    op.create_table(
        'us_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('geom', Geometry('MULTIPOLYGON', srid=4326), nullable=False),
    )
    op.create_index('idx_us_states_geom', 'us_states', ['geom'], postgresql_using='gist')
    op.create_index('idx_us_states_code', 'us_states', ['state_code'], unique=True)


def downgrade() -> None:
    op.drop_table('us_states')
    op.drop_table('countries')
```

- [ ] **Step 3: Run migration**

```bash
cd haminfo && alembic upgrade head
```

Expected: Tables `countries` and `us_states` created with spatial indexes.

- [ ] **Step 4: Verify tables exist**

```bash
psql -h localhost -U haminfo -d haminfo -c "\dt countries"
psql -h localhost -U haminfo -d haminfo -c "\dt us_states"
```

Expected: Both tables listed.

- [ ] **Step 5: Commit**

```bash
git add haminfo/alembic/versions/*add_boundary_tables*.py
git commit -m "feat: add boundary tables migration for geographic filtering"
```

---

### Task 2: Create Natural Earth Data Loading Script

**Files:**
- Create: `scripts/load_natural_earth.py`

- [ ] **Step 1: Create the loading script**

```python
#!/usr/bin/env python3
"""Load Natural Earth boundaries into PostGIS.

Downloads Natural Earth 10m Admin 0 (countries) and Admin 1 (states/provinces),
then loads them into the countries and us_states tables.

Usage:
    python scripts/load_natural_earth.py --db-url postgresql://user:pass@host/db

Requires: ogr2ogr (from GDAL), wget or curl
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Natural Earth 10m data URLs
COUNTRIES_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
STATES_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip"


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and print it."""
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def download_and_extract(url: str, dest_dir: Path) -> Path:
    """Download a zip file and extract it."""
    zip_name = url.split("/")[-1]
    zip_path = dest_dir / zip_name
    
    # Download
    print(f"Downloading {zip_name}...")
    run_cmd(["curl", "-L", "-o", str(zip_path), url])
    
    # Extract
    print(f"Extracting {zip_name}...")
    run_cmd(["unzip", "-o", str(zip_path), "-d", str(dest_dir)])
    
    # Return path to shapefile (without .zip extension, with .shp)
    shp_name = zip_name.replace(".zip", ".shp")
    return dest_dir / shp_name


def load_countries(db_url: str, shp_path: Path) -> None:
    """Load country boundaries into PostGIS."""
    print("\nLoading countries...")
    
    # Use ogr2ogr to load shapefile into PostGIS
    # -nln: table name
    # -overwrite: replace existing data
    # -lco: layer creation options
    # -sql: select only needed columns and rename geometry
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:{db_url}",
        str(shp_path),
        "-nln", "countries",
        "-overwrite",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=id",
        "-sql", """
            SELECT 
                ISO_A2 as iso_a2,
                ISO_A3 as iso_a3,
                NAME as name
            FROM ne_10m_admin_0_countries
            WHERE ISO_A2 != '-99'
        """,
        "-nlt", "MULTIPOLYGON",
        "-t_srs", "EPSG:4326",
    ]
    
    result = run_cmd(cmd, check=False)
    if result.returncode != 0:
        print(f"Error loading countries: {result.stderr}")
        sys.exit(1)
    
    print(f"  Countries loaded successfully")


def load_us_states(db_url: str, shp_path: Path) -> None:
    """Load US state boundaries into PostGIS."""
    print("\nLoading US states...")
    
    # Filter to US only (iso_a2 = 'US') and use postal code
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:{db_url}",
        str(shp_path),
        "-nln", "us_states",
        "-overwrite",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=id",
        "-sql", """
            SELECT 
                postal as state_code,
                name as name
            FROM ne_10m_admin_1_states_provinces
            WHERE iso_a2 = 'US' AND postal IS NOT NULL
        """,
        "-nlt", "MULTIPOLYGON",
        "-t_srs", "EPSG:4326",
    ]
    
    result = run_cmd(cmd, check=False)
    if result.returncode != 0:
        print(f"Error loading US states: {result.stderr}")
        sys.exit(1)
    
    print(f"  US states loaded successfully")


def verify_data(db_url: str) -> None:
    """Verify data was loaded correctly."""
    import psycopg2
    
    # Parse connection string for psycopg2
    # db_url format: postgresql://user:pass@host:port/dbname
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM countries")
    country_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM us_states")
    state_count = cur.fetchone()[0]
    
    # Test a known point (New York City)
    cur.execute("""
        SELECT iso_a2 FROM countries 
        WHERE ST_Contains(geom, ST_SetSRID(ST_Point(-74.006, 40.7128), 4326))
    """)
    nyc_country = cur.fetchone()
    
    cur.execute("""
        SELECT state_code FROM us_states 
        WHERE ST_Contains(geom, ST_SetSRID(ST_Point(-74.006, 40.7128), 4326))
    """)
    nyc_state = cur.fetchone()
    
    conn.close()
    
    print(f"\nVerification:")
    print(f"  Countries loaded: {country_count}")
    print(f"  US states loaded: {state_count}")
    print(f"  NYC test - Country: {nyc_country[0] if nyc_country else 'NOT FOUND'}")
    print(f"  NYC test - State: {nyc_state[0] if nyc_state else 'NOT FOUND'}")
    
    if country_count < 200:
        print("WARNING: Expected ~250 countries, got less")
    if state_count < 50:
        print("WARNING: Expected ~50 US states, got less")
    if nyc_country and nyc_country[0] != 'US':
        print("WARNING: NYC should be in US")
    if nyc_state and nyc_state[0] != 'NY':
        print("WARNING: NYC should be in NY")


def main():
    parser = argparse.ArgumentParser(description="Load Natural Earth data into PostGIS")
    parser.add_argument(
        "--db-url",
        required=True,
        help="PostgreSQL connection URL (postgresql://user:pass@host/db)"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download, use existing files in temp dir"
    )
    args = parser.parse_args()
    
    # Use a persistent temp directory for caching downloads
    work_dir = Path(tempfile.gettempdir()) / "natural_earth_data"
    work_dir.mkdir(exist_ok=True)
    
    if not args.skip_download:
        countries_shp = download_and_extract(COUNTRIES_URL, work_dir)
        states_shp = download_and_extract(STATES_URL, work_dir)
    else:
        countries_shp = work_dir / "ne_10m_admin_0_countries.shp"
        states_shp = work_dir / "ne_10m_admin_1_states_provinces.shp"
    
    load_countries(args.db_url, countries_shp)
    load_us_states(args.db_url, states_shp)
    verify_data(args.db_url)
    
    print("\n✓ Natural Earth data loaded successfully!")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x scripts/load_natural_earth.py
```

- [ ] **Step 3: Test script locally (or on prod)**

```bash
python scripts/load_natural_earth.py --db-url "postgresql://haminfo:password@localhost/haminfo"
```

Expected output:
```
Downloading ne_10m_admin_0_countries.zip...
Extracting ne_10m_admin_0_countries.zip...
Downloading ne_10m_admin_1_states_provinces.zip...
Extracting ne_10m_admin_1_states_provinces.zip...

Loading countries...
  Countries loaded successfully

Loading US states...
  US states loaded successfully

Verification:
  Countries loaded: ~250
  US states loaded: ~51
  NYC test - Country: US
  NYC test - State: NY

✓ Natural Earth data loaded successfully!
```

- [ ] **Step 4: Commit**

```bash
git add scripts/load_natural_earth.py
git commit -m "feat: add Natural Earth data loading script"
```

---

## Chunk 2: Geo Cache Module with Tests

### Task 3: Create GeoCache Class with Unit Tests

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`
- Create: `haminfo-dashboard/tests/test_geo_cache.py`

- [ ] **Step 1: Write failing tests for GeoCache**

Create `haminfo-dashboard/tests/test_geo_cache.py`:

```python
# tests/test_geo_cache.py
"""Tests for geographic caching module."""

import pytest
from unittest.mock import MagicMock, patch

from haminfo_dashboard.geo_cache import (
    LocationInfo,
    GeoCache,
    geo_cache,
)


class TestLocationInfo:
    """Tests for LocationInfo dataclass."""

    def test_create_with_country_only(self):
        """Test creating LocationInfo with just country."""
        info = LocationInfo(country_code="US", state_code=None)
        assert info.country_code == "US"
        assert info.state_code is None

    def test_create_with_country_and_state(self):
        """Test creating LocationInfo with country and state."""
        info = LocationInfo(country_code="US", state_code="CA")
        assert info.country_code == "US"
        assert info.state_code == "CA"

    def test_create_with_no_location(self):
        """Test creating LocationInfo for ocean/unknown."""
        info = LocationInfo(country_code=None, state_code=None)
        assert info.country_code is None
        assert info.state_code is None


class TestGeoCache:
    """Tests for GeoCache class."""

    def test_grid_key_rounds_to_resolution(self):
        """Test that coordinates are rounded to grid resolution."""
        cache = GeoCache(grid_resolution=0.1)
        
        # 42.123 should round to 42.1
        key1 = cache._grid_key(42.123, -71.456)
        assert key1 == (42.1, -71.5)
        
        # 42.149 should also round to 42.1
        key2 = cache._grid_key(42.149, -71.449)
        assert key2 == (42.1, -71.4)

    def test_grid_key_handles_negative_coordinates(self):
        """Test grid key with negative lat/lon."""
        cache = GeoCache(grid_resolution=0.1)
        key = cache._grid_key(-33.856, 151.209)
        assert key == (-33.9, 151.2)

    def test_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        cache = GeoCache()
        result = cache.get(42.123, -71.456)
        assert result is None

    def test_cache_hit_after_put(self):
        """Test that put followed by get returns cached value."""
        cache = GeoCache()
        info = LocationInfo(country_code="US", state_code="MA")
        
        cache.put(42.123, -71.456, info)
        result = cache.get(42.123, -71.456)
        
        assert result is not None
        assert result.country_code == "US"
        assert result.state_code == "MA"

    def test_nearby_coordinates_share_cache_entry(self):
        """Test that nearby coordinates use same grid cell."""
        cache = GeoCache(grid_resolution=0.1)
        info = LocationInfo(country_code="US", state_code="MA")
        
        # Put at 42.123
        cache.put(42.123, -71.456, info)
        
        # Get at 42.149 (same grid cell)
        result = cache.get(42.149, -71.449)
        
        assert result is not None
        assert result.country_code == "US"

    def test_lru_eviction(self):
        """Test that LRU eviction works when max_size reached."""
        cache = GeoCache(max_size=3, grid_resolution=1.0)
        
        # Fill cache with 3 entries
        cache.put(1.0, 1.0, LocationInfo("A", None))
        cache.put(2.0, 2.0, LocationInfo("B", None))
        cache.put(3.0, 3.0, LocationInfo("C", None))
        
        # Access first entry to make it recently used
        cache.get(1.0, 1.0)
        
        # Add 4th entry - should evict B (least recently used)
        cache.put(4.0, 4.0, LocationInfo("D", None))
        
        # A should still be there (recently accessed)
        assert cache.get(1.0, 1.0) is not None
        # B should be evicted
        assert cache.get(2.0, 2.0) is None
        # C and D should be there
        assert cache.get(3.0, 3.0) is not None
        assert cache.get(4.0, 4.0) is not None

    def test_stats_tracking(self):
        """Test that hit/miss stats are tracked."""
        cache = GeoCache()
        info = LocationInfo(country_code="US", state_code=None)
        
        # Miss
        cache.get(42.0, -71.0)
        
        # Put and hit
        cache.put(42.0, -71.0, info)
        cache.get(42.0, -71.0)
        cache.get(42.0, -71.0)
        
        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 2 / 3

    def test_thread_safety(self):
        """Test that cache is thread-safe."""
        import threading
        
        cache = GeoCache(max_size=1000)
        errors = []
        
        def writer():
            for i in range(100):
                cache.put(float(i), float(i), LocationInfo("X", None))
        
        def reader():
            for i in range(100):
                try:
                    cache.get(float(i), float(i))
                except Exception as e:
                    errors.append(e)
        
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestGlobalCache:
    """Tests for global geo_cache instance."""

    def test_global_cache_exists(self):
        """Test that global cache is initialized."""
        assert geo_cache is not None
        assert isinstance(geo_cache, GeoCache)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'haminfo_dashboard.geo_cache'"

- [ ] **Step 3: Implement GeoCache module**

Create `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`:

```python
# haminfo_dashboard/geo_cache.py
"""Geographic caching for reverse geocoding lookups.

Provides an in-memory LRU cache for mapping coordinates to countries/states.
Uses grid-based bucketing to reduce cache size while maintaining accuracy.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class LocationInfo:
    """Geographic location information for a coordinate."""
    
    country_code: Optional[str]  # ISO 3166-1 alpha-2 (e.g., "US")
    state_code: Optional[str]    # For US locations only (e.g., "CA")


class GeoCache:
    """Thread-safe LRU cache for geographic lookups.
    
    Uses grid-based bucketing to map nearby coordinates to the same
    cache entry. Default resolution of 0.1 degrees (~11km) provides
    a good balance between accuracy and cache efficiency.
    
    Attributes:
        max_size: Maximum number of entries before LRU eviction.
        grid_resolution: Coordinate rounding resolution in degrees.
    """
    
    def __init__(
        self,
        max_size: int = 100_000,
        grid_resolution: float = 0.1,
    ):
        """Initialize the cache.
        
        Args:
            max_size: Maximum cache entries (default 100k).
            grid_resolution: Grid cell size in degrees (default 0.1 ≈ 11km).
        """
        self._cache: OrderedDict[tuple[float, float], LocationInfo] = OrderedDict()
        self._max_size = max_size
        self._resolution = grid_resolution
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
    
    def _grid_key(self, lat: float, lon: float) -> tuple[float, float]:
        """Round coordinates to grid resolution.
        
        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.
            
        Returns:
            Tuple of (rounded_lat, rounded_lon).
        """
        return (
            round(lat / self._resolution) * self._resolution,
            round(lon / self._resolution) * self._resolution,
        )
    
    def get(self, lat: float, lon: float) -> Optional[LocationInfo]:
        """Get cached location info for coordinates.
        
        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.
            
        Returns:
            LocationInfo if cached, None otherwise.
        """
        key = self._grid_key(lat, lon)
        with self._lock:
            if key in self._cache:
                self._hits += 1
                # Move to end for LRU
                self._cache.move_to_end(key)
                return self._cache[key]
            self._misses += 1
            return None
    
    def put(self, lat: float, lon: float, info: LocationInfo) -> None:
        """Cache location info for coordinates.
        
        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.
            info: Location information to cache.
        """
        key = self._grid_key(lat, lon)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = info
    
    @property
    def stats(self) -> dict[str, float]:
        """Get cache statistics.
        
        Returns:
            Dict with hits, misses, size, and hit_rate.
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "hit_rate": self._hits / max(1, total),
            }
    
    def clear(self) -> None:
        """Clear all cached entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global cache instance
geo_cache = GeoCache()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/geo_cache.py
git add haminfo-dashboard/tests/test_geo_cache.py
git commit -m "feat: add GeoCache class with LRU eviction and tests"
```

---

### Task 4: Add Reverse Geocoding Functions

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`
- Modify: `haminfo-dashboard/tests/test_geo_cache.py`

- [ ] **Step 1: Add failing tests for reverse geocoding**

Add to `tests/test_geo_cache.py`:

```python
class TestReverseGeocode:
    """Tests for reverse_geocode function."""

    def test_reverse_geocode_finds_country(self):
        """Test that reverse_geocode finds country for valid coordinates."""
        from haminfo_dashboard.geo_cache import reverse_geocode
        
        # Mock session with country result
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = ("US",)
        
        result = reverse_geocode(mock_session, 40.7128, -74.006)
        
        assert result.country_code == "US"

    def test_reverse_geocode_finds_us_state(self):
        """Test that reverse_geocode finds state for US coordinates."""
        from haminfo_dashboard.geo_cache import reverse_geocode
        
        # Mock session: first call returns US, second returns NY
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.side_effect = [
            ("US",),   # Country query
            ("NY",),   # State query
        ]
        
        result = reverse_geocode(mock_session, 40.7128, -74.006)
        
        assert result.country_code == "US"
        assert result.state_code == "NY"

    def test_reverse_geocode_no_state_for_non_us(self):
        """Test that non-US countries don't get state lookup."""
        from haminfo_dashboard.geo_cache import reverse_geocode
        
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = ("DE",)
        
        result = reverse_geocode(mock_session, 52.52, 13.405)  # Berlin
        
        assert result.country_code == "DE"
        assert result.state_code is None
        # Should only have one execute call (country, no state)
        assert mock_session.execute.call_count == 1

    def test_reverse_geocode_ocean_returns_none(self):
        """Test that ocean coordinates return None country."""
        from haminfo_dashboard.geo_cache import reverse_geocode
        
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = None
        
        result = reverse_geocode(mock_session, 0.0, 0.0)  # Gulf of Guinea
        
        assert result.country_code is None
        assert result.state_code is None


class TestGetLocationInfo:
    """Tests for get_location_info function with caching."""

    def test_get_location_info_uses_cache(self):
        """Test that get_location_info checks cache first."""
        from haminfo_dashboard.geo_cache import get_location_info, geo_cache, LocationInfo
        
        # Pre-populate cache
        geo_cache.put(42.0, -71.0, LocationInfo("US", "MA"))
        
        mock_session = MagicMock()
        
        result = get_location_info(mock_session, 42.0, -71.0)
        
        assert result.country_code == "US"
        assert result.state_code == "MA"
        # Session should not be used (cache hit)
        mock_session.execute.assert_not_called()
        
        # Clean up
        geo_cache.clear()

    def test_get_location_info_cache_miss_queries_db(self):
        """Test that cache miss triggers DB query."""
        from haminfo_dashboard.geo_cache import get_location_info, geo_cache
        
        geo_cache.clear()  # Ensure empty cache
        
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.side_effect = [
            ("US",),   # Country
            ("CA",),   # State
        ]
        
        result = get_location_info(mock_session, 34.0522, -118.2437)  # LA
        
        assert result.country_code == "US"
        assert result.state_code == "CA"
        # Should have queried DB
        assert mock_session.execute.call_count == 2
        
        # Clean up
        geo_cache.clear()

    def test_get_location_info_caches_result(self):
        """Test that DB result is cached for future lookups."""
        from haminfo_dashboard.geo_cache import get_location_info, geo_cache
        
        geo_cache.clear()
        
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.side_effect = [
            ("JP",),   # Country (Japan)
            # No state query for non-US
        ]
        
        # First call - cache miss
        result1 = get_location_info(mock_session, 35.6762, 139.6503)  # Tokyo
        
        # Reset mock
        mock_session.reset_mock()
        
        # Second call - should be cache hit
        result2 = get_location_info(mock_session, 35.6762, 139.6503)
        
        assert result1.country_code == "JP"
        assert result2.country_code == "JP"
        # Second call should not hit DB
        mock_session.execute.assert_not_called()
        
        # Clean up
        geo_cache.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py::TestReverseGeocode -v
cd haminfo-dashboard && pytest tests/test_geo_cache.py::TestGetLocationInfo -v
```

Expected: FAIL with "cannot import name 'reverse_geocode'"

- [ ] **Step 3: Implement reverse geocoding functions**

Add to the imports section at the top of `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`:

```python
from sqlalchemy import text
```

Then add the following functions after the `GeoCache` class:

```python
from sqlalchemy import text


def reverse_geocode(session: "Session", lat: float, lon: float) -> LocationInfo:
    """Look up country and state for coordinates using PostGIS.
    
    Queries the countries table (and us_states if in US) to determine
    the geographic location for the given coordinates.
    
    Args:
        session: SQLAlchemy database session.
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        
    Returns:
        LocationInfo with country_code and optional state_code.
    """
    # Query countries table
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
    
    # If US, also query state
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


def get_location_info(session: "Session", lat: float, lon: float) -> LocationInfo:
    """Get location info with caching.
    
    Checks the global geo_cache first, falls back to PostGIS query
    on cache miss, and caches the result for future lookups.
    
    Args:
        session: SQLAlchemy database session.
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        
    Returns:
        LocationInfo with country_code and optional state_code.
    """
    # Check cache first
    cached = geo_cache.get(lat, lon)
    if cached is not None:
        return cached
    
    # Cache miss - query PostGIS
    info = reverse_geocode(session, lat, lon)
    
    # Cache result (including None for ocean/invalid - negative caching)
    geo_cache.put(lat, lon, info)
    
    return info
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/geo_cache.py
git add haminfo-dashboard/tests/test_geo_cache.py
git commit -m "feat: add reverse_geocode and get_location_info functions"
```

---

### Task 5: Add Cache Warm-up Function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`
- Modify: `haminfo-dashboard/tests/test_geo_cache.py`

- [ ] **Step 1: Add failing test for warm_cache**

Add to `tests/test_geo_cache.py`:

```python
class TestWarmCache:
    """Tests for cache warm-up functionality."""

    def test_warm_cache_populates_from_recent_packets(self):
        """Test that warm_cache loads grid cells from recent packets."""
        from haminfo_dashboard.geo_cache import warm_cache, geo_cache
        
        geo_cache.clear()
        
        # Mock session that returns grid cells and country lookups
        mock_session = MagicMock()
        
        # Mock grid cell query result
        mock_grid_result = MagicMock()
        mock_grid_result.fetchall.return_value = [
            (42.1, -71.5),  # Boston area
            (34.1, -118.2),  # LA area
        ]
        
        # Mock country/state lookups
        mock_country_result = MagicMock()
        mock_country_result.fetchone.side_effect = [
            ("US",), ("MA",),  # Boston
            ("US",), ("CA",),  # LA
        ]
        
        # Set up execute to return different mocks based on call
        call_count = [0]
        def mock_execute(query, params=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_grid_result
            return mock_country_result
        
        mock_session.execute.side_effect = mock_execute
        
        stats = warm_cache(mock_session, hours=24)
        
        assert stats["grid_cells_found"] == 2
        assert stats["populated"] == 2
        assert stats["errors"] == 0
        
        # Verify cache was populated
        assert geo_cache.stats["size"] == 2
        
        # Clean up
        geo_cache.clear()

    def test_warm_cache_handles_errors_gracefully(self):
        """Test that warm_cache continues on individual lookup errors."""
        from haminfo_dashboard.geo_cache import warm_cache, geo_cache
        
        geo_cache.clear()
        
        mock_session = MagicMock()
        
        # Grid cells
        mock_grid_result = MagicMock()
        mock_grid_result.fetchall.return_value = [
            (42.1, -71.5),
            (0.0, 0.0),  # This one will error
            (34.1, -118.2),
        ]
        
        call_count = [0]
        def mock_execute(query, params=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_grid_result
            # Simulate error on second grid cell
            if params and params.get("lat") == 0.0:
                raise Exception("Database error")
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("US",)
            return mock_result
        
        mock_session.execute.side_effect = mock_execute
        
        stats = warm_cache(mock_session, hours=24)
        
        assert stats["grid_cells_found"] == 3
        assert stats["populated"] == 2  # 2 succeeded
        assert stats["errors"] == 1     # 1 failed
        
        # Clean up
        geo_cache.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py::TestWarmCache -v
```

Expected: FAIL with "cannot import name 'warm_cache'"

- [ ] **Step 3: Implement warm_cache function**

Add to the imports section at the top of `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py`:

```python
from datetime import datetime, timedelta
```

Then add the following function after `get_location_info`:

```python
from datetime import datetime, timedelta


def warm_cache(session: "Session", hours: int = 24) -> dict[str, int]:
    """Pre-populate cache from recent packets with positions.
    
    Queries distinct grid cells from recent packets and reverse geocodes
    each one to populate the cache. This ensures fast lookups for
    commonly-seen locations.
    
    Args:
        session: SQLAlchemy database session.
        hours: How many hours of history to load (default 24).
        
    Returns:
        Dict with grid_cells_found, populated, errors, and cache_size.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Get distinct grid cells from recent packets
    # Using 0.1 degree resolution to match cache
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
    
    for row in grid_cells:
        try:
            lat = float(row[0])
            lon = float(row[1])
            info = reverse_geocode(session, lat, lon)
            geo_cache.put(lat, lon, info)
            populated += 1
        except Exception:
            errors += 1
            # Continue on individual errors
    
    return {
        "grid_cells_found": len(grid_cells),
        "populated": populated,
        "errors": errors,
        "cache_size": geo_cache.stats["size"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_geo_cache.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/geo_cache.py
git add haminfo-dashboard/tests/test_geo_cache.py
git commit -m "feat: add warm_cache function for startup cache population"
```

---

## Chunk 3: Integration with Dashboard

### Task 6: Integrate Cache Warm-up into App Startup

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/app.py`

- [ ] **Step 1: Add geo cache warm-up to _warm_cache function**

Edit `haminfo-dashboard/src/haminfo_dashboard/app.py`, add to imports:

```python
from haminfo_dashboard.geo_cache import warm_cache as warm_geo_cache, geo_cache
```

Then modify `_warm_cache()` function to add at the end (before session.close()):

```python
def _warm_cache() -> None:
    """Pre-populate cache with expensive queries on startup.

    This ensures the home page loads quickly on first request.
    """
    from haminfo.db.db import setup_session
    from haminfo_dashboard.queries import (
        get_dashboard_stats,
        get_top_stations,
        get_country_breakdown,
        get_hourly_distribution,
    )
    from haminfo_dashboard.geo_cache import warm_cache as warm_geo_cache, geo_cache

    print('Warming cache with dashboard stats...', file=sys.stderr, flush=True)

    try:
        session_factory = setup_session()
        session = session_factory()

        # Pre-cache the main dashboard queries
        get_dashboard_stats(session)
        print('  - Dashboard stats cached', file=sys.stderr, flush=True)

        get_top_stations(session, limit=10)
        print('  - Top stations cached', file=sys.stderr, flush=True)

        get_country_breakdown(session, limit=10)
        print('  - Country breakdown cached', file=sys.stderr, flush=True)

        get_hourly_distribution(session)
        print('  - Hourly distribution cached', file=sys.stderr, flush=True)

        # Warm geo cache for reverse geocoding
        try:
            geo_stats = warm_geo_cache(session, hours=24)
            print(
                f'  - Geo cache warmed: {geo_stats["populated"]} cells, '
                f'{geo_stats["errors"]} errors',
                file=sys.stderr,
                flush=True,
            )
        except Exception as e:
            print(f'  - Geo cache warm-up failed: {e}', file=sys.stderr, flush=True)

        session.close()
        print('Cache warming complete', file=sys.stderr, flush=True)
    except Exception as e:
        print(f'Cache warming failed: {e}', file=sys.stderr, flush=True)
        import traceback

        traceback.print_exc()
```

- [ ] **Step 2: Verify app still starts**

```bash
cd haminfo-dashboard && python -c "from haminfo_dashboard.app import create_app; print('OK')"
```

Expected: "OK" (no import errors)

- [ ] **Step 3: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/app.py
git commit -m "feat: integrate geo cache warm-up into app startup"
```

---

### Task 7: Update WebSocket to Use Geographic Filtering

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/websocket.py`
- Create: `haminfo-dashboard/tests/test_websocket.py`

- [ ] **Step 1: Write failing test for geographic broadcast**

Create `haminfo-dashboard/tests/test_websocket.py`:

```python
# tests/test_websocket.py
"""Tests for WebSocket module."""

import pytest
from unittest.mock import MagicMock, patch


class TestBroadcastPacket:
    """Tests for broadcast_packet function."""

    def test_broadcast_to_live_feed_always(self):
        """Test that packets always go to live_feed room."""
        from haminfo_dashboard.websocket import broadcast_packet, socketio
        
        with patch.object(socketio, 'emit') as mock_emit:
            packet = {"from_call": "W1ABC", "latitude": None, "longitude": None}
            broadcast_packet(packet)
            
            # Should emit to live_feed
            mock_emit.assert_any_call('packet', packet, room='live_feed')

    @patch('haminfo_dashboard.websocket.get_location_info')
    def test_broadcast_to_country_room_with_coords(self, mock_get_location):
        """Test that packets with coords go to country room."""
        from haminfo_dashboard.websocket import broadcast_packet, socketio
        from haminfo_dashboard.geo_cache import LocationInfo
        
        mock_get_location.return_value = LocationInfo("US", "CA")
        
        with patch.object(socketio, 'emit') as mock_emit:
            packet = {"from_call": "W1ABC", "latitude": 34.05, "longitude": -118.24}
            broadcast_packet(packet)
            
            # Should emit to country room
            mock_emit.assert_any_call('packet', packet, room='country:US')

    @patch('haminfo_dashboard.websocket.get_location_info')
    def test_broadcast_to_state_room_for_us(self, mock_get_location):
        """Test that US packets also go to state room."""
        from haminfo_dashboard.websocket import broadcast_packet, socketio
        from haminfo_dashboard.geo_cache import LocationInfo
        
        mock_get_location.return_value = LocationInfo("US", "CA")
        
        with patch.object(socketio, 'emit') as mock_emit:
            packet = {"from_call": "W1ABC", "latitude": 34.05, "longitude": -118.24}
            broadcast_packet(packet)
            
            # Should emit to state room
            mock_emit.assert_any_call('packet', packet, room='state:CA')

    @patch('haminfo_dashboard.websocket.get_location_info')
    def test_no_country_room_for_ocean(self, mock_get_location):
        """Test that ocean coordinates don't emit to country room."""
        from haminfo_dashboard.websocket import broadcast_packet, socketio
        from haminfo_dashboard.geo_cache import LocationInfo
        
        mock_get_location.return_value = LocationInfo(None, None)
        
        with patch.object(socketio, 'emit') as mock_emit:
            packet = {"from_call": "W1ABC", "latitude": 0.0, "longitude": 0.0}
            broadcast_packet(packet)
            
            # Should only emit to live_feed, not country room
            # call_args_list contains Call objects where kwargs are at .kwargs
            calls = [call.kwargs.get('room') for call in mock_emit.call_args_list]
            assert 'live_feed' in calls
            assert not any(room and room.startswith('country:') for room in calls)

    @patch('haminfo_dashboard.websocket.get_location_info')
    def test_handles_geo_lookup_error(self, mock_get_location):
        """Test that geo lookup errors don't break broadcast."""
        from haminfo_dashboard.websocket import broadcast_packet, socketio
        
        mock_get_location.side_effect = Exception("DB error")
        
        with patch.object(socketio, 'emit') as mock_emit:
            packet = {"from_call": "W1ABC", "latitude": 34.05, "longitude": -118.24}
            
            # Should not raise
            broadcast_packet(packet)
            
            # Should still emit to live_feed
            mock_emit.assert_called_with('packet', packet, room='live_feed')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd haminfo-dashboard && pytest tests/test_websocket.py -v
```

Expected: FAIL (various import/mock issues)

- [ ] **Step 3: Update broadcast_packet to use geographic filtering**

Edit `haminfo-dashboard/src/haminfo_dashboard/websocket.py`:

First, update the imports at the top of the file to remove `get_country_from_callsign`:

```python
# haminfo_dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations

from datetime import datetime

from flask_socketio import SocketIO, emit, join_room, leave_room
import gevent

from haminfo_dashboard.utils import (
    get_packet_human_info,
    get_packet_addressee,
    normalize_packet_type,
    # NOTE: get_country_from_callsign removed - using geographic filtering instead
)
```

Then replace the existing `broadcast_packet` function (at the end of the file):

```python
# Module-level session factory (initialized once)
_session_factory = None


def _get_session():
    """Get a database session, initializing factory on first call."""
    global _session_factory
    if _session_factory is None:
        from haminfo.db.db import setup_session
        _session_factory = setup_session()
    return _session_factory()


def broadcast_packet(packet_data: dict):
    """Broadcast new packet to all connected clients.

    Emits to:
    - 'live_feed' room (all clients on homepage/live feed)
    - 'country:<code>' room (clients viewing that country's detail page)
    - 'state:<code>' room (clients viewing that state's detail page, US only)
    
    Uses PostGIS reverse geocoding with caching for geographic filtering.
    """
    if socketio:
        # Always emit to global live feed
        socketio.emit('packet', packet_data, room='live_feed')

        # Geographic filtering for country/state rooms
        lat = packet_data.get('latitude')
        lon = packet_data.get('longitude')

        if lat is not None and lon is not None:
            try:
                from haminfo_dashboard.geo_cache import get_location_info

                session = _get_session()
                try:
                    info = get_location_info(session, lat, lon)

                    if info.country_code:
                        # Broadcast to country room
                        socketio.emit(
                            'packet', packet_data, room=f'country:{info.country_code}'
                        )

                        # If US, also broadcast to state room
                        if info.state_code:
                            socketio.emit(
                                'packet', packet_data, room=f'state:{info.state_code}'
                            )
                finally:
                    session.close()
            except Exception as e:
                # Log error but don't fail the broadcast
                print(f'Geo lookup failed: {e}')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && pytest tests/test_websocket.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/websocket.py
git add haminfo-dashboard/tests/test_websocket.py
git commit -m "feat: update broadcast_packet to use geographic filtering"
```

---

### Task 8: Update Country Query Functions

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py`

- [ ] **Step 1: Update get_all_countries_breakdown to use spatial join**

Edit `haminfo-dashboard/src/haminfo_dashboard/queries.py`.

First, ensure `text` is imported at the top of the file (it should already be there, but verify):

```python
from sqlalchemy import text
```

Then replace the `get_all_countries_breakdown` function and add the new `_get_all_countries_from_spatial` helper:

```python
def get_all_countries_breakdown(session: Session) -> list[dict[str, Any]]:
    """Get packet counts by country for all countries.
    
    Uses PostGIS spatial join to accurately determine country from coordinates,
    rather than callsign prefix matching.
    
    Args:
        session: Database session.
        
    Returns:
        List of dicts with country_code, country_name, unique_stations, packet_count.
    """
    # Check if we have the countries table
    try:
        result = session.execute(text("SELECT 1 FROM countries LIMIT 1"))
        has_countries_table = result.fetchone() is not None
    except Exception:
        has_countries_table = False
    
    if has_countries_table:
        return _get_all_countries_from_spatial(session)
    else:
        # Fallback to prefix-based if countries table not loaded
        return _get_all_countries_from_aggregates(session)


def _get_all_countries_from_spatial(session: Session) -> list[dict[str, Any]]:
    """Get country breakdown using PostGIS spatial join."""
    from haminfo_dashboard.utils import COUNTRY_FLAGS
    
    query = text("""
        SELECT 
            c.iso_a2 as country_code,
            c.name as country_name,
            COUNT(DISTINCT p.from_call) as unique_stations,
            COUNT(*) as packet_count
        FROM aprs_packet p
        JOIN countries c ON ST_Contains(c.geom, ST_SetSRID(ST_Point(p.longitude, p.latitude), 4326))
        WHERE p.created_at > NOW() - INTERVAL '24 hours'
          AND p.latitude IS NOT NULL
          AND p.longitude IS NOT NULL
        GROUP BY c.iso_a2, c.name
        ORDER BY packet_count DESC
    """)
    
    results = session.execute(query).fetchall()
    
    return [
        {
            "country_code": row.country_code,
            "country_name": row.country_name,
            "flag": COUNTRY_FLAGS.get(row.country_code, ""),
            "unique_stations": row.unique_stations,
            "packet_count": row.packet_count,
        }
        for row in results
    ]
```

- [ ] **Step 2: Update get_country_stats to use spatial filtering**

Replace the `get_country_stats` function:

```python
def get_country_stats(session: Session, country_code: str) -> dict[str, Any]:
    """Get statistics for a specific country using geographic filtering.
    
    Args:
        session: Database session.
        country_code: ISO 3166-1 alpha-2 country code (e.g., "US").
        
    Returns:
        Dict with country stats (packet_count, unique_stations, etc.).
    """
    from haminfo_dashboard.utils import COUNTRY_FLAGS, get_country_name
    
    # Check if countries table exists
    try:
        result = session.execute(text("SELECT 1 FROM countries LIMIT 1"))
        has_countries_table = result.fetchone() is not None
    except Exception:
        has_countries_table = False
    
    if has_countries_table:
        query = text("""
            SELECT 
                COUNT(*) as packet_count,
                COUNT(DISTINCT p.from_call) as unique_stations
            FROM aprs_packet p
            JOIN countries c ON ST_Contains(c.geom, ST_SetSRID(ST_Point(p.longitude, p.latitude), 4326))
            WHERE c.iso_a2 = :country_code
              AND p.created_at > NOW() - INTERVAL '24 hours'
              AND p.latitude IS NOT NULL
        """)
        result = session.execute(query, {"country_code": country_code}).fetchone()
    else:
        # Fallback to prefix matching
        from haminfo_dashboard.utils import get_prefixes_for_country
        prefixes = get_prefixes_for_country(country_code)
        if not prefixes:
            return {
                "country_code": country_code,
                "country_name": get_country_name(country_code),
                "flag": COUNTRY_FLAGS.get(country_code, ""),
                "packet_count": 0,
                "unique_stations": 0,
            }
        
        prefix_patterns = [f"{p}%" for p in prefixes]
        query = text("""
            SELECT 
                COUNT(*) as packet_count,
                COUNT(DISTINCT from_call) as unique_stations
            FROM aprs_packet
            WHERE created_at > NOW() - INTERVAL '24 hours'
              AND (""" + " OR ".join([f"from_call LIKE :p{i}" for i in range(len(prefix_patterns))]) + ")")
        
        params = {f"p{i}": p for i, p in enumerate(prefix_patterns)}
        result = session.execute(query, params).fetchone()
    
    return {
        "country_code": country_code,
        "country_name": get_country_name(country_code),
        "flag": COUNTRY_FLAGS.get(country_code, ""),
        "packet_count": result.packet_count if result else 0,
        "unique_stations": result.unique_stations if result else 0,
    }
```

- [ ] **Step 3: Update get_country_top_stations to use spatial filtering**

Replace the `get_country_top_stations` function:

```python
def get_country_top_stations(
    session: Session, country_code: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Get top stations in a country by packet count using geographic filtering.
    
    Args:
        session: Database session.
        country_code: ISO 3166-1 alpha-2 country code.
        limit: Maximum number of stations to return.
        
    Returns:
        List of dicts with callsign and packet_count.
    """
    # Check if countries table exists
    try:
        result = session.execute(text("SELECT 1 FROM countries LIMIT 1"))
        has_countries_table = result.fetchone() is not None
    except Exception:
        has_countries_table = False
    
    if has_countries_table:
        query = text("""
            SELECT 
                p.from_call as callsign,
                COUNT(*) as packet_count
            FROM aprs_packet p
            JOIN countries c ON ST_Contains(c.geom, ST_SetSRID(ST_Point(p.longitude, p.latitude), 4326))
            WHERE c.iso_a2 = :country_code
              AND p.created_at > NOW() - INTERVAL '24 hours'
              AND p.latitude IS NOT NULL
            GROUP BY p.from_call
            ORDER BY packet_count DESC
            LIMIT :limit
        """)
        results = session.execute(query, {"country_code": country_code, "limit": limit}).fetchall()
    else:
        # Fallback to prefix matching
        from haminfo_dashboard.utils import get_prefixes_for_country
        prefixes = get_prefixes_for_country(country_code)
        if not prefixes:
            return []
        
        prefix_patterns = [f"{p}%" for p in prefixes]
        query = text("""
            SELECT 
                from_call as callsign,
                COUNT(*) as packet_count
            FROM aprs_packet
            WHERE created_at > NOW() - INTERVAL '24 hours'
              AND (""" + " OR ".join([f"from_call LIKE :p{i}" for i in range(len(prefix_patterns))]) + """)
            GROUP BY from_call
            ORDER BY packet_count DESC
            LIMIT :limit
        """)
        
        params = {f"p{i}": p for i, p in enumerate(prefix_patterns)}
        params["limit"] = limit
        results = session.execute(query, params).fetchall()
    
    return [
        {"callsign": row.callsign, "packet_count": row.packet_count}
        for row in results
    ]
```

- [ ] **Step 4: Run existing tests and verify spatial queries work**

```bash
cd haminfo-dashboard && pytest tests/ -v
```

Expected: All existing tests PASS.

If tests fail due to the new behavior (e.g., tests that mock prefix-based queries), update them to mock the `countries` table check to return `False` so fallback is used:

```python
# Example: In test setup, mock the table check
mock_session.execute.return_value.fetchone.return_value = None  # No countries table
```

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py
git commit -m "feat: update country queries to use PostGIS spatial filtering"
```

---

### Task 9: Add API Endpoint for Geo Cache Stats

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/api.py`

- [ ] **Step 1: Add geo cache stats endpoint**

Add to `haminfo-dashboard/src/haminfo_dashboard/api.py`:

```python
@dashboard_bp.route('/api/dashboard/geo-cache-stats')
def api_geo_cache_stats():
    """Get geo cache statistics."""
    from haminfo_dashboard.geo_cache import geo_cache
    
    stats = geo_cache.stats
    return jsonify({
        "hits": stats["hits"],
        "misses": stats["misses"],
        "size": stats["size"],
        "hit_rate": round(stats["hit_rate"] * 100, 1),
    })
```

- [ ] **Step 2: Test the endpoint**

```bash
curl http://localhost:5000/api/dashboard/geo-cache-stats
```

Expected: JSON with cache statistics.

- [ ] **Step 3: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/api.py
git commit -m "feat: add geo cache stats API endpoint"
```

---

## Chunk 4: Production Deployment

### Task 10: Deploy and Verify

**Files:**
- N/A (deployment commands)

**Rollback Plan:** If issues arise after deployment:
1. Revert `broadcast_packet()` in websocket.py to use `get_country_from_callsign()` 
2. Keep boundary tables (no harm)
3. Disable geo cache warm-up by commenting out in app.py
4. Redeploy: `docker compose build ... && docker compose up -d haminfo-dashboard`

- [ ] **Step 0: Backup production database**

```bash
ssh waboring@cloud.hemna.com
docker exec haminfo_db pg_dump -U haminfo haminfo > ~/backups/haminfo_$(date +%Y%m%d_%H%M%S).sql
```

Expected: SQL dump file created in ~/backups/

- [ ] **Step 1: Run migration on production**

```bash
ssh waboring@cloud.hemna.com
cd ~/docker/haminfo/haminfo-repo
git pull
cd haminfo
# Verify alembic can connect (uses DATABASE_URL from environment)
alembic current
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade ... -> xxx_add_boundary_tables
```

- [ ] **Step 2: Load Natural Earth data on production**

```bash
python scripts/load_natural_earth.py --db-url "postgresql://haminfo:PASSWORD@haminfo_db/haminfo"
```

Expected output:
```
Downloading ne_10m_admin_0_countries.zip...
Extracting ne_10m_admin_0_countries.zip...
...
Loading countries...
  Countries loaded successfully
Loading US states...
  US states loaded successfully

Verification:
  Countries loaded: 242
  US states loaded: 51
  NYC test - Country: US
  NYC test - State: NY

✓ Natural Earth data loaded successfully!
```

Verify with query:
```bash
docker exec -it haminfo_db psql -U haminfo -c "SELECT COUNT(*) FROM countries; SELECT COUNT(*) FROM us_states;"
```

Expected: ~242 countries, ~51 US states

- [ ] **Step 3: Deploy dashboard**

```bash
cd ~/docker/haminfo
docker compose build --build-arg CACHEBUST=$(date +%s) haminfo-dashboard
docker compose up -d haminfo-dashboard
```

- [ ] **Step 4: Verify geo cache is warming**

```bash
docker logs haminfo-dashboard 2>&1 | grep -i geo
```

Expected output (numbers will vary based on recent activity):
```
  - Geo cache warmed: 15234 cells, 0 errors
```

If errors > 0, check for database connectivity issues.

- [ ] **Step 5: Verify countries page works**

Open https://haminfo.hemna.com/countries and verify:
- [ ] Countries list appears with packet counts (not all zeros)
- [ ] US should have highest packet count typically
- [ ] Click on a country (e.g., US) - detail page loads
- [ ] Top stations list shows callsigns
- [ ] Live feed shows packets (may take a few seconds)
- [ ] Packets appearing match the expected country

Test a known location: Find a packet from a US station, verify it appears on /country/US but NOT on /country/DE.

- [ ] **Step 6: Check geo cache stats**

```bash
curl https://haminfo.hemna.com/api/dashboard/geo-cache-stats
```

Expected response (after a few minutes of operation):
```json
{"hits": 1234, "misses": 56, "size": 15234, "hit_rate": 95.7}
```

Hit rate should be >90% after warm-up. If hit_rate < 50%, investigate:
- Is cache warming completing?
- Are many new locations appearing?

- [ ] **Step 7: Monitor for 10 minutes**

```bash
# Watch for errors in logs
docker logs -f haminfo-dashboard 2>&1 | grep -i "error\|exception\|fail"
```

Expected: No geo-related errors. Some transient network errors are acceptable.

- [ ] **Step 8: Final verification - spatial accuracy test**

Test that geographic filtering is working correctly:
```bash
# Query a packet with known coordinates
docker exec -it haminfo_db psql -U haminfo -c "
  SELECT from_call, latitude, longitude, 
         (SELECT iso_a2 FROM countries WHERE ST_Contains(geom, ST_SetSRID(ST_Point(longitude, latitude), 4326)))
  FROM aprs_packet 
  WHERE latitude IS NOT NULL 
  ORDER BY created_at DESC 
  LIMIT 5;
"
```

Expected: Each packet shows the correct country code based on its coordinates.

---

## Summary

This plan implements geographic filtering in 4 chunks:

1. **Database Schema** - Create boundary tables, load Natural Earth data
2. **Geo Cache Module** - LRU cache with reverse geocoding, tests
3. **Dashboard Integration** - WebSocket broadcasting, query functions, startup warm-up
4. **Production Deployment** - Migration, data load, deploy, verify

Total estimated time: 2-3 hours

Key files created/modified:
- `haminfo/alembic/versions/xxx_add_boundary_tables.py` (new)
- `scripts/load_natural_earth.py` (new)
- `haminfo-dashboard/src/haminfo_dashboard/geo_cache.py` (new)
- `haminfo-dashboard/tests/test_geo_cache.py` (new)
- `haminfo-dashboard/tests/test_websocket.py` (new)
- `haminfo-dashboard/src/haminfo_dashboard/app.py` (modified)
- `haminfo-dashboard/src/haminfo_dashboard/websocket.py` (modified)
- `haminfo-dashboard/src/haminfo_dashboard/queries.py` (modified)
- `haminfo-dashboard/src/haminfo_dashboard/api.py` (modified)
