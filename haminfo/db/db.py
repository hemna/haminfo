from oslo_config import cfg
from oslo_log import log as logging
import sqlalchemy
from sqlalchemy import create_engine, func, and_
from sqlalchemy import Boolean, Column, Date, Float, Integer, String, Sequence
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geography
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound

from haminfo import utils

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
Base = declarative_base()


def init_db_schema(engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


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


def find_nearest_to(session, lat, lon, freq_band="2m", limit=1):
    poi = 'SRID=4326;POINT({} {})'.format(lon, lat)
    poi_point = func.ST_Point(lon, lat)
    query = session.query(
        Station,
        func.ST_Distance(Station.location, poi).label('distance'),
        func.ST_Azimuth(poi_point, func.ST_Point(Station.long, Station.lat)
                        ).label('bearing')
    ).filter(
        Station.freq_band == freq_band
    ).order_by(
        Station.location.distance_centroid(poi)
    ).limit(limit)
    # SELECT station.id, station.callsign, station.landmark,
    #        station.nearest_city, station.county,
    #    ST_Distance(station.location, 'SRID=4326;POINT(-78.84950 37.34433)') /
    #                1609 as dist
    # FROM station ORDER BY
    #    station.location <-> 'SRID=4326;POINT(-78.84950 37.34433)'::geometry
    # LIMIT 10;
    return query


class Station(Base):
    __tablename__ = 'station'

    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    state_id = Column(Integer, primary_key=True)
    repeater_id = Column(Integer, primary_key=True)
    last_update = Column(Date)
    frequency = Column(Float(decimal_return_scale=3))
    input_frequency = Column(Float(decimal_return_scale=3))
    freq_band = Column(String)
    offset = Column(Float(decimal_return_scale=3))
    lat = Column(Float)
    long = Column(Float)
    location = Column(Geography('POINT'))
    uplink_offset = Column(String)
    downlink_offset = Column(String)
    uplink_tone = Column(Float(decimal_return_scale=2))
    downlink_tone = Column(Float(decimal_return_scale=2))
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

    def __repr__(self):
        return ("<Station(callsign='{}', freq='{}', offset='{}', country='{}',"
                "state='{}', county='{}')>".format(
                    self.callsign, self.frequency, self.offset,
                    self.country, self.state, self.county))

    def to_dict(self):
        dict_ = {}
        for key in self.__mapper__.c.keys():
            # LOG.debug("KEY {}".format(key))
            if key == 'last_update':
                dict_[key] = str(getattr(self, key))
            elif key == "offset":
                dict_[key] = "{:.2f}".format(float(getattr(self, key)))
            elif key == 'location':
                # don't include this.
                pass
            else:
                dict_[key] = getattr(self, key)
        return dict_

    @staticmethod
    def find_station_by_ids(session, state_id, repeater_id):
        try:
            station = session.query(Station).filter(
                and_(Station.state_id == state_id,
                     Station.repeater_id == repeater_id)).one()
            return station
        except NoResultFound:
            return None

    @staticmethod
    def update_from_json(r_json, station):
        if r_json["Last Update"] == "0000-00-00":
            # no last update time?
            r_json["Last Update"] = "1970-10-24"

        offset = float(r_json["Input Freq"]) - float(r_json["Frequency"])

        freq_band = utils.frequency_band_mhz(float(r_json["Frequency"]))

        if station:
            station.last_update = r_json["Last Update"]
            station.frequency = r_json["Frequency"]
            station.input_frequency = r_json["Input Freq"]
            station.offset = offset
            station.freq_band = freq_band
            station.uplink_offset = r_json["PL"]
            station.downlink_offset = r_json["TSQ"]
            station.lat = r_json["Lat"]
            station.long = r_json["Long"]
            station.location = "POINT({} {})".format(r_json['Long'],
                                                     r_json['Lat'])
            station.callsign = r_json["Callsign"]
            station.country = r_json["Country"]
            station.state = r_json["State"]
            station.county = r_json["County"]
            station.nearest_city = r_json["Nearest City"]
            station.landmark = r_json["Landmark"]
            station.operational_status = r_json["Operational Status"]
            station.use = r_json["Use"]
            station.ares = utils.bool_from_str(r_json["ARES"])
            station.races = utils.bool_from_str(r_json["RACES"])
            station.skywarn = utils.bool_from_str(r_json["SKYWARN"])
            station.canwarn = utils.bool_from_str(r_json["CANWARN"])
            station.allstar_node = utils.bool_from_str(r_json["AllStar Node"])
            station.echolink_node = utils.bool_from_str(
                r_json["EchoLink Node"])
            station.irlp_node = utils.bool_from_str(r_json["IRLP Node"])
            station.wires_node = utils.bool_from_str(r_json["Wires Node"])
            station.fm_analog = utils.bool_from_str(r_json["FM Analog"])
            station.dmr = utils.bool_from_str(r_json["DMR"])
            station.dstar = utils.bool_from_str(r_json["D-Star"])
        return station

    @staticmethod
    def from_json(r_json):

        if r_json["Last Update"] == "0000-00-00":
            # no last update time?
            r_json["Last Update"] = "1970-10-24"

        offset = float(r_json["Input Freq"]) - float(r_json["Frequency"])

        freq_band = utils.frequency_band_mhz(float(r_json["Frequency"]))

        st = Station(state_id=r_json["State ID"],
                     repeater_id=r_json["Rptr ID"],
                     last_update=r_json["Last Update"],
                     frequency=r_json["Frequency"],
                     input_frequency=r_json["Input Freq"],
                     offset=offset,
                     freq_band=freq_band,
                     uplink_offset=r_json["PL"],
                     downlink_offset=r_json["TSQ"],
                     lat=r_json["Lat"],
                     long=r_json["Long"],
                     location="POINT({} {})".format(r_json['Long'],
                                                    r_json['Lat']),
                     callsign=r_json["Callsign"],
                     country=r_json["Country"],
                     state=r_json["State"],
                     county=r_json["County"],
                     nearest_city=r_json["Nearest City"],
                     landmark=r_json["Landmark"],
                     operational_status=r_json["Operational Status"],
                     use=r_json["Use"],
                     ares=utils.bool_from_str(r_json["ARES"]),
                     races=utils.bool_from_str(r_json["RACES"]),
                     skywarn=utils.bool_from_str(r_json["SKYWARN"]),
                     canwarn=utils.bool_from_str(r_json["CANWARN"]),
                     allstar_node=utils.bool_from_str(r_json["AllStar Node"]),
                     echolink_node=utils.bool_from_str(
                         r_json["EchoLink Node"]),
                     irlp_node=utils.bool_from_str(r_json["IRLP Node"]),
                     wires_node=utils.bool_from_str(r_json["Wires Node"]),
                     fm_analog=utils.bool_from_str(r_json["FM Analog"]),
                     dmr=utils.bool_from_str(r_json["DMR"]),
                     dstar=utils.bool_from_str(r_json["D-Star"]))
        return st
