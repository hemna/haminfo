import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.exc import NoResultFound

from haminfo.db.models.modelbase import ModelBase
from haminfo import utils


class Station(ModelBase):
    __tablename__ = 'station'

    id = sa.Column(sa.Integer, sa.Sequence('station_id_seq'), primary_key=True)
    state_id = sa.Column(sa.String, primary_key=True)
    repeater_id = sa.Column(sa.Integer, primary_key=True)
    last_update = sa.Column(sa.Date)
    frequency = sa.Column(sa.Float(decimal_return_scale=4))
    input_frequency = sa.Column(sa.Float(decimal_return_scale=4))
    freq_band = sa.Column(sa.String)
    offset = sa.Column(sa.Float(decimal_return_scale=4))
    lat = sa.Column(sa.Float)
    long = sa.Column(sa.Float)
    location = sa.Column(Geography('POINT'))
    uplink_offset = sa.Column(sa.String)
    downlink_offset = sa.Column(sa.String)
    uplink_tone = sa.Column(sa.Float(decimal_return_scale=3))
    downlink_tone = sa.Column(sa.Float(decimal_return_scale=3))
    nearest_city = sa.Column(sa.String)
    landmark = sa.Column(sa.String)
    country = sa.Column(sa.String)
    state = sa.Column(sa.String)
    county = sa.Column(sa.String)
    callsign = sa.Column(sa.String)
    use = sa.Column(sa.String)
    operational_status = sa.Column(sa.String)
    ares = sa.Column(sa.Boolean)
    races = sa.Column(sa.Boolean)
    skywarn = sa.Column(sa.Boolean)
    canwarn = sa.Column(sa.Boolean)
    allstar_node = sa.Column(sa.Boolean)
    echolink_node = sa.Column(sa.Boolean)
    irlp_node = sa.Column(sa.Boolean)
    wires_node = sa.Column(sa.Boolean)
    fm_analog = sa.Column(sa.Boolean)
    dmr = sa.Column(sa.Boolean)
    dstar = sa.Column(sa.Boolean)

    def __repr__(self):
        return ("<Station(callsign='{}', freq='{}', offset='{}', country='{}',"
                "state='{}', county='{}')>".format(
                    self.callsign, self.frequency, self.offset,
                    self.country, self.state, self.county)
                )

    def to_dict(self):
        dict_ = {}
        for key in self.__mapper__.c.keys():
            # LOG.debug("KEY {}".format(key))
            if key == 'last_update':
                dict_[key] = str(getattr(self, key))
            elif (key == "offset" or key == "uplink_offset"
                  or key == "uplink_tone" or key == "downlink_tone"
                  or key == "frequency" or key == "input_frequency"):
                val = getattr(self, key, 0.0)
                if val and utils.isfloat(val):
                    val = float(val)
                else:
                    val = 0.000
                dict_[key] = "{:.4f}".format(val)
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
                sa.and_(Station.state_id == state_id,
                        Station.repeater_id == repeater_id)).one()
            return station
        except NoResultFound:
            return None

    @staticmethod
    def find_station_by_callsign(session, callsign):
        try:
            station = session.query(Station).filter(
                Station.callsign == callsign
            ).one()
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
            if 'State' in r_json:
                station.state = r_json["State"]
            if 'County' in r_json:
                station.county = r_json["County"]
            station.nearest_city = r_json["Nearest City"]
            station.landmark = r_json["Landmark"]
            station.operational_status = r_json["Operational Status"]
            station.use = r_json["Use"]
            if 'ARES' in r_json:
                station.ares = utils.bool_from_str(r_json["ARES"])
            if 'RACES' in r_json:
                station.races = utils.bool_from_str(r_json["RACES"])
            if 'SKYWARN' in r_json:
                station.skywarn = utils.bool_from_str(r_json["SKYWARN"])
            if 'CANWARN' in r_json:
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
                     nearest_city=r_json["Nearest City"],
                     landmark=r_json["Landmark"],
                     operational_status=r_json["Operational Status"],
                     use=r_json["Use"],
                     allstar_node=utils.bool_from_str(r_json["AllStar Node"]),
                     echolink_node=utils.bool_from_str(
                         r_json["EchoLink Node"]),
                     irlp_node=utils.bool_from_str(r_json["IRLP Node"]),
                     wires_node=utils.bool_from_str(r_json["Wires Node"]),
                     fm_analog=utils.bool_from_str(r_json["FM Analog"]),
                     dmr=utils.bool_from_str(r_json["DMR"]),
                     dstar=utils.bool_from_str(r_json["D-Star"]))

        if "State" in r_json:
            st.state = r_json["State"]
        if "County" in r_json:
            st.county = r_json["County"]

        if 'ARES' in r_json:
            st.ares = utils.bool_from_str(r_json["ARES"])
        else:
            st.ares = False
        if 'RACES' in r_json:
            st.races = utils.bool_from_str(r_json["RACES"])
        else:
            st.races = False
        if 'SKYWARN' in r_json:
            st.skywarn = utils.bool_from_str(r_json["SKYWARN"])
        else:
            st.skywarn = False
        if 'CANWARN' in r_json:
            st.canwarn = utils.bool_from_str(r_json["CANWARN"])
        else:
            st.canwarn = False
        return st
