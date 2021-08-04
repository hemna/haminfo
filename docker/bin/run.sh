#!/usr/bin/env bash
set -x

if [ ! -z "${APRSD_PLUGINS}" ]; then
    OLDIFS=$IFS
    IFS=','
    echo "Installing pypi plugins '$APRSD_PLUGINS'";
    for plugin in ${APRSD_PLUGINS}; do
        IFS=$OLDIFS
        # call your procedure/other scripts here below
        echo "Installing '$plugin'"
        pip3 install $plugin
    done
fi

# check to see if there is a config file
APP_CONFIG="/config/haminfo.conf"
if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist. Creating."
    oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask > $APP_CONFIG
    echo "Must configure Database Connection.  Edit $APP_CONFIG"
else
    /usr/local/bin/haminfo_api --config-file $APP_CONFIG --loglevel DEBUG
fi
