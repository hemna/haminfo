#!/usr/bin/env bash
set -x

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    if [ ! -z "${INIT_DB}" ]; then
        echo "Initializing Database"
        /usr/local/bin/haminfo_load  --config-file $APP_CONFIG --log-level DEBUG -i --force
    fi
    haminfo_api --help
    /usr/local/bin/haminfo_api --config-file $APP_CONFIG --log-level DEBUG
fi
