#!/usr/bin/env python
"""Backfill state column for weather stations using bounding box detection.

Uses the existing US_STATE_BOUNDS, CA_PROVINCE_BOUNDS, AU_STATE_BOUNDS from
haminfo_dashboard.utils to determine state from lat/lon coordinates.

Usage:
    python scripts/backfill_station_states.py [--dry-run] [--limit N] [--verbose]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from haminfo.db.db import setup_session
from haminfo.db.models.weather_report import WeatherStation


# Import bounding boxes from dashboard utils
sys.path.insert(0, str(Path(__file__).parent.parent / 'haminfo-dashboard' / 'src'))
from haminfo_dashboard.utils import (
    US_STATE_BOUNDS,
    get_state_from_coords,
)

# Verify imports worked
if not US_STATE_BOUNDS:
    print('ERROR: US_STATE_BOUNDS not found in utils.py')
    sys.exit(1)


def get_state_for_station(
    lat: float, lon: float, country_code: str | None
) -> str | None:
    """Determine state/province from coordinates.

    Args:
        lat: Latitude
        lon: Longitude
        country_code: Country code (US, CA, AU) or None

    Returns:
        State/province code or None
    """
    if country_code not in ('US', 'CA', 'AU'):
        return None

    result = get_state_from_coords(lat, lon, country_code)
    if result:
        return result[0]  # Return just the code, not (code, name) tuple
    return None


def backfill_states(
    dry_run: bool = False, limit: int | None = None, verbose: bool = False
) -> dict:
    """Backfill state column for weather stations.

    Args:
        dry_run: If True, don't commit changes
        limit: Maximum number of stations to process
        verbose: If True, print each station update

    Returns:
        Dict with statistics
    """
    session_factory = setup_session()
    session = session_factory()

    stats = {
        'total': 0,
        'updated': 0,
        'skipped_no_country': 0,
        'skipped_unsupported_country': 0,
        'skipped_no_match': 0,
        'by_country': {},
    }

    try:
        # Query stations where state is NULL
        query = session.query(WeatherStation).filter(
            WeatherStation.state.is_(None),
            WeatherStation.latitude.isnot(None),
            WeatherStation.longitude.isnot(None),
        )

        if limit:
            query = query.limit(limit)

        stations = query.all()
        stats['total'] = len(stations)

        print(f'Processing {stats["total"]} stations...')

        for i, station in enumerate(stations):
            if i > 0 and i % 100 == 0:
                print(f'  Processed {i}/{stats["total"]}...')
                if not dry_run:
                    session.commit()

            country = station.country_code
            if not country:
                stats['skipped_no_country'] += 1
                continue

            country = country.upper()
            if country not in ('US', 'CA', 'AU'):
                stats['skipped_unsupported_country'] += 1
                continue

            state = get_state_for_station(station.latitude, station.longitude, country)

            if state:
                if not dry_run:
                    station.state = state
                stats['updated'] += 1
                stats['by_country'][country] = stats['by_country'].get(country, 0) + 1
                if verbose:
                    print(f'  {station.callsign}: {country} -> {state}')
            else:
                stats['skipped_no_match'] += 1

        if not dry_run:
            session.commit()
            print('\nChanges committed.')
        else:
            print('\nDRY RUN - no changes made.')

        return stats

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill weather station states')
    parser.add_argument(
        '--dry-run', action='store_true', help='Preview without making changes'
    )
    parser.add_argument('--limit', type=int, help='Limit number of stations to process')
    parser.add_argument(
        '--verbose', '-v', action='store_true', help='Print each station update'
    )
    args = parser.parse_args()

    print('=' * 60)
    print('Weather Station State Backfill')
    print('=' * 60)

    stats = backfill_states(
        dry_run=args.dry_run, limit=args.limit, verbose=args.verbose
    )

    print('\n' + '=' * 60)
    print('Summary:')
    print(f'  Total processed: {stats["total"]}')
    print(f'  Updated: {stats["updated"]}')
    print(f'  Skipped (no country): {stats["skipped_no_country"]}')
    print(f'  Skipped (unsupported country): {stats["skipped_unsupported_country"]}')
    print(f'  Skipped (no state match): {stats["skipped_no_match"]}')
    print('\nBy country:')
    for country, count in sorted(stats['by_country'].items()):
        print(f'  {country}: {count}')


if __name__ == '__main__':
    main()
