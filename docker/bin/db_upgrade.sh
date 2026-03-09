#!/usr/bin/env bash
# Run database schema upgrade via alembic

set -x

COLUMNS=${COLUMNS:-160}
export COLUMNS

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    uv run oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    # Dynamically find the installed package path instead of hardcoding python version
    SRC_DIR=$(python -c "import haminfo.db; import os; print(os.path.dirname(haminfo.db.__file__))")
    cd "$SRC_DIR"
    uv run haminfo db schema-upgrade -c $APP_CONFIG
fi
