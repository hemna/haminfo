#!/usr/bin/env bash
# Run the MQTT listener for aprsd packets coming from aprsd's
# aprsd-mqtt_plugin

set -x

COLUMNS=${COLUMNS:-160}
export COLUMNS

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    $HOME/.local/bin/oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    $HOME/.local/bin/haminfo_mqtt --loglevel DEBUG
fi
