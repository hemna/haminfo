from datetime import datetime

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
    # Timestamp tracking when haminfo last modified this record
    updated_at = sa.Column(
        sa.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return (
            "<Station(callsign='{}', freq='{}', offset='{}', country='{}',"
            "state='{}', county='{}')>".format(
                self.callsign,
                self.frequency,
                self.offset,
                self.country,
                self.state,
                self.county,
            )
        )

    def to_dict(self):
        dict_ = {}
        for key in self.__mapper__.c.keys():
            # LOG.debug("KEY {}".format(key))
            if key == 'last_update':
                dict_[key] = str(getattr(self, key))
            elif key == 'updated_at':
                val = getattr(self, key)
                dict_[key] = str(val) if val else None
            elif (
                key == 'offset'
                or key == 'uplink_offset'
                or key == 'uplink_tone'
                or key == 'downlink_tone'
                or key == 'frequency'
                or key == 'input_frequency'
            ):
                val = getattr(self, key, 0.0)
                if val and utils.isfloat(val):
                    val = float(val)
                else:
                    val = 0.000
                dict_[key] = '{:.4f}'.format(val)
            elif key == 'location':
                # don't include this.
                pass
            else:
                dict_[key] = getattr(self, key)
        return dict_

    @staticmethod
    def find_station_by_ids(session, state_id, repeater_id):
        try:
            station = (
                session.query(Station)
                .filter(
                    sa.and_(
                        Station.state_id == state_id, Station.repeater_id == repeater_id
                    )
                )
                .one()
            )
            return station
        except NoResultFound:
            return None

    @staticmethod
    def find_station_by_callsign(session, callsign):
        try:
            station = session.query(Station).filter(Station.callsign == callsign).one()
            return station
        except NoResultFound:
            return None

    @staticmethod
    def _parse_json_fields(r_json, for_update=False):
        """Parse and normalize common fields from RepeaterBook JSON.

        Returns a dict of field values ready to assign to a Station instance.
        Handles default values and optional fields consistently.

        Args:
            r_json: The JSON data from RepeaterBook API.
            for_update: If True, omit optional boolean fields that are missing
                        from the payload to preserve existing DB values.
        """
        # Normalize invalid date
        last_update = r_json['Last Update']
        if last_update == '0000-00-00':
            last_update = '1970-10-24'

        offset = float(r_json['Input Freq']) - float(r_json['Frequency'])
        freq_band = utils.frequency_band_mhz(float(r_json['Frequency']))

        fields = {
            'last_update': last_update,
            'frequency': r_json['Frequency'],
            'input_frequency': r_json['Input Freq'],
            'offset': offset,
            'freq_band': freq_band,
            'uplink_offset': r_json['PL'],
            'downlink_offset': r_json['TSQ'],
            'lat': r_json['Lat'],
            'long': r_json['Long'],
            'location': 'POINT({} {})'.format(r_json['Long'], r_json['Lat']),
            'callsign': r_json['Callsign'],
            'country': r_json['Country'],
            'nearest_city': r_json['Nearest City'],
            'landmark': r_json['Landmark'],
            'operational_status': r_json['Operational Status'],
            'use': r_json['Use'],
            'allstar_node': utils.bool_from_str(r_json['AllStar Node']),
            'echolink_node': utils.bool_from_str(r_json['EchoLink Node']),
            'irlp_node': utils.bool_from_str(r_json['IRLP Node']),
            'wires_node': utils.bool_from_str(r_json['Wires Node']),
            'fm_analog': utils.bool_from_str(r_json['FM Analog']),
            'dmr': utils.bool_from_str(r_json['DMR']),
            'dstar': utils.bool_from_str(r_json['D-Star']),
        }

        # Optional fields - only include state/county if present
        if 'State' in r_json:
            fields['state'] = r_json['State']
        elif not for_update:
            fields['state'] = None

        if 'County' in r_json:
            fields['county'] = r_json['County']
        elif not for_update:
            fields['county'] = None

        # Optional boolean fields - for updates, only include if present in payload
        # to preserve existing DB values when API omits these fields
        optional_bools = [
            ('ARES', 'ares'),
            ('RACES', 'races'),
            ('SKYWARN', 'skywarn'),
            ('CANWARN', 'canwarn'),
        ]
        for json_key, field_name in optional_bools:
            if json_key in r_json:
                fields[field_name] = utils.bool_from_str(r_json[json_key])
            elif not for_update:
                # For new records, default to False
                fields[field_name] = False
            # For updates with missing keys, don't include in fields dict
            # so existing DB values are preserved

        return fields

    @staticmethod
    def update_from_json(r_json, station):
        """Update an existing Station from RepeaterBook JSON data."""
        if not station:
            return station

        fields = Station._parse_json_fields(r_json, for_update=True)
        for key, value in fields.items():
            setattr(station, key, value)

        return station

    @staticmethod
    def from_json(r_json):
        """Create a new Station from RepeaterBook JSON data."""
        fields = Station._parse_json_fields(r_json, for_update=False)

        # Add primary key fields only present in new records
        fields['state_id'] = r_json['State ID']
        fields['repeater_id'] = r_json['Rptr ID']

        return Station(**fields)
