# Database Clone Command Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `haminfo db clone-from` CLI command to clone all data from a source PostgreSQL database to the local database.

**Architecture:** New command in `haminfo/cmds/db.py` that uses `pg_dump` piped to `psql` for efficient data transfer. Helper functions handle URL parsing, connectivity testing, and sequence reset.

**Tech Stack:** Click (CLI), subprocess (pg_dump/psql), SQLAlchemy (connectivity test, sequence reset), oslo.config (config file parsing)

**Spec:** `docs/superpowers/specs/2026-03-22-db-clone-command-design.md`

---

## Chunk 1: Core Implementation

### Task 1: Add URL Parsing Helper

**Files:**
- Create: `haminfo/db/clone.py`
- Test: `tests/test_db_clone.py`

- [ ] **Step 1: Create test file with URL parsing tests**

```python
# tests/test_db_clone.py
"""Tests for database clone functionality."""

import pytest


class TestParseDbUrl:
    """Test PostgreSQL URL parsing."""

    def test_parse_standard_url(self):
        """Parse a standard PostgreSQL URL."""
        from haminfo.db.clone import parse_db_url

        url = 'postgresql://user:pass@host.example.com:5432/dbname'
        result = parse_db_url(url)

        assert result['user'] == 'user'
        assert result['password'] == 'pass'
        assert result['host'] == 'host.example.com'
        assert result['port'] == '5432'
        assert result['database'] == 'dbname'

    def test_parse_url_default_port(self):
        """Parse URL without explicit port (defaults to 5432)."""
        from haminfo.db.clone import parse_db_url

        url = 'postgresql://user:pass@host.example.com/dbname'
        result = parse_db_url(url)

        assert result['port'] == '5432'

    def test_parse_url_with_special_chars_in_password(self):
        """Parse URL with URL-encoded special characters in password."""
        from haminfo.db.clone import parse_db_url

        # Password is "p@ss:word" URL-encoded as "p%40ss%3Aword"
        url = 'postgresql://user:p%40ss%3Aword@host/dbname'
        result = parse_db_url(url)

        assert result['password'] == 'p@ss:word'

    def test_parse_invalid_url_raises(self):
        """Invalid URL raises ValueError."""
        from haminfo.db.clone import parse_db_url

        with pytest.raises(ValueError, match='Invalid database URL'):
            parse_db_url('not-a-valid-url')

    def test_parse_non_postgresql_url_raises(self):
        """Non-PostgreSQL URL raises ValueError."""
        from haminfo.db.clone import parse_db_url

        with pytest.raises(ValueError, match='Only PostgreSQL'):
            parse_db_url('mysql://user:pass@host/db')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Create clone.py with parse_db_url function**

```python
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
        raise ValueError(f'Invalid database URL: {e}')

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add parse_db_url helper for clone command"
```

---

### Task 2: Add Connection Test Helper

**Files:**
- Modify: `haminfo/db/clone.py`
- Modify: `tests/test_db_clone.py`

- [ ] **Step 1: Add test for connection testing**

Add to `tests/test_db_clone.py`:

```python
from unittest.mock import patch, MagicMock


