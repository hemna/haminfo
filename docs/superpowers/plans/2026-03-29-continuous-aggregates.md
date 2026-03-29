# Continuous Aggregates Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement TimescaleDB continuous aggregates to improve dashboard query performance from 14.6s to <100ms.

**Architecture:** Create three continuous aggregates (hourly stats, station stats, prefix stats) on the aprs_packet hypertable. Update dashboard queries to read from aggregates instead of raw table. Keep fallback queries for resilience.

**Tech Stack:** TimescaleDB, PostgreSQL, Alembic, SQLAlchemy, Python

**Prerequisites verified:** 
- `aprs_packet` is already a hypertable in production (5 chunks, compression enabled)
- `weather_report` is already a hypertable in production (5 chunks, compression enabled)

---

## ~~Chunk 1: Convert aprs_packet to Hypertable~~ SKIP - Already Done

**VERIFIED:** Production database already has `aprs_packet` as a hypertable:
```
 hypertable_schema | hypertable_name | num_chunks | compression_enabled 
-------------------+-----------------+------------+---------------------
 public            | aprs_packet     |          5 | t
```

No migration needed. Proceed to Chunk 2.

---

## Chunk 2: Create Continuous Aggregates Migration

### Task 1: Create Migration for Continuous Aggregates

**Files:**
- Create: `haminfo/db/versions/d5e6f7a8b9c0_create_continuous_aggregates.py`

- [ ] **Step 1: Create migration file**

```python
"""Create continuous aggregates for dashboard performance.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-03-29

Creates three continuous aggregates:
1. aprs_stats_hourly - basic stats per hour (packet count, unique stations, prefixes)
2. aprs_station_stats_hourly - per-station packet counts
3. aprs_prefix_stats_hourly - per-prefix packet counts

See docs/superpowers/specs/2026-03-29-continuous-aggregates-design.md

IMPORTANT: Requires aprs_packet to be a hypertable first (already done in production).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # Aggregate 1: Hourly Stats
    # Pre-computes basic stats per hour for flexible time-window queries
    op.execute("""
        CREATE MATERIALIZED VIEW aprs_stats_hourly
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('1 hour', timestamp) AS bucket,
            count(*) AS packet_count,
            count(DISTINCT from_call) AS unique_stations,
            count(DISTINCT substring(from_call, 1, 2)) AS unique_prefixes
        FROM aprs_packet
        GROUP BY bucket
        WITH NO DATA
    """)

    # Refresh policy: every 5 minutes, update last 2 hours
    op.execute("""
        SELECT add_continuous_aggregate_policy('aprs_stats_hourly',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes')
    """)

    # Retention: 30 days
    op.execute("""
        SELECT add_retention_policy('aprs_stats_hourly', INTERVAL '30 days')
    """)

    # Aggregate 2: Station Stats (Per Hour)
    # Pre-computes per-station packet counts for top stations query
    op.execute("""
        CREATE MATERIALIZED VIEW aprs_station_stats_hourly
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('1 hour', timestamp) AS bucket,
            from_call,
            count(*) AS packet_count
        FROM aprs_packet
        GROUP BY bucket, from_call
        WITH NO DATA
    """)

    # Refresh policy: every 5 minutes, update last 2 hours
    op.execute("""
        SELECT add_continuous_aggregate_policy('aprs_station_stats_hourly',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes')
    """)

    # Retention: 7 days
    op.execute("""
        SELECT add_retention_policy('aprs_station_stats_hourly', INTERVAL '7 days')
    """)

    # Aggregate 3: Prefix Stats (Per Hour)
    # Pre-computes packet counts by callsign prefix for country breakdown
    op.execute("""
        CREATE MATERIALIZED VIEW aprs_prefix_stats_hourly
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('1 hour', timestamp) AS bucket,
            substring(from_call, 1, 2) AS prefix,
            count(*) AS packet_count
        FROM aprs_packet
        GROUP BY bucket, prefix
        WITH NO DATA
    """)

    # Refresh policy: every 5 minutes, update last 2 hours
    op.execute("""
        SELECT add_continuous_aggregate_policy('aprs_prefix_stats_hourly',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes')
    """)

    # Retention: 30 days
    op.execute("""
        SELECT add_retention_policy('aprs_prefix_stats_hourly', INTERVAL '30 days')
    """)


def downgrade():
    # Remove in reverse order
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aprs_prefix_stats_hourly CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aprs_station_stats_hourly CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aprs_stats_hourly CASCADE")
```

