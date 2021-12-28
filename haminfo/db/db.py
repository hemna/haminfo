from oslo_config import cfg
from oslo_log import log as logging
import sqlalchemy
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from haminfo.db.models.station import Station
from haminfo.db.models.modelbase import ModelBase

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

grp = cfg.OptGroup('database')
cfg.CONF.register_group(grp)
database_opts = [
    cfg.StrOpt('connection',
               help='The SQLAlchemy connection string to use to connect to '
                    'the database.',
               secret=True),
    cfg.BoolOpt('debug',
                default=False,
                help='Enable SQL query debugging'),
]

CONF.register_opts(database_opts, group="database")

# Mapping of human filter string to db column name
STATION_FEATURES = {
    "ares": "ares",
    "races": "races",
    "skywarn": "skywarn",
    "allstar": "allstar_node",
    "echolink": "echolink_node",
    "irlp": "irlp_node",
    "wires": "wires_node",
    "fm": "fm_analog",
    "dmr": "dmr",
    "dstar": "dstar",
}


# Probably should nuke this now we are using alembic
def init_db_schema(engine):
    LOG.info("Dropping all tables")
    ModelBase.metadata.drop_all(engine)
    LOG.info("Creating all tables")
    ModelBase.metadata.create_all(engine)


def setup_connection():
    # engine = create_engine('sqlite:///:memory:', echo=True)
    engine = create_engine(CONF.database.connection, echo=CONF.database.debug)
    return engine


def setup_session(engine):
    return sessionmaker(bind=engine)


def delete_USA_state_repeaters(state, session):
    stmt = sqlalchemy.delete(
        Station
    ).where(
        Station.state == state
    ).execution_options(synchronize_session="fetch")
    session.execute(stmt)


def find_nearest_to(session, lat, lon, freq_band="2m", limit=1, filters=None):
    poi = 'SRID=4326;POINT({} {})'.format(lon, lat)
    poi_point = func.ST_Point(lon, lat)
    LOG.info("Band: {}  Limit: {} Filters? {}".format(
        freq_band, limit, filters))

    # query = session.query(
    #    Station,
    #    func.ST_Distance(Station.location, poi).label('distance'),
    #    func.ST_Azimuth(poi_point, func.ST_Point(Station.long, Station.lat)
    #                    ).label('bearing')
    # ).filter(
    #    Station.freq_band == freq_band
    # )
    # SELECT station.id, station.callsign, station.landmark,
    #        station.nearest_city, station.county,
    #    ST_Distance(station.location, 'SRID=4326;POINT(-78.84950 37.34433)') /
    #                1609 as dist
    # FROM station ORDER BY
    #    station.location <-> 'SRID=4326;POINT(-78.84950 37.34433)'::geometry
    # LIMIT 10;
    filter_parts = []
    filter_parts.append(Station.freq_band == freq_band)
    if filters:
        # We need to add a where clause for filtering
        filter_parts = []
        for filter in filters:
            # make sure it matches a column name
            LOG.info("Add filter '{}".format(filter))
            if filter in STATION_FEATURES:
                filter_str = STATION_FEATURES[filter]
                filter_parts.append(getattr(Station, filter_str) == True)  # noqa

    query = session.query(
        Station,
        func.ST_Distance(Station.location, poi).label('distance'),
        func.ST_Azimuth(poi_point, func.ST_Point(Station.long, Station.lat)
                        ).label('bearing')
    ).filter(
        *filter_parts
    ).order_by(
        Station.location.distance_centroid(poi)
    ).limit(limit)

    return query


def get_num_repeaters_in_db(session):
    rows = session.query(Station).count()
    return rows
