#!/usr/bin/env bash
# Run the MQTT listener for aprsd packets coming from aprsd's
# aprsd-mqtt_plugin

set -x

COLUMNS=${COLUMNS:-160}
export COLUMNS

source /app/.venv/bin/activate

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    uv run oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    uv run haminfo wx-mqtt-injest --loglevel DEBUG
fi
