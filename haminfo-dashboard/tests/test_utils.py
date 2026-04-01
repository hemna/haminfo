# tests/test_utils.py
"""Tests for utility functions."""

import pytest
from haminfo_dashboard.utils import (
    get_country_from_callsign,
    format_packet_summary,
    normalize_packet_type,
)


class TestGetCountryFromCallsign:
    """Tests for get_country_from_callsign function."""

    def test_us_callsigns(self):
        """Test US callsign prefixes."""
        assert get_country_from_callsign('W1ABC') == ('US', 'United States')
        assert get_country_from_callsign('K1ABC') == ('US', 'United States')
        assert get_country_from_callsign('N1ABC') == ('US', 'United States')
        assert get_country_from_callsign('AA1ABC') == ('US', 'United States')

    def test_malaysia_callsigns(self):
        """Test Malaysian callsign prefixes."""
        assert get_country_from_callsign('9M2PJU') == ('MY', 'Malaysia')
        assert get_country_from_callsign('9W2ABC') == ('MY', 'Malaysia')

    def test_australia_callsigns(self):
        """Test Australian callsign prefixes."""
        assert get_country_from_callsign('VK3ABC') == ('AU', 'Australia')

    def test_japan_callsigns(self):
        """Test Japanese callsign prefixes."""
        assert get_country_from_callsign('JA1ABC') == ('JP', 'Japan')
        assert get_country_from_callsign('JH1ABC') == ('JP', 'Japan')

    def test_uk_callsigns(self):
        """Test UK callsign prefixes."""
        assert get_country_from_callsign('G3ABC') == ('GB', 'United Kingdom')
        assert get_country_from_callsign('M0ABC') == ('GB', 'United Kingdom')

    def test_germany_callsigns(self):
        """Test German callsign prefixes."""
        assert get_country_from_callsign('DL1ABC') == ('DE', 'Germany')
        assert get_country_from_callsign('DO1ABC') == ('DE', 'Germany')

    def test_ssid_stripping(self):
        """Test that SSID suffix is stripped."""
        assert get_country_from_callsign('9M2PJU-9') == ('MY', 'Malaysia')
        assert get_country_from_callsign('W1ABC-15') == ('US', 'United States')

    def test_case_insensitivity(self):
        """Test that matching is case-insensitive."""
        assert get_country_from_callsign('w1abc') == ('US', 'United States')
        assert get_country_from_callsign('9m2pju') == ('MY', 'Malaysia')

    def test_unknown_callsign(self):
        """Test unknown callsign returns None."""
        assert get_country_from_callsign('XY1ABC') is None
        assert get_country_from_callsign('') is None
        assert get_country_from_callsign(None) is None


