"""empty message

Revision ID: d4cc331a0932
Revises: 6df48db8b086
Create Date: 2023-07-14 13:54:42.119933

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4cc331a0932'
down_revision = '6df48db8b086'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('weather_station',
                  sa.Column('country_code', sa.String(), nullable=True))


def downgrade():
    op.drop_column('weather_station', 'country_code')
