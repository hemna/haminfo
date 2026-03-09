"""Tests for haminfo utility functions."""

from __future__ import annotations

import pytest

from haminfo.utils import (
    bool_from_str,
    isfloat,
    degrees_to_cardinal,
    frequency_band_mhz,
    strfdelta,
    flatten_dict,
    human_size,
)
from datetime import timedelta


class TestBoolFromStr:
    """Tests for bool_from_str conversion."""

    def test_no_returns_false(self):
        assert bool_from_str('No') is False

    def test_yes_returns_true(self):
        assert bool_from_str('Yes') is True

    def test_empty_string_returns_true(self):
        # Any non-"No" value returns True
        assert bool_from_str('') is True

    def test_other_string_returns_true(self):
        assert bool_from_str('Maybe') is True


class TestIsFloat:
    """Tests for isfloat validation."""

    def test_integer(self):
        assert isfloat(42) is True

    def test_float(self):
        assert isfloat(3.14) is True

    def test_string_float(self):
        assert isfloat('3.14') is True

    def test_string_int(self):
        assert isfloat('42') is True

    def test_non_numeric_string(self):
        assert isfloat('abc') is False

    def test_empty_string(self):
        assert isfloat('') is False


class TestDegreesToCardinal:
    """Tests for degrees_to_cardinal conversion."""

    def test_north(self):
        assert degrees_to_cardinal(0) == 'N'
        assert degrees_to_cardinal(360) == 'N'

    def test_east(self):
        assert degrees_to_cardinal(90) == 'E'

    def test_south(self):
        assert degrees_to_cardinal(180) == 'S'

    def test_west(self):
        assert degrees_to_cardinal(270) == 'W'

    def test_northeast(self):
        assert degrees_to_cardinal(45) == 'NE'

    def test_southeast(self):
        assert degrees_to_cardinal(135) == 'SE'

    def test_southwest(self):
        assert degrees_to_cardinal(225) == 'SW'

    def test_northwest(self):
        assert degrees_to_cardinal(315) == 'NW'


class TestFrequencyBandMhz:
    """Tests for frequency_band_mhz conversion."""

    def test_2m_band(self):
        assert frequency_band_mhz(146.940) == '2m'

    def test_70cm_band(self):
        assert frequency_band_mhz(440.0) == '70cm'

    def test_6m_band(self):
        assert frequency_band_mhz(52.0) == '6m'

    def test_1_25m_band(self):
        assert frequency_band_mhz(224.0) == '1.25m'

    def test_unknown_frequency(self):
        # Frequency outside any known band
        result = frequency_band_mhz(999999.0)
        assert result is None


class TestStrfDelta:
    """Tests for strfdelta time formatting."""

    def test_simple_time(self):
        td = timedelta(hours=1, minutes=30, seconds=45)
        result = strfdelta(td)
        assert '01' in result
        assert '30' in result
        assert '45' in result

    def test_with_days(self):
        td = timedelta(days=2, hours=3, minutes=15, seconds=0)
        result = strfdelta(td)
        assert '2 days' in result

    def test_zero_delta(self):
        td = timedelta(0)
        result = strfdelta(td)
        assert '00' in result


class TestFlattenDict:
    """Tests for flatten_dict utility."""

    def test_flat_dict(self):
        d = {'a': 1, 'b': 2}
        result = flatten_dict(d)
        assert result == {'a': 1, 'b': 2}

    def test_nested_dict(self):
        d = {'a': {'b': {'c': 1}}}
        result = flatten_dict(d)
        assert result == {'a.b.c': 1}

    def test_mixed_dict(self):
        d = {'a': 1, 'b': {'c': 2, 'd': 3}}
        result = flatten_dict(d)
        assert result == {'a': 1, 'b.c': 2, 'b.d': 3}

    def test_custom_separator(self):
        d = {'a': {'b': 1}}
        result = flatten_dict(d, sep='/')
        assert result == {'a/b': 1}

    def test_empty_dict(self):
        result = flatten_dict({})
        assert result == {}


class TestHumanSize:
    """Tests for human_size formatting."""

    def test_bytes(self):
        assert human_size(500) == '500 bytes'

    def test_kilobytes(self):
        result = human_size(1024)
        assert 'KB' in result

    def test_megabytes(self):
        result = human_size(1024 * 1024)
        assert 'MB' in result

    def test_gigabytes(self):
        result = human_size(1024 * 1024 * 1024)
        assert 'GB' in result
