import click
import datetime
import json
import logging as python_logging
import os
import sys

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo import utils, log
from haminfo import mqtt_injest  # noqa: needed for config


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)


@click.command()
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
def main(config_file, log_level):
    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)

    python_logging.captureWarnings(True)
    log.setup_logging()

    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__} ')
    # Dump out the config options read from config file
    CONF.log_opt_values(LOG, logging.DEBUG)

    now = datetime.datetime.now()

    try:
        modify_time = os.path.getmtime(CONF.mqtt.keepalive_file)
        modify_date = datetime.datetime.fromtimestamp(modify_time)
        max_timeout = {"hours": 0.0, "minutes": 15, "seconds": 0}
        max_delta = datetime.timedelta(**max_timeout)
        diff = now - modify_date
        if diff > max_delta:
            LOG.error(f"Healthcheck file is old! {CONF.mqtt.keepalive_file} : {diff}")
            return -1
        else:
            LOG.info(f"Healthcheck file age {diff}")
    except Exception as ex:
        LOG.error(f"Failed: {ex}")
        return -1

    # try and read the keep alive json file
    try:
        fp = open(CONF.mqtt.keepalive_file)
        keepalive_data = json.load(fp)
        LOG.info(keepalive_data)
        fp.close()
    except Exception:
        LOG.error(f"Failed to read/parse the keepalive file {CONF.mqtt.keepalive_file}")
        return -1


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
