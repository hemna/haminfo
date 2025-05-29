import click
import json
from oslo_log import log as logging
import requests
from rich.console import Console
import secrets
from ratelimit import limits, sleep_and_retry
from ratelimit.exception import RateLimitException
from functools import wraps
import time

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db
from haminfo.db.models.station import Station

LOG = logging.getLogger(utils.DOMAIN)
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@cli.group(help='RepeaterBook type subcommands', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def rb(ctx):
    pass


def sleep_and_retry(func):
    '''
    Return a wrapped function that rescues rate limit exceptions, sleeping the
    current thread until rate limit resets.

    :param function func: The function to decorate.
    :return: Decorated function.
    :rtype: function
    '''
    @wraps(func)
    def wrapper(*args, **kargs):
        '''
        Call the rate limited function. If the function raises a rate limit
        exception sleep for the remaing time period and retry the function.

        :param args: non-keyword variable length argument list to the decorated function.
        :param kargs: keyworded variable length argument list to the decorated function.
        '''
        while True:
            try:
                return func(*args, **kargs)
            except RateLimitException as exception:
                LOG.debug(f"Rate limit waiting for {exception.period_remaining}")
                time.sleep(30)
                # time.sleep(exception.period_remaining)
    return wrapper


# only alloe 1 request every 10 minutes
@sleep_and_retry
@limits(calls=1, period=600)
def fetch_repeaters(url, session, fetch_only=False):
    console = Console()

    try:
        headers = {
            'User-Agent': f"haminfo/{haminfo.__version__} (https://github.com/hemna/haminfo; waboring@hemna.com)",
        }
        msg = f"Fetching '{url}'"
        LOG.debug(msg)
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            console.print("Failed to fetch repeaters {}".format(resp.status_code))
            return
        else:
            LOG.debug(f"URL responded with {resp.status_code}")
    except Exception as ex:
        console.print("Failed to fetch repeaters {}".format(ex))
        return

    # Filter out unwanted characters
    # Wisconsin has some bogus characters in it
    data = resp.text
    data = ''.join((i if 0x20 <= ord(i) < 127 else ' ' for i in data))
    repeater_json = {}
    try:
        repeater_json = json.loads(data)
    except Exception as ex:
        LOG.exception(ex)
        # LOG.error(data)
    # repeater_json = resp.json()

    count = 0
    if "count" in repeater_json and repeater_json["count"] > 0:
        LOG.info(f"Found {repeater_json['count']} repeaters to load")
        countdown = repeater_json["count"]
        for repeater in repeater_json["results"]:
            if 'Frequency' in repeater:
                # If we don't have a frequency, it's useless.
                msg_text = f"({countdown}) {repeater.get('Callsign', None)} {repeater['Frequency']} : {repeater['Country']}"
                LOG.info(msg_text)

                if not fetch_only:
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


def fetch_NA_country_repeaters_by_state(session, country,       # noqa:N802
                                        state=None, state_names=None,
                                        fetch_only=False):
    count = 1
    inserted = 0
    if state:
        msg = f"Fetching {country}, {state}"
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}&state={}").format(
                requests.utils.quote(country),
                requests.utils.quote(state))
            inserted = fetch_repeaters(url, session, fetch_only)
        except Exception as ex:
            LOG.error(f"Failed fetching state '{state}'  '{ex}'")
            raise ex
    elif state_names:
        # Fetch by state name
        for state in state_names:
            msg = f"Fetching {country}, {state} - ({count} of {len(state_names)})"
            LOG.info(msg)
            try:
                url = ("https://www.repeaterbook.com/api/export.php?"
                       "country={}&state={}").format(
                    requests.utils.quote(country),
                    requests.utils.quote(state))
                inserted += fetch_repeaters(url, session, fetch_only)
                count += 1
            except Exception as ex:
                # Log the exception and continue
                LOG.error(f"Failed to fetch '{state}' because {ex}")
    else:
        # Just fetch by country
        msg = f"Fetching {country}"
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}").format(
                requests.utils.quote(country))
            inserted = fetch_repeaters( url, session, fetch_only)
        except Exception as ex:
            LOG.error(f"Failed fetching Country '{country}'  '{ex}'")
            raise ex
    return inserted


def fetch_EU_country_repeaters(session, country, fetch_only=False):   # noqa: N802+
    # Just fetch by country
    LOG.info(f"Fetching {country}")
    try:
        url = ("https://www.repeaterbook.com/api/exportROW.php?"
               "country={}").format(
            requests.utils.quote(country))
        count = fetch_repeaters(url, session, fetch_only)
    except Exception as ex:
        LOG.error("Failed fetching Country '{}'".format(country))
        LOG.exception(ex)
        raise ex
    return count


def fetch_USA_repeaters_by_state(session, state=None, fetch_only=False):  # noqa: N802
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
    LOG.info(f"Fetching repeaters for '{country}' {len(state_names)}")
    return fetch_NA_country_repeaters_by_state(session, country, state,
                                               state_names,
                                               fetch_only=fetch_only)


