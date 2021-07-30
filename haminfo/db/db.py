from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy import create_engine
from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry
from sqlalchemy.orm import sessionmaker

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

database_opts = [
    cfg.StrOpt('connection',
               help='The SQLAlchemy connection string to use to connect to '
                    'the database.',
               secret=True,
               deprecated_opts=[cfg.DeprecatedOpt('sql_connection',
                                                  group='DEFAULT'),
                                cfg.DeprecatedOpt('sql_connection',
                                                  group='DATABASE'),
                                cfg.DeprecatedOpt('connection',
                                                  group='sql'), ]),
]

CONF.register_opts(database_opts, group='database')

Base = declarative_base()


class Station(Base):
    __tablename__ = 'station'

    id = Column(Integer, primary_key=True)
    state_id = Column(String)
    repeater_id = Column(Integer)
    frequency = Column(String)
    input_frequency = Column(String)
    lat = Column(Float)
    long = Column(Float)
    point = Column(Geometry('POINT'))
    pl = Column(String)
    tsq = Column(String)
    uplink_tone = Column(Float)
    downlink_tone = Column(Float)
    location = Column(String)
    county = Column(String)
    callsign = Column(String)
    use = Column(String)
    operating_status = Column(String)
    mode = Column(String)
    ares = Column(Boolean)
    races = Column(Boolean)
    skywarn = Column(Boolean)
    canwarn = Column(Boolean)
    allstar_node = Column(Boolean)
    echolink_node = Column(Boolean)
    irlp_node = Column(Boolean)
    wires_node = Column(Boolean)
    fm_analog = Column(Boolean)
    dmr = Column(Boolean)
    dstar = Column(Boolean)

    @staticmethod
    def _from_json(r_json):
        st = Station(state_id=r_json["State ID"], repeater_id=r_json["Rptr ID"],
                     frequency=r_json["Frequency"], input_frequency=r_json["Input Freq"],
                     pl=r_json["PL"], tsq=r_json["TSQ"],
                     lat=r_json["Lat"], long=r_json["Long"],
                     point="POINT({} {})".format(r_json['Lat'], r_json['Long']),
                     callsign=r_json["Callsign"])
        return st


def setup():
    connection_str = 'postgresql://haminfo:haminfo@192.168.1.5/haminfo'
    #engine = create_engine('sqlite:///:memory:', echo=True)
    engine = create_engine(connection_str, echo=True)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session
