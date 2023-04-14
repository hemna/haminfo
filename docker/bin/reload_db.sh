#!/usr/bin/env bash
# Shell script that is run from a cron job
# update the database from repeaterbook
set -x

time $HOME/.local/bin/haminfo_load
