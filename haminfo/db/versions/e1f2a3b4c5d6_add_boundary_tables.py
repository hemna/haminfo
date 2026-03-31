"""Add boundary tables for reverse geocoding.

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2026-03-31

Creates two tables for storing Natural Earth boundary data:
1. countries - ISO country boundaries for reverse geocoding
2. us_states - US state boundaries for US-specific reverse geocoding

These tables enable determining which country/state a GPS coordinate is in.
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    # Create countries table for world boundary data
    op.create_geospatial_table(
        'countries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('iso_a2', sa.String(2), nullable=False),
        sa.Column('iso_a3', sa.String(3), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column(
            'geom',
            Geometry(
                geometry_type='MULTIPOLYGON',
                srid=4326,
                spatial_index=False,
                from_text='ST_GeomFromEWKT',
                name='geometry',
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create GIST index for spatial queries on countries
    op.create_geospatial_index(
        'idx_countries_geom',
        'countries',
        ['geom'],
        unique=False,
        postgresql_using='gist',
        postgresql_ops={},
    )

    # Create unique index on iso_a2 for countries
    op.create_index('ix_countries_iso_a2', 'countries', ['iso_a2'], unique=True)

    # Create us_states table for US state boundary data
    op.create_geospatial_table(
        'us_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column(
            'geom',
            Geometry(
                geometry_type='MULTIPOLYGON',
                srid=4326,
                spatial_index=False,
                from_text='ST_GeomFromEWKT',
                name='geometry',
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create GIST index for spatial queries on us_states
    op.create_geospatial_index(
        'idx_us_states_geom',
        'us_states',
        ['geom'],
        unique=False,
        postgresql_using='gist',
        postgresql_ops={},
    )

    # Create unique index on state_code for us_states
    op.create_index('ix_us_states_state_code', 'us_states', ['state_code'], unique=True)


def downgrade():
    # Drop us_states table and indexes
    op.drop_index('ix_us_states_state_code', table_name='us_states')
    op.drop_geospatial_index(
        'idx_us_states_geom',
        table_name='us_states',
        postgresql_using='gist',
        column_name='geom',
    )
    op.drop_geospatial_table('us_states')

    # Drop countries table and indexes
    op.drop_index('ix_countries_iso_a2', table_name='countries')
    op.drop_geospatial_index(
        'idx_countries_geom',
        table_name='countries',
        postgresql_using='gist',
        column_name='geom',
    )
    op.drop_geospatial_table('countries')
