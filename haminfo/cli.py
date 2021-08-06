"""Console script for haminfo."""
import sys
import click

from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DOMAIN = "haminfo"


@click.command()
def main():
    """Console script for haminfo."""
    click.echo("Replace this message by putting your code into "
               "haminfo.cli.main")
    click.echo("See click documentation at https://click.palletsprojects.com/")

    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
