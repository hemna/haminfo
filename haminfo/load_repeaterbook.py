import click
import click_completion
import os
import requests
import sys
import time
import urllib3
import logging as python_logging
import sqlalchemy
from tabulate import tabulate
from textwrap import indent

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo import utils
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

def delete_state_repeaters(state, session):
    stmt = sqlalchemy.delete(db.Station).where(db.Station.state == state).execution_options(synchronize_session="fetch")
    session.execute(stmt)

def fetch_repeaters(sp, url, session):
    resp = requests.get(url)
    if resp.status_code != 200:
        print("Failed to fetch repeaters {}".format(resp.status_code))
        return

    # print("{}".format(resp.json()))
    repeater_json = resp.json()
    count = 0
    if "count" in repeater_json and repeater_json["count"] > 0:
        sp.write("Found {} repeaters to load".format(
            repeater_json["count"]
        ))
        count = repeater_json["count"]
        for repeater in repeater_json["results"]:
            if "Callsign" in repeater:
                sp.text = "({}) {} {} : {}, {}".format(
                    count,
                    repeater['Callsign'],
                    repeater['Frequency'],
                    repeater['Country'],
                    repeater['State'])
                repeater_obj = db.Station._from_json(repeater)
                session.add(repeater_obj)
            time.sleep(0.001)
            count -= 1
    session.commit()
    return count


def fetch_USA_repeaters_by_state(sp, session, state=None):
    state_names = ["Alaska", "Alabama", "Arkansas", "American Samoa", "Arizona", "California", "Colorado",
                   "Connecticut", "District ", "of Columbia", "Delaware", "Florida", "Georgia", "Guam", "Hawaii",
                   "Iowa", "Idaho", "Illinois", "Indiana", "Kansas", "Kentucky", "Louisiana", "Massachusetts",
                   "Maryland", "Maine", "Michigan", "Minnesota", "Missouri", "Mississippi", "Montana", "North Carolina",
                   "North Dakota", "Nebraska", "New Hampshire", "New Jersey", "New Mexico", "Nevada", "New York",
                   "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Puerto Rico", "Rhode Island", "South Carolina",
                   "South Dakota", "Tennessee", "Texas", "Utah", "Virginia", "Virgin Islands", "Vermont", "Washington",
                   "Wisconsin", "West Virginia", "Wyoming"]

    url = "https://www.repeaterbook.com/api/export.php?country=United%20States&state={}"
    count = 0
    if state:
        sp.write("Fetching US State of {}".format(state))
        delete_state_repeaters(state, session)
        count = fetch_repeaters(sp, url.format(state), session)
    else:
        for state in state_names:
            delete_state_repeaters(state, session)
            sp.write("Fetching US State of {}".format(state))
            count += fetch_repeaters(sp, url.format(state), session)
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
    "--loglevel",
    default="DEBUG",
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
def main(disable_spinner, config_file, loglevel, init_db, force):
    global LOG, CONF
    print(sys.argv[1:])
    print("config_file = {}".format(config_file))
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)
    python_logging.captureWarnings(True)
    utils.setup_logging()
    LOG.warning("PISS '{}".format(CONF.config_file))

    CONF.log_opt_values(LOG, utils.LOG_LEVELS[loglevel])

    if disable_spinner or not sys.stdout.isatty():
        utils.Spinner.enabled = False

    engine = db.setup_connection()
    if init_db:
        if not force:
            count = 10
            wait_text ="Wiping out the ENTIRE DB in {}"
            with utils.Spinner.get(text=wait_text.format(count)) as sp:
                for i in range(10):
                    time.sleep(1)
                    count -= 1
                    sp.text = wait_text.format(count)

        db.init_db_schema(engine)

    Session = db.setup_session(engine)
    session = Session()

    count = 0
    with utils.Spinner.get(text="Load and insert repeaters!!!") as sp:
        cnt = fetch_USA_repeaters_by_state(sp, session, "Wisconsin")
        #cnt = fetch_USA_repeaters_by_state(sp, session, "Virginia")
        #count += cnt
        #sp.text = "Virginia completed {}".format(cnt)
        #time.sleep(1)
        #cnt = fetch_USA_repeaters_by_state(sp, session, "California")
        #count += cnt
        #sp.text = "California completed {}".format(cnt)
        #time.sleep(1)
        #cnt = fetch_USA_repeaters_by_state(sp, session, "North Carolina")
        count += cnt

if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
