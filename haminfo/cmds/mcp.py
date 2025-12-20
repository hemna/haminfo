import click
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy import text

from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)

mcp = FastMCP("HamInfo")


def rows_to_dicts(rows):
    """Convert SQLAlchemy Row objects to dictionaries"""
    if not rows:
        return []
    # SQLAlchemy 2.0+ Row objects can be converted using _mapping
    return [dict(row._mapping) for row in rows]


@mcp.resource("schema://stations")
def get_stations_schema() -> str:
    """Get the stations table schema"""
    conn = db.setup_session()
    schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='stations'")).fetchone()
    return schema[0] if schema else ""


@mcp.resource("schema://weather_stations")
def get_weather_stations_schema() -> str:
    """Get the weather stations table schema"""
    conn = db.setup_session()
    schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_stations'")).fetchone()
    return schema[0] if schema else ""


@mcp.resource("schema://weather_reports")
def get_weather_reports_schema() -> str:
    """Get the weather reports table schema"""
    conn = db.setup_session()
    schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_reports'")).fetchone()
    return schema[0] if schema else ""


@mcp.resource("schema://aprs_packet")
def get_aprs_packet_schema() -> str:
    """Get the aprs_packet table schema"""
    conn = db.setup_session()
    schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='aprs_packet'")).fetchone()
    return schema[0] if schema else ""


@mcp.tool()
def query_data(sql: str) -> str:
    """Execute SQL queries safely"""
    conn = db.setup_session()
    try:
        result = conn.execute(text(sql)).fetchall()
        rows_dict = rows_to_dicts(result)
        return json.dumps(rows_dict, indent=2, default=str)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def query_stations(query: str = "SELECT * FROM stations LIMIT 10") -> str:
    """Query the stations table"""
    conn = db.setup_session()
    try:
        result = conn.execute(text(query)).fetchall()
        rows_dict = rows_to_dicts(result)
        return json.dumps(rows_dict, indent=2, default=str)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def query_weather_stations(query: str = "SELECT * FROM weather_stations LIMIT 10") -> str:
    """Query the weather stations table"""
    conn = db.setup_session()
    try:
        result = conn.execute(text(query)).fetchall()
        rows_dict = rows_to_dicts(result)
        return json.dumps(rows_dict, indent=2, default=str)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def query_weather_reports(query: str = "SELECT * FROM weather_reports LIMIT 10") -> str:
    """Query the weather reports table"""
    conn = db.setup_session()
    try:
        result = conn.execute(text(query)).fetchall()
        rows_dict = rows_to_dicts(result)
        return json.dumps(rows_dict, indent=2, default=str)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def query_aprs_packets(query: str = "SELECT * FROM aprs_packet LIMIT 10") -> str:
    """Query the aprs_packet table"""
    conn = db.setup_session()
    try:
        result = conn.execute(text(query)).fetchall()
        rows_dict = rows_to_dicts(result)
        return json.dumps(rows_dict, indent=2, default=str)
    except Exception as e:
        return f"Error: {str(e)}"


class HamInfoMCP:
    def __init__(self, ctx):
        self.mcp = FastMCP("HamInfo")
        self._setup_resources()
        self._setup_tools()
        self.ctx = ctx

    def _get_db_session(self):
        return db.setup_session()

    def _setup_resources(self):

        @self.mcp.resource("schema://stations")
        def get_stations_schema(self) -> str:
            """Get the stations table schema"""
            conn = self._get_db_session()
            schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='stations'")).fetchone()
            return schema[0] if schema else ""

        @self.mcp.resource("schema://weather_stations")
        def get_weather_stations_schema(self) -> str:
            """Get the weather stations table schema"""
            conn = self._get_db_session()
            schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_stations'")).fetchone()
            return schema[0] if schema else ""

        @self.mcp.resource("schema://weather_reports")
        def get_weather_reports_schema(self) -> str:
            """Get the weather reports table schema"""
            conn = self._get_db_session()
            schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_reports'")).fetchone()
            return schema[0] if schema else ""

    def _setup_tools(self):
        @mcp.tool()
        def query_data(sql: str) -> str:
            """Execute SQL queries safely"""
            conn = self._get_db_session()
            try:
                result = conn.execute(text(sql)).fetchall()
                rows_dict = rows_to_dicts(result)
                return json.dumps(rows_dict, indent=2, default=str)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_stations(query: str = "SELECT * FROM stations LIMIT 10") -> str:
            """Query the stations table"""
            conn = self._get_db_session()
            try:
                result = conn.execute(text(query)).fetchall()
                rows_dict = rows_to_dicts(result)
                return json.dumps(rows_dict, indent=2, default=str)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_weather_stations(query: str = "SELECT * FROM weather_stations LIMIT 10") -> str:
            """Query the weather stations table"""
            conn = self._get_db_session()
            try:
                result = conn.execute(text(query)).fetchall()
                rows_dict = rows_to_dicts(result)
                return json.dumps(rows_dict, indent=2, default=str)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_weather_reports(query: str = "SELECT * FROM weather_reports LIMIT 10") -> str:
            """Query the weather reports table"""
            conn = self._get_db_session()
            try:
                result = conn.execute(text(query)).fetchall()
                rows_dict = rows_to_dicts(result)
                return json.dumps(rows_dict, indent=2, default=str)
            except Exception as e:
                return f"Error: {str(e)}"

    def run(self):
        """Run the MCP server"""
        self.mcp.run()


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def mcp_server(ctx):
    """Start the MCP server for haminfo database access"""
    global mcp
    import sys
    from loguru import logger
    from haminfo.conf import log as conf_log

    # Disable stdout logging for MCP server - it breaks JSON-RPC over stdio
    # Remove any handlers that write to stdout
    logger.remove()
    # Re-add only file logging if configured, but no stdout
    handlers = []
    if CONF.logging.logfile:
        handlers.append(
            {
                "sink": CONF.logging.logfile,
                "serialize": False,
                "format": CONF.logging.logformat,
                "colorize": False,
                "level": conf_log.LOG_LEVELS[ctx.obj["loglevel"]],
            },
        )
    # Add stderr handler for errors (doesn't interfere with JSON-RPC on stdout)
    handlers.append(
        {
            "sink": sys.stderr,
            "serialize": False,
            "format": CONF.logging.logformat,
            "colorize": True,
            "level": conf_log.LOG_LEVELS[ctx.obj["loglevel"]],
        },
    )
    logger.configure(handlers=handlers)

    #server = HamInfoMCP(ctx)
    #server.run()
    #mcp.run()
    mcp.run(transport="stdio")
