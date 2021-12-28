import click
import click_completion
import json
import os
import requests
import sys
import urllib3
import logging as python_logging

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo import utils, spinner
from haminfo.db import db
from haminfo.db.models.station import Station

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
    LOG.debug("Fetching {}".format(url))
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
                sp.text = "({}) {} {} : {}".format(
                    countdown,
                    repeater.get('Callsign', None),
                    repeater['Frequency'],
                    repeater['Country']
                )
                LOG.debug("{}".format(sp.text))

                station = Station.find_station_by_ids(
                    session, repeater['State ID'],
                    int(repeater['Rptr ID']))

                if station:
                    # Update an existing record so we maintain the id in the DB
                    repeater_obj = Station.update_from_json(
                        repeater, station)
                else:
                    repeater_obj = Station.from_json(repeater)

                session.add(repeater_obj)

                # Just in case we want to fail on a single repeater
                # this allows all others to be commited to the DB
                # and not lost.  less efficient for sure.
                session.commit()
            else:
                LOG.warning("No frequency for {}".format(repeater))
            # time.sleep(0.001)
            countdown -= 1
            count += 1
    # session.commit()
    return count


def fetch_NA_country_repeaters_by_state(sp, session, country,
                                        state=None, state_names=None):

    count = 0
    if state:
        msg = "Fetching {}, {}".format(country, state)
        sp.write(msg)
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}&state={}").format(
                requests.utils.quote(country),
                requests.utils.quote(state))
            count = fetch_repeaters(sp, url, session)
        except Exception as ex:
            LOG.error("Failed fetching state '{}'  '{}'".format(state, ex))
            raise ex
    elif state_names:
        # Fetch by state name
        for state in state_names:
            msg = "Fetching {}, {}".format(country, state)
            sp.write(msg)
            LOG.info(msg)
            try:
                url = ("https://www.repeaterbook.com/api/export.php?"
                       "country={}&state={}").format(
                    requests.utils.quote(country),
                    requests.utils.quote(state))
                count += fetch_repeaters(sp, url, session)
            except Exception as ex:
                # Log the exception and continue
                LOG.error("Failed to fetch '{}' because {}".format(state, ex))
    else:
        # Just fetch by country
        msg = "Fetching {}".format(country)
        sp.write(msg)
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}").format(
                requests.utils.quote(country))
            count = fetch_repeaters(sp, url, session)
        except Exception as ex:
            LOG.error("Failed fetching Country '{}'  '{}'".format(country, ex))
            raise ex
    return count


def fetch_EU_country_repeaters(sp, session, country):
    # Just fetch by country
    msg = "Fetching {}".format(country)
    sp.write(msg)
    LOG.info(msg)
    try:
        url = ("https://www.repeaterbook.com/api/exportROW.php?"
               "country={}").format(
            requests.utils.quote(country))
        count = fetch_repeaters(sp, url, session)
    except Exception as ex:
        LOG.error("Failed fetching Country '{}'".format(country))
        LOG.exception(ex)
        raise ex
    return count


def fetch_USA_repeaters_by_state(sp, session, state=None):
    """Only fetch United States repeaters."""
    country = "United States"
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
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(sp, session, country, state,
                                               state_names)


def fetch_Canada_repeaters(sp, session):
    country = "Canada"
    state_names = ["Alberta", "British Columbia", "Manitoba", "New Brunswick",
                   "Newfoundland and Labrador", "Nova Scotia", "Nunavut",
                   "Ontario", "Northwest Territories", "Prince Edward Island",
                   "Quebec", "Saskatchewan", "Yukon"]
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        sp, session, country, state=None, state_names=state_names)


def fetch_south_america_repeaters(sp, session):
    countries = ["Argentina", "Bolivia", "Brazil", "Caribbean Netherlands",
                 "Chile", "Columbia", "Curacao", "Ecuador", "Panama",
                 "Paraguay", "Peru", "Uruguay", "Venezuela"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country)

    return count


def fetch_Mexico_repeaters(sp, session):
    country = "Mexico"
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        sp, session, country, state=None)


def fetch_EU_repeaters(sp, session):
    EU_COUNTRIES = ["Ablania", "Andorra", "Austria", "Belarus",
                    "Belgium", "Bosnia and Herzegovina",
                    "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
                    "Denmark", "Estonia", "Faroe Islands", "Finland",
                    "France", "Georgia", "Germany", "Guernsey",
                    "Greece", "Hungary", "Iceland", "Isle of Man",
                    "Ireland", "Italy", "Jersey", "Kosovo", "Latvia",
                    "Liechtenstein", "Lithuania", "Luxembourg", "Macedonia",
                    "Malta", "Netherlands", "Norway", "Poland", "Portugal",
                    "Romania", "Russian Federation", "San Marino", "Serbia",
                    "Slovakia", "Slovenia", "Spain", "Sweden", "Switzerland",
                    "Ukraine", "United Kingdom"]
    count = 0
    for country in EU_COUNTRIES:
        count += fetch_EU_country_repeaters(sp, session, country)

    return count


def fetch_asian_repeaters(sp, session):
    countries = ["Australia", "Azerbaijan", "China", "India", "Indonesia",
                 "Israel", "Japan", "Jordan", "Kuwait", "Malaysia", "Nepal",
                 "New Zealand", "Oman", "Philippines", "Singapore",
                 "South Korea", "Sri Lanka", "Thailand", "Turkey",
                 "Taiwan", "United Arab Emirates"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country)

    return count


def fetch_africa_repeaters(sp, session):
    countries = ["Morocco", "Namibia", "South Africa"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country)

    return count


def fetch_caribbean_repeaters(sp, session):
    countries = ["Bahamas", "Barbados", "Costa Rica", "Cayman Islands",
                 "Dominican Republic", "El Salvador", "Grenada",
                 "Guatemala", "Haiti", "Honduras", "Jamaica", "Nicaragua",
                 "Saint Vincent and the Grenadines",
                 "Trinidad and Tobago"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country)

    return count


def fetch_all_countries(sp, session):
    count = 0
    count += fetch_USA_repeaters_by_state(sp, session)
    count += fetch_Canada_repeaters(sp, session)
    count += fetch_EU_repeaters(sp, session)
    count += fetch_asian_repeaters(sp, session)
    count += fetch_south_america_repeaters(sp, session)
    count += fetch_africa_repeaters(sp, session)
    count += fetch_caribbean_repeaters(sp, session)
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
    "--force",
    "force",
    show_default=True,
    is_flag=True,
    default=False,
    help="Used with -i, means don't wait for a DB wipe",
)
@click.version_option()
def main(disable_spinner, config_file, log_level, force):
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
    Session = db.setup_session(engine)
    session = Session()

    count = 0
    with spinner.Spinner.get(text="Load and insert repeaters from USA") as sp:
        try:
            # count += fetch_USA_repeaters_by_state(sp, session, "Virginia")
            # count += fetch_USA_repeaters_by_state(sp, session)
            # count += fetch_Canada_repeaters(sp, session)
            # count += fetch_EU_repeaters(sp, session)
            # count += fetch_asian_repeaters(sp, session)
            # count += fetch_south_america_repeaters(sp, session)
            # count += fetch_africa_repeaters(sp, session)
            # count += fetch_caribbean_repeaters(sp, session)
            count = fetch_all_countries(sp, session)

        except Exception as ex:
            LOG.error("Failed to fetch state because {}".format(ex))

    LOG.info("Loaded {} repeaters to the DB.".format(count))

    session.close()


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
