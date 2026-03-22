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
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))

    engine = haminfo_db._setup_connection()
    haminfo_db.init_db_schema(engine)


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_upgrade(ctx):
    """Upgrade the database schema"""
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))

    # config = migrate._find_alembic_conf()
    # env.run_migrations_online(config)
    migrate.db_sync()


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_version(ctx):
    """Get the current database schema version and compare with latest available"""
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))

    current_version = migrate.db_version()
    latest_version = migrate.db_latest_version()

    if current_version:
        click.echo(f'Current Database Schema version: {current_version}')
        LOG.info(f'Current Database Schema version: {current_version}')
    else:
        click.echo('Current Database Schema version: None (no migrations applied)')
        LOG.info('Current Database Schema version: None (no migrations applied)')

    if latest_version:
        click.echo(f'Latest available migration version: {latest_version}')
        LOG.info(f'Latest available migration version: {latest_version}')

        # Compare versions
        if current_version == latest_version:
            click.echo('✓ Database is up to date (at latest version)')
            LOG.info('Database is up to date')
        elif current_version is None:
            click.echo('⚠ Database is not initialized (no migrations applied)')
            LOG.warning('Database is not initialized')
        else:
            click.echo('⚠ Database is behind (needs upgrade)')
            LOG.warning(
                f'Database version {current_version} is behind latest {latest_version}'
            )
    else:
        click.echo('No migration files found in versions directory')
        LOG.warning('No migration files found')


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def clean_wx_reports(ctx):
    """Clean out old weather reports"""
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))

    db_session = haminfo_db.setup_session()
    session = db_session()
    haminfo_db.clean_weather_reports(session)


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.option(
    '--days',
    default=30,
    type=int,
    help='Number of days of data to retain (default: 30)',
)
@click.version_option()
def clean_aprs_packets(ctx: click.Context, days: int) -> None:
    """Clean out old APRS packets.

    Deletes APRS packets with received_at older than the specified
    number of days (default 30).

    Args:
        ctx: Click context (injected by @click.pass_context).
        days: Number of days of data to retain.

    Example:
        haminfo db clean-aprs-packets --days 7
    """
    LOG.info('haminfo version: {}'.format(haminfo.__version__))

    db_session = haminfo_db.setup_session()
    session = db_session()
    count = haminfo_db.clean_aprs_packets(session, days)
    click.echo(f'Deleted {count} APRS packets older than {days} days')


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.argument('message', required=True)
@click.option(
    '--no-autogenerate',
    is_flag=True,
    default=False,
    help='Create an empty migration without autogenerate',
)
@click.version_option()
def schema_revision(ctx, message, no_autogenerate):
    """Create a new database schema migration revision

    Creates a new Alembic migration file by comparing the current database
    schema with the SQLAlchemy models. The MESSAGE argument provides a
    descriptive name for the migration.

    Example:
        haminfo db schema-revision "add aprs_packet table"
    """
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))
    LOG.info(f'Creating migration revision: {message}')

    autogenerate = not no_autogenerate
    migrate.db_revision(message, autogenerate=autogenerate)