class TestTestDbConnection:
    """Test database connection testing."""

    @patch('haminfo.db.clone.create_engine')
    def test_connection_success(self, mock_create_engine):
        """Successful connection returns True."""
        from haminfo.db.clone import test_db_connection

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_engine.return_value = mock_engine

        result = test_db_connection('postgresql://user:pass@host/db')

        assert result is True

    @patch('haminfo.db.clone.create_engine')
    def test_connection_failure(self, mock_create_engine):
        """Failed connection returns False."""
        from haminfo.db.clone import test_db_connection

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception('Connection refused')
        mock_create_engine.return_value = mock_engine

        result = test_db_connection('postgresql://user:pass@host/db')

        assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py::TestTestDbConnection -v`
Expected: FAIL with "ImportError" (function doesn't exist)

- [ ] **Step 3: Add test_db_connection function**

Add to `haminfo/db/clone.py`:

```python
from sqlalchemy import create_engine, text


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py::TestTestDbConnection -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add test_db_connection helper"
```

---

### Task 3: Add Table List Helper

**Files:**
- Modify: `haminfo/db/clone.py`
- Modify: `tests/test_db_clone.py`

- [ ] **Step 1: Add tests for table list filtering**

Add to `tests/test_db_clone.py`:

```python
class TestGetTableList:
    """Test table list generation."""

    def test_default_tables(self):
        """Returns all application tables by default."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=None, exclude=None)

        assert 'station' in tables
        assert 'weather_station' in tables
        assert 'weather_report' in tables
        assert 'aprs_packet' in tables
        assert 'request' in tables
        assert 'wx_request' in tables
        assert 'alembic_version' not in tables

    def test_include_filter(self):
        """Include filter limits to specified tables."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=['station', 'weather_station'], exclude=None)

        assert tables == ['station', 'weather_station']

    def test_exclude_filter(self):
        """Exclude filter removes specified tables."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=None, exclude=['request', 'wx_request'])

        assert 'station' in tables
        assert 'request' not in tables
        assert 'wx_request' not in tables

    def test_include_invalid_table_raises(self):
        """Including invalid table raises ValueError."""
        from haminfo.db.clone import get_table_list

        with pytest.raises(ValueError, match='Unknown table'):
            get_table_list(include=['station', 'invalid_table'], exclude=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py::TestGetTableList -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Add get_table_list function**

Add to `haminfo/db/clone.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py::TestGetTableList -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add get_table_list helper"
```

---

### Task 4: Add pg_dump Command Builder

**Files:**
- Modify: `haminfo/db/clone.py`
- Modify: `tests/test_db_clone.py`

- [ ] **Step 1: Add tests for pg_dump command building**

Add to `tests/test_db_clone.py`:

```python
class TestBuildPgDumpCommand:
    """Test pg_dump command construction."""

    def test_basic_command(self):
        """Build basic pg_dump command."""
        from haminfo.db.clone import build_pg_dump_command

        db_info = {
            'host': 'prod.example.com',
            'port': '5432',
            'user': 'haminfo',
            'database': 'haminfo',
        }
        tables = ['station', 'weather_station']

        cmd = build_pg_dump_command(db_info, tables)

        assert cmd[0] == 'pg_dump'
        assert '--data-only' in cmd
        assert '--no-owner' in cmd
        assert '--no-privileges' in cmd
        assert '-h' in cmd
        assert 'prod.example.com' in cmd
        assert '-p' in cmd
        assert '5432' in cmd
        assert '-U' in cmd
        assert 'haminfo' in cmd
        assert '--table=station' in cmd
        assert '--table=weather_station' in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py::TestBuildPgDumpCommand -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Add build_pg_dump_command function**

Add to `haminfo/db/clone.py`:

```python
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
        '-h', db_info['host'],
        '-p', db_info['port'],
        '-U', db_info['user'],
        '-d', db_info['database'],
    ]

    for table in tables:
        cmd.append(f'--table={table}')

    return cmd
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py::TestBuildPgDumpCommand -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add build_pg_dump_command helper"
```

---

### Task 5: Add psql Command Builder

**Files:**
- Modify: `haminfo/db/clone.py`
- Modify: `tests/test_db_clone.py`

- [ ] **Step 1: Add tests for psql command building**

Add to `tests/test_db_clone.py`:

```python
class TestBuildPsqlCommand:
    """Test psql command construction."""

    def test_basic_command(self):
        """Build basic psql command."""
        from haminfo.db.clone import build_psql_command

        db_info = {
            'host': 'localhost',
            'port': '5432',
            'user': 'haminfo',
            'database': 'haminfo',
        }

        cmd = build_psql_command(db_info)

        assert cmd[0] == 'psql'
        assert '--quiet' in cmd
        assert '-h' in cmd
        assert 'localhost' in cmd
        assert '-p' in cmd
        assert '5432' in cmd
        assert '-U' in cmd
        assert 'haminfo' in cmd
        assert '-d' in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py::TestBuildPsqlCommand -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Add build_psql_command function**

Add to `haminfo/db/clone.py`:

```python
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
        '--set', 'ON_ERROR_STOP=on',
        '-h', db_info['host'],
        '-p', db_info['port'],
        '-U', db_info['user'],
        '-d', db_info['database'],
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py::TestBuildPsqlCommand -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add build_psql_command helper"
```

---

## Chunk 2: CLI Command and Integration

### Task 6: Add clone-from CLI Command (Basic Structure)

**Files:**
- Modify: `haminfo/cmds/db.py`

- [ ] **Step 1: Add the clone_from command structure**

Add to `haminfo/cmds/db.py` at the end of the file:

```python
from haminfo.db import clone as db_clone


@db.command()
@cli_helper.add_options(cli_helper.common_options)
@click.argument('source_db_url', required=False)
@click.option(
    '--source-config',
    type=click.Path(exists=True),
    help='Path to config file with source DB connection',
)
@click.option(
    '--dry-run',
    is_flag=True,
    default=False,
    help='Show what would be done without executing',
)
@click.option(
    '--tables',
    help='Comma-separated tables to clone (default: all)',
)
@click.option(
    '--exclude-tables',
    help='Comma-separated tables to exclude',
)
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Skip confirmation prompt',
)
@click.pass_context
@cli_helper.process_standard_options
def clone_from(ctx, source_db_url, source_config, dry_run, tables, exclude_tables, force):
    """Clone all data from a source database (e.g., production).

    This command replaces ALL data in the local database with data from
    the source. Use with caution.

    SOURCE_DB_URL is the PostgreSQL connection URL for the source database.
    Alternatively, use --source-config to specify a config file.

    Examples:

        # Clone from production via direct URL
        haminfo db clone-from "postgresql://user:pass@prod-host/haminfo"

        # Clone using a config file for source credentials
        haminfo db clone-from --source-config /path/to/prod.conf

        # Clone only station and weather_station tables
        haminfo db clone-from "postgresql://..." --tables station,weather_station

        # Clone all except request logs
        haminfo db clone-from "postgresql://..." --exclude-tables request,wx_request

        # Dry run to see what would happen
        haminfo db clone-from "postgresql://..." --dry-run
    """
    console = click.get_current_context().obj or {}

    # Validate we have a source URL
    if not source_db_url and not source_config:
        raise click.UsageError(
            'Either SOURCE_DB_URL argument or --source-config option is required'
        )

    # Get source URL from config if provided
    if source_config:
        from oslo_config import cfg as oslo_cfg
        source_conf = oslo_cfg.ConfigOpts()
        source_conf(['--config-file', source_config])
        source_db_url = source_conf.database.connection

    # Parse table filters
    include_tables = tables.split(',') if tables else None
    exclude_tables_list = exclude_tables.split(',') if exclude_tables else None

    try:
        table_list = db_clone.get_table_list(include_tables, exclude_tables_list)
    except ValueError as e:
        raise click.UsageError(str(e))

    # Get local DB URL from config
    local_db_url = CONF.database.connection

    click.echo('Connecting to source database...', nl=False)
    if not db_clone.test_db_connection(source_db_url):
        click.echo(' FAILED')
        raise click.ClickException('Cannot connect to source database')
    click.echo(' OK')

    click.echo('Connecting to local database...', nl=False)
    if not db_clone.test_db_connection(local_db_url):
        click.echo(' FAILED')
        raise click.ClickException('Cannot connect to local database')
    click.echo(' OK')

    click.echo('')
    click.echo('WARNING: This will REPLACE all data in the local database.')
    click.echo(f'Tables to clone: {", ".join(table_list)}')
    click.echo('')

    if dry_run:
        click.echo('DRY RUN - no changes will be made')
        source_info = db_clone.parse_db_url(source_db_url)
        click.echo(f'Would connect to source: {source_info["host"]}:{source_info["port"]}/{source_info["database"]}')
        click.echo(f'Would clone tables: {", ".join(table_list)}')
        click.echo('Would truncate local tables and restore from source')
        return

    if not force:
        if not click.confirm('Continue?'):
            click.echo('Aborted.')
            return

    click.echo('Cloning data...')
    try:
        row_counts = db_clone.clone_database(
            source_url=source_db_url,
            target_url=local_db_url,
            tables=table_list,
        )
        click.echo('')
        for table, count in row_counts.items():
            click.echo(f'  {table}: {count:,} rows')
        click.echo('')
        click.echo('Clone completed successfully.')
    except Exception as e:
        LOG.exception('Clone failed')
        raise click.ClickException(f'Clone failed: {e}')
```

- [ ] **Step 2: Verify command shows in help**

Run: `cd /Users/I530566/devel/mine/hamradio/haminfo && python -m haminfo db --help`
Expected: `clone-from` appears in command list

- [ ] **Step 3: Commit**

```bash
git add haminfo/cmds/db.py
git commit -m "feat(db): add clone-from CLI command structure"
```

---

### Task 7: Implement clone_database Function

**Files:**
- Modify: `haminfo/db/clone.py`
- Modify: `tests/test_db_clone.py`

- [ ] **Step 1: Add integration test for clone_database**

Add to `tests/test_db_clone.py`:

```python
import subprocess


class TestCloneDatabase:
    """Test database cloning."""

    @patch('haminfo.db.clone.subprocess.Popen')
    @patch('haminfo.db.clone.create_engine')
    def test_clone_executes_pg_dump_psql_pipeline(self, mock_engine, mock_popen):
        """Clone executes pg_dump | psql pipeline."""
        from haminfo.db.clone import clone_database

        # Mock subprocess pipeline
        mock_pg_dump = MagicMock()
        mock_pg_dump.stdout = MagicMock()
        mock_pg_dump.wait.return_value = 0

        mock_psql = MagicMock()
        mock_psql.wait.return_value = 0

        mock_popen.side_effect = [mock_pg_dump, mock_psql]

        # Mock SQLAlchemy for truncate and count
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.return_value.connect.return_value = mock_conn

        result = clone_database(
            source_url='postgresql://user:pass@source/db',
            target_url='postgresql://user:pass@target/db',
            tables=['station'],
        )

        # Verify pg_dump was called
        assert mock_popen.call_count == 2
        pg_dump_call = mock_popen.call_args_list[0]
        assert 'pg_dump' in pg_dump_call[0][0][0]

        # Verify psql was called
        psql_call = mock_popen.call_args_list[1]
        assert 'psql' in psql_call[0][0][0]

    @patch('haminfo.db.clone.subprocess.Popen')
    @patch('haminfo.db.clone.create_engine')
    def test_clone_raises_on_pg_dump_failure(self, mock_engine, mock_popen):
        """Clone raises exception if pg_dump fails."""
        from haminfo.db.clone import clone_database, CloneError

        # Mock failed pg_dump
        mock_pg_dump = MagicMock()
        mock_pg_dump.stdout = MagicMock()
        mock_pg_dump.wait.return_value = 1
        mock_pg_dump.stderr = MagicMock()
        mock_pg_dump.stderr.read.return_value = b'pg_dump: error'

        mock_popen.return_value = mock_pg_dump

        # Mock SQLAlchemy
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.return_value.connect.return_value = mock_conn

        with pytest.raises(CloneError, match='pg_dump failed'):
            clone_database(
                source_url='postgresql://user:pass@source/db',
                target_url='postgresql://user:pass@target/db',
                tables=['station'],
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_clone.py::TestCloneDatabase -v`
Expected: FAIL with "ImportError" (function doesn't exist)

- [ ] **Step 3: Add clone_database function**

Add to `haminfo/db/clone.py`:

```python
import os
import subprocess


class CloneError(Exception):
    """Error during database clone operation."""
    pass


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
        raise CloneError(f'pg_dump failed with code {pg_dump_proc.returncode}: {stderr}')

    if psql_proc.returncode != 0:
        raise CloneError(f'psql failed with code {psql_proc.returncode}: {psql_stderr.decode()}')

    # Re-enable FK constraints and reset sequences
    with target_engine.connect() as conn:
        conn.execute(text('SET session_replication_role = DEFAULT'))
        conn.commit()

        # Reset sequences
        for table in tables:
            try:
                conn.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                        false
                    )
                """))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_clone.py::TestCloneDatabase -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/test_db_clone.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add haminfo/db/clone.py tests/test_db_clone.py
