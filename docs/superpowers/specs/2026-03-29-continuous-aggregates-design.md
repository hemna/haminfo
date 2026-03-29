# Continuous Aggregates for Dashboard Performance

**Date**: 2026-03-29
**Status**: Approved
**Author**: Claude

## Problem Statement

Dashboard queries are slow due to scanning 7+ million rows for 24-hour aggregations:

| Query | Current Time | Issue |
|-------|-------------|-------|
| COUNT packets (24h) | 940ms | Scans entire 24h window |
| COUNT DISTINCT stations | 14.6s | Very expensive distinct |
| Top stations GROUP BY | 2.4s | Aggregation overhead |
| Hourly distribution | ~1s | GROUP BY hour |
| Country breakdown | ~2s | GROUP BY prefix |

The `aprs_packet` table has ~25 million rows, with ~7.4 million in the last 24 hours.

## Solution: TimescaleDB Continuous Aggregates

Use TimescaleDB continuous aggregates to pre-compute dashboard statistics. These are materialized views that auto-refresh incrementally.

## Prerequisites

### Convert aprs_packet to Hypertable

**Critical**: Continuous aggregates can only be created on TimescaleDB hypertables. The `aprs_packet` table must be converted first.

```sql
-- Create hypertable from existing table
-- This requires recreating the table since we need a different primary key structure
-- The (from_call, timestamp) composite key enables efficient time-series queries

-- Migration will:
-- 1. Create new table with composite primary key (from_call, timestamp)
-- 2. Convert to hypertable partitioned by timestamp
-- 3. Add compression policy for older chunks

SELECT create_hypertable('aprs_packet', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => true);

-- Enable compression on chunks older than 7 days
ALTER TABLE aprs_packet SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'from_call',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('aprs_packet', INTERVAL '7 days');
```

**Note**: The model already defines `(from_call, timestamp)` as the composite primary key (see `haminfo/db/models/aprs_packet.py:40-46`), but the existing migration doesn't implement this. A new migration is needed.

## Design

### Aggregate 1: Hourly Stats

Pre-computes basic stats per hour for flexible time-window queries.

```sql
CREATE MATERIALIZED VIEW aprs_stats_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    count(*) AS packet_count,
    count(DISTINCT from_call) AS unique_stations,
    count(DISTINCT substring(from_call, 1, 2)) AS unique_prefixes
FROM aprs_packet
GROUP BY bucket
WITH NO DATA;

-- Refresh policy: every 5 minutes, update last 2 hours
SELECT add_continuous_aggregate_policy('aprs_stats_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Retention: 30 days
SELECT add_retention_policy('aprs_stats_hourly', INTERVAL '30 days');
```

**Satisfies**:
- `get_dashboard_stats()` - total_packets_24h, unique_stations (approximate), countries
- `get_hourly_distribution()` - hourly packet counts

**Note on COUNT DISTINCT**: Summing hourly unique counts across 24 hours will overcount (same station appearing in multiple hours counted multiple times). This is acceptable per user requirements.

### Aggregate 2: Station Stats (Per Hour)

Pre-computes per-station packet counts for top stations query.

```sql
CREATE MATERIALIZED VIEW aprs_station_stats_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    from_call,
    count(*) AS packet_count
FROM aprs_packet
GROUP BY bucket, from_call
WITH NO DATA;

-- Refresh policy: every 5 minutes, update last 2 hours
SELECT add_continuous_aggregate_policy('aprs_station_stats_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Retention: 7 days (per user requirement)
SELECT add_retention_policy('aprs_station_stats_hourly', INTERVAL '7 days');
```

**Satisfies**:
- `get_top_stations()` - top N stations by packet count

### Aggregate 3: Prefix Stats (Per Hour)

Pre-computes packet counts by callsign prefix for country breakdown.

```sql
CREATE MATERIALIZED VIEW aprs_prefix_stats_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    substring(from_call, 1, 2) AS prefix,
    count(*) AS packet_count
FROM aprs_packet
GROUP BY bucket, prefix
WITH NO DATA;

-- Refresh policy: every 5 minutes, update last 2 hours
SELECT add_continuous_aggregate_policy('aprs_prefix_stats_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Retention: 30 days
SELECT add_retention_policy('aprs_prefix_stats_hourly', INTERVAL '30 days');
```

**Satisfies**:
- `get_country_breakdown()` - packet counts by country

## Dashboard Query Changes

### get_dashboard_stats()

**Before** (slow - scans raw table):
```python
total_packets = session.query(func.count(APRSPacket.from_call))
    .filter(APRSPacket.received_at >= last_24h).scalar()
unique_stations = session.query(func.count(distinct(APRSPacket.from_call)))
    .filter(APRSPacket.received_at >= last_24h).scalar()
```

