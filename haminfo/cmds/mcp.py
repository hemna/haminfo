"""MCP (Model Context Protocol) server for haminfo database access.

Provides safe, validated access to the haminfo database via MCP tools
and resources. All SQL queries are validated to prevent injection attacks.
"""

import click
import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy import text, inspect

from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils
from haminfo.db import db
from haminfo.utils.sql_validator import (
    validate_query,
    validate_table_name,
    SQLValidationError,
    MAX_RESULT_LIMIT,
)

CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)

mcp = FastMCP('HamInfo')


def _enforce_table_allowlist(sql: str) -> None:
    """Validate that all table references in a query are in the allowlist.

    Extracts table names from FROM and JOIN clauses and validates each one.

    Args:
        sql: The SQL query to check.

    Raises:
        SQLValidationError: If any referenced table is not allowed.
    """
    import re

    upper = sql.upper()
    # Extract table names from FROM and JOIN clauses
    table_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    tables = re.findall(table_pattern, sql, re.IGNORECASE)
    for table in tables:
        validate_table_name(table)


def _normalize_limit(limit: int) -> int:
    """Normalize a limit value to be within valid range.

    Args:
        limit: The requested limit.

    Returns:
        Clamped limit between 1 and MAX_RESULT_LIMIT.
    """
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        return 10
    return max(1, min(limit, MAX_RESULT_LIMIT))


def _get_session():
    """Get a database session, creating one if needed."""
    return db.setup_session()


def _rows_to_dicts(rows) -> list[dict]:
    """Convert SQLAlchemy Row objects to dictionaries.

    Args:
        rows: SQLAlchemy result rows.

    Returns:
        List of dictionaries representing the rows.
    """
    if not rows:
        return []
    return [dict(row._mapping) for row in rows]


def _execute_safe_query(sql: str) -> str:
    """Execute a validated SQL query and return JSON results.

    Args:
        sql: The SQL query to validate and execute.

    Returns:
        JSON string of results or error message.
    """
    try:
        validated_sql = validate_query(sql)
        # Also enforce table allowlist on free-form queries
        _enforce_table_allowlist(validated_sql)
    except SQLValidationError as e:
        return json.dumps({'error': str(e), 'type': 'validation_error'})

    session_factory = _get_session()
    try:
        with session_factory() as session:
            result = session.execute(text(validated_sql)).fetchall()
            rows = _rows_to_dicts(result)
            return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return json.dumps({'error': str(e), 'type': 'execution_error'})


@mcp.resource('schema://stations')
def get_stations_schema() -> str:
    """Get the stations table schema."""
    session_factory = _get_session()
    try:
        with session_factory() as session:
            inspector = inspect(session.bind)
            columns = inspector.get_columns('station')
            schema_info = [
                {'name': col['name'], 'type': str(col['type'])} for col in columns
            ]
            return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({'error': str(e)})


@mcp.resource('schema://weather_stations')
def get_weather_stations_schema() -> str:
    """Get the weather stations table schema."""
    session_factory = _get_session()
    try:
        with session_factory() as session:
            inspector = inspect(session.bind)
            columns = inspector.get_columns('weather_station')
            schema_info = [
                {'name': col['name'], 'type': str(col['type'])} for col in columns
            ]
            return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({'error': str(e)})


@mcp.resource('schema://weather_reports')
def get_weather_reports_schema() -> str:
    """Get the weather reports table schema."""
    session_factory = _get_session()
    try:
        with session_factory() as session:
            inspector = inspect(session.bind)
            columns = inspector.get_columns('weather_report')
            schema_info = [
                {'name': col['name'], 'type': str(col['type'])} for col in columns
            ]
            return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({'error': str(e)})


@mcp.resource('schema://aprs_packet')
def get_aprs_packet_schema() -> str:
    """Get the aprs_packet table schema."""
    session_factory = _get_session()
    try:
        with session_factory() as session:
            inspector = inspect(session.bind)
            columns = inspector.get_columns('aprs_packet')
            schema_info = [
                {'name': col['name'], 'type': str(col['type'])} for col in columns
            ]
            return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({'error': str(e)})


@mcp.tool()
def query_data(sql: str) -> str:
    """Execute a validated SQL SELECT query against the haminfo database.

    Only SELECT queries are allowed. Dangerous operations like DROP,
    DELETE, UPDATE, INSERT, etc. are blocked. A LIMIT clause is
    automatically added if not present.

    Args:
        sql: A SQL SELECT query string.

    Returns:
        JSON string of query results or error message.
    """
    return _execute_safe_query(sql)


