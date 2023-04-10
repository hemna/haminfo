"""add weather report table

Revision ID: 1f323c5a9860
Revises: 8c3048879a88
Create Date: 2023-04-10 15:07:18.056287

"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1f323c5a9860'
down_revision = '8c3048879a88'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_geospatial_table('weather_report',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('callsign', sa.String(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('location', Geography(geometry_type='POINT', spatial_index=False, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.PrimaryKeyConstraint('id', 'callsign')
    )
    op.create_geospatial_index('idx_weather_report_location', 'weather_report', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.alter_column('station', 'location',
               existing_type=Geography(geometry_type='POINT', srid=4326, from_text='ST_GeogFromText', name='geography'),
               type_=Geography(geometry_type='POINT', from_text='ST_GeogFromText', name='geography'),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('station', 'location',
               existing_type=Geography(geometry_type='POINT', from_text='ST_GeogFromText', name='geography'),
               type_=Geography(geometry_type='POINT', srid=4326, from_text='ST_GeogFromText', name='geography'),
               existing_nullable=True)
    op.drop_geospatial_index('idx_weather_report_location', table_name='weather_report', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('weather_report')
    # ### end Alembic commands ###
