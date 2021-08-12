#!/usr/bin/env bash
# Shell script that is run from a cron job
# update the database from repeaterbook
set -x

time haminfo_load
