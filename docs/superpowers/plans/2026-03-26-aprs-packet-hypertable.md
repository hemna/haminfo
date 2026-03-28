# APRS Packet Hypertable Migration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the `aprs_packet` table to a TimescaleDB hypertable with compression to reduce storage from 6.2 GB to ~500 MB.

**Architecture:** Create a new hypertable with `timestamp` as the partitioning column, migrate data from the existing table, recreate indexes including the GIST spatial index, enable compression segmented by `from_call` for optimal query performance.

**Tech Stack:** PostgreSQL 15, TimescaleDB, PostGIS/GeoAlchemy2

---

## Pre-Migration Checklist

- [ ] Verify current table size: `6,190 MB`
- [ ] Verify row count: `~12.75 million rows`
- [ ] Verify TimescaleDB extension is installed
- [ ] Ensure adequate disk space for migration (~12 GB free needed temporarily)
- [ ] Plan for ~5-10 minutes of downtime for the MQTT ingestion service

---

## Chunk 1: Database Migration

### Task 1: Stop MQTT Ingestion Service

**Purpose:** Prevent new inserts during migration

- [ ] **Step 1: Stop the MQTT service**

```bash
ssh waboring@cloud.hemna.com 'cd ~/docker/haminfo && docker compose stop mqtt_injest'
```

Expected: Service stops, no new packets being inserted

- [ ] **Step 2: Verify no active connections to aprs_packet**

```sql
SELECT pid, state, query 
FROM pg_stat_activity 
WHERE query LIKE '%aprs_packet%' AND state != 'idle';
```

Expected: No active queries on aprs_packet

---

### Task 2: Create New Hypertable

**Purpose:** Create the hypertable structure without the `id` column

- [ ] **Step 1: Create the new table structure**

```sql
CREATE TABLE aprs_packet_new (
    from_call VARCHAR(9) NOT NULL,
    to_call VARCHAR(9),
    path VARCHAR(100),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    raw TEXT NOT NULL,
    packet_type VARCHAR(20),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    altitude DOUBLE PRECISION,
    course SMALLINT,
    speed DOUBLE PRECISION,
    symbol CHAR(1),
    symbol_table CHAR(1),
    comment TEXT
);
```

- [ ] **Step 2: Convert to hypertable with 7-day chunks**

```sql
SELECT create_hypertable(
    'aprs_packet_new',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days'
);
```

Expected: `(1,public,aprs_packet_new,t)`

---

### Task 3: Migrate Data

**Purpose:** Copy all data from old table to new hypertable

- [ ] **Step 1: Copy data (excluding id column)**

```sql
INSERT INTO aprs_packet_new (
    from_call, to_call, path, timestamp, received_at, raw,
    packet_type, latitude, longitude, location, altitude,
    course, speed, symbol, symbol_table, comment
)
SELECT 
    from_call, to_call, path, timestamp, received_at, raw,
    packet_type, latitude, longitude, location, altitude,
    course, speed, symbol, symbol_table, comment
FROM aprs_packet;
```

Expected: `INSERT 0 12750205` (approximately)

- [ ] **Step 2: Verify row count matches**

```sql
SELECT 
    (SELECT COUNT(*) FROM aprs_packet) as old_count,
    (SELECT COUNT(*) FROM aprs_packet_new) as new_count;
```

Expected: Both counts should match

---

### Task 4: Create Indexes on New Table

**Purpose:** Recreate all indexes for query performance

- [ ] **Step 1: Create from_call index**

```sql
CREATE INDEX ix_aprs_packet_new_from_call 
ON aprs_packet_new (from_call);
```

- [ ] **Step 2: Create timestamp index**

```sql
CREATE INDEX ix_aprs_packet_new_timestamp 
ON aprs_packet_new (timestamp DESC);
```

- [ ] **Step 3: Create received_at index**

```sql
CREATE INDEX ix_aprs_packet_new_received_at 
ON aprs_packet_new (received_at DESC);
```

- [ ] **Step 4: Create packet_type index**

```sql
CREATE INDEX ix_aprs_packet_new_packet_type 
ON aprs_packet_new (packet_type);
```

- [ ] **Step 5: Create to_call index**

```sql
CREATE INDEX ix_aprs_packet_new_to_call 
ON aprs_packet_new (to_call);
```

- [ ] **Step 6: Create composite index for position lookups**

```sql
CREATE INDEX ix_aprs_packet_new_from_call_ts_pos 
ON aprs_packet_new (from_call, timestamp DESC) 
WHERE latitude IS NOT NULL;
```

- [ ] **Step 7: Create GIST spatial index**

```sql
CREATE INDEX idx_aprs_packet_new_location 
ON aprs_packet_new USING GIST (location);
```

---

### Task 5: Swap Tables

**Purpose:** Replace old table with new hypertable

- [ ] **Step 1: Drop old table**

```sql
DROP TABLE aprs_packet;
```

- [ ] **Step 2: Rename new table**

```sql
ALTER TABLE aprs_packet_new RENAME TO aprs_packet;
```

