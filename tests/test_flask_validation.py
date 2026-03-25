"""Tests for Flask API input validation."""

from __future__ import annotations

import pytest

from haminfo.flask import (
    validate_lat_lon,
    validate_count,
    validate_iso_timestamp,
    validate_wx_fields,
    ValidationError,
    LAT_MIN,
    LAT_MAX,
    LON_MIN,
    LON_MAX,
    COUNT_MIN,
    COUNT_MAX,
    VALID_WX_FIELDS,
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


class TestValidateIsoTimestamp:
    """Tests for ISO 8601 timestamp validation."""

    def test_valid_utc_timestamp(self):
        from datetime import datetime, timezone

        result = validate_iso_timestamp('2026-03-20T00:00:00Z')
        assert result == datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)

    def test_valid_timestamp_with_offset(self):
        from datetime import datetime, timezone

        result = validate_iso_timestamp('2026-03-20T12:00:00+00:00')
        assert result == datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)

    def test_timestamp_without_timezone_assumes_utc(self):
        from datetime import datetime, timezone

        result = validate_iso_timestamp('2026-03-20T00:00:00')
        assert result == datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)

    def test_rejects_none(self):
        with pytest.raises(ValidationError, match='required'):
            validate_iso_timestamp(None, 'start')

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match='required'):
            validate_iso_timestamp('', 'start')

    def test_rejects_invalid_format(self):
        with pytest.raises(ValidationError, match='Invalid timestamp'):
            validate_iso_timestamp('not-a-date', 'start')

    def test_rejects_partial_date(self):
        with pytest.raises(ValidationError, match='Invalid timestamp'):
            validate_iso_timestamp('2026-03-20', 'start')

    def test_error_includes_field_name(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_iso_timestamp('bad', 'end')
        assert exc_info.value.field == 'end'


class TestValidateWxFields:
    """Tests for weather field validation."""

    def test_valid_single_field(self):
        result = validate_wx_fields('temperature')
        assert result == ['temperature']

    def test_valid_multiple_fields(self):
        result = validate_wx_fields('temperature,humidity,pressure')
        assert result == ['temperature', 'humidity', 'pressure']

    def test_strips_whitespace(self):
        result = validate_wx_fields(' temperature , humidity ')
        assert result == ['temperature', 'humidity']

    def test_all_valid_fields(self):
        all_fields = ','.join(VALID_WX_FIELDS)
        result = validate_wx_fields(all_fields)
        assert set(result) == set(VALID_WX_FIELDS)

    def test_rejects_none(self):
        with pytest.raises(ValidationError, match='required'):
            validate_wx_fields(None)

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match='required'):
            validate_wx_fields('')

    def test_rejects_invalid_field(self):
        with pytest.raises(ValidationError, match='Invalid field'):
            validate_wx_fields('invalid_field')

    def test_rejects_mixed_valid_invalid(self):
        with pytest.raises(ValidationError, match='Invalid field'):
            validate_wx_fields('temperature,bad_field')

    def test_error_lists_valid_fields(self):
        with pytest.raises(ValidationError, match='temperature'):
            validate_wx_fields('bad')
