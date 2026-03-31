# haminfo_dashboard/geo_cache.py
"""Geographic caching for reverse geocoding lookups."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import threading
from typing import Optional

# TYPE_CHECKING block reserved for future use (e.g., Session for DB lookups)


@dataclass
class LocationInfo:
    """Geographic location information for a coordinate."""

    country_code: Optional[str]  # ISO 3166-1 alpha-2 (e.g., "US")
    state_code: Optional[str]  # For US locations only (e.g., "CA")


class GeoCache:
    """Thread-safe LRU cache for geographic lookups.

    Uses grid-based bucketing to map nearby coordinates to the same
    cache entry. Default resolution of 0.1 degrees (~11km).
    """

    def __init__(self, max_size: int = 100_000, grid_resolution: float = 0.1):
        self._cache: OrderedDict[tuple[float, float], LocationInfo] = OrderedDict()
        self._max_size = max_size
        self._resolution = grid_resolution
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _grid_key(self, lat: float, lon: float) -> tuple[float, float]:
        """Round coordinates to grid resolution."""
        return (
            round(lat / self._resolution) * self._resolution,
            round(lon / self._resolution) * self._resolution,
        )

    def get(self, lat: float, lon: float) -> Optional[LocationInfo]:
        """Get cached location info for coordinates."""
        key = self._grid_key(lat, lon)
        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key)  # LRU update
                return self._cache[key]
            self._misses += 1
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

    @property
    def stats(self) -> dict[str, float]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                'hits': self._hits,
                'misses': self._misses,
                'size': len(self._cache),
                'hit_rate': self._hits / max(1, total),
            }

    def clear(self) -> None:
        """Clear all cached entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global cache instance
geo_cache = GeoCache()
