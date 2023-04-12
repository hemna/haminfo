"""add WeatherStation and WeatherReport

Revision ID: 898b1497d0b2
Revises: 8c3048879a88
Create Date: 2023-04-11 12:24:46.547328

"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '898b1497d0b2'
down_revision = '8c3048879a88'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_geospatial_table('weather_station',
    sa.Column('id', sa.Integer(), nullable=False, unique=True),
    sa.Column('callsign', sa.String(), nullable=False, unique=True),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('location', Geography(geometry_type='POINT', spatial_index=False, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.Column('comment', sa.String(), nullable=True),
    sa.Column('symbol', sa.CHAR(), nullable=True),
    sa.Column('symbol_table', sa.CHAR(), nullable=True),
    sa.PrimaryKeyConstraint('id', 'callsign'),
    sa.UniqueConstraint('callsign')
    )
    op.create_geospatial_index('idx_weather_station_location', 'weather_station', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('weather_report',
    sa.Column('id', sa.Integer(), nullable=False, unique=True),
    sa.Column('weather_station_id', sa.Integer(), nullable=True),
    sa.Column('temperature', sa.Float(decimal_return_scale=2), nullable=True),
    sa.Column('humidity', sa.Integer(), nullable=True),
    sa.Column('pressure', sa.Float(decimal_return_scale=2), nullable=True),
    sa.Column('course', sa.Integer(), nullable=True),
    sa.Column('wind_speed', sa.Float(decimal_return_scale=3), nullable=True),
    sa.Column('wind_gust', sa.Float(decimal_return_scale=4), nullable=True),
    sa.Column('rain_1h', sa.Float(decimal_return_scale=2), nullable=True),
    sa.Column('rain_24h', sa.Float(decimal_return_scale=2), nullable=True),
    sa.Column('rain_since_midnight', sa.Float(decimal_return_scale=2), nullable=True),
    sa.Column('time', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['weather_station_id'], ['weather_station.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('weather_report')
    op.drop_geospatial_index('idx_weather_station_location', table_name='weather_station', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('weather_station')
    # ### end Alembic commands ###
