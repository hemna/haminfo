# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Database setup and migration commands."""

import os

from alembic import command as alembic_api
from alembic import config as alembic_config
from alembic import migration as alembic_migration
from alembic.script import ScriptDirectory
from oslo_config import cfg
#from oslo_db import options
from oslo_log import log as logging

#from cinder.db.sqlalchemy import api as db_api
from haminfo.db import db

#options.set_defaults(cfg.CONF)

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

def _find_alembic_conf():
    """Get the project's alembic configuration

    :returns: An instance of ``alembic.config.Config``
    """
    path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), 'alembic.ini')

    config = alembic_config.Config(os.path.abspath(path))
    # we don't want to use the logger configuration from the file, which is
    # only really intended for the CLI
    # https://stackoverflow.com/a/42691781/613428
    config.attributes['configure_logger'] = False

    return config


def get_url():
    url = CONF.database.connection
    assert url, "Couldn't find DB url!!"
    print(f"Using DB URL {url}")
    return url


def _upgrade_alembic(engine, config, version):
    # re-use the connection rather than creating a new one
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        alembic_api.upgrade(config, version or 'head')


def db_version():
    """Get database version."""
    engine = db.get_engine()

    with engine.connect() as conn:
        m_context = alembic_migration.MigrationContext.configure(conn)
        return m_context.get_current_revision()


def db_latest_version():
    """Get the latest available migration version from the versions directory."""
    config = _find_alembic_conf()
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if heads:
        # If there are multiple heads, return the first one (or join them)
        # In most cases there should be only one head
        return heads[0] if len(heads) == 1 else ', '.join(heads)
    return None


def db_sync(version=None, engine=None):
    """Migrate the database to `version` or the most recent version.

    We're currently straddling two migration systems, sqlalchemy-migrate and
    alembic. This handles both by ensuring we switch from one to the other at
    the appropriate moment.
    """

    # if the user requested a specific version, check if it's an integer: if
    # so, we're almost certainly in sqlalchemy-migrate land and won't support
    # that
    if version is not None and version.isdigit():
        raise ValueError(
            'You requested an sqlalchemy-migrate database version; this is '
            'no longer supported'
        )

    if engine is None:
        engine = db.get_engine()

    config = _find_alembic_conf()

    # discard the URL encoded in alembic.ini in favour of the URL configured
    # for the engine by the database fixtures, casting from
    # 'sqlalchemy.engine.url.URL' to str in the process. This returns a
    # RFC-1738 quoted URL, which means that a password like "foo@" will be
    # turned into "foo%40". This in turns causes a problem for
    # set_main_option() because that uses ConfigParser.set, which (by design)
    # uses *python* interpolation to write the string out ... where "%" is the
    # special python interpolation character! Avoid this mismatch by quoting
    # all %'s for the set below.
    #engine_url = str(engine.url).replace('%', '%%')
    #config.set_main_option('sqlalchemy.url', str(engine_url))
    engine_url = get_url().replace('%', '%%')
    LOG.info(f"Setting DB URL {engine_url}")
    config.set_main_option('sqlalchemy.url', engine_url)
    LOG.info(f"Using DB URL from config '{config.get_main_option('sqlalchemy.url')}'")
    LOG.info(f"DB version {db_version()}")

    LOG.info('Applying migration(s)')
    _upgrade_alembic(engine, config, version)
    LOG.info('Migration(s) applied')


def db_revision(message, autogenerate=True, engine=None):
    """Create a new Alembic migration revision.

    This function creates a new migration file by comparing the current
    database schema with the SQLAlchemy models defined in the codebase.

    :param message: A descriptive message for the migration
    :param autogenerate: If True, automatically detect model changes (default: True)
    :param engine: Optional database engine (will be created if not provided)
    """
    if engine is None:
        engine = db.get_engine()

    config = _find_alembic_conf()

    # Set the database URL in the config
    engine_url = get_url().replace('%', '%%')
    LOG.info(f"Setting DB URL {engine_url}")
    config.set_main_option('sqlalchemy.url', engine_url)

    # Import models to ensure they're registered with ModelBase.metadata
    # This is necessary for autogenerate to detect them
    import haminfo.db.models.__all_models  # noqa

    LOG.info(f"Creating new migration revision: {message}")
    LOG.info(f"Autogenerate: {autogenerate}")

    # Use the engine's connection for autogenerate comparison
    with engine.connect() as connection:
        config.attributes['connection'] = connection
        alembic_api.revision(
            config,
            message=message,
            autogenerate=autogenerate,
        )

    LOG.info('Migration revision created successfully')
