"""Add country_code column to aprs_packet table.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-03-31

Adds a denormalized country_code column to aprs_packet for fast country-based
queries. The country code is determined at insert time using reverse geocoding
from the packet's GPS coordinates.

This eliminates the need for expensive spatial joins when querying packets
by country.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    # Add country_code column to aprs_packet
    # Using VARCHAR(2) to store ISO 3166-1 alpha-2 codes (e.g., 'US', 'DE', 'JP')
    op.add_column('aprs_packet', sa.Column('country_code', sa.String(2), nullable=True))

    # Create index for fast country-based queries
    # This index will dramatically speed up queries like:
    # SELECT * FROM aprs_packet WHERE country_code = 'US' AND received_at > ...
    op.create_index(
        'idx_aprs_packet_country_code',
        'aprs_packet',
        ['country_code'],
        if_not_exists=True,
    )

    # Create composite index for country + time queries
    # This is the most common query pattern for the countries dashboard
    op.create_index(
        'idx_aprs_packet_country_received',
        'aprs_packet',
        ['country_code', 'received_at'],
        postgresql_using='btree',
        if_not_exists=True,
    )


def downgrade():
    op.drop_index('idx_aprs_packet_country_received', table_name='aprs_packet')
    op.drop_index('idx_aprs_packet_country_code', table_name='aprs_packet')
    op.drop_column('aprs_packet', 'country_code')
