from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy import create_engine
from sqlalchemy import Boolean, Column, Date, Float, Integer, String
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry
from sqlalchemy.orm import sessionmaker

#LOG = logging.getLogger(__name__)
CONF = cfg.CONF

grp = cfg.OptGroup('database')
cfg.CONF.register_group(grp)
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

CONF.register_opts(database_opts, group="database")
Base = declarative_base()


class Station(Base):
    __tablename__ = 'station'

    state_id = Column(String, primary_key=True)
    repeater_id = Column(Integer, primary_key=True)
    last_update = Column(Date)
    frequency = Column(String)
    input_frequency = Column(String)
    offset = Column(String)
    lat = Column(Float)
    long = Column(Float)
    point = Column(Geometry('POINT'))
    uplink_offset = Column(String)
    downlink_offset = Column(String)
    uplink_tone = Column(Float)
    downlink_tone = Column(Float)
    nearest_city = Column(String)
    landmark = Column(String)
    country = Column(String)
    state = Column(String)
    county = Column(String)
    callsign = Column(String)
    use = Column(String)
    operational_status = Column(String)
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

        def _bool(bool_str):
            if bool_str == "No":
                return False
            else:
                return True

        if r_json["Last Update"] == "0000-00-00":
            # no last update time?
            r_json["Last Update"] = "1970-10-24"

        offset = float(r_json["Input Freq"]) - float(r_json["Frequency"])

        st = Station(state_id=r_json["State ID"], repeater_id=r_json["Rptr ID"],
                     last_update=r_json["Last Update"],
                     frequency=r_json["Frequency"], input_frequency=r_json["Input Freq"],
                     offset=offset,
                     uplink_offset=r_json["PL"], downlink_offset=r_json["TSQ"],
                     lat=r_json["Lat"], long=r_json["Long"],
                     point="POINT({} {})".format(r_json['Lat'], r_json['Long']),
                     callsign=r_json["Callsign"],
                     country=r_json["Country"], state=r_json["State"], county=r_json["County"],
                     nearest_city=r_json["Nearest City"], landmark=r_json["Landmark"],
                     operational_status=r_json["Operational Status"], use=r_json["Use"],
                     ares=_bool(r_json["ARES"]), races=_bool(r_json["RACES"]), skywarn=_bool(r_json["SKYWARN"]),
                     canwarn=_bool(r_json["CANWARN"]), allstar_node=_bool(r_json["AllStar Node"]),
                     echolink_node=_bool(r_json["EchoLink Node"]), irlp_node=_bool(r_json["IRLP Node"]),
                     wires_node=_bool(r_json["Wires Node"]), fm_analog=_bool(r_json["FM Analog"]),
                     dmr=_bool(r_json["DMR"]), dstar=_bool(r_json["D-Star"]))
        return st

def init_db_schema(engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

def setup_connection():
    connection_str = 'postgresql://haminfo:haminfo@192.168.1.5/haminfo'
    #engine = create_engine('sqlite:///:memory:', echo=True)
    engine = create_engine(connection_str, echo=False)
    return engine

def setup_session(engine):
    return sessionmaker(bind=engine)