def get_country_code(latitude, longitude, geolocator, max_retries=3):
    """Get country code from coordinates using reverse geocoding."""
    for attempt in range(max_retries):
        try:
            location = geolocator.reverse(
                (latitude, longitude), language='en', addressdetails=True
            )
            if location and hasattr(location, 'raw'):
                address = location.raw.get('address')
                if address and 'country_code' in address:
                    return address['country_code'].upper()
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                LOG.warning(f'Geocoding timeout/error, retrying in {wait_time}s...')
                time.sleep(wait_time)
            else:
                LOG.error(f'Failed after {max_retries} attempts: {e}')
                return None
        except Exception as e:
            LOG.error(f'Unexpected error: {e}')
            return None

    return None


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.option(
    '--batch-size',
    default=10,
    help='Number of stations to process before committing (default: 10)',
)
@click.option(
    '--delay',
    default=1.1,
    help='Delay between geocoding requests in seconds (default: 1.1)',
)
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
    LOG.info('haminfo_load version: {}'.format(haminfo.__version__))

    db_session = haminfo_db.setup_session()
    session = db_session()

    # Get all stations with NULL country_code
    stations = (
        session.query(WeatherStation)
        .filter(WeatherStation.country_code.is_(None))
        .all()
    )

    total = len(stations)
    LOG.info(f'Found {total} weather stations with NULL country_code')
    click.echo(f'Found {total} weather stations with NULL country_code')

    if total == 0:
        click.echo('No stations to update.')
        return

    # Initialize geocoder
    geolocator = Nominatim(user_agent='haminfo-country-code-updater')

    updated = 0
    failed = 0

    for idx, station in enumerate(stations, 1):
        click.echo(
            f'[{idx}/{total}] Processing {station.callsign} '
            f'({station.latitude}, {station.longitude})...',
            nl=False,
        )

        country_code = get_country_code(station.latitude, station.longitude, geolocator)

        if country_code:
            station.country_code = country_code
            session.add(station)
            updated += 1
            click.echo(f' ✓ Set to {country_code}')
            LOG.info(f'Updated {station.callsign} to {country_code}')
        else:
            failed += 1
            click.echo(' ✗ Failed to get country code')
            LOG.warning(f'Failed to get country code for {station.callsign}')

        # Commit every batch_size stations to avoid losing progress
        if idx % batch_size == 0:
            try:
                session.commit()
                click.echo(f'  Committed batch ({idx}/{total})')
                LOG.info(f'Committed batch ({idx}/{total})')
            except Exception as e:
                session.rollback()
                click.echo(f'  Error committing batch: {e}')
                LOG.error(f'Error committing batch: {e}')

        # Rate limiting - Nominatim allows 1 request per second
        time.sleep(delay)

    # Final commit
    try:
        session.commit()
        click.echo(f'\nCompleted: {updated} updated, {failed} failed')
        LOG.info(f'Completed: {updated} updated, {failed} failed')
    except Exception as e:
        session.rollback()
        click.echo(f'\nError in final commit: {e}')
        LOG.error(f'Error in final commit: {e}')
        sys.exit(1)


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.argument('source_db_url', required=False)
@click.option(
    '--source-config',
    type=click.Path(exists=True),
    help='Path to config file with source DB connection',
)
@click.option(
    '--dry-run',
    is_flag=True,
    default=False,
    help='Show what would be done without executing',
)
@click.option(
    '--tables',
    help='Comma-separated tables to clone (default: all)',
)
@click.option(
    '--exclude-tables',
    help='Comma-separated tables to exclude',
)
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Skip confirmation prompt',
)
@click.pass_context
@cli_helper.process_standard_options
def clone_from(
    ctx, source_db_url, source_config, dry_run, tables, exclude_tables, force
):
    """Clone all data from a source database (e.g., production).

    This command replaces ALL data in the local database with data from
    the source. Use with caution.

    SOURCE_DB_URL is the PostgreSQL connection URL for the source database.
    Alternatively, use --source-config to specify a config file.

    Examples:

        # Clone from production via direct URL
        haminfo db clone-from "postgresql://user:pass@prod-host/haminfo"

        # Clone using a config file for source credentials
        haminfo db clone-from --source-config /path/to/prod.conf

        # Clone only station and weather_station tables
        haminfo db clone-from "postgresql://..." --tables station,weather_station

        # Clone all except request logs
        haminfo db clone-from "postgresql://..." --exclude-tables request,wx_request

        # Dry run to see what would happen
        haminfo db clone-from "postgresql://..." --dry-run
    """
    from haminfo.db import clone as db_clone

    # Validate we have a source URL
    if not source_db_url and not source_config:
        raise click.UsageError(
            'Either SOURCE_DB_URL argument or --source-config option is required'
        )

    # Get source URL from config if provided
    if source_config:
        from oslo_config import cfg as oslo_cfg

        source_conf = oslo_cfg.ConfigOpts()
        source_conf(['--config-file', source_config])
        source_db_url = source_conf.database.connection

    # Parse table filters
    include_tables = tables.split(',') if tables else None
    exclude_tables_list = exclude_tables.split(',') if exclude_tables else None

    try:
        table_list = db_clone.get_table_list(include_tables, exclude_tables_list)
    except ValueError as e:
        raise click.UsageError(str(e)) from e

    # Get local DB URL from config
    local_db_url = CONF.database.connection

    click.echo('Connecting to source database...', nl=False)
    if not db_clone.test_db_connection(source_db_url):
        click.echo(' FAILED')
        raise click.ClickException('Cannot connect to source database')
    click.echo(' OK')

    click.echo('Connecting to local database...', nl=False)
    if not db_clone.test_db_connection(local_db_url):
        click.echo(' FAILED')
        raise click.ClickException('Cannot connect to local database')
    click.echo(' OK')

    click.echo('')
    click.echo('WARNING: This will REPLACE all data in the local database.')
    click.echo(f'Tables to clone: {", ".join(table_list)}')
    click.echo('')

    if dry_run:
        click.echo('DRY RUN - no changes will be made')
        source_info = db_clone.parse_db_url(source_db_url)
        click.echo(
            f'Would connect to source: {source_info["host"]}:{source_info["port"]}/{source_info["database"]}'
        )
        click.echo(f'Would clone tables: {", ".join(table_list)}')
        click.echo('Would truncate local tables and restore from source')
        return

    if not force:
        if not click.confirm('Continue?'):
            click.echo('Aborted.')
            return

    click.echo('Cloning data...')
    try:
        row_counts = db_clone.clone_database(
            source_url=source_db_url,
            target_url=local_db_url,
            tables=table_list,
        )
        click.echo('')
        for table, count in row_counts.items():
            click.echo(f'  {table}: {count:,} rows')
        click.echo('')
        click.echo('Clone completed successfully.')
    except Exception as e:
        LOG.exception('Clone failed')
        raise click.ClickException(f'Clone failed: {e}') from e
