#!/bin/bash
# The cron service's main entry point

# Start the run once job.
echo "Docker container has been started"

declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /app/container.env

touch /app/haminfo.log
# Setup a cron schedule
# To run the DB reload/update at 7am
# crontab calculator: https://crontab.guru/
echo "SHELL=/bin/bash
BASH_ENV=/app/container.env
1 1 1 * * /app/reload_db.sh >> /app/haminfo.log 2>&1
# every sunday run cleanup
1 1 * * 7 /app/clean_db.sh >> /app/haminfo.log 2>&1
# This extra line makes it a valid cron" > scheduler.txt

crontab scheduler.txt
echo "Sarting Cron and tailing /app/haminfo.log"
sudo cron -L15 && tail -f /app/haminfo.log
