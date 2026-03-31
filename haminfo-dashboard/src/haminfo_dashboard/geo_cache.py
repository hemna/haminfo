# haminfo_dashboard/geo_cache.py
"""Fast in-memory geo cache using reverse_geocoder.

Uses the reverse_geocoder library for microsecond-fast country lookups
instead of slow PostGIS ST_Contains queries. The library uses a k-d tree
with built-in city/country data.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
import logging

import reverse_geocoder as rg

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOG = logging.getLogger(__name__)

# ISO-3166 country code mapping for US states
US_STATE_CODES = {
    'Alabama': 'AL',
    'Alaska': 'AK',
    'Arizona': 'AZ',
    'Arkansas': 'AR',
    'California': 'CA',
    'Colorado': 'CO',
    'Connecticut': 'CT',
    'Delaware': 'DE',
    'Florida': 'FL',
    'Georgia': 'GA',
    'Hawaii': 'HI',
    'Idaho': 'ID',
    'Illinois': 'IL',
    'Indiana': 'IN',
    'Iowa': 'IA',
    'Kansas': 'KS',
    'Kentucky': 'KY',
    'Louisiana': 'LA',
    'Maine': 'ME',
    'Maryland': 'MD',
    'Massachusetts': 'MA',
    'Michigan': 'MI',
    'Minnesota': 'MN',
    'Mississippi': 'MS',
    'Missouri': 'MO',
    'Montana': 'MT',
    'Nebraska': 'NE',
    'Nevada': 'NV',
    'New Hampshire': 'NH',
    'New Jersey': 'NJ',
    'New Mexico': 'NM',
    'New York': 'NY',
    'North Carolina': 'NC',
    'North Dakota': 'ND',
    'Ohio': 'OH',
    'Oklahoma': 'OK',
    'Oregon': 'OR',
    'Pennsylvania': 'PA',
    'Rhode Island': 'RI',
    'South Carolina': 'SC',
    'South Dakota': 'SD',
    'Tennessee': 'TN',
    'Texas': 'TX',
    'Utah': 'UT',
    'Vermont': 'VT',
    'Virginia': 'VA',
    'Washington': 'WA',
    'West Virginia': 'WV',
    'Wisconsin': 'WI',
    'Wyoming': 'WY',
    'District of Columbia': 'DC',
}


@dataclass
class LocationInfo:
    """Geographic location information."""

    country_code: Optional[str]
    state_code: Optional[str] = None


class GeoCache:
    """Fast in-memory geographic lookup using reverse_geocoder.

    This replaces the slow PostGIS-based cache with a k-d tree lookup
    that runs in microseconds. No warm-up needed - the library loads
    its data on first use.
    """

    def __init__(self):
        self._initialized = False
        self._lookups = 0

    def _ensure_initialized(self):
        """Initialize reverse_geocoder on first use."""
        if not self._initialized:
            # First lookup triggers data load (~1 second)
            LOG.info('Initializing reverse geocoder (first lookup)...')
            self._initialized = True

    def lookup(self, lat: float, lon: float) -> LocationInfo:
        """Look up country and state for coordinates.

        Uses reverse_geocoder's k-d tree for fast lookup (~1 microsecond).

        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.

        Returns:
            LocationInfo with country_code and state_code (if US).
        """
        self._ensure_initialized()
        self._lookups += 1

        try:
            # reverse_geocoder returns list of results, get first
            results = rg.search((lat, lon), mode=1)  # mode=1 for single coord
            if not results:
                return LocationInfo(country_code=None, state_code=None)

            result = results[0]
            country_code = result.get('cc')
            state_code = None

            # For US, extract state from admin1 field
            if country_code == 'US':
                admin1 = result.get('admin1', '')
                state_code = US_STATE_CODES.get(admin1)

            return LocationInfo(country_code=country_code, state_code=state_code)

        except Exception as e:
            LOG.warning(f'Reverse geocode failed for ({lat}, {lon}): {e}')
            return LocationInfo(country_code=None, state_code=None)

    @property
    def stats(self) -> dict:
        """Get lookup statistics."""
        return {
            'lookups': self._lookups,
            'initialized': self._initialized,
            # For compatibility with old cache interface
            'hits': self._lookups,
            'misses': 0,
            'size': 0,
            'hit_rate': 1.0,
        }

    def clear(self) -> None:
        """Reset statistics (cache itself is in-memory, no clearing needed)."""
        self._lookups = 0


# Global cache instance
geo_cache = GeoCache()


def reverse_geocode(session: 'Session', lat: float, lon: float) -> LocationInfo:
    """Look up country and state for coordinates.

    This is kept for API compatibility but now uses the fast
    in-memory reverse_geocoder instead of PostGIS.

    Args:
        session: Database session (ignored, kept for compatibility).
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        LocationInfo with country_code and state_code.
    """
    return geo_cache.lookup(lat, lon)


def get_location_info(session: 'Session', lat: float, lon: float) -> LocationInfo:
    """Get location info for coordinates.

    Fast microsecond lookup using in-memory k-d tree.

    Args:
        session: Database session (ignored, kept for compatibility).
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        LocationInfo with country_code and state_code.
    """
    return geo_cache.lookup(lat, lon)


def warm_cache(session: 'Session', hours: int = 24) -> dict[str, int]:
    """Warm-up function for compatibility.

    With reverse_geocoder, no warm-up is needed - the k-d tree is
    loaded on first lookup. This function is kept for API compatibility.

    Args:
        session: Database session (ignored).
        hours: Ignored.

    Returns:
        Stats dict for compatibility.
    """
    # Trigger initialization by doing one lookup
    geo_cache.lookup(0, 0)

    return {
        'grid_cells_found': 0,
        'populated': 0,
        'errors': 0,
        'cache_size': 0,
    }
