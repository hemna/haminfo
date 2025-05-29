import click
import json
from oslo_log import log as logging
import requests
from rich.console import Console
import secrets
from ratelimit import limits, sleep_and_retry

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db
from haminfo.db.models.station import Station


LOG = logging.getLogger(utils.DOMAIN)

# only alloe 1 request every 10 minutes
@sleep_and_retry
@limits(calls=1, period=600)
def fetch_repeaters(sp, url, session, fetch_only=False):
    console = Console()

    try:
        headers = {
            'User-Agent': f"haminfo/{haminfo.__version__} (https://github.com/hemna/haminfo; waboring@hemna.com)",
        }
        LOG.debug(f"Fetching '{url}' headers {headers}")
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            console.print("Failed to fetch repeaters {}".format(resp.status_code))
            return
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
        sp.update("Found {} repeaters to load".format(
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


def fetch_NA_country_repeaters_by_state(sp, session, country,       # noqa:N802
                                        state=None, state_names=None,
                                        fetch_only=False):
    count = 0
    if state:
        msg = "Fetching {}, {}".format(country, state)
        sp.update(msg)
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}&state={}").format(
                requests.utils.quote(country),
                requests.utils.quote(state))
            count = fetch_repeaters(sp, url, session, fetch_only)
        except Exception as ex:
            LOG.error("Failed fetching state '{}'  '{}'".format(state, ex))
            raise ex
    elif state_names:
        # Fetch by state name
        for state in state_names:
            msg = "Fetching {}, {}".format(country, state)
            sp.update(msg)
            LOG.info(msg)
            try:
                url = ("https://www.repeaterbook.com/api/export.php?"
                       "country={}&state={}").format(
                    requests.utils.quote(country),
                    requests.utils.quote(state))
                count += fetch_repeaters(sp, url, session, fetch_only)
            except Exception as ex:
                # Log the exception and continue
                LOG.error("Failed to fetch '{}' because {}".format(state, ex))
                LOG.error(ex)
    else:
        # Just fetch by country
        msg = "Fetching {}".format(country)
        sp.update(msg)
        LOG.info(msg)
        try:
            url = ("https://www.repeaterbook.com/api/export.php?"
                   "country={}").format(
                requests.utils.quote(country))
            count = fetch_repeaters(sp, url, session, fetch_only)
        except Exception as ex:
            LOG.error("Failed fetching Country '{}'  '{}'".format(country, ex))
            raise ex
    return count


def fetch_EU_country_repeaters(sp, session, country, fetch_only=False):   # noqa: N802
    # Just fetch by country
    msg = "Fetching {}".format(country)
    sp.update(msg)
    LOG.info(msg)
    try:
        url = ("https://www.repeaterbook.com/api/exportROW.php?"
               "country={}").format(
            requests.utils.quote(country))
        count = fetch_repeaters(sp, url, session, fetch_only)
    except Exception as ex:
        LOG.error("Failed fetching Country '{}'".format(country))
        LOG.exception(ex)
        raise ex
    return count


def fetch_USA_repeaters_by_state(sp, session, state=None, fetch_only=False):  # noqa: N802
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
    LOG.info("Fetching repeaters for '{}'".format(country))
    return fetch_NA_country_repeaters_by_state(sp, session, country, state,
                                               state_names,
                                               fetch_only=fetch_only)


def fetch_Canada_repeaters(sp, session, fetch_only=False):  # noqa: N802
    country = "Canada"
    state_names = ["Alberta", "British Columbia", "Manitoba", "New Brunswick",
                   "Newfoundland and Labrador", "Nova Scotia", "Nunavut",
                   "Ontario", "Northwest Territories", "Prince Edward Island",
                   "Quebec", "Saskatchewan", "Yukon"]
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        sp, session, country, state=None, state_names=state_names,
        fetch_only=fetch_only)


def fetch_south_america_repeaters(sp, session, fetch_only=False):
    countries = ["Argentina", "Bolivia", "Brazil", "Caribbean Netherlands",
                 "Chile", "Columbia", "Curacao", "Ecuador", "Panama",
                 "Paraguay", "Peru", "Uruguay", "Venezuela"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_Mexico_repeaters(sp, session, fetch_only=False):  # noqa: N802
    country = "Mexico"
    LOG.info("Fetching repeaters for {}".format(country))
    return fetch_NA_country_repeaters_by_state(
        sp, session, country, state=None, fetch_only=fetch_only)


def fetch_EU_repeaters(sp, session, fetch_only=False):    # noqa: N802
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
        count += fetch_EU_country_repeaters(sp, session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_asian_repeaters(sp, session, fetch_only=False):
    countries = ["Australia", "Azerbaijan", "China", "India", "Indonesia",
                 "Israel", "Japan", "Jordan", "Kuwait", "Malaysia", "Nepal",
                 "New Zealand", "Oman", "Philippines", "Singapore",
                 "South Korea", "Sri Lanka", "Thailand", "Turkey",
                 "Taiwan", "United Arab Emirates"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_africa_repeaters(sp, session, fetch_only=False):
    countries = ["Morocco", "Namibia", "South Africa"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_caribbean_repeaters(sp, session, fetch_only=False):
    countries = ["Bahamas", "Barbados", "Costa Rica", "Cayman Islands",
                 "Dominican Republic", "El Salvador", "Grenada",
                 "Guatemala", "Haiti", "Honduras", "Jamaica", "Nicaragua",
                 "Saint Vincent and the Grenadines",
                 "Trinidad and Tobago"]

    count = 0
    for country in countries:
        count += fetch_EU_country_repeaters(sp, session, country,
                                            fetch_only=fetch_only)

    return count


def fetch_all_countries(sp, session, fetch_only=False):
    count = 0
    count += fetch_USA_repeaters_by_state(sp, session, fetch_only=fetch_only)
    count += fetch_Canada_repeaters(sp, session, fetch_only=fetch_only)
    count += fetch_EU_repeaters(sp, session, fetch_only=fetch_only)
    count += fetch_asian_repeaters(sp, session, fetch_only=fetch_only)
    count += fetch_south_america_repeaters(sp, session, fetch_only=fetch_only)
    count += fetch_africa_repeaters(sp, session, fetch_only=fetch_only)
    count += fetch_caribbean_repeaters(sp, session, fetch_only=fetch_only)
    return count


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
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
def fetch_repeaterbook(ctx, disable_spinner, force, fetch_only):
    """Fetch the stations from the haminfo API."""
    console = Console()
    console.print("Fetching stations from the haminfo API")

    if not fetch_only:
        db_session = db.setup_session()
        session = db_session()
    else:
        session = None

    count = 0
    with console.status("Load and insert repeaters from repeaterbook") as sp:
        try:
            # count += fetch_USA_repeaters_by_state(sp, session, "Virginia")
            # count += fetch_USA_repeaters_by_state(sp, session)
            # count += fetch_Canada_repeaters(sp, session)
            # count += fetch_EU_repeaters(sp, session)
            # count += fetch_asian_repeaters(sp, session)
            # count += fetch_south_america_repeaters(sp, session)
            # count += fetch_africa_repeaters(sp, session)
            # count += fetch_caribbean_repeaters(sp, session)
            count = fetch_all_countries(sp, session, fetch_only)

        except Exception as ex:
            LOG.error("Failed to fetch state because {}".format(ex))

    LOG.info("Loaded {} repeaters to the DB.".format(count))

    if session:
        session.close()
