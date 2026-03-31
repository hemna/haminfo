"""Tests for geographic caching module."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from haminfo_dashboard.geo_cache import GeoCache, LocationInfo, geo_cache


class TestLocationInfo:
    """Tests for LocationInfo dataclass."""

    def test_create_with_country_only(self):
        """LocationInfo with just country code."""
        info = LocationInfo(country_code='US', state_code=None)
        assert info.country_code == 'US'
        assert info.state_code is None

    def test_create_with_country_and_state(self):
        """LocationInfo with country and state codes."""
        info = LocationInfo(country_code='US', state_code='CA')
        assert info.country_code == 'US'
        assert info.state_code == 'CA'

    def test_create_with_no_location(self):
        """LocationInfo for ocean/unknown location."""
        info = LocationInfo(country_code=None, state_code=None)
        assert info.country_code is None
        assert info.state_code is None


class TestGeoCache:
    """Tests for GeoCache class."""

    def test_grid_key_rounds_to_resolution(self):
        """Coordinates should round to grid resolution (0.1 degrees)."""
        cache = GeoCache(grid_resolution=0.1)
        # 42.123 rounds to 42.1, -71.456 rounds to -71.5
        key = cache._grid_key(42.123, -71.456)
        assert key == (42.1, -71.5)

    def test_grid_key_handles_negative_coordinates(self):
        """Grid key should work correctly with negative coordinates."""
        cache = GeoCache(grid_resolution=0.1)
        # -33.856 rounds to -33.9, 151.209 rounds to 151.2
        key = cache._grid_key(-33.856, 151.209)
        # Use pytest.approx for floating point comparison
        assert key == pytest.approx((-33.9, 151.2))

    def test_cache_miss_returns_none(self):
        """get() on empty cache should return None."""
        cache = GeoCache()
        result = cache.get(42.123, -71.456)
        assert result is None

    def test_cache_hit_after_put(self):
        """put() then get() should return cached value."""
        cache = GeoCache()
        info = LocationInfo(country_code='US', state_code='MA')
        cache.put(42.123, -71.456, info)
        result = cache.get(42.123, -71.456)
        assert result is not None
        assert result.country_code == 'US'
        assert result.state_code == 'MA'

    def test_nearby_coordinates_share_cache_entry(self):
        """Coordinates within same grid cell should share cache entry."""
        cache = GeoCache(grid_resolution=0.1)
        info = LocationInfo(country_code='US', state_code='MA')

        # Put at 42.123
        cache.put(42.123, -71.456, info)

        # Get at 42.149 (rounds to same 42.1 grid cell)
        result = cache.get(42.149, -71.456)
        assert result is not None
        assert result.country_code == 'US'

    def test_lru_eviction(self):
        """Oldest entry should be evicted when max_size exceeded."""
        cache = GeoCache(max_size=3, grid_resolution=0.1)

        # Add 3 items
        cache.put(1.0, 1.0, LocationInfo(country_code='A', state_code=None))
        cache.put(2.0, 2.0, LocationInfo(country_code='B', state_code=None))
        cache.put(3.0, 3.0, LocationInfo(country_code='C', state_code=None))

        # Verify all 3 exist (these get() calls change LRU order)
        # After puts: [1, 2, 3] - 1 is oldest
        # After get(1): [2, 3, 1] - 2 is oldest
        # After get(2): [3, 1, 2] - 3 is oldest
        # After get(3): [1, 2, 3] - 1 is oldest again
        assert cache.get(1.0, 1.0) is not None
        assert cache.get(2.0, 2.0) is not None
        assert cache.get(3.0, 3.0) is not None

        # Add 4th item - should evict item 1 (the oldest after the gets)
        cache.put(4.0, 4.0, LocationInfo(country_code='D', state_code=None))

        # Item 1 should be evicted (it was oldest)
        assert cache.get(1.0, 1.0) is None
        # Others should still exist
        assert cache.get(2.0, 2.0) is not None
        assert cache.get(3.0, 3.0) is not None
        assert cache.get(4.0, 4.0) is not None

    def test_stats_tracking(self):
        """Stats should track hits, misses, size, and hit_rate correctly."""
        cache = GeoCache()
        info = LocationInfo(country_code='US', state_code=None)

        # Initial state
        stats = cache.stats
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['size'] == 0
        assert stats['hit_rate'] == 0.0

        # Miss
        cache.get(1.0, 1.0)
        stats = cache.stats
        assert stats['misses'] == 1
        assert stats['hits'] == 0

        # Put and hit
        cache.put(1.0, 1.0, info)
        cache.get(1.0, 1.0)
        stats = cache.stats
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['size'] == 1
        assert stats['hit_rate'] == 0.5  # 1 hit / 2 total

    def test_thread_safety(self):
        """Concurrent reads/writes should not raise exceptions."""
        cache = GeoCache(max_size=100)
        errors = []

        def writer(thread_id: int):
            try:
                for i in range(100):
                    lat = float(thread_id * 100 + i) / 10
                    cache.put(
                        lat,
                        lat,
                        LocationInfo(country_code=f'T{thread_id}', state_code=None),
                    )
            except Exception as e:
                errors.append(e)

        def reader(thread_id: int):
            try:
                for i in range(100):
                    lat = float(thread_id * 100 + i) / 10
                    cache.get(lat, lat)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(5):
                futures.append(executor.submit(writer, i))
                futures.append(executor.submit(reader, i))

            for f in futures:
                f.result()

        assert len(errors) == 0, f'Thread safety errors: {errors}'


class TestGlobalCache:
    """Tests for global cache instance."""

    def test_global_cache_exists(self):
        """geo_cache should be a GeoCache instance."""
        assert geo_cache is not None
        assert isinstance(geo_cache, GeoCache)
