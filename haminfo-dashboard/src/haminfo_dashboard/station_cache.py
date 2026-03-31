# haminfo_dashboard/station_cache.py
"""In-memory cache for station locations.

Tracks the last known country_code for each callsign so that packets
without coordinates can still be routed to country-specific live feeds.
When a packet with coordinates arrives, the station's country is updated.
Subsequent packets from that callsign (even without coordinates) use
the cached country.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

LOG = logging.getLogger(__name__)


@dataclass
class StationLocation:
    """Cached location info for a station."""

    country_code: str
    state_code: Optional[str] = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


class StationLocationCache:
    """In-memory cache mapping callsigns to their last known location.

    Thread-safe for the typical use case of single-writer (poll_packets)
    and single-reader (broadcast_packet) in the same greenlet.
    """

    def __init__(self, max_size: int = 100_000):
        """Initialize cache.

        Args:
            max_size: Maximum number of stations to cache. When exceeded,
                oldest entries are evicted.
        """
        self._cache: dict[str, StationLocation] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, callsign: str) -> Optional[StationLocation]:
        """Get cached location for a callsign.

        Args:
            callsign: The callsign to look up (with or without SSID).

        Returns:
            StationLocation if found, None otherwise.
        """
        # Normalize: strip SSID for lookup
        base_call = callsign.split('-')[0].upper() if callsign else None
        if not base_call:
            return None

        location = self._cache.get(base_call)
        if location:
            self._hits += 1
        else:
            self._misses += 1
        return location

    def update(
        self,
        callsign: str,
        country_code: str,
        state_code: Optional[str] = None,
    ) -> None:
        """Update cached location for a callsign.

        Args:
            callsign: The callsign (with or without SSID).
            country_code: ISO country code (e.g., 'US', 'DE').
            state_code: US state code if applicable (e.g., 'CA', 'TX').
        """
        if not callsign or not country_code:
            return

        # Normalize: strip SSID for storage
        base_call = callsign.split('-')[0].upper()

        # Evict oldest entries if at capacity
        if len(self._cache) >= self._max_size and base_call not in self._cache:
            self._evict_oldest()

        self._cache[base_call] = StationLocation(
            country_code=country_code,
            state_code=state_code,
        )

    def _evict_oldest(self, count: int = 1000) -> None:
        """Evict oldest entries from cache.

        Args:
            count: Number of entries to evict.
        """
        if not self._cache:
            return

        # Sort by updated_at and remove oldest
        sorted_calls = sorted(
            self._cache.keys(),
            key=lambda c: self._cache[c].updated_at,
        )
        for call in sorted_calls[:count]:
            del self._cache[call]

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            'size': len(self._cache),
            'max_size': self._max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': self._hits / total if total > 0 else 0.0,
        }

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# Global cache instance
station_cache = StationLocationCache()


def warm_station_cache(session, hours: int = 24) -> dict:
    """Pre-warm the station cache from recent position packets.

    Loads the most recent position (with country_code) for each unique
    callsign from the last N hours. This ensures that when we receive
    a message/status/telemetry packet, we already know the station's country.

    Args:
        session: SQLAlchemy database session.
        hours: How far back to look for position packets.

    Returns:
        Dict with warming statistics.
    """
    from sqlalchemy import text

    LOG.info(f'Warming station cache from last {hours}h of position packets...')

    # Get most recent country_code for each callsign
    # Uses DISTINCT ON to get one row per callsign (most recent)
    query = text(
        """
        SELECT DISTINCT ON (from_call)
            from_call,
            country_code
        FROM aprs_packet
        WHERE received_at > NOW() - INTERVAL ':hours hours'
          AND country_code IS NOT NULL
        ORDER BY from_call, received_at DESC
    """.replace(':hours', str(hours))
    )

    try:
        result = session.execute(query)
        count = 0
        for row in result:
            station_cache.update(row.from_call, row.country_code)
            count += 1

        LOG.info(f'Station cache warmed with {count} stations')
        return {'stations_loaded': count, 'hours': hours}

    except Exception as e:
        LOG.error(f'Failed to warm station cache: {e}')
        return {'stations_loaded': 0, 'hours': hours, 'error': str(e)}