- [ ] **Step 2: Verify migration syntax**

Run: `cd haminfo/db && python -c "from versions.d5e6f7a8b9c0_create_continuous_aggregates import upgrade, downgrade; print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit migration**

```bash
git add haminfo/db/versions/d5e6f7a8b9c0_create_continuous_aggregates.py
git commit -m "migration: create continuous aggregates for dashboard"
```

---

## Chunk 3: Update Dashboard Queries

### Task 3: Add Aggregate Query Functions

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/queries.py`

- [ ] **Step 1: Add USE_AGGREGATES feature flag**

Add near top of file after imports:

```python
# Feature flag for continuous aggregates
# Set to True after migrations are run and aggregates are populated
USE_CONTINUOUS_AGGREGATES = False
```

- [ ] **Step 2: Update get_dashboard_stats() to use aggregates**

Replace the function with:

```python
@cached('dashboard:stats', ttl=300)
def get_dashboard_stats(session: Session) -> dict[str, Any]:
    """Get summary statistics for dashboard.

    Args:
        session: Database session.

    Returns:
        Dict with total_packets_24h, unique_stations, countries, weather_stations.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_dashboard_stats_from_aggregates(session)
    return _get_dashboard_stats_from_raw(session)


def _get_dashboard_stats_from_aggregates(session: Session) -> dict[str, Any]:
    """Get dashboard stats from continuous aggregates (fast)."""
    result = session.execute(text("""
        SELECT 
            COALESCE(SUM(packet_count), 0) as total_packets,
            COALESCE(SUM(unique_stations), 0) as unique_stations,
            COALESCE(SUM(unique_prefixes), 0) as unique_prefixes
        FROM aprs_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
    """)).fetchone()

    # Weather stations still from regular query
    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0

    return {
        'total_packets_24h': result.total_packets if result else 0,
        'unique_stations': result.unique_stations if result else 0,
        'countries': result.unique_prefixes if result else 0,
        'weather_stations': weather_stations,
    }


def _get_dashboard_stats_from_raw(session: Session) -> dict[str, Any]:
    """Get dashboard stats from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    total_packets = (
        session.query(func.count(APRSPacket.from_call))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    unique_stations = (
        session.query(func.count(distinct(APRSPacket.from_call)))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    countries = (
        session.query(func.count(distinct(func.substring(APRSPacket.from_call, 1, 2))))
        .filter(APRSPacket.received_at >= last_24h)
        .scalar()
        or 0
    )

    weather_stations = session.query(func.count(WeatherStation.id)).scalar() or 0

    return {
        'total_packets_24h': total_packets,
        'unique_stations': unique_stations,
        'countries': countries,
        'weather_stations': weather_stations,
    }
```

- [ ] **Step 3: Update get_top_stations() to use aggregates**

Replace the function with:

```python
@cached('dashboard:top_stations:{limit}')
def get_top_stations(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get top stations by packet count in the last 24 hours.

    Args:
        session: Database session.
        limit: Maximum number of stations to return.

    Returns:
        List of dicts with callsign, count, and country info.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_top_stations_from_aggregates(session, limit)
    return _get_top_stations_from_raw(session, limit)


def _get_top_stations_from_aggregates(session: Session, limit: int) -> list[dict[str, Any]]:
    """Get top stations from continuous aggregates (fast)."""
    results = session.execute(text("""
        SELECT from_call, SUM(packet_count) as total_count
        FROM aprs_station_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY from_call
        ORDER BY total_count DESC
        LIMIT :limit
    """), {'limit': limit}).fetchall()

    stations = []
    for row in results:
        country_info = get_country_from_callsign(row.from_call)
        stations.append({
            'callsign': row.from_call,
            'count': int(row.total_count),
            'country_code': country_info[0] if country_info else None,
            'country_name': country_info[1] if country_info else None,
        })

    return stations


def _get_top_stations_from_raw(session: Session, limit: int) -> list[dict[str, Any]]:
    """Get top stations from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    results = (
        session.query(
            APRSPacket.from_call,
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(APRSPacket.from_call)
        .order_by(func.count(APRSPacket.from_call).desc())
        .limit(limit)
        .all()
    )

    stations = []
    for callsign, count in results:
        country_info = get_country_from_callsign(callsign)
        stations.append({
            'callsign': callsign,
            'count': count,
            'country_code': country_info[0] if country_info else None,
            'country_name': country_info[1] if country_info else None,
        })

    return stations
```

