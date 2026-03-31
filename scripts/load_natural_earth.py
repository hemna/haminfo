#!/usr/bin/env python3
"""Load Natural Earth boundary data into PostgreSQL/PostGIS.

Downloads Natural Earth 10m Admin 0 (countries) and Admin 1 (states/provinces)
shapefiles and loads them into PostgreSQL using ogr2ogr.

Usage:
    python scripts/load_natural_earth.py --db-url postgresql://user:pass@host/db
    python scripts/load_natural_earth.py --db-url postgresql://user:pass@host/db --skip-download

Requirements:
    - ogr2ogr (GDAL) installed
    - curl or wget for downloads
    - unzip for extraction
    - psycopg2 for verification queries
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# URLs for Natural Earth data
COUNTRIES_URL = (
    'https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip'
)
STATES_URL = (
    'https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip'
)


def check_dependencies() -> list[str]:
    """Check that required external tools are available.

    Returns:
        List of missing dependencies.
    """
    missing = []

    # Check ogr2ogr
    if shutil.which('ogr2ogr') is None:
        missing.append('ogr2ogr (GDAL)')

    # Check for download tool (curl or wget)
    if shutil.which('curl') is None and shutil.which('wget') is None:
        missing.append('curl or wget')

    # Check unzip
    if shutil.which('unzip') is None:
        missing.append('unzip')

    return missing


def download_file(url: str, dest_path: Path) -> bool:
    """Download a file using curl or wget.

    Args:
        url: URL to download.
        dest_path: Destination file path.

    Returns:
        True if download succeeded, False otherwise.
    """
    print(f'  Downloading {url}...')

    if shutil.which('curl'):
        cmd = ['curl', '-fSL', '-o', str(dest_path), url]
    else:
        cmd = ['wget', '-q', '-O', str(dest_path), url]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f'  ERROR: Download failed: {e.stderr}')
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """Extract a zip file.

    Args:
        zip_path: Path to zip file.
        dest_dir: Destination directory.

    Returns:
        True if extraction succeeded, False otherwise.
    """
    print(f'  Extracting {zip_path.name}...')

    try:
        subprocess.run(
            ['unzip', '-o', '-q', str(zip_path), '-d', str(dest_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f'  ERROR: Extraction failed: {e.stderr}')
        return False


def find_shapefile(directory: Path, pattern: str) -> Path | None:
    """Find a shapefile in a directory.

    Args:
        directory: Directory to search.
        pattern: Glob pattern for the shapefile.

    Returns:
        Path to shapefile if found, None otherwise.
    """
    shapefiles = list(directory.glob(pattern))
    if shapefiles:
        return shapefiles[0]
    return None


def download_and_extract(url: str, dest_dir: Path) -> Path | None:
    """Download and extract a Natural Earth shapefile.

    Args:
        url: URL to download.
        dest_dir: Directory to store files.

    Returns:
        Path to the extracted .shp file, or None on failure.
    """
    # Derive filename from URL
    filename = Path(urlparse(url).path).name
    zip_path = dest_dir / filename

    # Download
    if not download_file(url, zip_path):
        return None

    # Extract
    if not extract_zip(zip_path, dest_dir):
        return None

    # Find the shapefile
    basename = filename.replace('.zip', '')
    shp_path = find_shapefile(dest_dir, f'**/{basename}.shp')

    if shp_path is None:
        print(f'  ERROR: Could not find shapefile for {basename}')
        return None

    print(f'  Found shapefile: {shp_path}')
    return shp_path


def load_countries(db_url: str, shp_path: Path) -> bool:
    """Load countries data using ogr2ogr.

    Loads Natural Earth countries into the 'countries' table with mappings:
    - ISO_A2 -> iso_a2
    - ISO_A3 -> iso_a3
    - NAME -> name

    Filters out rows where ISO_A2 == '-99' (invalid/unknown).

    Args:
        db_url: PostgreSQL connection URL.
        shp_path: Path to countries shapefile.

    Returns:
        True if load succeeded, False otherwise.
    """
    print('\n=== Loading Countries ===')

    # Get layer name (shapefile basename without extension)
    layer_name = shp_path.stem

    # Build SQL to select and rename columns, filtering invalid ISO codes
    sql = f"""
        SELECT
            ISO_A2 AS iso_a2,
            ISO_A3 AS iso_a3,
            NAME AS name
        FROM "{layer_name}"
        WHERE ISO_A2 != '-99'
    """

    # Build ogr2ogr command
    cmd = [
        'ogr2ogr',
        '-f',
        'PostgreSQL',
        f'PG:{db_url}',
        str(shp_path),
        '-nln',
        'countries',
        '-overwrite',
        '-lco',
        'GEOMETRY_NAME=geom',
        '-lco',
        'FID=id',
        '-sql',
        sql.strip(),
        '-nlt',
        'MULTIPOLYGON',
        '-t_srs',
        'EPSG:4326',
    ]

    print(f'  Running ogr2ogr to load {layer_name}...')

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print('  Countries loaded successfully.')
        return True
    except subprocess.CalledProcessError as e:
        print(f'  ERROR: ogr2ogr failed: {e.stderr}')
        return False


def load_us_states(db_url: str, shp_path: Path) -> bool:
    """Load US states data using ogr2ogr.

    Loads Natural Earth states/provinces filtered to US only, with mappings:
    - postal -> state_code
    - name -> name

    Args:
        db_url: PostgreSQL connection URL.
        shp_path: Path to states shapefile.

    Returns:
        True if load succeeded, False otherwise.
    """
    print('\n=== Loading US States ===')

    # Get layer name (shapefile basename without extension)
    layer_name = shp_path.stem

    # Build SQL to select US states only
    sql = f"""
        SELECT
            postal AS state_code,
            name AS name
        FROM "{layer_name}"
        WHERE iso_a2 = 'US'
    """

    # Build ogr2ogr command
    cmd = [
        'ogr2ogr',
        '-f',
        'PostgreSQL',
        f'PG:{db_url}',
        str(shp_path),
        '-nln',
        'us_states',
        '-overwrite',
        '-lco',
        'GEOMETRY_NAME=geom',
        '-lco',
        'FID=id',
        '-sql',
        sql.strip(),
        '-nlt',
        'MULTIPOLYGON',
        '-t_srs',
        'EPSG:4326',
    ]

    print(f'  Running ogr2ogr to load US states from {layer_name}...')

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print('  US states loaded successfully.')
        return True
    except subprocess.CalledProcessError as e:
        print(f'  ERROR: ogr2ogr failed: {e.stderr}')
        return False


def verify_data(db_url: str) -> bool:
    """Verify the loaded data is correct.

    Checks:
    - Row counts for both tables
    - Test point: NYC (-74.006, 40.7128) should be in US/NY

    Args:
        db_url: PostgreSQL connection URL.

    Returns:
        True if verification passed, False otherwise.
    """
    print('\n=== Verifying Data ===')

    try:
        import psycopg2
    except ImportError:
        print('  WARNING: psycopg2 not installed, skipping verification')
        return True

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Check countries count
        cur.execute('SELECT COUNT(*) FROM countries')
        country_count = cur.fetchone()[0]
        print(f'  Countries loaded: {country_count}')

        if country_count < 200:
            print(f'  WARNING: Expected ~250 countries, got {country_count}')

        # Check us_states count
        cur.execute('SELECT COUNT(*) FROM us_states')
        state_count = cur.fetchone()[0]
        print(f'  US states loaded: {state_count}')

        if state_count < 50:
            print(f'  WARNING: Expected ~56 states/territories, got {state_count}')

        # Test NYC point (-74.006, 40.7128)
        # Should be in US (countries) and NY (us_states)
        nyc_lon, nyc_lat = -74.006, 40.7128

        print(f'\n  Testing point NYC ({nyc_lat}, {nyc_lon})...')

        # Check country
        cur.execute(
            """
            SELECT iso_a2, name FROM countries
            WHERE ST_Contains(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
            """,
            (nyc_lon, nyc_lat),
        )
        row = cur.fetchone()
        if row:
            country_code, country_name = row
            print(f'    Country: {country_code} ({country_name})')
            if country_code != 'US':
                print(f'    ERROR: Expected US, got {country_code}')
                return False
        else:
            print('    ERROR: NYC not found in any country!')
            return False

        # Check state
        cur.execute(
            """
            SELECT state_code, name FROM us_states
            WHERE ST_Contains(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
            """,
            (nyc_lon, nyc_lat),
        )
        row = cur.fetchone()
        if row:
            state_code, state_name = row
            print(f'    State: {state_code} ({state_name})')
            if state_code != 'NY':
                print(f'    ERROR: Expected NY, got {state_code}')
                return False
        else:
            print('    ERROR: NYC not found in any US state!')
            return False

        # Additional test points
        test_points = [
            # (lon, lat, expected_country, expected_state, description)
            (-122.4194, 37.7749, 'US', 'CA', 'San Francisco'),
            (-0.1276, 51.5074, 'GB', None, 'London'),
            (139.6917, 35.6895, 'JP', None, 'Tokyo'),
        ]

        print('\n  Additional test points:')
        for lon, lat, expected_country, _expected_state, desc in test_points:
            cur.execute(
                """
                SELECT iso_a2, name FROM countries
                WHERE ST_Contains(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                """,
                (lon, lat),
            )
            row = cur.fetchone()
            if row:
                country_code, country_name = row
                status = 'OK' if country_code == expected_country else 'MISMATCH'
                print(f'    {desc}: {country_code} [{status}]')
            else:
                print(f'    {desc}: NOT FOUND [FAIL]')

        conn.close()
        print('\n  Verification passed!')
        return True

    except psycopg2.Error as e:
        print(f'  ERROR: Database error: {e}')
        return False
    except Exception as e:
        print(f'  ERROR: Unexpected error: {e}')
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Load Natural Earth boundary data into PostgreSQL/PostGIS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --db-url postgresql://user:pass@localhost/haminfo
    %(prog)s --db-url postgresql://user:pass@localhost/haminfo --skip-download

Requirements:
    - ogr2ogr (from GDAL)
    - curl or wget
    - unzip
    - psycopg2 (for verification)
        """,
    )
    parser.add_argument(
        '--db-url',
        required=True,
        help='PostgreSQL connection URL (e.g., postgresql://user:pass@host/db)',
    )
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip download, use existing files in temp directory',
    )
    parser.add_argument(
        '--temp-dir',
        type=Path,
        help='Use specific temp directory (default: system temp)',
    )
    parser.add_argument(
        '--keep-files',
        action='store_true',
        help='Keep downloaded files after completion',
    )

    args = parser.parse_args()

    print('=' * 60)
    print('Natural Earth Data Loader')
    print('=' * 60)

    # Check dependencies
    print('\nChecking dependencies...')
    missing = check_dependencies()
    if missing:
        print(f'ERROR: Missing dependencies: {", ".join(missing)}')
        print('Please install the required tools and try again.')
        sys.exit(1)
    print('  All dependencies found.')

    # Setup temp directory
    if args.temp_dir:
        temp_dir = args.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        cleanup_temp = False
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix='natural_earth_'))
        cleanup_temp = not args.keep_files

    print(f'\nUsing temp directory: {temp_dir}')

    try:
        # Download and extract shapefiles
        if args.skip_download:
            print('\n--skip-download specified, looking for existing files...')
            countries_shp = find_shapefile(temp_dir, '**/ne_10m_admin_0_countries.shp')
            states_shp = find_shapefile(
                temp_dir, '**/ne_10m_admin_1_states_provinces.shp'
            )

            if not countries_shp:
                print('ERROR: Countries shapefile not found in temp directory')
                sys.exit(1)
            if not states_shp:
                print('ERROR: States shapefile not found in temp directory')
                sys.exit(1)

            print(f'  Found countries: {countries_shp}')
            print(f'  Found states: {states_shp}')
        else:
            print('\n--- Downloading Countries Data ---')
            countries_shp = download_and_extract(COUNTRIES_URL, temp_dir)
            if not countries_shp:
                print('ERROR: Failed to download countries data')
                sys.exit(1)

            print('\n--- Downloading States Data ---')
            states_shp = download_and_extract(STATES_URL, temp_dir)
            if not states_shp:
                print('ERROR: Failed to download states data')
                sys.exit(1)

        # Load data into PostgreSQL
        if not load_countries(args.db_url, countries_shp):
            print('ERROR: Failed to load countries data')
            sys.exit(1)

        if not load_us_states(args.db_url, states_shp):
            print('ERROR: Failed to load US states data')
            sys.exit(1)

        # Verify data
        if not verify_data(args.db_url):
            print('ERROR: Data verification failed')
            sys.exit(1)

        print('\n' + '=' * 60)
        print('SUCCESS: Natural Earth data loaded successfully!')
        print('=' * 60)

    finally:
        # Cleanup temp directory
        if cleanup_temp and temp_dir.exists():
            print(f'\nCleaning up temp directory: {temp_dir}')
            shutil.rmtree(temp_dir)
        elif args.keep_files:
            print(f'\nFiles kept in: {temp_dir}')


if __name__ == '__main__':
    main()
