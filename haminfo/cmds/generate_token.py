import click
from rich.console import Console
import secrets
import time

from haminfo.main import cli
from haminfo import cli_helper


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
@click.pass_context
@cli_helper.process_standard_options
def generate_token(ctx, disable_spinner):
    """Generate a token for the haminfo API."""
    console = Console()
    console.print("Generating a new token for the haminfo API")

    if disable_spinner:
        time.sleep(2)
        apikey = secrets.token_urlsafe()
    else:
        with console.status("Generating token..."):
            time.sleep(2)
            apikey = secrets.token_urlsafe()

    console.print(f"Generated API Key: [bold green]{apikey}[/]")
    console.print("Add api_key to \[web] section of config file")  # noqa
    console.print(f"[bold green]api_key = {apikey}[/]")
