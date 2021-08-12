#!/bin/bash
# The cron service's main entry point

# Start the run once job.
echo "Docker container has been started"

declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /home/haminfo/container.env

touch /home/haminfo/haminfo.log
# Setup a cron schedule
# To run the DB reload/update at 7am
echo "SHELL=/bin/bash
BASH_ENV=/home/haminfo/container.env
* 7 * * * /home/haminfo/reload_db.sh >> /home/haminfo/haminfo.log 2>&1
# This extra line makes it a valid cron" > scheduler.txt

crontab scheduler.txt
echo "Sarting Cron and tailing /home/haminfo/haminfo.log"
sudo cron -L15 && tail -f /home/haminfo/haminfo.log
