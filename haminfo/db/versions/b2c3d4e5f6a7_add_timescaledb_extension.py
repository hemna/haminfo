"""Add TimescaleDB extension.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22

Enables TimescaleDB extension for time-series compression support.
See docs/superpowers/specs/2026-03-22-timescaledb-compression-design.md
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Enable TimescaleDB extension
    # This requires the TimescaleDB package to be installed in PostgreSQL
    op.execute('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE')


def downgrade():
    # Note: Cannot easily drop timescaledb if hypertables exist
    # Would need to convert hypertables back to regular tables first
    # This is intentionally left as a no-op for safety
    pass
