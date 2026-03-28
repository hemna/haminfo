# haminfo_dashboard/cli.py
"""Command-line interface for haminfo-dashboard."""

from __future__ import annotations

import click
from oslo_config import cfg

CONF = cfg.CONF


@click.command()
@click.option(
    '-c',
    '--config',
    'config_file',
    required=True,
    type=click.Path(exists=True),
    help='Path to haminfo config file',
)
@click.option(
    '-h',
    '--host',
    default='0.0.0.0',
    help='Host to bind to (default: 0.0.0.0)',
)
@click.option(
    '-p',
    '--port',
    default=5001,
    type=int,
    help='Port to bind to (default: 5001)',
)
@click.option(
    '--debug/--no-debug',
    default=False,
    help='Enable debug mode',
)
def main(config_file: str, host: str, port: int, debug: bool) -> None:
    """Run the APRS Dashboard web server.

    Requires a haminfo config file for database connection settings.

    Example:
        haminfo-dashboard -c /etc/haminfo/haminfo.conf
    """
    from haminfo_dashboard.app import create_app
    from haminfo_dashboard.websocket import socketio

    click.echo(f'Starting APRS Dashboard on {host}:{port}')
    click.echo(f'Using config: {config_file}')

    app = create_app(config_file=config_file)

    # Use socketio.run() for WebSocket support
    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
    )


if __name__ == '__main__':
    main()
