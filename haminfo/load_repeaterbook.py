import click
import click_completion
import os
import requests
import sys
import urllib3
from tabulate import tabulate
from textwrap import indent

from oslo_config import cfg
from oslo_log import log as logging

from haminfo import utils
from haminfo.db import db

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DOMAIN = "haminfo"


def custom_startswith(string, incomplete):
    """A custom completion match that supports case insensitive matching."""
    if os.environ.get('_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE'):
        string = string.lower()
        incomplete = incomplete.lower()
    return string.startswith(incomplete)


click_completion.core.startswith = custom_startswith
click_completion.init()


@click.command()
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
@click.version_option()
def main(disable_spinner):
    if disable_spinner or not sys.stdout.isatty():
        utils.Spinner.enabled = False

    utils.setup_logging()
    click.echo("started load_repeaterbook")
    Session = db.setup()
    session = Session()

    with utils.Spinner.get(text="Load and insert repeaters!!!") as sp:
        #url = "https://www.repeaterbook.com/api/export.php?country=United%20States"
        url = "https://www.repeaterbook.com/api/export.php?country=Canada"
        resp = requests.get(url)
        if resp.status_code != 200:
            print("Failed to fetch repeaters {}".format(resp.status_code))
            return

        #print("{}".format(resp.json()))
        repeater_json = resp.json()
        if ("count" in repeater_json and
                repeater_json["count"] > 0):
            sp.write("  Found {} repeaters to load".format(
                repeater_json["count"]
            ))
            for repeater in repeater_json["results"]:
                #sp.write(repeater)
                if "Callsign" in repeater:
                    sp.write("process {} : {}, {}".format(
                        repeater['Callsign'],
                        repeater['Country'],
                        repeater['State'],
                    ))
                    repeater_obj = db.Station._from_json(repeater)
                    sp.write(repeater_obj)
                    session.add(repeater_obj)
                    session.commit()


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
