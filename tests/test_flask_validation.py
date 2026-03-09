"""Tests for Flask API input validation."""

from __future__ import annotations

import pytest

from haminfo.flask import (
    validate_lat_lon,
    validate_count,
    ValidationError,
    LAT_MIN,
    LAT_MAX,
    LON_MIN,
    LON_MAX,
    COUNT_MIN,
    COUNT_MAX,
)


class TestValidateLatLon:
    """Tests for lat/lon validation."""

    def test_valid_coordinates(self):
        lat, lon = validate_lat_lon(37.7749, -122.4194)
        assert lat == 37.7749
        assert lon == -122.4194

    def test_valid_string_coordinates(self):
        lat, lon = validate_lat_lon('37.7749', '-122.4194')
        assert lat == 37.7749
        assert lon == -122.4194

    def test_boundary_values(self):
        lat, lon = validate_lat_lon(90.0, 180.0)
        assert lat == 90.0
        assert lon == 180.0

        lat, lon = validate_lat_lon(-90.0, -180.0)
        assert lat == -90.0
        assert lon == -180.0

    def test_zero_coordinates(self):
        lat, lon = validate_lat_lon(0, 0)
        assert lat == 0.0
        assert lon == 0.0

    def test_rejects_none_lat(self):
        with pytest.raises(ValidationError, match='required'):
            validate_lat_lon(None, -122.0)

    def test_rejects_none_lon(self):
        with pytest.raises(ValidationError, match='required'):
            validate_lat_lon(37.0, None)

    def test_rejects_non_numeric_lat(self):
        with pytest.raises(ValidationError, match='numeric'):
            validate_lat_lon('abc', -122.0)

    def test_rejects_non_numeric_lon(self):
        with pytest.raises(ValidationError, match='numeric'):
            validate_lat_lon(37.0, 'xyz')

    def test_rejects_lat_too_high(self):
        with pytest.raises(ValidationError, match='lat'):
            validate_lat_lon(91.0, -122.0)

    def test_rejects_lat_too_low(self):
        with pytest.raises(ValidationError, match='lat'):
            validate_lat_lon(-91.0, -122.0)

    def test_rejects_lon_too_high(self):
        with pytest.raises(ValidationError, match='lon'):
            validate_lat_lon(37.0, 181.0)

    def test_rejects_lon_too_low(self):
        with pytest.raises(ValidationError, match='lon'):
            validate_lat_lon(37.0, -181.0)


class TestValidateCount:
    """Tests for count validation."""

    def test_valid_count(self):
        assert validate_count(10) == 10

    def test_string_count(self):
        assert validate_count('5') == 5

    def test_default_value(self):
        assert validate_count(None) == 10  # DEFAULT_COUNT

    def test_custom_default(self):
        assert validate_count(None, default=25) == 25

    def test_min_boundary(self):
        assert validate_count(COUNT_MIN) == COUNT_MIN

    def test_max_boundary(self):
        assert validate_count(COUNT_MAX) == COUNT_MAX

    def test_rejects_zero(self):
        with pytest.raises(ValidationError, match='count'):
            validate_count(0)

    def test_rejects_negative(self):
        with pytest.raises(ValidationError, match='count'):
            validate_count(-1)

    def test_rejects_too_high(self):
        with pytest.raises(ValidationError, match='count'):
            validate_count(COUNT_MAX + 1)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValidationError, match='integer'):
            validate_count('abc')

    def test_rejects_float_string(self):
        with pytest.raises(ValidationError, match='integer'):
            validate_count('1.5')


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_error_with_field(self):
        err = ValidationError('bad input', 'lat')
        assert str(err) == 'bad input'
        assert err.field == 'lat'

    def test_error_without_field(self):
        err = ValidationError('bad input')
        assert err.field == ''
