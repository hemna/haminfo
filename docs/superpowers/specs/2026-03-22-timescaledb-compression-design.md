# TimescaleDB Integration for Weather Report Compression

## Overview

Integrate TimescaleDB to compress historical weather report data, reducing storage from ~3.5 GB/month to ~1 GB/month while maintaining full query capability.

## Problem Statement

- **Current storage**: 3.5 GB for 31 days of weather reports (7.3M rows)
- **Projected annual**: ~42 GB/year uncompressed
- **Growth rate**: ~236K new reports/day from 12,400 weather stations across 97 countries

## Solution: TimescaleDB Hypertables with Compression

### Why TimescaleDB?

1. **Transparent compression** - Queries work without code changes
2. **Time-series optimized** - Built for exactly this use case
3. **PostgreSQL native** - Just an extension, minimal changes needed
4. **Automatic policies** - Set once, runs automatically
5. **Proven at scale** - Handles billions of rows

### Expected Results

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Monthly storage | 3.5 GB | ~1 GB | 73-76% |
| Annual storage | 42 GB | ~12 GB | ~30 GB |
| Query performance | Baseline | Same or better* | - |

*Recent data queries unchanged; historical queries slightly slower but acceptable

## Technical Design

### 1. Docker Image Change

Replace PostGIS image with TimescaleDB image that includes PostGIS:

```yaml
# Before
image: postgis/postgis:15-3.4

# After  
image: timescale/timescaledb-ha:pg15-latest
# Or: timescale/timescaledb:latest-pg15 (smaller, no HA features)
```

### 2. Database Migration Steps

#### Step 1: Enable Extension
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

#### Step 2: Convert weather_report to Hypertable

**Important**: Table must have data migrated carefully. TimescaleDB requires:
- A time column (we have `time`)
- Primary key must include the time column

```sql
-- Backup existing data
CREATE TABLE weather_report_backup AS SELECT * FROM weather_report;

-- Drop existing constraints that conflict
ALTER TABLE weather_report DROP CONSTRAINT IF EXISTS weather_report_pkey;

-- Create new primary key including time
ALTER TABLE weather_report ADD PRIMARY KEY (id, time);

-- Convert to hypertable with weekly chunks
SELECT create_hypertable('weather_report', 'time', 
    chunk_time_interval => INTERVAL '7 days',
    migrate_data => true
);
```

#### Step 3: Add Compression Policy

```sql
-- Enable compression on the hypertable
ALTER TABLE weather_report SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'weather_station_id',
    timescaledb.compress_orderby = 'time DESC'
);

-- Compress chunks older than 30 days automatically
SELECT add_compression_policy('weather_report', INTERVAL '30 days');
```

#### Step 4: Optional - Add Retention Policy

```sql
-- Automatically drop data older than 1 year (optional)
SELECT add_retention_policy('weather_report', INTERVAL '1 year');
```

### 3. Compression Settings Rationale

| Setting | Value | Reason |
|---------|-------|--------|
| `chunk_time_interval` | 7 days | Balance between chunk count and compression efficiency |
| `compress_segmentby` | `weather_station_id` | Queries often filter by station; improves query performance |
| `compress_orderby` | `time DESC` | Most queries want recent data first |
| `compression_policy` | 30 days | Keep recent data fast, compress older data |

### 4. Index Strategy

TimescaleDB automatically creates time-based indexes. We should keep:

```sql
-- These existing indexes remain useful
CREATE INDEX IF NOT EXISTS ix_weather_report_station_time 
    ON weather_report (weather_station_id, time DESC);
    
-- TimescaleDB will create chunk-level indexes automatically
```

### 5. Monitoring Compression

```sql
-- Check compression status
SELECT 
    chunk_schema,
    chunk_name,
    compression_status,
    pg_size_pretty(before_compression_total_bytes) as before,
    pg_size_pretty(after_compression_total_bytes) as after
FROM chunk_compression_stats('weather_report');

-- Overall compression ratio
SELECT 
    pg_size_pretty(SUM(before_compression_total_bytes)) as total_before,
    pg_size_pretty(SUM(after_compression_total_bytes)) as total_after,
    ROUND(100 - (SUM(after_compression_total_bytes)::numeric / 
                  SUM(before_compression_total_bytes)::numeric * 100), 1) as compression_pct
FROM chunk_compression_stats('weather_report');
```

## Schema Changes

### weather_report table

No column changes needed. Only structural changes:

1. Primary key changes from `(id)` to `(id, time)` - required for hypertable
2. Table becomes a hypertable (transparent to application)

### Foreign Keys

The existing foreign key `weather_report.weather_station_id -> weather_station.id` remains unchanged.

## Application Impact

### No Code Changes Required

- SQLAlchemy queries work unchanged
- Flask API unchanged
- MCP server unchanged
- All existing queries continue to work

### Performance Considerations

| Query Type | Impact |
|------------|--------|
| Recent data (< 30 days) | No change |
| Historical aggregations | May be faster (compressed reads) |
| Point queries on old data | Slightly slower (decompression) |
| Inserts | No change (goes to uncompressed chunks) |

## Migration Plan

### Phase 1: Development Testing
1. Update docker-compose.yml to use TimescaleDB image
2. Create Alembic migrations
3. Test on dev environment with cloned data
4. Verify all queries work correctly

### Phase 2: Production Migration
1. Schedule maintenance window (low traffic period)
2. Backup production database
3. Run migrations
4. Verify data integrity
5. Monitor compression progress

### Rollback Plan

If issues occur:
1. TimescaleDB hypertables can be converted back to regular tables
2. Backup ensures data safety
3. Docker image can be reverted

## Files to Modify

1. `docker/docker-compose.yml` - Change PostgreSQL image
2. `haminfo/db/alembic/versions/xxx_add_timescaledb.py` - New migration
3. `haminfo/db/alembic/versions/xxx_convert_hypertable.py` - Convert table
4. `README.md` - Document TimescaleDB requirement

## Testing Checklist

- [ ] Extension creates successfully
- [ ] Hypertable conversion completes
- [ ] Existing data preserved
- [ ] All API endpoints work
- [ ] MCP queries work
- [ ] Compression policy activates
- [ ] New inserts work correctly
- [ ] Foreign key constraints work

## References

- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Compression Documentation](https://docs.timescale.com/use-timescale/latest/compression/)
- [Migration Guide](https://docs.timescale.com/migrate/latest/)
