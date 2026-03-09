"""Tests for haminfo database models.

Tests the pure-Python logic in model classes: from_json, to_dict, is_valid,
update_from_json, etc. These tests do NOT require a database connection —
they instantiate model objects directly and test their methods.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from haminfo.db.models.station import Station
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo.db.models.aprs_packet import APRSPacket


# ---------------------------------------------------------------------------
# Station model tests
# ---------------------------------------------------------------------------


class TestStationFromJson:
    """Test Station.from_json() factory method."""

    def test_basic_station_from_json(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        assert station is not None
        assert station.callsign == 'W6ABC'
        assert station.state_id == '51'
        assert station.repeater_id == '12345'
        assert station.country == 'United States'
        assert station.state == 'California'
        assert station.county == 'San Francisco'
        assert station.nearest_city == 'San Francisco'
        assert station.landmark == 'Twin Peaks'
        assert station.operational_status == 'On-air'
        assert station.use == 'OPEN'

    def test_frequency_and_offset(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        # Frequency is stored as-is from JSON (string); DB column coerces to float
        assert float(station.frequency) == pytest.approx(146.940, abs=0.001)
        assert float(station.input_frequency) == pytest.approx(146.340, abs=0.001)
        # offset = input - frequency
        expected_offset = float('146.340') - float('146.940')
        assert float(station.offset) == pytest.approx(expected_offset, abs=0.001)

    def test_freq_band_calculated(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        # 146.940 MHz is in the 2m band (144-148 MHz)
        assert station.freq_band == '2m'

    def test_boolean_fields(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        assert station.ares is True
        assert station.races is False
        assert station.skywarn is True
        assert station.canwarn is False
        assert station.fm_analog is True
        assert station.dmr is False
        assert station.dstar is False
        assert station.allstar_node is False
        assert station.echolink_node is False
        assert station.irlp_node is False
        assert station.wires_node is False

    def test_location_point(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        # Location should be POINT(long lat) format
        assert 'POINT(' in station.location
        assert '-122.4194' in station.location
        assert '37.7749' in station.location

    def test_zero_date_becomes_epoch(self, sample_repeater_json):
        sample_repeater_json['Last Update'] = '0000-00-00'
        station = Station.from_json(sample_repeater_json)
        assert station.last_update == '1970-10-24'

    def test_missing_state_field(self, sample_repeater_json):
        del sample_repeater_json['State']
        station = Station.from_json(sample_repeater_json)
        # state should not be set (default None)
        assert station.state is None

    def test_missing_county_field(self, sample_repeater_json):
        del sample_repeater_json['County']
        station = Station.from_json(sample_repeater_json)
        assert station.county is None

    def test_missing_ares_races_fields(self):
        """Test that missing optional boolean fields default to False."""
        json_data = {
            'State ID': '10',
            'Rptr ID': '99',
            'Last Update': '2024-06-01',
            'Frequency': '444.000',
            'Input Freq': '449.000',
            'PL': '100.0',
            'TSQ': '',
            'Lat': '40.0',
            'Long': '-75.0',
            'Callsign': 'N3TEST',
            'Country': 'United States',
            'Nearest City': 'Philadelphia',
            'Landmark': '',
            'Operational Status': 'On-air',
            'Use': 'OPEN',
            'AllStar Node': 'No',
            'EchoLink Node': 'No',
            'IRLP Node': 'No',
            'Wires Node': 'No',
            'FM Analog': 'Yes',
            'DMR': 'Yes',
            'D-Star': 'No',
            # No ARES, RACES, SKYWARN, CANWARN
        }
        station = Station.from_json(json_data)
        assert station.ares is False
        assert station.races is False
        assert station.skywarn is False
        assert station.canwarn is False


class TestStationUpdateFromJson:
    """Test Station.update_from_json() method."""

    def test_update_existing_station(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        # Modify the JSON
        sample_repeater_json['Callsign'] = 'W6XYZ'
        sample_repeater_json['Frequency'] = '147.000'
        sample_repeater_json['Input Freq'] = '147.600'
        updated = Station.update_from_json(sample_repeater_json, station)
        assert updated.callsign == 'W6XYZ'
        # Frequency is stored as-is from JSON; DB column coerces to float on insert
        assert float(updated.frequency) == pytest.approx(147.000, abs=0.001)
        assert float(updated.input_frequency) == pytest.approx(147.600, abs=0.001)

    def test_update_returns_same_object(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        updated = Station.update_from_json(sample_repeater_json, station)
        assert updated is station


class TestStationToDict:
    """Test Station.to_dict() serialization."""

    def test_to_dict_keys(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        d = station.to_dict()
        assert 'callsign' in d
        assert 'frequency' in d
        assert 'country' in d
        assert 'state' in d
        # location should NOT be in the dict
        assert 'location' not in d

    def test_to_dict_frequency_format(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        d = station.to_dict()
        # Frequencies should be formatted with 4 decimal places
        assert '.' in d['frequency']

    def test_to_dict_last_update_is_string(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        d = station.to_dict()
        assert isinstance(d['last_update'], str)


class TestStationRepr:
    """Test Station.__repr__() method."""

    def test_repr(self, sample_repeater_json):
        station = Station.from_json(sample_repeater_json)
        r = repr(station)
        assert 'Station' in r
        assert 'W6ABC' in r
        assert 'United States' in r


# ---------------------------------------------------------------------------
# WeatherStation model tests
# ---------------------------------------------------------------------------


class TestWeatherStationFromJson:
    """Test WeatherStation.from_json() factory method."""

    def test_basic_weather_station(self):
        data = {
            'from_call': 'WX4TEST',
            'latitude': 34.9463,
            'longitude': -123.7612,
            'comment': 'Weather Station',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        assert station is not None
        assert station.callsign == 'WX4TEST'
        assert station.latitude == 34.9463
        assert station.longitude == -123.7612
        assert station.comment == 'Weather Station'
        assert station.symbol == '_'
        assert station.symbol_table == '/'

    def test_location_point_format(self):
        data = {
            'from_call': 'WX5LOC',
            'latitude': 40.0,
            'longitude': -75.0,
            'comment': 'test',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        assert 'POINT(-75.0 40.0)' in station.location

    def test_null_bytes_stripped(self):
        data = {
            'from_call': 'WX\x004TEST',
            'latitude': 34.0,
            'longitude': -123.0,
            'comment': 'test\x00comment',
            'symbol': '_\x00',
            'symbol_table': '/\x00',
        }
        station = WeatherStation.from_json(data)
        assert '\x00' not in station.callsign
        assert station.callsign == 'WX4TEST'
        assert '\x00' not in station.comment

    def test_missing_latitude_returns_none(self):
        data = {
            'from_call': 'WX4TEST',
            'longitude': -123.0,
            'comment': 'test',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        assert station is None

    def test_missing_longitude_returns_none(self):
        data = {
            'from_call': 'WX4TEST',
            'latitude': 34.0,
            'comment': 'test',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        assert station is None

    def test_to_dict(self):
        data = {
            'from_call': 'WX4DICT',
            'latitude': 35.0,
            'longitude': -120.0,
            'comment': 'dict test',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        d = station.to_dict()
        assert d['callsign'] == 'WX4DICT'
        assert d['latitude'] == 35.0
        assert d['longitude'] == -120.0
        assert 'id' in d
        assert 'symbol' in d

    def test_repr(self):
        data = {
            'from_call': 'WX4REPR',
            'latitude': 35.0,
            'longitude': -120.0,
            'comment': 'repr test',
            'symbol': '_',
            'symbol_table': '/',
        }
        station = WeatherStation.from_json(data)
        r = repr(station)
        assert 'WeatherStation' in r
        assert 'WX4REPR' in r


# ---------------------------------------------------------------------------
# WeatherReport model tests
# ---------------------------------------------------------------------------


class TestWeatherReportFromJson:
    """Test WeatherReport.from_json() factory method."""

    def test_basic_report(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 90,
            'wind_speed': 5.0,
            'wind_gust': 10.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'WX4TEST>APRS:_test_raw_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report is not None
        assert report.temperature == 72.0
        assert report.humidity == 50
        assert report.pressure == 1013.2
        assert report.wind_direction == 90
        assert report.wind_speed == 5.0
        assert report.wind_gust == 10.0
        assert report.rain_1h == 0.0
        assert report.rain_24h == 0.0
        assert report.rain_since_midnight == 0.0
        assert report.weather_station_id == 1

    def test_missing_timestamp_uses_current(self):
        data = {
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 0,
            'wind_speed': 0.0,
            'wind_gust': 0.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'test_raw',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.time is not None

    def test_null_bytes_stripped_from_raw(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 0,
            'wind_speed': 0.0,
            'wind_gust': 0.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'test\x00raw\x00packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert '\x00' not in report.raw_report

    def test_default_values_when_missing(self):
        data = {
            'timestamp': 1704844800,
            'raw': 'minimal_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.temperature == 0
        assert report.humidity == 0
        assert report.pressure == 0
        assert report.wind_direction == 0
        assert report.wind_speed == 0.00
        assert report.wind_gust == 0.00


class TestWeatherReportIsValid:
    """Test WeatherReport.is_valid() method."""

    def test_valid_report(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 90,
            'wind_speed': 5.0,
            'wind_gust': 10.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'valid_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.is_valid() is True

    def test_all_zeros_is_invalid(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 0,
            'humidity': 0,
            'pressure': 0,
            'wind_direction': 0,
            'wind_speed': 0,
            'wind_gust': 0,
            'rain_1h': 0,
            'rain_24h': 0,
            'rain_since_midnight': 0,
            'raw': 'zero_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.is_valid() is False

    def test_only_temperature_nonzero_is_valid(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 32.0,
            'humidity': 0,
            'pressure': 0,
            'wind_direction': 0,
            'wind_speed': 0,
            'wind_gust': 0,
            'rain_1h': 0,
            'rain_24h': 0,
            'rain_since_midnight': 0,
            'raw': 'temp_only',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.is_valid() is True

    def test_only_rain_nonzero_is_valid(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 0,
            'humidity': 0,
            'pressure': 0,
            'wind_direction': 0,
            'wind_speed': 0,
            'wind_gust': 0,
            'rain_1h': 0.5,
            'rain_24h': 0,
            'rain_since_midnight': 0,
            'raw': 'rain_only',
        }
        report = WeatherReport.from_json(data, station_id=1)
        assert report.is_valid() is True


class TestWeatherReportToDict:
    """Test WeatherReport.to_dict() serialization."""

    def test_to_dict_keys(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 90,
            'wind_speed': 5.0,
            'wind_gust': 10.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'dict_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        d = report.to_dict()
        assert 'temperature' in d
        assert 'humidity' in d
        assert 'pressure' in d
        assert 'time' in d
        assert 'raw_report' in d

    def test_to_dict_time_is_string(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 0,
            'wind_speed': 0,
            'wind_gust': 0,
            'rain_1h': 0,
            'rain_24h': 0,
            'rain_since_midnight': 0,
            'raw': 'time_test',
        }
        report = WeatherReport.from_json(data, station_id=1)
        d = report.to_dict()
        assert isinstance(d['time'], str)


class TestWeatherReportRepr:
    """Test WeatherReport.__repr__() method."""

    def test_repr(self):
        data = {
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 90,
            'wind_speed': 5.0,
            'wind_gust': 10.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
            'raw': 'repr_packet',
        }
        report = WeatherReport.from_json(data, station_id=1)
        r = repr(report)
        assert 'WeatherReport' in r
        assert '72.0' in r


# ---------------------------------------------------------------------------
# APRSPacket model tests
# ---------------------------------------------------------------------------


class TestAPRSPacketFromJson:
    """Test APRSPacket.from_json() factory method."""

    def test_position_packet(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        assert packet is not None
        assert packet.from_call == 'N0CALL'
        assert packet.to_call == 'APRS'
        assert packet.packet_type == 'position'
        assert packet.latitude == 34.9463
        assert packet.longitude == -123.7612
        assert packet.symbol == '-'
        assert packet.symbol_table == '/'
        assert packet.comment == 'PHG2360'
        assert 'N0CALL' in packet.raw

    def test_weather_packet_type_detection(self):
        data = {
            'from_call': 'WX4AUTO',
            'to_call': 'APRS',
            'raw': 'WX4AUTO>APRS:weather',
            'timestamp': 1704844800,
            'latitude': 35.0,
            'longitude': -120.0,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'weather'

    def test_message_packet_type_detection(self):
        """Message packets are detected by type but fields not stored (lean schema)."""
        data = {
            'from_call': 'N0MSG',
            'to_call': 'APRS',
            'raw': 'N0MSG>APRS:message',
            'timestamp': 1704844800,
            'message_text': 'Hello World',
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'message'
        # message_text not stored in lean schema, raw packet preserved
        assert 'message' in packet.raw

    def test_status_packet_type_detection(self):
        """Status packets are detected by type but fields not stored (lean schema)."""
        data = {
            'from_call': 'N0STS',
            'to_call': 'APRS',
            'raw': 'N0STS>APRS:>status',
            'timestamp': 1704844800,
            'status': 'Operating portable',
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'status'
        # status field not stored in lean schema

    def test_telemetry_packet_type_detection(self):
        """Telemetry packets are detected by type but fields not stored (lean schema)."""
        data = {
            'from_call': 'N0TEL',
            'to_call': 'APRS',
            'raw': 'N0TEL>APRS:telemetry',
            'timestamp': 1704844800,
            'telemetry_analog': '[1, 2, 3]',
            'telemetry_digital': '10101010',
            'telemetry_sequence': 42,
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'telemetry'
        # telemetry fields not stored in lean schema

    def test_object_packet_type_detection(self):
        """Object packets are detected by type but fields not stored (lean schema)."""
        data = {
            'from_call': 'N0OBJ',
            'to_call': 'APRS',
            'raw': 'N0OBJ>APRS:object',
            'timestamp': 1704844800,
            'object_name': 'HAMFEST',
            'latitude': 35.0,
            'longitude': -120.0,
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'object'
        # object_name not stored but position data is preserved
        assert packet.latitude == 35.0
        assert packet.longitude == -120.0

    def test_query_packet_type_detection(self):
        """Query packets are detected by type but fields not stored (lean schema)."""
        data = {
            'from_call': 'N0QRY',
            'to_call': 'APRS',
            'raw': 'N0QRY>APRS:query',
            'timestamp': 1704844800,
            'query_type': 'POSITION',
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'query'
        # query fields not stored in lean schema

    def test_unknown_packet_type_fallback(self):
        data = {
            'from_call': 'N0UNK',
            'to_call': 'APRS',
            'raw': 'N0UNK>APRS:unknown',
            'timestamp': 1704844800,
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'unknown'

    def test_explicit_packet_type_overrides_detection(self):
        data = {
            'from_call': 'N0OVR',
            'to_call': 'APRS',
            'raw': 'N0OVR>APRS:override',
            'timestamp': 1704844800,
            'packet_type': 'custom-type',
            'temperature': 72.0,  # Would normally trigger "weather"
        }
        packet = APRSPacket.from_json(data)
        assert packet.packet_type == 'custom-type'

    def test_location_point_created(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        assert packet.location is not None
        assert 'POINT(' in packet.location
        assert '-123.7612' in packet.location

    def test_no_location_when_no_coords(self):
        data = {
            'from_call': 'N0LOC',
            'to_call': 'APRS',
            'raw': 'N0LOC>APRS:noloc',
            'timestamp': 1704844800,
        }
        packet = APRSPacket.from_json(data)
        assert packet.location is None
        assert packet.latitude is None
        assert packet.longitude is None

    def test_null_bytes_stripped(self):
        data = {
            'from_call': 'N0\x00CALL',
            'to_call': 'AP\x00RS',
            'raw': 'raw\x00data',
            'timestamp': 1704844800,
            'comment': 'test\x00comment',
        }
        packet = APRSPacket.from_json(data)
        assert '\x00' not in packet.from_call
        assert '\x00' not in packet.to_call
        assert '\x00' not in packet.raw
        assert '\x00' not in packet.comment

    def test_timestamp_from_int(self):
        data = {
            'from_call': 'N0TS',
            'to_call': 'APRS',
            'raw': 'N0TS>APRS:ts',
            'timestamp': 1704844800,
        }
        packet = APRSPacket.from_json(data)
        assert isinstance(packet.timestamp, datetime)
        assert packet.timestamp.year == 2024

    def test_timestamp_from_float(self):
        data = {
            'from_call': 'N0TS',
            'to_call': 'APRS',
            'raw': 'N0TS>APRS:ts',
            'timestamp': 1704844800.5,
        }
        packet = APRSPacket.from_json(data)
        assert isinstance(packet.timestamp, datetime)

    def test_missing_timestamp_uses_current(self):
        data = {
            'from_call': 'N0TS',
            'to_call': 'APRS',
            'raw': 'N0TS>APRS:ts',
        }
        packet = APRSPacket.from_json(data)
        # Should get a recent time (within last few seconds)
        assert packet.timestamp is not None

    def test_received_at_set(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        assert packet.received_at is not None

    def test_weather_packet_type_detected(self):
        """Weather packets detected by type, fields not stored (lean schema)."""
        data = {
            'from_call': 'WX4FULL',
            'to_call': 'APRS',
            'raw': 'WX4FULL>APRS:wx',
            'timestamp': 1704844800,
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'latitude': 35.0,
            'longitude': -120.0,
        }
        packet = APRSPacket.from_json(data)
        # Type detection still works
        assert packet.packet_type == 'weather'
        # Position data preserved for weather packets
        assert packet.latitude == 35.0
        assert packet.longitude == -120.0
        # Weather fields not stored in lean schema - raw preserved
        assert packet.raw is not None

    def test_position_metadata_fields(self):
        """Position-related metadata fields are preserved in lean schema."""
        data = {
            'from_call': 'N0META',
            'to_call': 'APRS',
            'raw': 'N0META>APRS:meta',
            'timestamp': 1704844800,
            'latitude': 35.0,
            'longitude': -120.0,
            'altitude': 150.0,
            'course': 270,
            'speed': 55.0,
            'symbol': '-',
            'symbol_table': '/',
            'comment': 'Test comment',
        }
        packet = APRSPacket.from_json(data)
        # Position fields preserved
        assert packet.altitude == 150.0
        assert packet.course == 270
        assert packet.speed == 55.0
        assert packet.symbol == '-'
        assert packet.symbol_table == '/'
        assert packet.comment == 'Test comment'


class TestAPRSPacketToDict:
    """Test APRSPacket.to_dict() serialization."""

    def test_to_dict_basic(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        d = packet.to_dict()
        assert 'from_call' in d
        assert 'to_call' in d
        assert 'raw' in d
        assert 'packet_type' in d
        assert d['from_call'] == 'N0CALL'

    def test_to_dict_datetime_is_string(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        d = packet.to_dict()
        # datetime fields should be ISO format strings
        assert isinstance(d['timestamp'], str)
        assert isinstance(d['received_at'], str)


class TestAPRSPacketRepr:
    """Test APRSPacket.__repr__() method."""

    def test_repr(self, sample_aprs_packet):
        packet = APRSPacket.from_json(sample_aprs_packet)
        r = repr(packet)
        assert 'APRSPacket' in r
        assert 'N0CALL' in r
        assert 'position' in r
