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
        which haminfo_load
        haminfo_load --help
        haminfo_load  --config-file $APP_CONFIG -i --force
    fi
    which haminfo_api
    haminfo_api --help
    haminfo_api --config-file $APP_CONFIG
fi
