#!/usr/bin/env bash
# Shell script that is run from a cron job
# update the database from repeaterbook
set -x

source /app/.venv/bin/activate
APP_CONFIG="/config/haminfo.conf"
time uv run haminfo rb fetch-all-repeaters -c $APP_CONFIG --loglevel DEBUG
