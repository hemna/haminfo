from hashlib import md5
from oslo_config import cfg
from oslo_log import log as logging

from dogpile.cache.region import make_region
import sqlalchemy
from sqlalchemy import create_engine, func
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from haminfo.db import caching_query
from haminfo.db.models.station import Station
from haminfo.db.models.modelbase import ModelBase
from haminfo.db.models.request import Request
from haminfo import utils


LOG = logging.getLogger(utils.DOMAIN)
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

memcached_opts = [
    cfg.StrOpt('url',
               help='The memcached connection string to use.',
               secret=True),
]
CONF.register_opts(memcached_opts, group="memcached")

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

# the global cache object
cache = None


# Probably should nuke this now we are using alembic
def init_db_schema(engine):
    LOG.info("Dropping all tables")
    ModelBase.metadata.drop_all(engine)
    LOG.info("Creating all tables")
    ModelBase.metadata.create_all(engine)


def md5_key_mangler(key):
    """Receive cache keys as long concatenated strings;
    distill them into an md5 hash.

    """
    return md5(key.encode("ascii")).hexdigest()


def _create_cache_regions():
    regions = {}

    regions["default"] = make_region(
        # the "dbm" backend needs
        # string-encoded keys
        key_mangler=md5_key_mangler
    ).configure(
        "dogpile.cache.pylibmc",
        expiration_time=3600,
        arguments={"url": [CONF.memcached.url]},
    )
    return regions


def _setup_connection():
    # engine = create_engine('sqlite:///:memory:', echo=True)
    engine = create_engine(CONF.database.connection,
                           echo=CONF.database.debug, )
    return engine


def setup_session():
    global cache
    regions = _create_cache_regions()
    engine = _setup_connection()
    session = scoped_session(sessionmaker(bind=engine))
    cache = caching_query.ORMCache(regions)
    cache.listen_on_session(session)

    return session


def delete_USA_state_repeaters(state, session):
    stmt = sqlalchemy.delete(
        Station
    ).where(
        Station.state == state
    ).execution_options(synchronize_session="fetch")
    session.execute(stmt)


def log_request(session, params, results):
    """Log a nearest request to the DB."""
    r = Request.from_json(params)
    LOG.info(r)
    stations = []
    station_ids = []
    for result in results:
        stations.append(result["callsign"])
        # Use our DB ID here, not repeater_id
        station_ids.append(str(result["id"]))

    LOG.info(f"Station_ids {station_ids}")
    r.stations = ','.join(stations)
    r.repeater_ids = ','.join(station_ids)
    session.add(r)
    session.commit()
    invalidate_requests_cache(session)


def find_stations_by_callsign(session, stations):
    """Find data for the stations."""
    query = session.query(
        Station
    ).options(
        caching_query.FromCache('default')
    ).filter(
        Station.callsign.in_(tuple(stations))
    )
    return query


def find_stations_by_ids(session, repeater_ids):
    """Find data for the stations."""
    query = session.query(
        Station
    ).options(
        caching_query.FromCache('default')
    ).filter(
        Station.id.in_(tuple(repeater_ids))
    )
    return query


def find_requests(session, number=None):
    if number:
        query = session.query(
            Request
        ).options(
            caching_query.FromCache('default')
        ).order_by(
            Request.id.desc()
        ).limit(
            number
        )
    else:
        # Get them all.
        query = session.query(
            Request
        ).options(
            caching_query.FromCache('default')
        ).order_by(
            Request.id.desc()
        )

    return query


def invalidate_requests_cache(session):
    """This nukes the cached queries for requests."""
    global cache

    LOG.info("Invalidate requests cache")

    cache.invalidate(
        session.query(Request).order_by(
            Request.id.desc()
        ).limit(25),
        {},
        caching_query.FromCache("default")
    )
    cache.invalidate(
        session.query(Request).order_by(
            Request.id.desc()
        ).limit(50),
        {},
        caching_query.FromCache("default")
    )
    cache.invalidate(
        session.query(Request).order_by(
            Request.id.desc()
        ),
        {},
        caching_query.FromCache("default")
    )


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
