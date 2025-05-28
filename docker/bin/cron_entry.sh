#!/bin/bash
# The cron service's main entry point

# Start the run once job.
echo "Docker container has been started"

declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /app/container.env

touch /app/haminfo.log
# Setup a cron schedule
# To run the DB reload/update at 7am
echo "SHELL=/bin/bash
BASH_ENV=/app/container.env
* 7 * * * /app/reload_db.sh >> /app/haminfo.log 2>&1
# This extra line makes it a valid cron" > scheduler.txt

crontab scheduler.txt
echo "Sarting Cron and tailing /app/haminfo.log"
sudo cron -L15 && tail -f /app/haminfo.log
