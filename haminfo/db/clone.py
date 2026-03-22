# haminfo/db/clone.py
"""Database cloning utilities."""

import os
import subprocess
from urllib.parse import urlparse, unquote

from sqlalchemy import create_engine, text


class CloneError(Exception):
    """Error during database clone operation."""

    pass


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


def clone_database(source_url: str, target_url: str, tables: list) -> dict:
    """Clone data from source database to target database.

    Uses pg_dump | psql pipeline for efficient data transfer.

    Args:
        source_url: Source PostgreSQL connection URL
        target_url: Target PostgreSQL connection URL
        tables: List of table names to clone

    Returns:
        Dict mapping table names to row counts

    Raises:
        CloneError: If clone operation fails
    """
    source_info = parse_db_url(source_url)
    target_info = parse_db_url(target_url)

    # Set up environment with passwords
    env = os.environ.copy()
    source_env = env.copy()
    source_env['PGPASSWORD'] = source_info['password']
    target_env = env.copy()
    target_env['PGPASSWORD'] = target_info['password']

    # Connect to target to truncate tables
    target_engine = create_engine(target_url)
    with target_engine.connect() as conn:
        # Disable FK constraints
        conn.execute(text('SET session_replication_role = replica'))
        conn.commit()

        # Truncate tables in reverse order (for FK dependencies)
        for table in reversed(tables):
            conn.execute(text(f'TRUNCATE TABLE {table} CASCADE'))
        conn.commit()

    # Build commands
    pg_dump_cmd = build_pg_dump_command(source_info, tables)
    psql_cmd = build_psql_command(target_info)

    # Execute pg_dump | psql pipeline
    pg_dump_proc = subprocess.Popen(
        pg_dump_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=source_env,
    )

    psql_proc = subprocess.Popen(
        psql_cmd,
        stdin=pg_dump_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=target_env,
    )

    # Close pg_dump stdout in parent to allow SIGPIPE
    pg_dump_proc.stdout.close()

    # Wait for processes
    psql_stdout, psql_stderr = psql_proc.communicate()
    pg_dump_proc.wait()

    if pg_dump_proc.returncode != 0:
        stderr = pg_dump_proc.stderr.read().decode() if pg_dump_proc.stderr else ''
        raise CloneError(
            f'pg_dump failed with code {pg_dump_proc.returncode}: {stderr}'
        )

    if psql_proc.returncode != 0:
        raise CloneError(
            f'psql failed with code {psql_proc.returncode}: {psql_stderr.decode()}'
        )

    # Re-enable FK constraints and reset sequences
    with target_engine.connect() as conn:
        conn.execute(text('SET session_replication_role = DEFAULT'))
        conn.commit()

        # Reset sequences
        for table in tables:
            try:
                conn.execute(
                    text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                        false
                    )
                """)
                )
            except Exception:
                # Table might not have an id column with sequence
                pass
        conn.commit()

    # Get row counts
    row_counts = {}
    with target_engine.connect() as conn:
        for table in tables:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
            row_counts[table] = result.scalar()

    return row_counts
