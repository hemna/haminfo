# Database Clone Command Design

**Date:** 2026-03-22  
**Status:** Approved  
**Author:** Claude + User

## Problem Statement

The development environment needs repeater data (and other tables) for testing, but:
- RepeaterBook API is rate-limited (1 request per 10 minutes)
- Dev shouldn't hit RepeaterBook unnecessarily
- Production already has ~40k repeaters that could be copied

## Solution

A new CLI command `haminfo db clone-from` that clones all data from a source PostgreSQL database (production) to the local database (dev) using `pg_dump` piped to `psql` for maximum efficiency.

## Requirements

1. Run on dev to pull data from production
2. Use direct PostgreSQL connection (via Tailscale VPN)
3. Replace all data in dev (truncate + insert for identical copy)
4. Clone all tables, not just station
5. Optimize for efficiency

## Command Interface

```bash
haminfo db clone-from <source_db_url> [OPTIONS]

# Example with direct URL:
haminfo db clone-from "postgresql://haminfo:password@cloud.hemna.com:5432/haminfo"

# Example with config file reference:
haminfo db clone-from --source-config /path/to/prod-haminfo.conf
```

### Options

| Option | Description |
|--------|-------------|
| `--source-config PATH` | Path to config file containing source DB connection |
| `--dry-run` | Show what would be done without executing |
| `--tables LIST` | Comma-separated list of tables to clone (default: all) |
| `--exclude-tables LIST` | Comma-separated list of tables to exclude |
| `--force` | Skip confirmation prompt |

### Tables

Default tables to clone (all application tables):
- `station` — Repeaters from RepeaterBook
- `weather_station` — Weather station metadata
- `weather_report` — Weather observations
- `aprs_packet` — APRS packet log
- `request` — API request log
- `wx_request` — Weather API request log

The `alembic_version` table is excluded (schema migrations are managed separately).

## Implementation

### File Location

`haminfo/cmds/db.py` — Extend existing `db` command group.

### Command Flow

```
1. Parse source connection (from arg or --source-config)
2. Test connectivity to both source and local DBs
3. Determine tables to clone (all or filtered)
4. Display confirmation prompt (unless --force)
5. Execute clone:
   a. Disable FK constraints: SET session_replication_role = replica
   b. Truncate local tables (in dependency order)
   c. Run: pg_dump --data-only ... | psql ...
   d. Re-enable FK constraints
   e. Reset sequences based on max IDs
6. Report row counts per table
```

### Core Implementation

```python
@db.command()
@click.argument('source_db_url', required=False)
@click.option('--source-config', help='Path to config file with source DB connection')
@click.option('--dry-run', is_flag=True, help='Show what would be done')
@click.option('--tables', help='Comma-separated tables to clone (default: all)')
@click.option('--exclude-tables', help='Comma-separated tables to exclude')
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
@cli_helper.process_standard_options
def clone_from(ctx, source_db_url, source_config, dry_run, tables, exclude_tables, force):
    """Clone all data from a source database (e.g., production).
    
    This command replaces ALL data in the local database with data from
    the source. Use with caution.
    
    Examples:
    
        # Clone from production via direct URL
        haminfo db clone-from "postgresql://user:pass@prod-host/haminfo"
        
        # Clone using a config file for source credentials
        haminfo db clone-from --source-config /path/to/prod.conf
        
        # Clone only station and weather_station tables
        haminfo db clone-from "postgresql://..." --tables station,weather_station
        
        # Clone all except request logs
        haminfo db clone-from "postgresql://..." --exclude-tables request,wx_request
    """
```

### Helper Functions

```python
def _parse_db_url(url: str) -> dict:
    """Parse PostgreSQL URL into components for pg_dump/psql."""
    # Returns: {'host': ..., 'port': ..., 'user': ..., 'password': ..., 'database': ...}

def _test_db_connection(url: str) -> bool:
    """Test if database is reachable."""

def _get_table_list(session, include: list | None, exclude: list | None) -> list:
    """Get list of tables to clone."""

def _run_pg_dump_restore(source: dict, target: dict, tables: list, dry_run: bool):
    """Execute pg_dump | psql pipeline."""

def _reset_sequences(session, tables: list):
    """Reset sequences to max(id) + 1 for each table."""

def _get_row_counts(session, tables: list) -> dict:
    """Get row counts for reporting."""
```

