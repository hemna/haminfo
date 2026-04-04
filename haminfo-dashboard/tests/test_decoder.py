"""Tests for APRS packet decoder."""

import pytest
from haminfo_dashboard.decoder import decode_packet


class TestDecodePacket:
    """Tests for decode_packet function."""

    def test_decode_position_packet(self):
        """Test decoding a basic position packet."""
        raw = 'W3ADO-1>APRS,WIDE1-1,qAR,W3XYZ:@092345z3955.00N/07520.00W_'
        result = decode_packet(raw)

        assert result['success'] is True
        assert result['error'] is None
        assert result['parsed']['from'] == 'W3ADO-1'
        assert result['parsed']['to'] == 'APRS'
        assert 'latitude' in result['parsed']
        assert 'longitude' in result['parsed']

    def test_decode_invalid_packet(self):
        """Test decoding invalid packet returns error."""
        raw = 'this is not a valid aprs packet'
        result = decode_packet(raw)

        assert result['success'] is False
        assert result['error'] is not None
        assert 'parsed' not in result or result['parsed'] is None

    def test_decode_empty_packet(self):
        """Test decoding empty string returns error."""
        result = decode_packet('')

        assert result['success'] is False
        assert 'empty' in result['error'].lower()

    def test_decode_weather_packet(self):
        """Test decoding a weather packet extracts weather data."""
        raw = 'W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_090/005g010t072r001h85b10234'
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'weather' in result['sections']
        weather = result['sections']['weather']
        # aprslib returns metric values (Celsius, m/s, etc.)
        # Temperature 72F = 22.22C
        assert weather.get('temperature') is not None
        assert abs(weather.get('temperature') - 22.22) < 0.1
        # Wind gust 10mph = 4.47 m/s
        assert weather.get('wind_gust') is not None
        assert abs(weather.get('wind_gust') - 4.47) < 0.1
        # Humidity should be 85%
        assert weather.get('humidity') == 85

    def test_decode_message_packet(self):
        """Test decoding a message packet."""
        raw = 'W3ADO-1>APRS::W3XYZ    :Hello World{123'
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'message' in result['sections']
        msg = result['sections']['message']
        assert 'W3XYZ' in msg.get('addressee', '')

    def test_annotations_include_source(self):
        """Test that annotations include source callsign with value."""
        raw = 'W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_'
        result = decode_packet(raw)

        assert result['success'] is True
        assert result['raw'] == raw  # Verify raw is included
        source_annotations = [
            a for a in result['annotations'] if a['field'] == 'source'
        ]
        assert len(source_annotations) == 1
        assert source_annotations[0]['start'] == 0
        assert source_annotations[0]['end'] == 7  # "W3ADO-1"
        assert source_annotations[0]['value'] == 'W3ADO-1'  # Verify value included

    def test_sections_always_has_station(self):
        """Test that sections always includes station info."""
        raw = 'W3ADO-1>APRS:>Status message'
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'station' in result['sections']
        assert result['sections']['station']['from'] == 'W3ADO-1'

    def test_decode_mice_packet(self):
        """Test decoding a Mic-E encoded packet."""
        # Mic-E packet: position encoded in destination field, data after `
        raw = 'WB4APR-14>3X0PWW:`2,olDR>/`"4F}'
        result = decode_packet(raw)

        assert result['success'] is True
        assert result['parsed'] is not None
        # Mic-E packets should be identified as mic-e format
        assert result['parsed'].get('format') == 'mic-e'
        # Should have position data
        assert 'latitude' in result['parsed']
        assert 'longitude' in result['parsed']
        # Verify we can get annotations
        assert len(result['annotations']) > 0
        # Verify source annotation has value
        source_ann = [a for a in result['annotations'] if a['field'] == 'source'][0]
        assert source_ann['value'] == 'WB4APR-14'
