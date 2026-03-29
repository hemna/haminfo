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
    op.execute('DROP MATERIALIZED VIEW IF EXISTS aprs_prefix_stats_hourly CASCADE')
    op.execute('DROP MATERIALIZED VIEW IF EXISTS aprs_station_stats_hourly CASCADE')
    op.execute('DROP MATERIALIZED VIEW IF EXISTS aprs_stats_hourly CASCADE')