git commit -m "feat(db): add clone_database function with pg_dump|psql pipeline"
```

---

### Task 8: Add Missing Import and Final Cleanup

**Files:**
- Modify: `haminfo/db/clone.py`

- [ ] **Step 1: Verify all imports are correct**

Ensure `haminfo/db/clone.py` has these imports at the top:

```python
"""Database cloning utilities."""

import os
import subprocess
from urllib.parse import urlparse, unquote

from sqlalchemy import create_engine, text
```

- [ ] **Step 2: Run linter**

Run: `ruff check haminfo/db/clone.py`
Expected: No errors

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS (222+ tests)

- [ ] **Step 4: Commit any fixes**

```bash
git add haminfo/db/clone.py
git commit -m "chore(db): cleanup imports in clone module" --allow-empty
```

---

### Task 9: Update Dockerfile for postgresql-client

**Files:**
- Modify: `docker/Dockerfile`

- [ ] **Step 1: Check current Dockerfile**

Read `docker/Dockerfile` to understand current structure.

- [ ] **Step 2: Add postgresql-client installation**

Add after the base apt-get install section:

```dockerfile
# Install PostgreSQL client tools for db clone-from command
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile
git commit -m "chore(docker): add postgresql-client for db clone command"
```

---

### Task 10: Manual Integration Test

- [ ] **Step 1: Test CLI help**

Run: `python -m haminfo db clone-from --help`
Expected: Shows usage with all options

- [ ] **Step 2: Test dry-run mode**

Run: `python -m haminfo db clone-from "postgresql://haminfo:haminfo@cloud.hemna.com/haminfo" --dry-run --config haminfo.conf`
Expected: Shows "DRY RUN" output with tables that would be cloned

- [ ] **Step 3: Document results**

Note any issues found during manual testing for follow-up.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | URL parsing helper | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 2 | Connection test helper | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 3 | Table list helper | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 4 | pg_dump command builder | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 5 | psql command builder | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 6 | CLI command structure | `haminfo/cmds/db.py` |
| 7 | clone_database function | `haminfo/db/clone.py`, `tests/test_db_clone.py` |
| 8 | Import cleanup | `haminfo/db/clone.py` |
| 9 | Dockerfile update | `docker/Dockerfile` |
| 10 | Manual integration test | N/A |

**Total commits:** ~10 small, focused commits
