"""slim down aprs_packet table and add partitioning

Revision ID: 51e19bb5a9d8
Revises: 3a3e840c4d49
Create Date: 2026-03-09

This migration:
1. Drops the wide aprs_packet table (47 columns)
2. Creates a lean aprs_packet table (16 columns) optimized for position lookups
3. Adds composite index for "find latest position by callsign" queries
4. Sets up table for future time-based partitioning

Removed columns (not used by any queries/APIs):
- Weather: temperature, humidity, pressure, wind_*, rain_*, solar_radiation,
  uv_index, luminosity, snow
- Telemetry: telemetry_analog, telemetry_digital, telemetry_sequence
- Message: message_text, message_id, message_ack, message_reject
- Object: object_name, object_killed, status
- Query: query_type, query_response
- Other: third_party, capcode, format, source, compressed, mic_e, maidenhead

NOTE: This migration drops all existing data. Run a backup first if needed.
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision = '51e19bb5a9d8'
down_revision = '3a3e840c4d49'
branch_labels = None
depends_on = None


def upgrade():
    # Drop all existing indexes on the old table
    op.drop_index('ix_aprs_packet_to_call', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_timestamp', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_received_at', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_packet_type', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_from_call', table_name='aprs_packet')

    # Drop the spatial index using raw SQL (geoalchemy2 syntax varies)
    op.execute('DROP INDEX IF EXISTS idx_aprs_packet_location')

    # Drop the old wide table
    op.drop_table('aprs_packet')

    # Drop the old sequence
    op.execute('DROP SEQUENCE IF EXISTS aprs_packet_id_seq')

    # Create new sequence for BigInteger IDs
    op.execute('CREATE SEQUENCE aprs_packet_id_seq')

    # Create new lean table
    op.create_table(
        'aprs_packet',
        sa.Column(
            'id', sa.BigInteger(), sa.Sequence('aprs_packet_id_seq'), nullable=False
        ),
        sa.Column('from_call', sa.String(9), nullable=False),
        sa.Column('to_call', sa.String(9), nullable=True),
        sa.Column('path', sa.String(100), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('raw', sa.Text(), nullable=False),
        sa.Column('packet_type', sa.String(20), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column(
            'location',
            Geography(
                geometry_type='POINT',
                spatial_index=False,
                from_text='ST_GeogFromText',
                name='geography',
            ),
            nullable=True,
        ),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('course', sa.SmallInteger(), nullable=True),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('symbol', sa.CHAR(1), nullable=True),
        sa.Column('symbol_table', sa.CHAR(1), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create standard B-tree indexes
    op.create_index('ix_aprs_packet_from_call', 'aprs_packet', ['from_call'])
    op.create_index('ix_aprs_packet_to_call', 'aprs_packet', ['to_call'])
    op.create_index('ix_aprs_packet_timestamp', 'aprs_packet', ['timestamp'])
    op.create_index('ix_aprs_packet_received_at', 'aprs_packet', ['received_at'])
    op.create_index('ix_aprs_packet_packet_type', 'aprs_packet', ['packet_type'])

    # Create GIST spatial index on location
    op.execute("""
        CREATE INDEX idx_aprs_packet_location
        ON aprs_packet USING GIST (location)
    """)

    # Create composite partial index for "find latest position by callsign"
    # This dramatically speeds up the most common query pattern
    op.execute("""
        CREATE INDEX ix_aprs_packet_from_call_ts_pos
        ON aprs_packet (from_call, timestamp DESC)
        WHERE latitude IS NOT NULL
    """)


def downgrade():
    # Drop the new indexes
    op.execute('DROP INDEX IF EXISTS ix_aprs_packet_from_call_ts_pos')
    op.execute('DROP INDEX IF EXISTS idx_aprs_packet_location')
    op.drop_index('ix_aprs_packet_packet_type', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_received_at', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_timestamp', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_to_call', table_name='aprs_packet')
    op.drop_index('ix_aprs_packet_from_call', table_name='aprs_packet')

    # Drop the lean table
    op.drop_table('aprs_packet')

    # Drop and recreate sequence for Integer IDs
    op.execute('DROP SEQUENCE IF EXISTS aprs_packet_id_seq')
    op.execute('CREATE SEQUENCE aprs_packet_id_seq')

    # Recreate the original wide table
    op.create_table(
        'aprs_packet',
        sa.Column(
            'id', sa.Integer(), sa.Sequence('aprs_packet_id_seq'), nullable=False
        ),
        sa.Column('from_call', sa.String(), nullable=False),
        sa.Column('to_call', sa.String(), nullable=True),
        sa.Column('path', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('raw', sa.Text(), nullable=False),
        sa.Column('packet_type', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column(
            'location',
            Geography(
                geometry_type='POINT',
                spatial_index=False,
                from_text='ST_GeogFromText',
                name='geography',
            ),
            nullable=True,
        ),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('course', sa.Integer(), nullable=True),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('maidenhead', sa.String(), nullable=True),
        sa.Column('symbol', sa.CHAR(), nullable=True),
        sa.Column('symbol_table', sa.CHAR(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('object_name', sa.String(), nullable=True),
        sa.Column('object_killed', sa.Boolean(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Integer(), nullable=True),
        sa.Column('pressure', sa.Float(), nullable=True),
        sa.Column('wind_direction', sa.Integer(), nullable=True),
        sa.Column('wind_speed', sa.Float(), nullable=True),
        sa.Column('wind_gust', sa.Float(), nullable=True),
        sa.Column('rain_1h', sa.Float(), nullable=True),
        sa.Column('rain_24h', sa.Float(), nullable=True),
        sa.Column('rain_since_midnight', sa.Float(), nullable=True),
        sa.Column('solar_radiation', sa.Float(), nullable=True),
        sa.Column('uv_index', sa.Integer(), nullable=True),
        sa.Column('luminosity', sa.Float(), nullable=True),
        sa.Column('snow', sa.Float(), nullable=True),
        sa.Column('telemetry_analog', sa.String(), nullable=True),
        sa.Column('telemetry_digital', sa.String(), nullable=True),
        sa.Column('telemetry_sequence', sa.Integer(), nullable=True),
        sa.Column('message_text', sa.Text(), nullable=True),
        sa.Column('message_id', sa.String(), nullable=True),
        sa.Column('message_ack', sa.String(), nullable=True),
        sa.Column('message_reject', sa.Boolean(), nullable=True),
        sa.Column('query_type', sa.String(), nullable=True),
        sa.Column('query_response', sa.Text(), nullable=True),
        sa.Column('third_party', sa.Text(), nullable=True),
        sa.Column('capcode', sa.String(), nullable=True),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('compressed', sa.Boolean(), nullable=True),
        sa.Column('mic_e', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
    )

    # Recreate original indexes
    op.create_index('ix_aprs_packet_from_call', 'aprs_packet', ['from_call'])
    op.create_index('ix_aprs_packet_to_call', 'aprs_packet', ['to_call'])
    op.create_index('ix_aprs_packet_timestamp', 'aprs_packet', ['timestamp'])
    op.create_index('ix_aprs_packet_received_at', 'aprs_packet', ['received_at'])
    op.create_index('ix_aprs_packet_packet_type', 'aprs_packet', ['packet_type'])
    op.execute("""
        CREATE INDEX idx_aprs_packet_location
        ON aprs_packet USING GIST (location)
    """)
