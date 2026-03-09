import click
import sys
import time
from oslo_config import cfg
from oslo_log import log as logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db as haminfo_db
from haminfo.db import migrate
from haminfo.db.models.weather_report import WeatherStation


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@cli.group(help='Database type subcommands', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def db(ctx):
    pass


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_init(ctx):
    """Initialize the database schema"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    engine = haminfo_db._setup_connection()
    haminfo_db.init_db_schema(engine)


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_upgrade(ctx):
    """Upgrade the database schema"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    #config = migrate._find_alembic_conf()
    #env.run_migrations_online(config)
    migrate.db_sync()


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_version(ctx):
    """Get the current database schema version and compare with latest available"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    current_version = migrate.db_version()
    latest_version = migrate.db_latest_version()

    if current_version:
        click.echo(f"Current Database Schema version: {current_version}")
        LOG.info(f"Current Database Schema version: {current_version}")
    else:
        click.echo("Current Database Schema version: None (no migrations applied)")
        LOG.info("Current Database Schema version: None (no migrations applied)")

    if latest_version:
        click.echo(f"Latest available migration version: {latest_version}")
        LOG.info(f"Latest available migration version: {latest_version}")

        # Compare versions
        if current_version == latest_version:
            click.echo("✓ Database is up to date (at latest version)")
            LOG.info("Database is up to date")
        elif current_version is None:
            click.echo("⚠ Database is not initialized (no migrations applied)")
            LOG.warning("Database is not initialized")
        else:
            click.echo("⚠ Database is behind (needs upgrade)")
            LOG.warning(f"Database version {current_version} is behind latest {latest_version}")
    else:
        click.echo("No migration files found in versions directory")
        LOG.warning("No migration files found")


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def clean_wx_reports(ctx):
    """Clean out old weather reports"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    db_session = haminfo_db.setup_session()
    session = db_session()
    haminfo_db.clean_weather_reports(session)


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.argument('message', required=True)
@click.option('--no-autogenerate', is_flag=True, default=False,
              help='Create an empty migration without autogenerate')
@click.version_option()
def schema_revision(ctx, message, no_autogenerate):
    """Create a new database schema migration revision

    Creates a new Alembic migration file by comparing the current database
    schema with the SQLAlchemy models. The MESSAGE argument provides a
    descriptive name for the migration.

    Example:
        haminfo db schema-revision "add aprs_packet table"
    """
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))
    LOG.info(f"Creating migration revision: {message}")

    autogenerate = not no_autogenerate
    migrate.db_revision(message, autogenerate=autogenerate)


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
                LOG.warning(f"Geocoding timeout/error, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                LOG.error(f"Failed after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            LOG.error(f"Unexpected error: {e}")
            return None

    return None


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.option('--batch-size', default=10, help='Number of stations to process before committing (default: 10)')
@click.option('--delay', default=1.1, help='Delay between geocoding requests in seconds (default: 1.1)')
@click.version_option()
def populate_country_codes(ctx, batch_size, delay):
    """Populate NULL country_code values in weather_station table using reverse geocoding.

    This command will:
    1. Find all weather stations with NULL country_code
    2. Use Nominatim reverse geocoding to determine country from coordinates
    3. Update the database in batches

    Note: Nominatim has rate limits (approximately 1 request/second), so this
    may take a while if you have many stations. The script includes automatic
    rate limiting and retry logic.

    Example:
        haminfo db populate-country-codes
    """
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    db_session = haminfo_db.setup_session()
    session = db_session()

    # Get all stations with NULL country_code
    stations = session.query(WeatherStation).filter(
        WeatherStation.country_code.is_(None)
    ).all()

    total = len(stations)
    LOG.info(f"Found {total} weather stations with NULL country_code")
    click.echo(f"Found {total} weather stations with NULL country_code")

    if total == 0:
        click.echo("No stations to update.")
        return

    # Initialize geocoder
    geolocator = Nominatim(user_agent="haminfo-country-code-updater")

    updated = 0
    failed = 0

    for idx, station in enumerate(stations, 1):
        click.echo(f"[{idx}/{total}] Processing {station.callsign} "
              f"({station.latitude}, {station.longitude})...", nl=False)

        country_code = get_country_code(
            station.latitude,
            station.longitude,
            geolocator
        )

        if country_code:
            station.country_code = country_code
            session.add(station)
            updated += 1
            click.echo(f" ✓ Set to {country_code}")
            LOG.info(f"Updated {station.callsign} to {country_code}")
        else:
            failed += 1
            click.echo(" ✗ Failed to get country code")
            LOG.warning(f"Failed to get country code for {station.callsign}")

        # Commit every batch_size stations to avoid losing progress
        if idx % batch_size == 0:
            try:
                session.commit()
                click.echo(f"  Committed batch ({idx}/{total})")
                LOG.info(f"Committed batch ({idx}/{total})")
            except Exception as e:
                session.rollback()
                click.echo(f"  Error committing batch: {e}")
                LOG.error(f"Error committing batch: {e}")

        # Rate limiting - Nominatim allows 1 request per second
        time.sleep(delay)

    # Final commit
    try:
        session.commit()
        click.echo(f"\nCompleted: {updated} updated, {failed} failed")
        LOG.info(f"Completed: {updated} updated, {failed} failed")
    except Exception as e:
        session.rollback()
        click.echo(f"\nError in final commit: {e}")
        LOG.error(f"Error in final commit: {e}")
        sys.exit(1)
