# haminfo/db/clone.py
"""Database cloning utilities."""

from urllib.parse import urlparse, unquote


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
