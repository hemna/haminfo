"""Console script for haminfo."""
import sys
import click

from oslo_config import cfg
from oslo_log import log as logging

from haminfo import utils
from haminfo.db import db

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DOMAIN = "haminfo"


@click.command()
def main():
    """Console script for haminfo."""
    print("HAminfo starting BITCH")
    click.echo("Replace this message by putting your code into "
               "haminfo.cli.main")
    click.echo("See click documentation at https://click.palletsprojects.com/")

    setup_logging()

    engine = db.setup()
    print("{}".format(db.Station.__table__))

    LOG.info("I farted!  about to exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