- [ ] **Step 3: Rename indexes to match original names**

```sql
ALTER INDEX ix_aprs_packet_new_from_call RENAME TO ix_aprs_packet_from_call;
ALTER INDEX ix_aprs_packet_new_timestamp RENAME TO ix_aprs_packet_timestamp;
ALTER INDEX ix_aprs_packet_new_received_at RENAME TO ix_aprs_packet_received_at;
ALTER INDEX ix_aprs_packet_new_packet_type RENAME TO ix_aprs_packet_packet_type;
ALTER INDEX ix_aprs_packet_new_to_call RENAME TO ix_aprs_packet_to_call;
ALTER INDEX ix_aprs_packet_new_from_call_ts_pos RENAME TO ix_aprs_packet_from_call_ts_pos;
ALTER INDEX idx_aprs_packet_new_location RENAME TO idx_aprs_packet_location;
```

- [ ] **Step 4: Drop old sequence (no longer needed)**

```sql
DROP SEQUENCE IF EXISTS aprs_packet_id_seq;
```

---

## Chunk 2: Enable Compression

### Task 6: Configure Compression

**Purpose:** Enable compression for space savings

- [ ] **Step 1: Enable compression on the hypertable**

```sql
ALTER TABLE aprs_packet SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'from_call',
    timescaledb.compress_orderby = 'timestamp DESC'
);
```

- [ ] **Step 2: Add compression policy (compress chunks older than 7 days)**

```sql
SELECT add_compression_policy('aprs_packet', INTERVAL '7 days');
```

Expected: Returns job_id for the compression policy

- [ ] **Step 3: Manually compress existing old chunks**

```sql
SELECT compress_chunk(c)
FROM show_chunks('aprs_packet', older_than => INTERVAL '7 days') c;
```

- [ ] **Step 4: Verify compression results**

```sql
SELECT 
    pg_size_pretty(SUM(before_compression_total_bytes)) as before,
    pg_size_pretty(SUM(after_compression_total_bytes)) as after,
    ROUND(100 - (SUM(after_compression_total_bytes)::numeric / 
                  NULLIF(SUM(before_compression_total_bytes)::numeric, 0) * 100), 1) as savings_pct
FROM chunk_compression_stats('aprs_packet');
```

Expected: ~90%+ compression ratio

---

## Chunk 3: Application Updates & Verification

### Task 7: Update SQLAlchemy Model

**File:** `haminfo/db/models/aprs_packet.py`

**Purpose:** Remove id column from model since it's no longer used

- [ ] **Step 1: Update APRSPacket model**

Change the model to remove the `id` column and use `timestamp` + `from_call` as the logical key:

```python
class APRSPacket(ModelBase):
    """
    Lean model for storing APRS packets optimized for position lookups.
    
    Stored as a TimescaleDB hypertable partitioned by timestamp.
    No primary key - uses natural key of (timestamp, from_call) for lookups.
    """

    __tablename__ = 'aprs_packet'
    
    # TimescaleDB hypertables don't require a primary key
    # The timestamp column is used for partitioning
    __table_args__ = {'extend_existing': True}

    # Core APRS packet fields
    from_call = sa.Column(sa.String(9), nullable=False, index=True)
    to_call = sa.Column(sa.String(9), index=True)
    path = sa.Column(sa.String(100))

    # Timestamps - timestamp is the hypertable partition column
    timestamp = sa.Column(sa.DateTime, nullable=False, primary_key=True)
    received_at = sa.Column(
        sa.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    # ... rest of columns unchanged
```

- [ ] **Step 2: Update `__repr__` method**

```python
def __repr__(self):
    return (
        f"<APRSPacket(from_call='{self.from_call}', "
        f"to_call='{self.to_call}', packet_type='{self.packet_type}', "
        f"timestamp='{self.timestamp}')>"
    )
```

- [ ] **Step 3: Update db.py count query**

Change `func.count(APRSPacket.id)` to `func.count(APRSPacket.timestamp)` or `func.count('*')`.

---

### Task 8: Restart Services and Verify

- [ ] **Step 1: Restart MQTT ingestion service**

```bash
ssh waboring@cloud.hemna.com 'cd ~/docker/haminfo && docker compose start mqtt_injest'
```

- [ ] **Step 2: Verify new packets are being inserted**

```sql
SELECT from_call, timestamp, packet_type 
FROM aprs_packet 
ORDER BY timestamp DESC 
LIMIT 5;
```

Expected: Recent timestamps showing new inserts

- [ ] **Step 3: Test spatial query**

```sql
SELECT from_call, packet_type, timestamp,
       ROUND(ST_Distance(location, ST_MakePoint(-97.7431, 30.2672)::geography)::numeric / 1000, 1) as distance_km
FROM aprs_packet
WHERE ST_DWithin(location, ST_MakePoint(-97.7431, 30.2672)::geography, 50000)
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY distance_km
LIMIT 5;
```

Expected: Results with distance calculations

