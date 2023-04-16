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
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    $HOME/.local/bin/oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    case "$INIT_DB" in
        True|true|yes)
            echo "Initializing Database"
            time haminfo_load -i --force
            $HOME/.local/bin/haminfo_api
            ;;
        *)
            $HOME/.local/bin/haminfo_api --loglevel DEBUG
            ;;
    esac
fi
