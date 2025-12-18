import click
from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db as haminfo_db
from haminfo.db import migrate


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