def fetch_Canada_repeaters(session, fetch_only=False):  # noqa: N802
    country = "Canada"
    state_names = ["Alberta", "British Columbia", "Manitoba", "New Brunswick",
                   "Newfoundland and Labrador", "Nova Scotia", "Nunavut",
                   "Ontario", "Northwest Territories", "Prince Edward Island",
                   "Quebec", "Saskatchewan", "Yukon"]
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        session, country, state=None, state_names=state_names,
        fetch_only=fetch_only)


def fetch_south_america_repeaters(session, fetch_only=False):
    countries = ["Argentina", "Bolivia", "Brazil", "Caribbean Netherlands",
                 "Chile", "Columbia", "Curacao", "Ecuador", "Panama",
                 "Paraguay", "Peru", "Uruguay", "Venezuela"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_Mexico_repeaters(session, fetch_only=False):  # noqa: N802
    country = "Mexico"
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        session, country, state=None, fetch_only=fetch_only)


def fetch_EU_repeaters(session, fetch_only=False):    # noqa: N802
    eu_countries = ["Ablania", "Andorra", "Austria", "Belarus",
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
    for country in eu_countries:
        count += fetch_EU_country_repeaters(session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_asian_repeaters(session, fetch_only=False):
    countries = ["Australia", "Azerbaijan", "China", "India", "Indonesia",
                 "Israel", "Japan", "Jordan", "Kuwait", "Malaysia", "Nepal",
                 "New Zealand", "Oman", "Philippines", "Singapore",
                 "South Korea", "Sri Lanka", "Thailand", "Turkey",
                 "Taiwan", "United Arab Emirates"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_africa_repeaters(session, fetch_only=False):
    countries = ["Morocco", "Namibia", "South Africa"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_caribbean_repeaters(session, fetch_only=False):
    countries = ["Bahamas", "Barbados", "Costa Rica", "Cayman Islands",
                 "Dominican Republic", "El Salvador", "Grenada",
                 "Guatemala", "Haiti", "Honduras", "Jamaica", "Nicaragua",
                 "Saint Vincent and the Grenadines",
                 "Trinidad and Tobago"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_all_countries(session, fetch_only=False):
    count = 0
    count += fetch_USA_repeaters_by_state(session, fetch_only=fetch_only)
    count += fetch_Canada_repeaters(session, fetch_only=fetch_only)
    count += fetch_EU_repeaters(session, fetch_only=fetch_only)
    count += fetch_asian_repeaters(session, fetch_only=fetch_only)
    count += fetch_south_america_repeaters(session, fetch_only=fetch_only)
    count += fetch_africa_repeaters(session, fetch_only=fetch_only)
    count += fetch_caribbean_repeaters(session, fetch_only=fetch_only)
    return count



@rb.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option(
    "--fetch-only",
    "fetch_only",
    show_default=True,
    is_flag=True,
    default=False,
    help="Only fetch repeaters from repeaterbook",
)
@click.pass_context
@cli_helper.process_standard_options
def fetch_usa_repeaters(ctx, fetch_only):
    """Fetch the stations from the haminfo API."""
    console = Console()
    console.print("Fetching USA repeaters from repeaterbook")

    if not fetch_only:
        db_session = db.setup_session()
        session = db_session()
    else:
        session = None

    count = 0
    try:
        count = fetch_USA_repeaters_by_state(session, fetch_only=fetch_only)
    except Exception as ex:
        LOG.error(f"Failed to fetch USA repeaters because {ex}")
    LOG.info(f"Loaded {count} repeaters to the DB.")

    if session:
        session.close()


@rb.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option(
    "--force",
    "force",
    show_default=True,
    is_flag=True,
    default=False,
    help="Used with -i, means don't wait for a DB wipe",
)
@click.option(
    "--fetch-only",
    "fetch_only",
    show_default=True,
    is_flag=True,
    default=False,
    help="Only fetch repeaters from repeaterbook",
)
@click.pass_context
@cli_helper.process_standard_options
def fetch_all_repeaters(ctx, force, fetch_only):
    """Fetch the stations from the haminfo API."""
    console = Console()
    console.print("Fetching stations from the haminfo API")

    if not fetch_only:
        db_session = db.setup_session()
        session = db_session()
    else:
        session = None

    count = 0
    try:
        # count += fetch_USA_repeaters_by_state(sp, session, "Virginia")
        # count += fetch_USA_repeaters_by_state(sp, session)
        # count += fetch_Canada_repeaters(sp, session)
        # count += fetch_EU_repeaters(sp, session)
        # count += fetch_asian_repeaters(sp, session)
        # count += fetch_south_america_repeaters(sp, session)
        # count += fetch_africa_repeaters(sp, session)
        # count += fetch_caribbean_repeaters(sp, session)
        count = fetch_all_countries(session, fetch_only)

    except Exception as ex:
        LOG.error("Failed to fetch state because {}".format(ex))

    LOG.info("Loaded {} repeaters to the DB.".format(count))

    if session:
        session.close()
