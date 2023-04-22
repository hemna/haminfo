"""Add raw APRS report to wx report

Revision ID: 6df48db8b086
Revises: 6c283c2e789f
Create Date: 2023-04-22 12:01:42.069629

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6df48db8b086'
down_revision = '6c283c2e789f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('weather_report',
                  sa.Column('raw_report', sa.String(), nullable=True))

def downgrade():
    op.drop_column('weather_report', 'raw_report')
