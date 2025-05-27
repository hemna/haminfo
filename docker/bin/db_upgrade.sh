#!/usr/bin/env bash
# The main entry point of the API service

set -x

COLUMNS=${COLUMNS:-160}
export COLUMNS

# TODO(walt): setup a cron to run haminfo_load
# once a day.
INIT_DB=${INIT_DB:-False}

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
SRC_DIR="/app/.venv/lib/python3.11/site-packages/haminfo/db"
DB_CONFIG="/config/alembic.ini"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    uv run oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    cd $SRC_DIR
    uv run alembic --config $DB_CONFIG upgrade head
fi
