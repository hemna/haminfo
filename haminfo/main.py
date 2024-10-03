import click
from oslo_config import cfg
from oslo_log import log as logging


from haminfo import utils, cli_helper

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(cls=cli_helper.AliasedGroup, context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.pass_context
def cli(ctx):
    pass


def load_commands():
    from .cmds import (  # noqa
        generate_token,
        mapbox,
        fetch_repeaterbook,
        mqtt_injest,
        mqtt_healthcheck,
        db
    )


def main():
    load_commands()
    utils.load_entry_points("haminfo.extension")
    cli(auto_envvar_prefix="HAMINFO")
