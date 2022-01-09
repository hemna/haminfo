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

    def __repr__(self):
        return (f"<Request(callsign='{self.callsign}', created='{self.created}'"
                f", latitude='{self.latitude}', longitude='{self.longitude}'), "
                f"count='{self.count}' filters='{self.filters}' "
                f"stations='{self.stations}'>")

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
            created=datetime.datetime.now()
        )

        return r
