import click
from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db, migrate


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_init(ctx):
    """Initialize the database schema"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    engine = db._setup_connection()
    db.init_db_schema(engine)


@cli.command()
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


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def schema_version(ctx):
    """Upgrade the database schema"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    #config = migrate._find_alembic_conf()
    #env.run_migrations_online(config)
    version = migrate.db_version()
    LOG.info(f"Database Schema version: {version}")


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
@click.version_option()
def clean_wx_reports(ctx):
    """Clean out old weather reports"""
    LOG.info("haminfo_load version: {}".format(haminfo.__version__))

    db_session = db.setup_session()
    session = db_session()
    db.clean_weather_reports(session)