@mcp.tool()
def query_stations(
    callsign: Optional[str] = None,
    state: Optional[str] = None,
    freq_band: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Query ham radio repeater stations with safe parameterized filters.

    Args:
        callsign: Filter by callsign (partial match).
        state: Filter by state.
        freq_band: Filter by frequency band (e.g., '2m', '70cm').
        limit: Maximum number of results (default 10, max 1000).

    Returns:
        JSON string of matching stations.
    """
    limit = _normalize_limit(limit)
    conditions = []
    params = {'limit': limit}

    if callsign:
        conditions.append('callsign ILIKE :callsign')
        params['callsign'] = f'%{callsign}%'
    if state:
        conditions.append('state = :state')
        params['state'] = state
    if freq_band:
        conditions.append('freq_band = :freq_band')
        params['freq_band'] = freq_band

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    sql = f'SELECT * FROM station WHERE {where_clause} LIMIT :limit'

    session_factory = _get_session()
    try:
        with session_factory() as session:
            result = session.execute(text(sql), params).fetchall()
            rows = _rows_to_dicts(result)
            return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return json.dumps({'error': str(e), 'type': 'execution_error'})


@mcp.tool()
def query_weather_stations(
    callsign: Optional[str] = None,
    country_code: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Query weather stations with safe parameterized filters.

    Args:
        callsign: Filter by callsign (partial match).
        country_code: Filter by country code.
        limit: Maximum number of results (default 10, max 1000).

    Returns:
        JSON string of matching weather stations.
    """
    limit = _normalize_limit(limit)
    conditions = []
    params = {'limit': limit}

    if callsign:
        conditions.append('callsign ILIKE :callsign')
        params['callsign'] = f'%{callsign}%'
    if country_code:
        conditions.append('country_code = :country_code')
        params['country_code'] = country_code

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    sql = f'SELECT * FROM weather_station WHERE {where_clause} LIMIT :limit'

    session_factory = _get_session()
    try:
        with session_factory() as session:
            result = session.execute(text(sql), params).fetchall()
            rows = _rows_to_dicts(result)
            return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return json.dumps({'error': str(e), 'type': 'execution_error'})


@mcp.tool()
def query_weather_reports(
    weather_station_id: Optional[int] = None,
    limit: int = 10,
) -> str:
    """Query weather reports with safe parameterized filters.

    Args:
        weather_station_id: Filter by weather station ID.
        limit: Maximum number of results (default 10, max 1000).

    Returns:
        JSON string of matching weather reports, ordered by time descending.
    """
    limit = _normalize_limit(limit)
    conditions = []
    params = {'limit': limit}

    if weather_station_id is not None:
        conditions.append('weather_station_id = :station_id')
        params['station_id'] = weather_station_id

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    sql = (
        f'SELECT * FROM weather_report WHERE {where_clause} '
        f'ORDER BY time DESC LIMIT :limit'
    )

    session_factory = _get_session()
    try:
        with session_factory() as session:
            result = session.execute(text(sql), params).fetchall()
            rows = _rows_to_dicts(result)
            return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return json.dumps({'error': str(e), 'type': 'execution_error'})


@mcp.tool()
def query_aprs_packets(
    from_call: Optional[str] = None,
    packet_type: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Query APRS packets with safe parameterized filters.

    Args:
        from_call: Filter by source callsign (partial match).
        packet_type: Filter by packet type (e.g., 'weather', 'position').
        limit: Maximum number of results (default 10, max 1000).

    Returns:
        JSON string of matching APRS packets, ordered by timestamp descending.
    """
    limit = _normalize_limit(limit)
    conditions = []
    params = {'limit': limit}

    if from_call:
        conditions.append('from_call ILIKE :from_call')
        params['from_call'] = f'%{from_call}%'
    if packet_type:
        conditions.append('packet_type = :packet_type')
        params['packet_type'] = packet_type

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    sql = (
        f'SELECT * FROM aprs_packet WHERE {where_clause} '
        f'ORDER BY timestamp DESC LIMIT :limit'
    )

    session_factory = _get_session()
    try:
        with session_factory() as session:
            result = session.execute(text(sql), params).fetchall()
            rows = _rows_to_dicts(result)
            return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return json.dumps({'error': str(e), 'type': 'execution_error'})


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def mcp_server(ctx):
    """Start the MCP server for haminfo database access."""
    global mcp
    import sys
    from loguru import logger
    from haminfo.conf import log as conf_log

    # Disable stdout logging for MCP server - it breaks JSON-RPC over stdio
    logger.remove()
    handlers = []
    if CONF.logging.logfile:
        handlers.append(
            {
                'sink': CONF.logging.logfile,
                'serialize': False,
                'format': CONF.logging.logformat,
                'colorize': False,
                'level': conf_log.LOG_LEVELS[ctx.obj['loglevel']],
            },
        )
    # Add stderr handler for errors (doesn't interfere with JSON-RPC on stdout)
    handlers.append(
        {
            'sink': sys.stderr,
            'serialize': False,
            'format': CONF.logging.logformat,
            'colorize': True,
            'level': conf_log.LOG_LEVELS[ctx.obj['loglevel']],
        },
    )
    logger.configure(handlers=handlers)

    mcp.run(transport='stdio')
