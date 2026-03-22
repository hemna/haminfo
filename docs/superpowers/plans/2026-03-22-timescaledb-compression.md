# Implementation Plan: TimescaleDB Compression for Weather Reports

**Spec**: [2026-03-22-timescaledb-compression-design.md](../specs/2026-03-22-timescaledb-compression-design.md)
**Created**: 2026-03-22
**Status**: Ready for implementation

## Overview

Add TimescaleDB compression to reduce weather_report storage by ~75% (3.5 GB → ~1 GB per month).

## Implementation Tasks

### Task 1: Update Docker Image
**File**: `docker/docker-compose.yml`
**Effort**: Small
**Risk**: Low

Change the PostgreSQL image from PostGIS to TimescaleDB with PostGIS:

```yaml
haminfo_db:
  image: timescale/timescaledb-ha:pg15-latest
  # Or for smaller image without HA:
  # image: timescale/timescaledb:latest-pg15-postgis
```

**Verification**:
```bash
docker compose pull haminfo_db
docker compose up -d haminfo_db
docker exec haminfo_db psql -U haminfo -c "SELECT default_version, installed_version FROM pg_available_extensions WHERE name = 'timescaledb';"
```

---

### Task 2: Create Alembic Migration - Enable Extension
**File**: `haminfo/db/alembic/versions/xxxx_add_timescaledb_extension.py`
**Effort**: Small
**Risk**: Low

```python
"""Add TimescaleDB extension

Revision ID: xxxx
Revises: previous_revision
Create Date: 2026-03-22
"""
from alembic import op

revision = 'xxxx_timescaledb'
down_revision = 'previous'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

def downgrade():
    # Note: Cannot easily remove timescaledb if hypertables exist
    pass
```

**Verification**:
```bash
haminfo db schema-upgrade
docker exec haminfo_db psql -U haminfo -c "\dx timescaledb"
```

---

### Task 3: Create Alembic Migration - Convert to Hypertable
**File**: `haminfo/db/alembic/versions/xxxx_convert_weather_report_hypertable.py`
**Effort**: Medium
**Risk**: Medium (data migration)

```python
"""Convert weather_report to TimescaleDB hypertable

Revision ID: xxxx
Revises: xxxx_timescaledb
Create Date: 2026-03-22
"""
from alembic import op

revision = 'xxxx_hypertable'
down_revision = 'xxxx_timescaledb'
branch_labels = None
depends_on = None

def upgrade():
    # Step 1: Drop existing primary key
    op.execute("""
        ALTER TABLE weather_report 
        DROP CONSTRAINT IF EXISTS weather_report_pkey
    """)
    
    # Step 2: Add composite primary key including time column
    op.execute("""
        ALTER TABLE weather_report 
        ADD PRIMARY KEY (id, time)
    """)
    
    # Step 3: Convert to hypertable
    op.execute("""
        SELECT create_hypertable(
            'weather_report', 
            'time',
            chunk_time_interval => INTERVAL '7 days',
            migrate_data => true,
            if_not_exists => true
        )
    """)
    
    # Step 4: Enable compression
    op.execute("""
        ALTER TABLE weather_report SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'weather_station_id',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)
    
    # Step 5: Add compression policy (compress data older than 30 days)
    op.execute("""
        SELECT add_compression_policy(
            'weather_report', 
            INTERVAL '30 days',
            if_not_exists => true
        )
    """)

def downgrade():
    # Remove compression policy
    op.execute("""
        SELECT remove_compression_policy('weather_report', if_exists => true)
    """)
    
    # Decompress all chunks
    op.execute("""
        SELECT decompress_chunk(c, if_compressed => true)
        FROM show_chunks('weather_report') c
    """)
    
    # Note: Converting back from hypertable is complex
    # Would need to: create new table, copy data, drop hypertable, rename
```

**Verification**:
```sql
-- Check hypertable created
SELECT * FROM timescaledb_information.hypertables 
WHERE hypertable_name = 'weather_report';

-- Check compression enabled
SELECT * FROM timescaledb_information.compression_settings
WHERE hypertable_name = 'weather_report';

-- Check compression policy
SELECT * FROM timescaledb_information.jobs
WHERE hypertable_name = 'weather_report';
```

---

### Task 4: Add Compression Monitoring Query to MCP
**File**: `haminfo/cmds/mcp.py`
**Effort**: Small
**Risk**: Low

Add a new MCP tool for monitoring compression status:

```python
@mcp.tool()
def get_compression_stats() -> str:
    """Get TimescaleDB compression statistics for weather_report table."""
    # Query compression stats
    # Return formatted results
```

---

### Task 5: Update Docker Compose (Production)
**File**: `docker/docker-compose.yml` (on production server)
**Effort**: Small
**Risk**: Medium (production change)

Update production docker-compose.yml to use TimescaleDB image.

---

### Task 6: Manual Compression of Existing Data
**Effort**: Small
**Risk**: Low

After migration, manually compress existing old chunks:

```sql
-- Compress all chunks older than 30 days immediately
SELECT compress_chunk(c)
FROM show_chunks('weather_report', older_than => INTERVAL '30 days') c;

-- Check results
SELECT 
    pg_size_pretty(SUM(before_compression_total_bytes)) as before,
    pg_size_pretty(SUM(after_compression_total_bytes)) as after,
    ROUND(100 - (SUM(after_compression_total_bytes)::numeric / 
                  NULLIF(SUM(before_compression_total_bytes)::numeric, 0) * 100), 1) as savings_pct
FROM chunk_compression_stats('weather_report');
```

---

## Execution Order

### Phase 1: Development (docker-haminfo)

1. [ ] Update docker-compose.yml with TimescaleDB image
2. [ ] Restart database container
3. [ ] Run `haminfo db schema-upgrade` to apply migrations
4. [ ] Verify hypertable created
5. [ ] Run manual compression on existing data
6. [ ] Test all API endpoints
7. [ ] Test MCP queries
8. [ ] Verify new weather reports are inserted correctly

### Phase 2: Production (cloud.hemna.com)

1. [ ] Backup production database
2. [ ] Update docker-compose.yml
3. [ ] Restart database container
4. [ ] Run schema upgrade
5. [ ] Run manual compression
6. [ ] Monitor for 24 hours
7. [ ] Verify compression policy running automatically

---

## Rollback Procedure

If issues occur:

1. Stop application containers
2. Restore database from backup
3. Revert docker-compose.yml to PostGIS image
4. Restart containers

---

## Success Criteria

- [ ] TimescaleDB extension installed
- [ ] weather_report converted to hypertable
- [ ] Compression policy active
- [ ] Storage reduced by >70%
- [ ] All existing queries work
- [ ] New inserts work correctly
- [ ] MCP queries work
- [ ] No application errors

---

## Estimated Timeline

| Task | Duration |
|------|----------|
| Docker image update | 5 min |
| Create migrations | 30 min |
| Test on dev | 1 hour |
| Deploy to production | 30 min |
| Monitor & verify | 24 hours |
| **Total** | **~2 hours active + monitoring** |
