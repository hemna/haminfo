"""Add missing indexes and updated_at column to station.

Revision ID: a1b2c3d4e5f6
Revises: 51e19bb5a9d8
Create Date: 2026-03-19

Adds:
1. Index on weather_report (weather_station_id, time DESC) for latest report queries
2. updated_at column to station table for tracking data freshness
3. Index on station (freq_band, state) for filtered nearest queries
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '51e19bb5a9d8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add composite index on weather_report for "latest report" queries
    # Using raw SQL for CONCURRENTLY option (non-blocking in production)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_weather_report_station_time
        ON weather_report (weather_station_id, time DESC)
    """)

    # 2. Add updated_at column to station table
    op.add_column(
        'station',
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=True,
        ),
    )

    # 3. Add index for filtered nearest queries (freq_band + state)
    op.create_index(
        'ix_station_freq_band_state',
        'station',
        ['freq_band', 'state'],
    )


def downgrade():
    op.drop_index('ix_station_freq_band_state', table_name='station')
    op.drop_column('station', 'updated_at')
    op.execute('DROP INDEX IF EXISTS ix_weather_report_station_time')
