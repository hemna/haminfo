#!/usr/bin/env bash
# Entry point for the dashboard service

set -x

COLUMNS=${COLUMNS:-160}
export COLUMNS

APP_CONFIG="/config/haminfo.conf"

if [ ! -e "$APP_CONFIG" ]; then
    echo "'$APP_CONFIG' File does not exist."
    echo "Dashboard requires haminfo config file with database connection."
    exit 1
fi

# Run the dashboard
# Use gunicorn with gevent worker for production WebSocket support
uv run gunicorn \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --workers 1 \
    --bind 0.0.0.0:5001 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "haminfo_dashboard.app:create_app('$APP_CONFIG')"
