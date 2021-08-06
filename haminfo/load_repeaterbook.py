import click
import click_completion
import json
import os
import requests
import sys
import time
import urllib3
import logging as python_logging

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo import utils, spinner
from haminfo.db import db

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def custom_startswith(string, incomplete):
    """A custom completion match that supports case insensitive matching."""
    if os.environ.get('_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE'):
        string = string.lower()
        incomplete = incomplete.lower()
    return string.startswith(incomplete)


click_completion.core.startswith = custom_startswith
click_completion.init()


def fetch_repeaters(sp, url, session):
    resp = requests.get(url)
    if resp.status_code != 200:
        print("Failed to fetch repeaters {}".format(resp.status_code))
        return

    # Filter out unwanted characters
    # Wisconsin has some bogus characters in it
    data = resp.text
    data = ''.join((i if 0x20 <= ord(i) < 127 else ' ' for i in data))
    repeater_json = json.loads(data)
    # repeater_json = resp.json()

    count = 0
    if "count" in repeater_json and repeater_json["count"] > 0:
        sp.write("Found {} repeaters to load".format(
            repeater_json["count"]
        ))
        countdown = repeater_json["count"]
        for repeater in repeater_json["results"]:
            if 'Frequency' in repeater:
                # If we don't have a frequency, it's useless.
                sp.text = "({}) {} {} : {}, {}".format(
                    countdown,
                    repeater.get('Callsign', None),
                    repeater['Frequency'],
                    repeater['Country'],
                    repeater['State'],
                )

                station = db.Station.find_station_by_ids(
                    session, int(repeater['State ID']),
                    int(repeater['Rptr ID']))

                if station:
                    # Update an existing record so we maintain the id in the DB
                    repeater_obj = db.Station.update_from_json(
                        repeater, station)
                else:
                    repeater_obj = db.Station.from_json(repeater)
                session.add(repeater_obj)

                # Just in case we want to fail on a single repeater
                # this allows all others to be commited to the DB
                # and not lost.  less efficient for sure.
                session.commit()
            time.sleep(0.001)
            countdown -= 1
            count += 1
    # session.commit()
    return count


def fetch_USA_repeaters_by_state(sp, session, state=None):
    """Only fetch United States repeaters.

    TODO(waboring): fetch non US repeaters is needed
    """
    state_names = ["Alaska", "Alabama", "Arkansas", "American Samoa",
                   "Arizona", "California", "Colorado", "Connecticut",
                   "District of Columbia", "Delaware", "Florida", "Georgia",
                   "Guam", "Hawaii", "Iowa", "Idaho", "Illinois", "Indiana",
                   "Kansas", "Kentucky", "Louisiana", "Massachusetts",
                   "Maryland", "Maine", "Michigan", "Minnesota", "Missouri",
                   "Mississippi", "Montana", "North Carolina", "North Dakota",
                   "Nebraska", "New Hampshire", "New Jersey", "New Mexico",
                   "Nevada", "New York", "Ohio", "Oklahoma", "Oregon",
                   "Pennsylvania", "Puerto Rico", "Rhode Island",
                   "South Carolina", "South Dakota", "Tennessee", "Texas",
                   "Utah", "Virginia", "Virgin Islands", "Vermont",
                   "Washington", "Wisconsin", "West Virginia", "Wyoming"]

    url = ("https://www.repeaterbook.com/api/export.php?"
           "country=United%20States&state={}")
    count = 0
    if state:
        msg = "Fetching US State of {}".format(state)
        sp.write(msg)
        LOG.info(msg)
        # db.delete_USA_state_repeaters(state, session)
        try:
            count = fetch_repeaters(sp, url.format(state), session)
        except Exception as ex:
            LOG.error("Failed fetching state '{}'  '{}'".format(state, ex))
            raise ex
    else:
        for state in state_names:
            db.delete_USA_state_repeaters(state, session)
            msg = "Fetching US State of {}".format(state)
            sp.write(msg)
            LOG.info(msg)
            try:
                count += fetch_repeaters(sp, url.format(state), session)
            except Exception as ex:
                # Log the exception and continue
                LOG.error("Failed to fetch '{}' because {}".format(state, ex))
    return count


@click.command()
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
@click.option(
    "-c",
    "--config-file",
    "config_file",
    show_default=True,
    default=utils.DEFAULT_CONFIG_FILE,
    help="The aprsd config file to use for options.",
)
@click.option(
    "--log-level",
    "log_level",
    default="INFO",
    show_default=True,
    type=click.Choice(
        ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        case_sensitive=False,
    ),
    show_choices=True,
    help="The log level to use for aprsd.log",
)
@click.option(
    "-i",
    "init_db",
    show_default=True,
    is_flag=True,
    default=False,
    help="Wipe out the entire DB and recreate it from scratch.",
)
@click.option(
    "--force",
    "force",
    show_default=True,
    is_flag=True,
    default=False,
    help="Used with -i, means don't wait for a DB wipe",
)
@click.version_option()
def main(disable_spinner, config_file, log_level, init_db, force):
    global LOG, CONF

    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)
    python_logging.captureWarnings(True)
    utils.setup_logging()

    LOG.info("haminfo_load version: {}".format(haminfo.__version__))
    LOG.info("using config file {}".format(conf_file))

    if CONF.debug and log_level == "DEBUG":
        CONF.log_opt_values(LOG, utils.LOG_LEVELS[log_level])

    if disable_spinner or not sys.stdout.isatty():
        spinner.Spinner.enabled = False

    engine = db.setup_connection()
    if init_db:
        if not force:
            count = 10
            wait_text = "Wiping out the ENTIRE DB in {}"
            with spinner.Spinner.get(text=wait_text.format(count)) as sp:
                for i in range(10):
                    time.sleep(1)
                    count -= 1
                    sp.text = wait_text.format(count)

        db.init_db_schema(engine)

    Session = db.setup_session(engine)
    session = Session()

    count = 0
    with spinner.Spinner.get(text="Load and insert repeaters from USA") as sp:
        try:
            # count += fetch_USA_repeaters_by_state(sp, session, "Virginia")
            count += fetch_USA_repeaters_by_state(sp, session)
        except Exception as ex:
            LOG.error("Failed to fetch state because {}".format(ex))

    LOG.info("Loaded {} repeaters to the DB.".format(count))


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
