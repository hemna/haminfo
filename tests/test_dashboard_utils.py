# tests/test_dashboard_utils.py
"""Tests for dashboard utility functions."""

from __future__ import annotations

import pytest

from haminfo.dashboard.utils import get_country_from_callsign, format_packet_summary


class TestGetCountryFromCallsign:
    """Tests for get_country_from_callsign function."""

    def test_malaysian_callsign_9m2(self):
        """Recognizes Malaysian 9M2 callsigns."""
        result = get_country_from_callsign('9M2PJU')
        assert result == ('MY', 'Malaysia')

    def test_malaysian_callsign_9w(self):
        """Recognizes Malaysian 9W callsigns."""
        result = get_country_from_callsign('9W2ABC')
        assert result == ('MY', 'Malaysia')

    def test_us_callsign_w(self):
        """Recognizes US W callsigns."""
        result = get_country_from_callsign('W1AW')
        assert result == ('US', 'United States')

    def test_us_callsign_k(self):
        """Recognizes US K callsigns."""
        result = get_country_from_callsign('K1ABC')
        assert result == ('US', 'United States')

    def test_us_callsign_n(self):
        """Recognizes US N callsigns."""
        result = get_country_from_callsign('N0CALL')
        assert result == ('US', 'United States')

    def test_us_callsign_aa(self):
        """Recognizes US AA-AL callsigns."""
        result = get_country_from_callsign('AA1ABC')
        assert result == ('US', 'United States')

    def test_australian_callsign_vk(self):
        """Recognizes Australian VK callsigns."""
        result = get_country_from_callsign('VK2RG')
        assert result == ('AU', 'Australia')

    def test_japanese_callsign_ja(self):
        """Recognizes Japanese JA callsigns."""
        result = get_country_from_callsign('JA1XYZ')
        assert result == ('JP', 'Japan')

    def test_japanese_callsign_jh(self):
        """Recognizes Japanese JH callsigns."""
        result = get_country_from_callsign('JH1ABC')
        assert result == ('JP', 'Japan')

    def test_handles_ssid_suffix(self):
        """Strips SSID suffix before matching."""
        result = get_country_from_callsign('9M2PJU-9')
        assert result == ('MY', 'Malaysia')

    def test_handles_multiple_ssid(self):
        """Handles callsigns with multiple dashes."""
        result = get_country_from_callsign('W1AW-15')
        assert result == ('US', 'United States')

    def test_case_insensitive_lowercase(self):
        """Handles lowercase callsigns."""
        result = get_country_from_callsign('w1aw')
        assert result == ('US', 'United States')

    def test_case_insensitive_mixed(self):
        """Handles mixed case callsigns."""
        result = get_country_from_callsign('Vk2Rg')
        assert result == ('AU', 'Australia')

    def test_unknown_prefix_returns_none(self):
        """Returns None for unknown prefixes."""
        result = get_country_from_callsign('ZZTEST')
        assert result is None

    def test_empty_string_returns_none(self):
        """Returns None for empty string."""
        result = get_country_from_callsign('')
        assert result is None

    def test_none_returns_none(self):
        """Returns None for None input."""
        result = get_country_from_callsign(None)
        assert result is None

    def test_longest_prefix_match(self):
        """Matches longest prefix (9M before 9)."""
        # 9M should match Malaysia, not just the first character
        result = get_country_from_callsign('9M2ABC')
        assert result == ('MY', 'Malaysia')

    def test_uk_callsigns(self):
        """Recognizes UK callsigns."""
        assert get_country_from_callsign('G4ABC') == ('GB', 'United Kingdom')
        assert get_country_from_callsign('M0ABC') == ('GB', 'United Kingdom')

    def test_german_callsigns(self):
        """Recognizes German callsigns."""
        assert get_country_from_callsign('DL1ABC') == ('DE', 'Germany')
        assert get_country_from_callsign('DO1XYZ') == ('DE', 'Germany')


class TestFormatPacketSummary:
    """Tests for format_packet_summary function."""

    def test_position_packet_with_speed(self):
        """Formats position packet with speed."""
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'position',
            'latitude': 40.1234,
            'longitude': -105.5678,
            'speed': 55,
        }
        result = format_packet_summary(packet)

        assert 'N0CALL' in result
        assert 'Position' in result
        assert '40.1234' in result
        assert '-105.5678' in result
        assert '55' in result

    def test_position_packet_without_speed(self):
        """Formats position packet without speed."""
        packet = {
            'from_call': 'W1AW',
            'packet_type': 'position',
            'latitude': 41.7147,
            'longitude': -72.7272,
        }
        result = format_packet_summary(packet)

        assert 'W1AW' in result
        assert 'Position' in result
        assert '41.7147' in result
        assert 'km/h' not in result

    def test_weather_packet(self):
        """Formats weather packet."""
        packet = {
            'from_call': 'WX4TEST',
            'packet_type': 'weather',
            'temperature': 22,
            'humidity': 65,
        }
        result = format_packet_summary(packet)

        assert 'WX4TEST' in result
        assert 'WX' in result
        assert '22' in result
        assert '65' in result

    def test_status_packet(self):
        """Formats status packet."""
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'status',
            'status': 'Testing APRS system',
        }
        result = format_packet_summary(packet)

        assert 'N0CALL' in result
        assert 'Status' in result
        assert 'Testing' in result

    def test_status_packet_truncates_long_status(self):
        """Truncates long status messages."""
        long_status = 'A' * 100
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'status',
            'status': long_status,
        }
        result = format_packet_summary(packet)

        # Should truncate to 50 chars
        assert len(result) < 150

    def test_message_packet(self):
        """Formats message packet."""
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'message',
            'to_call': 'W1AW',
        }
        result = format_packet_summary(packet)

        assert 'N0CALL' in result
        assert 'Message' in result
        assert 'W1AW' in result

    def test_unknown_packet_type(self):
        """Handles unknown packet types."""
        packet = {
            'from_call': 'N0CALL',
            'packet_type': 'telemetry',
        }
        result = format_packet_summary(packet)

        assert 'N0CALL' in result
        assert 'telemetry' in result

    def test_missing_from_call(self):
        """Handles missing from_call."""
        packet = {
            'packet_type': 'position',
        }
        result = format_packet_summary(packet)

        assert '?' in result

    def test_missing_packet_type(self):
        """Handles missing packet_type."""
        packet = {
            'from_call': 'N0CALL',
        }
        result = format_packet_summary(packet)

        assert 'N0CALL' in result
        assert 'unknown' in result
