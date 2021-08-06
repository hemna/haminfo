"""Script to generate an api key. """

import click
import click_completion
import os
import secrets
import sys
import time
import urllib3
import logging as python_logging

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo import utils, spinner

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
@click.version_option()
def main(disable_spinner, config_file, log_level):
    global LOG, CONF

    click.echo("Using config_file = {}".format(config_file))
    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)
    python_logging.captureWarnings(True)
    utils.setup_logging()

    LOG.info("haminfo_token version: {}".format(haminfo.__version__))
    LOG.info("using config file {}".format(conf_file))

    if CONF.debug and log_level == "DEBUG":
        CONF.log_opt_values(LOG, utils.LOG_LEVELS[log_level])

    if disable_spinner or not sys.stdout.isatty():
        spinner.Spinner.enabled = False

    with spinner.Spinner.get(text="Generating api Key") as sp:
        time.sleep(2)
        apikey = secrets.token_urlsafe()

    msg = "Generated APIKEY={}".format(apikey)
    LOG.info(msg)
    LOG.info("Add api_key to [web] section of config file {}".format(conf_file))
    LOG.info("api_key = {}".format(apikey))


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