- [ ] **Step 4: Update get_hourly_distribution() to use aggregates**

Replace the function with:

```python
@cached('dashboard:hourly', ttl=300)
def get_hourly_distribution(session: Session) -> dict[str, list]:
    """Get packet count distribution by hour of day.

    Args:
        session: Database session.

    Returns:
        Dict with 'labels' (hour strings) and 'values' (counts) arrays.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_hourly_distribution_from_aggregates(session)
    return _get_hourly_distribution_from_raw(session)


def _get_hourly_distribution_from_aggregates(session: Session) -> dict[str, list]:
    """Get hourly distribution from continuous aggregates (fast)."""
    hourly_counts = session.execute(text("""
        SELECT EXTRACT(hour FROM bucket)::integer as hour, SUM(packet_count) as count
        FROM aprs_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY EXTRACT(hour FROM bucket)
    """)).fetchall()

    hour_map = {}
    for row in hourly_counts:
        if row.hour is not None:
            hour_map[row.hour] = int(row.count)

    labels = [f'{h:02d}:00' for h in range(24)]
    values = [hour_map.get(h, 0) for h in range(24)]

    return {'labels': labels, 'values': values}


def _get_hourly_distribution_from_raw(session: Session) -> dict[str, list]:
    """Get hourly distribution from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    dialect = session.bind.dialect.name if session.bind else 'postgresql'

    if dialect == 'sqlite':
        hour_expr = func.strftime('%H', APRSPacket.received_at)
    else:
        hour_expr = func.extract('hour', APRSPacket.received_at)

    hourly_counts = (
        session.query(
            hour_expr.label('hour'),
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(hour_expr)
        .all()
    )

    hour_map = {}
    for hour, count in hourly_counts:
        if hour is not None:
            hour_map[int(hour)] = count

    labels = [f'{h:02d}:00' for h in range(24)]
    values = [hour_map.get(h, 0) for h in range(24)]

    return {'labels': labels, 'values': values}
```

- [ ] **Step 5: Update get_country_breakdown() to use aggregates**

Replace the function with:

```python
@cached('dashboard:countries:{limit}')
def get_country_breakdown(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Get packet count breakdown by country.

    Args:
        session: Database session.
        limit: Maximum number of countries to return.

    Returns:
        List of dicts with country_code, country_name, count.
    """
    if USE_CONTINUOUS_AGGREGATES:
        return _get_country_breakdown_from_aggregates(session, limit)
    return _get_country_breakdown_from_raw(session, limit)


def _get_country_breakdown_from_aggregates(session: Session, limit: int) -> list[dict[str, Any]]:
    """Get country breakdown from continuous aggregates (fast)."""
    prefix_counts = session.execute(text("""
        SELECT prefix, SUM(packet_count) as count
        FROM aprs_prefix_stats_hourly
        WHERE bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY prefix
    """)).fetchall()

    country_counts: dict[tuple[str, str], int] = {}
    unknown_count = 0

    for row in prefix_counts:
        prefix = row.prefix
        count = int(row.count)
        if not prefix:
            unknown_count += count
            continue
        country_info = None
        if len(prefix) >= 2:
            country_info = CALLSIGN_PREFIXES.get(prefix[:2])
        if not country_info and len(prefix) >= 1:
            country_info = CALLSIGN_PREFIXES.get(prefix[:1])

        if country_info:
            key = country_info
            country_counts[key] = country_counts.get(key, 0) + count
        else:
            unknown_count += count

    result = [
        {'country_code': code, 'country_name': name, 'count': cnt}
        for (code, name), cnt in country_counts.items()
    ]
    result.sort(key=lambda x: x['count'], reverse=True)

    return result[:limit]


def _get_country_breakdown_from_raw(session: Session, limit: int) -> list[dict[str, Any]]:
    """Get country breakdown from raw table (slow fallback)."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    prefix_counts = (
        session.query(
            func.substring(APRSPacket.from_call, 1, 2).label('prefix'),
            func.count(APRSPacket.from_call).label('count'),
        )
        .filter(APRSPacket.received_at >= last_24h)
        .group_by(func.substring(APRSPacket.from_call, 1, 2))
        .all()
    )

    country_counts: dict[tuple[str, str], int] = {}
    unknown_count = 0

    for prefix, count in prefix_counts:
        if not prefix:
            unknown_count += count
            continue
        country_info = None
        if len(prefix) >= 2:
            country_info = CALLSIGN_PREFIXES.get(prefix[:2])
        if not country_info and len(prefix) >= 1:
            country_info = CALLSIGN_PREFIXES.get(prefix[:1])

        if country_info:
            key = country_info
            country_counts[key] = country_counts.get(key, 0) + count
        else:
            unknown_count += count

    result = [
        {'country_code': code, 'country_name': name, 'count': cnt}
        for (code, name), cnt in country_counts.items()
    ]
    result.sort(key=lambda x: x['count'], reverse=True)

    return result[:limit]
```

