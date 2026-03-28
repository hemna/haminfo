#!/usr/bin/env python3
"""Script to populate NULL country_code values in weather_station table."""
import sys
import time
from oslo_config import cfg
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

import haminfo
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation
from haminfo.log import log

CONF = cfg.CONF


def get_country_code(latitude, longitude, geolocator, max_retries=3):
    """Get country code from coordinates using reverse geocoding."""
    for attempt in range(max_retries):
        try:
            location = geolocator.reverse(
                (latitude, longitude),
                language="en",
                addressdetails=True
            )
            if location and hasattr(location, "raw"):
                address = location.raw.get("address")
                if address and "country_code" in address:
                    return address["country_code"].upper()
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                print(f"  Geocoding timeout/error, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"  Failed after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            print(f"  Unexpected error: {e}")
            return None

    return None


def main():
    """Main function to populate country codes."""
    # Initialize config - try to load from default config file
    import os
    from pathlib import Path
    default_config = str(Path.home() / ".config" / "haminfo" / "haminfo.conf")
    config_files = [default_config] if os.path.exists(default_config) else None

    try:
        CONF(config_files or [], project="haminfo", version=haminfo.__version__)
    except Exception:
        # If config file doesn't exist, try without it
        CONF([], project="haminfo", version=haminfo.__version__)

    log.setup_logging()

    # Setup database session
    db_session = db.setup_session()
    session = db_session()

    # Get all stations with NULL country_code
    stations = session.query(WeatherStation).filter(
        WeatherStation.country_code.is_(None)
    ).all()

    total = len(stations)
    print(f"Found {total} weather stations with NULL country_code")

    if total == 0:
        print("No stations to update.")
        return

    # Initialize geocoder
    geolocator = Nominatim(user_agent="haminfo-country-code-updater")

    updated = 0
    failed = 0

    for idx, station in enumerate(stations, 1):
        print(f"[{idx}/{total}] Processing {station.callsign} "
              f"({station.latitude}, {station.longitude})...", end=" ")

        country_code = get_country_code(
            station.latitude,
            station.longitude,
            geolocator
        )

        if country_code:
            station.country_code = country_code
            session.add(station)
            updated += 1
            print(f"✓ Set to {country_code}")
        else:
            failed += 1
            print("✗ Failed to get country code")

        # Commit every 10 stations to avoid losing progress
        if idx % 10 == 0:
            try:
                session.commit()
                print(f"  Committed batch ({idx}/{total})")
            except Exception as e:
                session.rollback()
                print(f"  Error committing batch: {e}")

        # Rate limiting - Nominatim allows 1 request per second
        time.sleep(1.1)

    # Final commit
    try:
        session.commit()
        print(f"\nCompleted: {updated} updated, {failed} failed")
    except Exception as e:
        session.rollback()
        print(f"\nError in final commit: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

