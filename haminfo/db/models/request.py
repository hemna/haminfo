import sqlalchemy as sa
import datetime

from haminfo.db.models.modelbase import ModelBase


class Request(ModelBase):
    __tablename__ = 'request'

    id = sa.Column(sa.Integer, sa.Sequence('request_id_seq'), primary_key=True)
    created = sa.Column(sa.DateTime)
    latitude = sa.Column(sa.Float)
    longitude = sa.Column(sa.Float)
    band = sa.Column(sa.String)
    filters = sa.Column(sa.String)
    count = sa.Column(sa.Integer)
    callsign = sa.Column(sa.String)
    stations = sa.Column(sa.String)
    repeater_ids = sa.Column(sa.String)

    def __repr__(self):
        return (f"<Request(callsign='{self.callsign}', created='{self.created}'"
                f", latitude='{self.latitude}', longitude='{self.longitude}'), "
                f"count='{self.count}' filters='{self.filters}' "
                f"stations='{self.stations}' repeater_ids='{self.repeater_ids}'>")

    def to_dict(self):
        dict_ = {}
        for key in self.__mapper__.c.keys():
            # LOG.debug("KEY {}".format(key))
            dict_[key] = getattr(self, key)
        return dict_

    @staticmethod
    def from_json(r_json):
        r = Request(
            latitude=r_json["lat"],
            longitude=r_json["lon"],
            band=r_json["band"],
            callsign=r_json.get("callsign", "None"),
            count=r_json.get("count", 1),
            filters=r_json.get("filters", "None"),
            stations=r_json.get("stations", "None"),
            repeater_ids=r_json.get("repeater_ids", "None"),
            created=datetime.datetime.now()
        )

        return r


class WXRequest(ModelBase):
    __tablename__ = 'wx_request'

    id = sa.Column(sa.Integer, sa.Sequence('wx_request_id_seq'), primary_key=True)
    created = sa.Column(sa.DateTime)
    latitude = sa.Column(sa.Float)
    longitude = sa.Column(sa.Float)
    count = sa.Column(sa.Integer)
    callsign = sa.Column(sa.String)
    station_callsigns = sa.Column(sa.String)
    wx_station_ids = sa.Column(sa.String)

    def __repr__(self):
        return (f"<WXRequest(callsign='{self.callsign}', created='{self.created}'"
                f", latitude='{self.latitude}', longitude='{self.longitude}'), "
                f"count='{self.count}' callsign='{self.callsign}' "
                f"stations='{self.station_callsigns}' repeater_ids='{self.wx_station_ids}'>")

    def to_dict(self):
        dict_ = {}
        for key in self.__mapper__.c.keys():
            # LOG.debug("KEY {}".format(key))
            dict_[key] = getattr(self, key)
        return dict_

    @staticmethod
    def from_json(r_json):
        r = WXRequest(
            latitude=r_json["lat"],
            longitude=r_json["lon"],
            callsign=r_json.get("callsign", "None"),
            count=r_json.get("count", 1),
            station_callsigns=r_json.get("station_callsigns", "None"),
            wx_station_ids=r_json.get("wx_station_ids", "None"),
            created=datetime.datetime.now()
        )

        return r