### pg_dump Command Construction

```python
pg_dump_cmd = [
    'pg_dump',
    '--data-only',           # Data only, no schema
    '--no-owner',            # Don't set ownership
    '--no-privileges',       # Don't set privileges
    '-h', source['host'],
    '-p', str(source['port']),
    '-U', source['user'],
    '-d', source['database'],
]

# Add table filters
for table in tables:
    pg_dump_cmd.extend(['--table', table])

# Set password via environment
env = os.environ.copy()
env['PGPASSWORD'] = source['password']
```

### psql Command Construction

```python
psql_cmd = [
    'psql',
    '-h', target['host'],
    '-p', str(target['port']),
    '-U', target['user'],
    '-d', target['database'],
    '--quiet',
    '--set', 'ON_ERROR_STOP=on',
]
```

### Pipeline Execution

```python
import subprocess

# Disable FK constraints first
session.execute(text("SET session_replication_role = replica"))

# Truncate tables
for table in reversed(tables):  # Reverse order for FK dependencies
    session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
session.commit()

# Run pg_dump | psql
pg_dump_proc = subprocess.Popen(
    pg_dump_cmd,
    stdout=subprocess.PIPE,
    env=env,
)
psql_proc = subprocess.Popen(
    psql_cmd,
    stdin=pg_dump_proc.stdout,
    env=env,
)
psql_proc.wait()

# Re-enable FK constraints
session.execute(text("SET session_replication_role = DEFAULT"))
```

## Error Handling

| Error | Handling |
|-------|----------|
| Source DB unreachable | Clear message: "Cannot connect to source database: {error}" |
| Local DB unreachable | Clear message: "Cannot connect to local database: {error}" |
| `pg_dump` not found | "pg_dump not found. Install postgresql-client package." |
| `psql` not found | "psql not found. Install postgresql-client package." |
| pg_dump fails | Report stderr, exit with error code |
| Partial failure | Report which tables succeeded/failed |

## Dependencies

### Required Binaries

- `pg_dump` — PostgreSQL dump utility
- `psql` — PostgreSQL client

### Dockerfile Change

Add `postgresql-client` to the Docker image:

```dockerfile
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
```

## Security Considerations

1. **Credentials not logged** — Source DB password passed via `PGPASSWORD` env var, never logged
2. **Read-only on source** — Command only reads from source, no write operations
3. **Confirmation prompt** — Prevents accidental data loss, bypassed only with `--force`
4. **Local only** — Designed to run on dev pulling from prod, not the reverse

## Usage Examples

### Basic clone (all tables)

```bash
# On dev machine
haminfo db clone-from "postgresql://haminfo:secret@cloud.hemna.com:5432/haminfo"
```

Output:
```
Connecting to source database... OK
Connecting to local database... OK

WARNING: This will REPLACE all data in the local database.
Tables to clone: station, weather_station, weather_report, aprs_packet, request, wx_request

Continue? [y/N]: y

Cloning data...
  station: 40,203 rows
  weather_station: 1,234 rows
  weather_report: 56,789 rows
  aprs_packet: 12,345 rows
  request: 8,901 rows
  wx_request: 2,345 rows

Clone completed successfully.
```

### Clone specific tables only

```bash
haminfo db clone-from "postgresql://..." --tables station,weather_station
```

### Clone with exclusions

```bash
haminfo db clone-from "postgresql://..." --exclude-tables request,wx_request,aprs_packet
```

### Dry run

```bash
haminfo db clone-from "postgresql://..." --dry-run
```

Output:
```
DRY RUN - no changes will be made

Would connect to source: cloud.hemna.com:5432/haminfo
Would clone tables: station, weather_station, weather_report, aprs_packet, request, wx_request
Would truncate local tables and restore from source
```

## Testing

### Unit Tests

- `test_parse_db_url()` — URL parsing
- `test_get_table_list()` — Include/exclude filtering
- `test_clone_dry_run()` — Dry run doesn't modify anything

### Integration Tests

- Test with two local PostgreSQL instances
- Verify row counts match after clone
- Verify sequences are reset correctly

## Future Enhancements (Not in Scope)

- Progress bar during transfer
- Compression for large transfers
- Incremental sync (only changed rows)
- SSH tunnel support built-in
