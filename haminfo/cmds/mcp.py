import click
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from oslo_config import cfg
from oslo_log import log as logging

from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db
from haminfo.db.models.weather_report import WeatherStation, WeatherReport

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)

mcp = FastMCP("HamInfo")


@mcp.resource("schema://stations")
def get_stations_schema() -> str:
    """Get the stations table schema"""
    conn = db.setup_session()
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stations'").fetchone()
    LOG.error(f"Schema(Stations): {schema}")
    return schema[0] if schema else ""


@mcp.resource("schema://weather_stations")
def get_weather_stations_schema() -> str:
    """Get the weather stations table schema"""
    conn = db.setup_session()
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_stations'").fetchone()
    LOG.error(f"Schema(Weather Stations): {schema}")
    return schema[0] if schema else ""


@mcp.resource("schema://weather_reports")
def get_weather_reports_schema() -> str:
    """Get the weather reports table schema"""
    conn = db.setup_session()
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_reports'").fetchone()
    LOG.error(f"Schema(Weather Reports): {schema}")
    return schema[0] if schema else ""


@mcp.tool()
def query_data(sql: str) -> str:
    """Execute SQL queries safely"""
    conn = db.setup_session()
    try:
        result = conn.execute(sql).fetchall()
        LOG.error(f"Query(Data): {result}")
        return "\n".join(str(row) for row in result)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def query_stations(query: str = "SELECT * FROM stations LIMIT 10") -> str:
    """Query the stations table"""
    conn = db.setup_session()
    try:
        result = conn.execute(query).fetchall()
        LOG.error(f"Result(Stations): {result}")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def query_weather_stations(query: str = "SELECT * FROM weather_stations LIMIT 10") -> str:
    """Query the weather stations table"""
    conn = db.setup_session()
    try:
        result = conn.execute(query).fetchall()
        LOG.error(f"Result(Weather Stations): {result}")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def query_weather_reports(query: str = "SELECT * FROM weather_reports LIMIT 10") -> str:
    """Query the weather reports table"""
    conn = db.setup_session()
    try:
        result = conn.execute(query).fetchall()
        LOG.error(f"Result(Weather Reports): {result}")
        return json.dumps(result, indent=2)
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
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stations'").fetchone()
            return schema[0] if schema else ""

        @self.mcp.resource("schema://weather_stations")
        def get_weather_stations_schema(self) -> str:
            """Get the weather stations table schema"""
            conn = self._get_db_session()
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_stations'").fetchone()
            return schema[0] if schema else ""

        @self.mcp.resource("schema://weather_reports")
        def get_weather_reports_schema(self) -> str:
            """Get the weather reports table schema"""
            conn = self._get_db_session()
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_reports'").fetchone()
            return schema[0] if schema else ""

    def _setup_tools(self):
        @mcp.tool()
        def query_data(sql: str) -> str:
            """Execute SQL queries safely"""
            conn = self._get_db_session()
            try:
                result = conn.execute(sql).fetchall()
                return "\n".join(str(row) for row in result)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_stations(query: str = "SELECT * FROM stations LIMIT 10") -> str:
            """Query the stations table"""
            conn = self._get_db_session()
            try:
                result = conn.execute(query).fetchall()
                return json.dumps(result, indent=2)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_weather_stations(query: str = "SELECT * FROM weather_stations LIMIT 10") -> str:
            """Query the weather stations table"""
            conn = self._get_db_session()
            try:
                result = conn.execute(query).fetchall()
                return json.dumps(result, indent=2)
            except Exception as e:
                return f"Error: {str(e)}"

        @self.mcp.tool()
        def query_weather_reports(query: str = "SELECT * FROM weather_reports LIMIT 10") -> str:
            """Query the weather reports table"""
            conn = self._get_db_connection()
            try:
                result = conn.execute(query).fetchall()
                return json.dumps(result, indent=2)
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

    #server = HamInfoMCP(ctx)
    #server.run()
    #mcp.run()
    LOG.info("Starting MCP server")
    LOG.info(f"MCP server started on port {mcp}")
    mcp.run(transport="stdio")