- [ ] **Step 4: Verify API endpoints work**

```bash
curl -s http://localhost:8081/stats | jq .aprs_packets
```

Expected: Stats showing packet counts

- [ ] **Step 5: Check final table size**

```sql
SELECT 
    pg_size_pretty(pg_total_relation_size('aprs_packet')) as total_size,
    (SELECT COUNT(*) FROM aprs_packet) as row_count;
```

Expected: ~500 MB total size (down from 6.2 GB)

---

## Rollback Procedure

If issues occur before dropping old table:

```sql
DROP TABLE IF EXISTS aprs_packet_new;
-- Original table unchanged, restart services
```

If issues occur after swap (need backup):

1. Stop all services
2. Restore from backup
3. Restart services

---

## Success Criteria

- [ ] All ~12.75 million rows migrated successfully
- [ ] Hypertable created with 7-day chunks
- [ ] All indexes recreated including GIST spatial index
- [ ] Compression enabled and working (~90% savings)
- [ ] New packet inserts working
- [ ] Spatial queries working
- [ ] API endpoints working
- [ ] Storage reduced from 6.2 GB to ~500 MB

---

## Estimated Timeline

| Task | Duration |
|------|----------|
| Stop MQTT service | 1 min |
| Create hypertable | 1 min |
| Migrate data | 3-5 min |
| Create indexes | 2-3 min |
| Swap tables | 1 min |
| Enable compression | 2-3 min |
| Compress old chunks | 2-3 min |
| Update model & restart | 2 min |
| Verification | 5 min |
| **Total** | **~20-25 minutes** |

---

## Single-Script Execution (Optional)

For convenience, here's a single SQL script that can be run in one transaction (except compression):

```sql
-- Run as a single script in psql
-- Note: Stop MQTT service first!

BEGIN;

-- Create new hypertable structure
CREATE TABLE aprs_packet_new (
    from_call VARCHAR(9) NOT NULL,
    to_call VARCHAR(9),
    path VARCHAR(100),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    raw TEXT NOT NULL,
    packet_type VARCHAR(20),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    altitude DOUBLE PRECISION,
    course SMALLINT,
    speed DOUBLE PRECISION,
    symbol CHAR(1),
    symbol_table CHAR(1),
    comment TEXT
);

-- Convert to hypertable
SELECT create_hypertable('aprs_packet_new', 'timestamp', chunk_time_interval => INTERVAL '7 days');

-- Migrate data
INSERT INTO aprs_packet_new (from_call, to_call, path, timestamp, received_at, raw, packet_type, latitude, longitude, location, altitude, course, speed, symbol, symbol_table, comment)
SELECT from_call, to_call, path, timestamp, received_at, raw, packet_type, latitude, longitude, location, altitude, course, speed, symbol, symbol_table, comment
FROM aprs_packet;

-- Create indexes
CREATE INDEX ix_aprs_packet_new_from_call ON aprs_packet_new (from_call);
CREATE INDEX ix_aprs_packet_new_timestamp ON aprs_packet_new (timestamp DESC);
CREATE INDEX ix_aprs_packet_new_received_at ON aprs_packet_new (received_at DESC);
CREATE INDEX ix_aprs_packet_new_packet_type ON aprs_packet_new (packet_type);
CREATE INDEX ix_aprs_packet_new_to_call ON aprs_packet_new (to_call);
CREATE INDEX ix_aprs_packet_new_from_call_ts_pos ON aprs_packet_new (from_call, timestamp DESC) WHERE latitude IS NOT NULL;
CREATE INDEX idx_aprs_packet_new_location ON aprs_packet_new USING GIST (location);

-- Swap tables
DROP TABLE aprs_packet;
ALTER TABLE aprs_packet_new RENAME TO aprs_packet;

-- Rename indexes
ALTER INDEX ix_aprs_packet_new_from_call RENAME TO ix_aprs_packet_from_call;
ALTER INDEX ix_aprs_packet_new_timestamp RENAME TO ix_aprs_packet_timestamp;
ALTER INDEX ix_aprs_packet_new_received_at RENAME TO ix_aprs_packet_received_at;
ALTER INDEX ix_aprs_packet_new_packet_type RENAME TO ix_aprs_packet_packet_type;
ALTER INDEX ix_aprs_packet_new_to_call RENAME TO ix_aprs_packet_to_call;
ALTER INDEX ix_aprs_packet_new_from_call_ts_pos RENAME TO ix_aprs_packet_from_call_ts_pos;
ALTER INDEX idx_aprs_packet_new_location RENAME TO idx_aprs_packet_location;

-- Drop old sequence
DROP SEQUENCE IF EXISTS aprs_packet_id_seq;

COMMIT;

-- Enable compression (must be outside transaction)
ALTER TABLE aprs_packet SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'from_call',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('aprs_packet', INTERVAL '7 days');

-- Compress existing old chunks
SELECT compress_chunk(c)
FROM show_chunks('aprs_packet', older_than => INTERVAL '7 days') c;
```
