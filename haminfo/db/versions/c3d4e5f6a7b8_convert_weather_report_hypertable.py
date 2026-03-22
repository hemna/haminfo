"""Convert weather_report to TimescaleDB hypertable with compression.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-22

Converts the weather_report table to a TimescaleDB hypertable and enables
compression for data older than 30 days. Expected storage savings: ~75%.

See docs/superpowers/specs/2026-03-22-timescaledb-compression-design.md

IMPORTANT: This migration requires TimescaleDB extension to be installed.
Run the previous migration (b2c3d4e5f6a7) first.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Drop existing primary key constraint
    # TimescaleDB requires the partitioning column (time) to be part of the primary key
    op.execute("""
        ALTER TABLE weather_report 
        DROP CONSTRAINT IF EXISTS weather_report_pkey
    """)

    # Step 2: Create new composite primary key including time column
    op.execute("""
        ALTER TABLE weather_report 
        ADD PRIMARY KEY (id, time)
    """)

    # Step 3: Convert to hypertable with 7-day chunks
    # migrate_data => true will move existing data into chunks
    # This may take a while for large tables (~7M rows)
    op.execute("""
        SELECT create_hypertable(
            'weather_report', 
            'time',
            chunk_time_interval => INTERVAL '7 days',
            migrate_data => true,
            if_not_exists => true
        )
    """)

    # Step 4: Enable compression on the hypertable
    # segment by station_id for better query performance when filtering by station
    # order by time DESC since most queries want recent data
    op.execute("""
        ALTER TABLE weather_report SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'weather_station_id',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)

    # Step 5: Add automatic compression policy
    # Compress chunks older than 30 days
    op.execute("""
        SELECT add_compression_policy(
            'weather_report', 
            INTERVAL '30 days',
            if_not_exists => true
        )
    """)


def downgrade():
    # Remove compression policy first
    op.execute("""
        SELECT remove_compression_policy('weather_report', if_exists => true)
    """)

    # Decompress all chunks (required before converting back)
    # Note: This may take a long time for large tables
    op.execute("""
        DO $$
        DECLARE
            chunk REGCLASS;
        BEGIN
            FOR chunk IN SELECT show_chunks('weather_report')
            LOOP
                BEGIN
                    PERFORM decompress_chunk(chunk, if_compressed => true);
                EXCEPTION WHEN OTHERS THEN
                    -- Chunk might not be compressed, continue
                    NULL;
                END;
            END LOOP;
        END $$;
    """)

    # Disable compression
    op.execute("""
        ALTER TABLE weather_report SET (
            timescaledb.compress = false
        )
    """)

    # Note: Converting back from hypertable to regular table is complex
    # and would require creating a new table, copying data, and swapping.
    # For now, the table remains a hypertable but without compression.
    # Full reversal would need manual intervention.
