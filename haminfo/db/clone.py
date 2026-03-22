# haminfo/db/clone.py
"""Database cloning utilities."""

from urllib.parse import urlparse, unquote

from sqlalchemy import create_engine, text


def parse_db_url(url: str) -> dict:
    """Parse PostgreSQL URL into components for pg_dump/psql.

    Args:
        url: PostgreSQL connection URL in format:
             postgresql://user:password@host:port/database

    Returns:
        Dict with keys: user, password, host, port, database

    Raises:
        ValueError: If URL is invalid or not PostgreSQL
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f'Invalid database URL: {e}') from e

    if not parsed.scheme:
        raise ValueError('Invalid database URL: missing scheme')

    if not parsed.scheme.startswith('postgresql'):
        raise ValueError(f'Only PostgreSQL URLs supported, got: {parsed.scheme}')

    if not parsed.hostname:
        raise ValueError('Invalid database URL: missing hostname')

    return {
        'user': parsed.username or '',
        'password': unquote(parsed.password) if parsed.password else '',
        'host': parsed.hostname,
        'port': str(parsed.port) if parsed.port else '5432',
        'database': parsed.path.lstrip('/') if parsed.path else '',
    }


def test_db_connection(url: str) -> bool:
    """Test if database is reachable.

    Args:
        url: PostgreSQL connection URL

    Returns:
        True if connection succeeds, False otherwise
    """
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True
    except Exception:
        return False


# Default tables to clone (all application tables)
DEFAULT_TABLES = [
    'station',
    'weather_station',
    'weather_report',
    'aprs_packet',
    'request',
    'wx_request',
]


def get_table_list(include: list | None, exclude: list | None) -> list:
    """Get list of tables to clone.

    Args:
        include: If provided, only clone these tables
        exclude: If provided, exclude these tables from default list

    Returns:
        List of table names to clone

    Raises:
        ValueError: If include contains unknown table names
    """
    if include:
        # Validate all tables exist
        unknown = set(include) - set(DEFAULT_TABLES)
        if unknown:
            raise ValueError(f'Unknown table(s): {", ".join(sorted(unknown))}')
        return list(include)

    tables = DEFAULT_TABLES.copy()
    if exclude:
        tables = [t for t in tables if t not in exclude]

    return tables


def build_pg_dump_command(db_info: dict, tables: list) -> list:
    """Build pg_dump command for data export.

    Args:
        db_info: Dict with host, port, user, database keys
        tables: List of table names to dump

    Returns:
        Command as list of strings for subprocess
    """
    cmd = [
        'pg_dump',
        '--data-only',
        '--no-owner',
        '--no-privileges',
        '-h',
        db_info['host'],
        '-p',
        db_info['port'],
        '-U',
        db_info['user'],
        '-d',
        db_info['database'],
    ]

    for table in tables:
        cmd.append(f'--table={table}')

    return cmd


def build_psql_command(db_info: dict) -> list:
    """Build psql command for data import.

    Args:
        db_info: Dict with host, port, user, database keys

    Returns:
        Command as list of strings for subprocess
    """
    return [
        'psql',
        '--quiet',
        '--set',
        'ON_ERROR_STOP=on',
        '-h',
        db_info['host'],
        '-p',
        db_info['port'],
        '-U',
        db_info['user'],
        '-d',
        db_info['database'],
    ]