class TestFormatPacketSummary:
    """Tests for format_packet_summary function."""

    def test_position_packet_with_speed(self):
        """Test formatting position packet with speed."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'position',
            'latitude': 42.1234,
            'longitude': -71.5678,
            'speed': 60,
        }
        result = format_packet_summary(packet)
        assert '42.1234' in result
        assert '-71.5678' in result
        assert '60km/h' in result

    def test_position_packet_without_speed(self):
        """Test formatting position packet without speed."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'position',
            'latitude': 42.1234,
            'longitude': -71.5678,
        }
        result = format_packet_summary(packet)
        assert '42.1234' in result
        assert '-71.5678' in result
        assert 'km/h' not in result

    def test_weather_packet(self):
        """Test formatting weather packet."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'weather',
            'temperature': 25,
            'humidity': 65,
        }
        result = format_packet_summary(packet)
        assert 'Weather' in result
        assert '25' in result
        assert '65' in result

    def test_status_packet(self):
        """Test formatting status packet."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'status',
            'comment': 'Hello world',
        }
        result = format_packet_summary(packet)
        assert 'Status' in result
        assert 'Hello world' in result

    def test_message_packet(self):
        """Test formatting message packet."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'message',
            'to_call': 'W2DEF',
        }
        result = format_packet_summary(packet)
        assert 'Message' in result
        assert 'W2DEF' in result

    def test_telemetry_packet_type(self):
        """Test formatting telemetry packet type."""
        packet = {
            'from_call': 'W1ABC',
            'packet_type': 'telemetry',
        }
        result = format_packet_summary(packet)
        assert 'Telemetry' in result


class TestNormalizePacketType:
    """Tests for normalize_packet_type function."""

    def test_beacon_with_position_becomes_position(self):
        """Beacon packets with coordinates should become position."""
        result = normalize_packet_type('beacon', latitude=47.785, longitude=11.967)
        assert result == 'position'

    def test_beacon_without_position_stays_beacon(self):
        """Beacon packets without coordinates should stay beacon."""
        result = normalize_packet_type('beacon', latitude=None, longitude=None)
        assert result == 'beacon'

    def test_telemetry_message_becomes_telemetry(self):
        """Telemetry-message should be normalized to telemetry."""
        result = normalize_packet_type('telemetry-message')
        assert result == 'telemetry'

    def test_bulletin_becomes_message(self):
        """Bulletin packets should become message."""
        result = normalize_packet_type('bulletin')
        assert result == 'message'

    def test_unknown_with_position_becomes_position(self):
        """Unknown packets with coordinates should become position."""
        result = normalize_packet_type('unknown', latitude=47.785, longitude=11.967)
        assert result == 'position'

    def test_unknown_without_position_stays_unknown(self):
        """Unknown packets without coordinates should stay unknown."""
        result = normalize_packet_type('unknown')
        assert result == 'unknown'

    def test_position_unchanged(self):
        """Position type should pass through unchanged."""
        result = normalize_packet_type('position', latitude=47.785, longitude=11.967)
        assert result == 'position'

    def test_weather_unchanged(self):
        """Weather type should pass through unchanged."""
        result = normalize_packet_type('weather')
        assert result == 'weather'

    def test_message_unchanged(self):
        """Message type should pass through unchanged."""
        result = normalize_packet_type('message')
        assert result == 'message'

    def test_none_becomes_unknown(self):
        """None packet_type should become unknown."""
        result = normalize_packet_type(None)
        assert result == 'unknown'

    def test_beacon_with_raw_packet_fallback(self):
        """Beacon without lat/lon should parse raw packet to get position."""
        raw = 'SP2ROC-14>APLRFD:!5246.08N/01855.98E#LoRa APRS Digi'
        result = normalize_packet_type('beacon', latitude=None, longitude=None, raw=raw)
        assert result == 'position'

    def test_unknown_with_raw_packet_fallback(self):
        """Unknown without lat/lon should parse raw packet to get position."""
        raw = 'DB0AU>APSVX1:!4747.10N/01158.02Er439.150MHz'
        result = normalize_packet_type(
            'unknown', latitude=None, longitude=None, raw=raw
        )
        assert result == 'position'

    def test_beacon_with_invalid_raw_stays_beacon(self):
        """Beacon with invalid raw packet should stay beacon."""
        result = normalize_packet_type(
            'beacon', latitude=None, longitude=None, raw='invalid'
        )
        assert result == 'beacon'

    def test_unknown_with_telemetry_raw_becomes_telemetry(self):
        """Unknown packet with telemetry data in raw should become telemetry."""
        # T# format is telemetry data
        raw = 'N1KSC-1>APMI03,qAR,KM4ZYG-10:T#190,085,014,076,000,00000000'
        result = normalize_packet_type(
            'unknown', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_unknown_with_telemetry_raw_2_becomes_telemetry(self):
        """Another telemetry data packet should become telemetry."""
        raw = 'KD4NFI-5>APMI04,TCPIP*,qAS,KD4NFI:T#180,000,000,100,000,00000000'
        result = normalize_packet_type(
            'unknown', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_message_with_telemetry_definition_eqns_becomes_telemetry(self):
        """Message packet with EQNS telemetry definition should become telemetry.

        This is the bug fix for telemetry definition packets (PARM/UNIT/BITS/EQNS)
        that were incorrectly classified as 'message' by the ingest pipeline.
        """
        raw = 'N1DTA-12>APMI06,TCPIP*,qAS,N1DTA::N1DTA-12 :EQNS.0,0.075,0,0,10,0,0,10,0,0,1,0,0,0,0'
        result = normalize_packet_type(
            'message', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_message_with_telemetry_definition_parm_becomes_telemetry(self):
        """Message packet with PARM telemetry definition should become telemetry."""
        raw = 'N1DTA-12>APMI06::N1DTA-12 :PARM.Voltage,Temperature,Current,Speed,Direction'
        result = normalize_packet_type(
            'message', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_message_with_telemetry_definition_unit_becomes_telemetry(self):
        """Message packet with UNIT telemetry definition should become telemetry."""
        raw = 'N1DTA-12>APMI06::N1DTA-12 :UNIT.Volts,Celsius,Amps,Knots,Degrees'
        result = normalize_packet_type(
            'message', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_message_with_telemetry_definition_bits_becomes_telemetry(self):
        """Message packet with BITS telemetry definition should become telemetry."""
        raw = 'N1DTA-12>APMI06::N1DTA-12 :BITS.11111111,My Project Title'
        result = normalize_packet_type(
            'message', latitude=None, longitude=None, raw=raw
        )
        assert result == 'telemetry'

    def test_regular_message_stays_message(self):
        """Regular message packet should stay as message."""
        raw = 'N0CALL>APRS::WB4BOR-9 :Hello World{123'
        result = normalize_packet_type(
            'message', latitude=None, longitude=None, raw=raw
        )
        assert result == 'message'