**After** (fast - queries aggregate):
```python
result = session.execute(text("""
    SELECT 
        COALESCE(SUM(packet_count), 0) as total_packets,
        COALESCE(SUM(unique_stations), 0) as unique_stations,
        COALESCE(SUM(unique_prefixes), 0) as unique_prefixes
    FROM aprs_stats_hourly
    WHERE bucket >= NOW() - INTERVAL '24 hours'
""")).fetchone()
```

### get_top_stations()

**Before**:
```python
results = session.query(APRSPacket.from_call, func.count(...))
    .filter(APRSPacket.received_at >= last_24h)
    .group_by(APRSPacket.from_call)
    .order_by(func.count(...).desc())
    .limit(limit).all()
```

**After**:
```python
results = session.execute(text("""
    SELECT from_call, SUM(packet_count) as total_count
    FROM aprs_station_stats_hourly
    WHERE bucket >= NOW() - INTERVAL '24 hours'
    GROUP BY from_call
    ORDER BY total_count DESC
    LIMIT :limit
"""), {'limit': limit}).fetchall()
```

### get_hourly_distribution()

**Before**:
```python
hourly_counts = session.query(
    func.extract('hour', APRSPacket.received_at),
    func.count(APRSPacket.from_call))
    .filter(APRSPacket.received_at >= last_24h)
    .group_by(...).all()
```

**After**:
```python
hourly_counts = session.execute(text("""
    SELECT EXTRACT(hour FROM bucket) as hour, SUM(packet_count) as count
    FROM aprs_stats_hourly
    WHERE bucket >= NOW() - INTERVAL '24 hours'
    GROUP BY EXTRACT(hour FROM bucket)
""")).fetchall()
```

### get_country_breakdown()

**Before**:
```python
prefix_counts = session.query(
    func.substring(APRSPacket.from_call, 1, 2),
    func.count(APRSPacket.from_call))
    .filter(APRSPacket.received_at >= last_24h)
    .group_by(...).all()
```

**After**:
```python
prefix_counts = session.execute(text("""
    SELECT prefix, SUM(packet_count) as count
    FROM aprs_prefix_stats_hourly
    WHERE bucket >= NOW() - INTERVAL '24 hours'
    GROUP BY prefix
""")).fetchall()
```

## Expected Performance

| Query | Current | After Aggregates | Improvement |
|-------|---------|------------------|-------------|
| Dashboard stats | 14.6s | <100ms | ~150x |
| Top stations | 2.4s | <200ms | ~12x |
| Hourly distribution | ~1s | <50ms | ~20x |
| Country breakdown | ~2s | <100ms | ~20x |

## Storage Overhead

| Aggregate | Estimated Rows | Retention |
|-----------|---------------|-----------|
| aprs_stats_hourly | ~720 (24×30) | 30 days |
| aprs_station_stats_hourly | ~6.7M (40K×24×7) | 7 days |
| aprs_prefix_stats_hourly | ~144K (200×24×30) | 30 days |

The station stats aggregate is the largest but 7-day retention keeps it manageable.

## Initial Data Population

After creating aggregates, backfill historical data:

```sql
CALL refresh_continuous_aggregate('aprs_stats_hourly', 
    NOW() - INTERVAL '30 days', NOW());
CALL refresh_continuous_aggregate('aprs_station_stats_hourly', 
    NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('aprs_prefix_stats_hourly', 
    NOW() - INTERVAL '30 days', NOW());
```

This may take several minutes for the initial backfill.

## Implementation Steps

1. **Create migration to convert aprs_packet to hypertable** (prerequisite)
2. **Run hypertable migration** on production database
3. **Create migration** for continuous aggregates (SQL)
4. **Run aggregates migration** on production database
5. **Backfill** historical data
6. **Update dashboard queries** to use aggregates
7. **Test** performance improvements
8. **Deploy** updated dashboard code

## Rollback Plan

If issues arise:
```sql
DROP MATERIALIZED VIEW aprs_stats_hourly CASCADE;
DROP MATERIALIZED VIEW aprs_station_stats_hourly CASCADE;
DROP MATERIALIZED VIEW aprs_prefix_stats_hourly CASCADE;
```

Dashboard code can fall back to raw table queries (existing code).

## Trade-offs

**Pros**:
- Dramatic query performance improvement (10-150x)
- Automatic incremental refresh
- No changes to data ingestion pipeline
- Native TimescaleDB feature (well-supported)

**Cons**:
- Approximate unique station counts (acceptable)
- 5-minute data staleness (acceptable, matches existing cache TTL)
- Storage overhead for station stats aggregate (~6.7M rows)
- Additional DB maintenance (retention policies)
