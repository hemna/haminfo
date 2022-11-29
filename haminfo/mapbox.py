import click
import click_completion
import logging as python_logging
import os
import urllib3
import sys

from oslo_config import cfg
from oslo_log import log as logging
from mapbox import Datasets
from rich.console import Console
from geojson import Feature, Point

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
@click.option(
    "--id",
    default="",
    help="The mapbox datasource ID"
)
@click.option(
    "--show",
    is_flag=True,
    default=False,
    help="List all the existing items in mapbox dataset"
)
@click.version_option()
def main(disable_spinner, config_file, log_level, force, id, show):
    global LOG, CONF

    console = Console()

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

    ds = Datasets()
    console.print(ds.baseuri)
    if show:
        if not id:
            console.print("shit")
            sys.exit(-1)
        entries = ds.read_dataset(id).json()
        console.print(entries)
        # for entry in entries:
        #    console.print(entry)
        # Show the features
        features = ds.list_features(id)
        if features.status_code == 200:
            f_json = features.json()
            console.print(f_json)
    else:
        # Load all the requests and put it in the dataset
        db_session = db.setup_session()
        session = db_session()

        with console.status("Fetching Records") as status:
            with session:
                query = db.find_requests(session, 0)
                console.print(query)
                count = query.count()
                for req in query:
                    status.update(f"Fetching {count} Records")
                    point = Point((req.longitude, req.latitude))
                    _dict = req.to_dict()
                    _dict['created'] = str(_dict['created'])
                    marker = Feature(geometry=point,
                                     id=str(req.id),
                                     properties=_dict
                                     )
                    console.print(marker)
                    result = ds.update_feature(id, str(req.id), marker)
                    if result.status_code == 200:
                        console.print(result.json())

                    count -= 1


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