- [ ] **Step 6: Add required import for text()**

Add to imports at top of file:

```python
from sqlalchemy import text
```

- [ ] **Step 7: Run tests to verify no regressions**

Run: `cd haminfo-dashboard && pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 8: Commit changes**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py
git commit -m "feat: add continuous aggregate query functions with feature flag"
```

---

## Chunk 4: Production Deployment

### Task 2: Run Migrations on Production

**Note:** These steps must be run on the production database server via SSH.

**Connection:** `ssh waboring@cloud.hemna.com` then `cd ~/docker/haminfo`

- [ ] **Step 1: Backup database before migration**

```bash
docker exec haminfo-db pg_dump -U haminfo haminfo > haminfo_backup_$(date +%Y%m%d_%H%M%S).sql
```

- [ ] **Step 2: Run continuous aggregates migration**

```bash
cd haminfo/db && alembic upgrade d5e6f7a8b9c0
```

Expected: Migration completes quickly

- [ ] **Step 3: Verify aggregates were created**

```bash
docker exec haminfo-db psql -U haminfo -d haminfo -c "SELECT * FROM timescaledb_information.continuous_aggregates;"
```

Expected: 3 rows (aprs_stats_hourly, aprs_station_stats_hourly, aprs_prefix_stats_hourly)

### Task 3: Backfill Historical Data

- [ ] **Step 1: Backfill aprs_stats_hourly (30 days)**

```sql
CALL refresh_continuous_aggregate('aprs_stats_hourly', 
    NOW() - INTERVAL '30 days', NOW());
```

Expected: Takes 1-5 minutes

- [ ] **Step 2: Backfill aprs_station_stats_hourly (7 days)**

```sql
CALL refresh_continuous_aggregate('aprs_station_stats_hourly', 
    NOW() - INTERVAL '7 days', NOW());
```

Expected: Takes 2-10 minutes (larger dataset)

- [ ] **Step 3: Backfill aprs_prefix_stats_hourly (30 days)**

```sql
CALL refresh_continuous_aggregate('aprs_prefix_stats_hourly', 
    NOW() - INTERVAL '30 days', NOW());
```

Expected: Takes 1-5 minutes

- [ ] **Step 4: Verify data was populated**

```sql
SELECT COUNT(*) FROM aprs_stats_hourly;
SELECT COUNT(*) FROM aprs_station_stats_hourly;
SELECT COUNT(*) FROM aprs_prefix_stats_hourly;
```

Expected: aprs_stats_hourly ~720 rows, station_stats ~millions, prefix_stats ~thousands

### Task 4: Enable Feature Flag and Deploy

- [ ] **Step 1: Update feature flag**

In `haminfo-dashboard/src/haminfo_dashboard/queries.py`:

```python
USE_CONTINUOUS_AGGREGATES = True
```

- [ ] **Step 2: Clear cache**

```bash
# Clear memcached if running
echo 'flush_all' | nc localhost 11211
```

- [ ] **Step 3: Restart dashboard service**

```bash
sudo systemctl restart haminfo-dashboard
```

- [ ] **Step 4: Verify performance improvement**

Check dashboard page load time. Should be <1s instead of >15s.

- [ ] **Step 5: Commit flag change**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/queries.py
git commit -m "feat: enable continuous aggregates for dashboard queries"
```

---

## Rollback Plan

If issues arise after deployment:

1. **Disable feature flag:**
   ```python
   USE_CONTINUOUS_AGGREGATES = False
   ```

2. **Restart service:**
   ```bash
   sudo systemctl restart haminfo-dashboard
   ```

3. **Optionally drop aggregates:**
   ```sql
   DROP MATERIALIZED VIEW aprs_stats_hourly CASCADE;
   DROP MATERIALIZED VIEW aprs_station_stats_hourly CASCADE;
   DROP MATERIALIZED VIEW aprs_prefix_stats_hourly CASCADE;
   ```

The dashboard will fall back to raw table queries automatically.
