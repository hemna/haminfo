"""Add repeater ids to request object

Rrevision ID: 5d3ebd160dee
Revises: 8c3048879a88
Create Date: 2021-12-28 12:21:24.704183

"""
from alembic import op
import sqlalchemy as sa
import imp


# revision identifiers, used by Alembic.
revision = '5d3ebd160dee'
down_revision = '8c3048879a88'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('request',
                  sa.Column('repeater_ids', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('request', 'repeater_ids')
    # ### end Alembic commands ###
