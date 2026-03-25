# Weather Station History API Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a REST API endpoint to fetch historical weather data with hourly aggregation for graphing, plus OpenAPI documentation for all endpoints.

**Architecture:** New GET endpoint at `/api/v1/wx/history` using TimescaleDB `time_bucket` for efficient hourly aggregation. Validation helpers parse ISO 8601 timestamps and field names. OpenAPI spec auto-generated using `apispec` library.

**Tech Stack:** Flask, SQLAlchemy, TimescaleDB, apispec, apispec-webframeworks

**Spec:** `docs/superpowers/specs/2026-03-24-wx-history-api-design.md`

**Out of scope:** Swagger UI (`/docs`) - can be added later if needed.

**Test environment:** Tests require PostgreSQL with TimescaleDB extension.

---

## File Structure

| File | Purpose |
|------|---------|
| `haminfo/flask.py` | Add `wx_history()` endpoint, validation helpers, OpenAPI setup |
| `haminfo/db/db.py` | Add `get_wx_history()` database function |
| `tests/test_flask_validation.py` | Add tests for new validation helpers |
| `tests/test_wx_history.py` | New file: integration tests for wx_history endpoint |
| `pyproject.toml` | Add apispec dependencies |

---

## Chunk 1: Validation Helpers

### Task 1: Add ISO 8601 Timestamp Validation

**Files:**
- Modify: `haminfo/flask.py` (add after `validate_callsigns` function ~line 210)
- Test: `tests/test_flask_validation.py`

- [ ] **Step 1: Write failing tests for validate_iso_timestamp**

Add to `tests/test_flask_validation.py`:

```python
from haminfo.flask import validate_iso_timestamp


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flask_validation.py::TestValidateIsoTimestamp -v`
Expected: FAIL with "cannot import name 'validate_iso_timestamp'"

- [ ] **Step 3: Implement validate_iso_timestamp**

Add to `haminfo/flask.py` after the `validate_callsigns` function:

```python
def validate_iso_timestamp(value: Any, field_name: str) -> datetime:
    """Validate and parse an ISO 8601 timestamp string.

    Args:
        value: Timestamp string to validate.
        field_name: Name of the field (for error messages).

    Returns:
        datetime object in UTC timezone.

    Raises:
        ValidationError: If value is missing or not a valid ISO 8601 timestamp.
    """
    if not value:
        raise ValidationError(f"'{field_name}' is required", field_name)

    try:
        # Try parsing with timezone
        if value.endswith('Z'):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(value)
        
        # If no timezone, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC
            dt = dt.astimezone(timezone.utc)
        
        return dt
    except (ValueError, AttributeError) as err:
        raise ValidationError(
            f"Invalid timestamp format for '{field_name}': {value}",
            field_name,
        ) from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_flask_validation.py::TestValidateIsoTimestamp -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/flask.py tests/test_flask_validation.py
git commit -m "feat: add ISO 8601 timestamp validation helper"
```

---

### Task 2: Add Field Name Validation

**Files:**
- Modify: `haminfo/flask.py`
- Test: `tests/test_flask_validation.py`

- [ ] **Step 1: Write failing tests for validate_wx_fields**

Add to `tests/test_flask_validation.py`:

```python
from haminfo.flask import validate_wx_fields, VALID_WX_FIELDS


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flask_validation.py::TestValidateWxFields -v`
Expected: FAIL with "cannot import name 'validate_wx_fields'"

- [ ] **Step 3: Implement validate_wx_fields**

Add to `haminfo/flask.py` after `validate_iso_timestamp`:

```python
# Valid weather report fields for history queries
VALID_WX_FIELDS = frozenset([
    'temperature',
    'humidity',
    'pressure',
    'wind_speed',
    'wind_direction',
    'wind_gust',
    'rain_1h',
    'rain_24h',
    'rain_since_midnight',
])


def validate_wx_fields(fields_str: Any) -> list[str]:
    """Validate and parse a comma-separated weather fields string.

    Args:
        fields_str: Comma-separated field names.

    Returns:
        List of validated field names.

    Raises:
        ValidationError: If input is empty or contains invalid field names.
    """
    if not fields_str or not isinstance(fields_str, str):
        raise ValidationError(
            'At least one valid field is required',
            'fields',
        )

    fields = [f.strip().lower() for f in fields_str.split(',') if f.strip()]

    if not fields:
        raise ValidationError(
            'At least one valid field is required',
            'fields',
        )

    for field in fields:
        if field not in VALID_WX_FIELDS:
            valid_list = ', '.join(sorted(VALID_WX_FIELDS))
            raise ValidationError(
                f"Invalid field: '{field}'. Valid fields: {valid_list}",
                'fields',
            )

    return fields
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_flask_validation.py::TestValidateWxFields -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/flask.py tests/test_flask_validation.py
git commit -m "feat: add weather field validation helper"
```

---

### Task 3: Add Date Range Validation

**Files:**
- Modify: `haminfo/flask.py`
- Test: `tests/test_flask_validation.py`

- [ ] **Step 1: Write failing tests for validate_date_range**

Add to `tests/test_flask_validation.py`:

```python
from datetime import datetime, timezone, timedelta
from haminfo.flask import validate_date_range, MAX_DATE_RANGE_DAYS


class TestValidateDateRange:
    """Tests for date range validation."""

    def test_valid_one_day_range(self):
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
        validate_date_range(start, end)  # Should not raise

    def test_valid_max_range(self):
        start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 31, 0, 0, 0, tzinfo=timezone.utc)
        validate_date_range(start, end)  # Should not raise

    def test_rejects_start_after_end(self):
        start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError, match='before'):
            validate_date_range(start, end)

    def test_rejects_start_equals_end(self):
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError, match='before'):
            validate_date_range(start, end)

    def test_rejects_range_exceeds_max(self):
        start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)  # 32 days
        with pytest.raises(ValidationError, match='30 days'):
            validate_date_range(start, end)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flask_validation.py::TestValidateDateRange -v`
Expected: FAIL with "cannot import name 'validate_date_range'"

- [ ] **Step 3: Implement validate_date_range**

Add to `haminfo/flask.py` after `validate_wx_fields`:

```python
MAX_DATE_RANGE_DAYS = 30


def validate_date_range(start: datetime, end: datetime) -> None:
    """Validate that a date range is valid.

    Args:
        start: Start datetime.
        end: End datetime.

    Raises:
        ValidationError: If start >= end or range exceeds maximum.
    """
    if start >= end:
        raise ValidationError(
            "'start' must be before 'end'",
            'start/end',
        )

    delta = end - start
    if delta.days > MAX_DATE_RANGE_DAYS:
        raise ValidationError(
            f'Date range exceeds maximum of {MAX_DATE_RANGE_DAYS} days',
            'start/end',
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_flask_validation.py::TestValidateDateRange -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/flask.py tests/test_flask_validation.py
git commit -m "feat: add date range validation helper"
```

---

## Chunk 2: Database Layer

### Task 4: Add get_wx_history Database Function

**Files:**
- Modify: `haminfo/db/db.py`
- Test: `tests/test_wx_history.py` (new file)

- [ ] **Step 1: Write failing test for get_wx_history**

Create `tests/test_wx_history.py`:

```python
"""Tests for weather history API."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from haminfo.db.db import get_wx_history


class TestGetWxHistory:
    """Tests for get_wx_history database function."""

    def test_returns_empty_list_for_no_data(self, db_session):
        """Test that empty result is returned when no data exists."""
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
        
        result = get_wx_history(
            db_session,
            station_id=99999,  # Non-existent station
            start=start,
            end=end,
            fields=['temperature'],
        )
        
        assert result == []

    def test_returns_hourly_aggregated_data(self, db_session, wx_station_with_reports):
        """Test that data is aggregated by hour."""
        station = wx_station_with_reports
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 3, 0, 0, tzinfo=timezone.utc)
        
        result = get_wx_history(
            db_session,
            station_id=station.id,
            start=start,
            end=end,
            fields=['temperature'],
        )
        
        assert len(result) > 0
        for row in result:
            assert 'time' in row
            assert 'temperature' in row

    def test_returns_only_requested_fields(self, db_session, wx_station_with_reports):
        """Test that only requested fields are returned."""
        station = wx_station_with_reports
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 3, 0, 0, tzinfo=timezone.utc)
        
        result = get_wx_history(
            db_session,
            station_id=station.id,
            start=start,
            end=end,
            fields=['temperature', 'humidity'],
        )
        
        if result:
            row = result[0]
            assert 'temperature' in row
            assert 'humidity' in row
            assert 'pressure' not in row
            assert 'wind_speed' not in row
```

- [ ] **Step 2: Add test fixtures to conftest.py**

Add to `tests/conftest.py`:

```python
from datetime import datetime, timezone, timedelta
from haminfo.db.models.weather_report import WeatherStation, WeatherReport


@pytest.fixture
def wx_station_with_reports(db_session):
    """Create a weather station with test reports."""
    station = WeatherStation(
        callsign='TEST1',
        latitude=42.0,
        longitude=-71.0,
        location='POINT(-71.0 42.0)',
    )
    db_session.add(station)
    db_session.flush()
    
    # Add reports at different times within the same hour
    base_time = datetime(2026, 3, 20, 0, 30, 0, tzinfo=timezone.utc)
    for i in range(5):
        report = WeatherReport(
            weather_station_id=station.id,
            time=base_time + timedelta(minutes=i * 10),
            temperature=20.0 + i,
            humidity=50 + i,
            pressure=1013.0,
            wind_speed=5.0,
            wind_direction=180,
            wind_gust=10.0,
            rain_1h=0.0,
            rain_24h=0.0,
            rain_since_midnight=0.0,
        )
        db_session.add(report)
    
    db_session.commit()
    return station
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_wx_history.py -v`
Expected: FAIL with "cannot import name 'get_wx_history'"

- [ ] **Step 4: Implement get_wx_history**

Add to `haminfo/db/db.py` after `get_wx_station_report`:

```python
def get_wx_history(
    session: Session,
    station_id: int,
    start: datetime,
    end: datetime,
    fields: list[str],
) -> list[dict[str, Any]]:
    """Get hourly aggregated weather history for a station.

    Uses TimescaleDB time_bucket for efficient aggregation.

    Args:
        session: Database session.
        station_id: Weather station ID.
        start: Start datetime (inclusive).
        end: End datetime (exclusive).
        fields: List of field names to include.

    Returns:
        List of dicts with 'time' and requested field values,
        ordered by time ascending.
    """
    # Build dynamic column selection based on requested fields
    field_mapping = {
        'temperature': WeatherReport.temperature,
        'humidity': WeatherReport.humidity,
        'pressure': WeatherReport.pressure,
        'wind_speed': WeatherReport.wind_speed,
        'wind_direction': WeatherReport.wind_direction,
        'wind_gust': WeatherReport.wind_gust,
        'rain_1h': WeatherReport.rain_1h,
        'rain_24h': WeatherReport.rain_24h,
        'rain_since_midnight': WeatherReport.rain_since_midnight,
    }

    # Use time_bucket for hourly aggregation (TimescaleDB)
    # Note: Tests should run against PostgreSQL with TimescaleDB extension
    bucket = func.time_bucket(
        sqlalchemy.literal_column("'1 hour'"),
        WeatherReport.time
    ).label('bucket')

    # Build select columns
    select_cols = [bucket]
    for field in fields:
        if field in field_mapping:
            select_cols.append(
                func.avg(field_mapping[field]).label(field)
            )

    query = (
        session.query(*select_cols)
        .filter(
            WeatherReport.weather_station_id == station_id,
            WeatherReport.time >= start,
            WeatherReport.time < end,
        )
        .group_by(bucket)
        .order_by(bucket)
    )

    results = []
    for row in query:
        entry = {'time': row.bucket.strftime('%Y-%m-%dT%H:%M:%SZ')}
        for field in fields:
            value = getattr(row, field, None)
            if value is not None:
                entry[field] = round(float(value), 2)
            else:
                entry[field] = None
        results.append(entry)

    return results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_wx_history.py -v`
Expected: All tests PASS (may need to adjust for test DB setup)

- [ ] **Step 6: Commit**

```bash
git add haminfo/db/db.py tests/test_wx_history.py tests/conftest.py
git commit -m "feat: add get_wx_history database function with hourly aggregation"
```

---

## Chunk 3: API Endpoint

### Task 5: Add wx_history Endpoint

**Files:**
- Modify: `haminfo/flask.py`
- Test: `tests/test_wx_history.py`

- [ ] **Step 1: Write failing integration tests for wx_history endpoint**

Add to `tests/test_wx_history.py`:

```python
class TestWxHistoryEndpoint:
    """Integration tests for /api/v1/wx/history endpoint."""

    def test_requires_api_key(self, client):
        """Test that endpoint requires authentication."""
        response = client.get('/api/v1/wx/history')
        assert response.status_code == 401

    def test_requires_station_identifier(self, client, api_key_header):
        """Test that station_id or callsign is required."""
        response = client.get(
            '/api/v1/wx/history?start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert 'station_id' in response.json['error'].lower() or 'callsign' in response.json['error'].lower()

    def test_requires_start_and_end(self, client, api_key_header):
        """Test that start and end are required."""
        response = client.get(
            '/api/v1/wx/history?station_id=1&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert 'start' in response.json['error'].lower() or 'end' in response.json['error'].lower()

    def test_requires_fields(self, client, api_key_header):
        """Test that fields parameter is required."""
        response = client.get(
            '/api/v1/wx/history?station_id=1&start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z',
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert 'field' in response.json['error'].lower()

    def test_returns_404_for_unknown_station(self, client, api_key_header):
        """Test that unknown station returns 404."""
        response = client.get(
            '/api/v1/wx/history?station_id=99999&start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 404

    def test_successful_response_structure(self, client, api_key_header, wx_station_with_reports):
        """Test successful response has correct structure."""
        station = wx_station_with_reports
        response = client.get(
            f'/api/v1/wx/history?station_id={station.id}&start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 200
        data = response.json
        assert 'station_id' in data
        assert 'callsign' in data
        assert 'history' in data
        assert 'count' in data
        assert isinstance(data['history'], list)

    def test_lookup_by_callsign(self, client, api_key_header, wx_station_with_reports):
        """Test lookup by callsign works."""
        station = wx_station_with_reports
        response = client.get(
            f'/api/v1/wx/history?callsign={station.callsign}&start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 200
        assert response.json['callsign'] == station.callsign

    def test_rejects_non_integer_station_id(self, client, api_key_header):
        """Test that non-integer station_id returns 400."""
        response = client.get(
            '/api/v1/wx/history?station_id=abc&start=2026-03-20T00:00:00Z&end=2026-03-21T00:00:00Z&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert 'integer' in response.json['error'].lower()
```

- [ ] **Step 2: Add test fixtures for Flask client**

Add to `tests/conftest.py` if not present:

```python
import pytest
from oslo_config import cfg
from haminfo.flask import create_app

# Set up test API key before app creation
TEST_API_KEY = 'test-api-key-12345'


@pytest.fixture(scope='session', autouse=True)
def setup_test_config():
    """Configure test settings."""
    cfg.CONF.set_override('api_key', TEST_API_KEY, group='web')


@pytest.fixture
def app(db_session):
    """Create Flask test application."""
    # Create a minimal context for testing
    class MockCtx:
        obj = {'loglevel': 'WARNING'}
    
    app = create_app(MockCtx())
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def api_key_header():
    """Return headers with valid API key."""
    return {'X-Api-Key': TEST_API_KEY}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_wx_history.py::TestWxHistoryEndpoint -v`
Expected: FAIL with 404 (endpoint not registered)

- [ ] **Step 4: Implement wx_history endpoint**

Add to `HaminfoFlask` class in `haminfo/flask.py`:

```python
    @require_appkey
    def wx_history(self) -> Response | tuple[Response, int]:
        """Handle GET /api/v1/wx/history - weather station historical data.

        Returns hourly aggregated weather data for graphing.

        Returns:
            Flask JSON response with history data or error.
        """
        # Validate station identifier
        station_id = request.args.get('station_id')
        callsign = request.args.get('callsign')

        if not station_id and not callsign:
            return jsonify({
                'error': "Either 'station_id' or 'callsign' is required",
                'field': 'station_id/callsign',
            }), 400

        # Validate timestamps
        try:
            start = validate_iso_timestamp(request.args.get('start'), 'start')
            end = validate_iso_timestamp(request.args.get('end'), 'end')
        except ValidationError as ex:
            return jsonify({'error': ex.message, 'field': ex.field}), 400

        # Validate date range
        try:
            validate_date_range(start, end)
        except ValidationError as ex:
            return jsonify({'error': ex.message, 'field': ex.field}), 400

        # Validate fields
        try:
            fields = validate_wx_fields(request.args.get('fields'))
        except ValidationError as ex:
            return jsonify({'error': ex.message, 'field': ex.field}), 400

        # Look up station
        session = self._get_db_session()
        with session() as session:
            # Resolve station_id and callsign
            if station_id:
                try:
                    station_id = int(station_id)
                except (ValueError, TypeError):
                    return jsonify({
                        'error': "'station_id' must be an integer",
                        'field': 'station_id',
                    }), 400
                
                station = session.query(WeatherStation).filter(
                    WeatherStation.id == station_id
                ).first()
            else:
                station = session.query(WeatherStation).filter(
                    WeatherStation.callsign == callsign.upper()
                ).first()

            if not station:
                return jsonify({
                    'error': 'Weather station not found',
                    'field': 'station_id/callsign',
                }), 404

            # Get history data
            history = db.get_wx_history(
                session,
                station_id=station.id,
                start=start,
                end=end,
                fields=fields,
            )

            return jsonify({
                'station_id': station.id,
                'callsign': station.callsign,
                'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'interval': '1h',
                'fields': fields,
                'history': history,
                'count': len(history),
            })
```

- [ ] **Step 5: Add import for WeatherStation at top of flask.py**

Add to imports in `haminfo/flask.py`:

```python
from haminfo.db.models.weather_report import WeatherStation
```

- [ ] **Step 6: Register route in create_app**

Add to `create_app()` function in `haminfo/flask.py` after the other routes:

```python
    app.route('/api/v1/wx/history', methods=['GET'])(server.wx_history)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_wx_history.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add haminfo/flask.py tests/test_wx_history.py tests/conftest.py
git commit -m "feat: add /api/v1/wx/history endpoint for historical weather data"
```

---

## Chunk 4: OpenAPI Documentation

### Task 6: Add apispec Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add apispec to dependencies**

Add to `dependencies` list in `pyproject.toml`:

```toml
    "apispec>=6.0.0",
    "apispec-webframeworks>=1.0.0",
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add apispec for OpenAPI documentation"
```

---

### Task 7: Add OpenAPI Endpoint

**Files:**
- Modify: `haminfo/flask.py`
- Test: `tests/test_wx_history.py`

- [ ] **Step 1: Write failing test for openapi.json endpoint**

Add to `tests/test_wx_history.py`:

```python
class TestOpenAPIEndpoint:
    """Tests for /openapi.json endpoint."""

    def test_openapi_returns_valid_spec(self, client):
        """Test that /openapi.json returns valid OpenAPI 3.0 spec."""
        response = client.get('/openapi.json')
        assert response.status_code == 200
        data = response.json
        assert data['openapi'].startswith('3.')
        assert 'info' in data
        assert 'paths' in data

    def test_openapi_includes_wx_history(self, client):
        """Test that wx_history endpoint is documented."""
        response = client.get('/openapi.json')
        data = response.json
        assert '/api/v1/wx/history' in data['paths']

    def test_openapi_no_auth_required(self, client):
        """Test that /openapi.json does not require authentication."""
        response = client.get('/openapi.json')
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wx_history.py::TestOpenAPIEndpoint -v`
Expected: FAIL with 404

- [ ] **Step 3: Implement OpenAPI spec generation**

Add to `haminfo/flask.py` after imports:

```python
from apispec import APISpec
from apispec.utils import validate_spec


def create_openapi_spec() -> APISpec:
    """Create OpenAPI specification for all haminfo endpoints."""
    spec = APISpec(
        title='Haminfo API',
        version=haminfo.__version__,
        openapi_version='3.0.3',
        info={
            'description': 'Ham radio information API for repeaters, weather stations, and APRS data.',
            'contact': {'email': 'waboring@hemna.com'},
        },
    )

    # Security scheme
    spec.components.security_scheme(
        'ApiKeyAuth',
        {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-Api-Key',
        }
    )

    # Weather History endpoint
    spec.path(
        path='/api/v1/wx/history',
        operations={
            'get': {
                'summary': 'Get weather station history',
                'description': 'Returns hourly aggregated weather data for graphing.',
                'security': [{'ApiKeyAuth': []}],
                'parameters': [
                    {'name': 'station_id', 'in': 'query', 'schema': {'type': 'integer'}, 'description': 'Weather station ID'},
                    {'name': 'callsign', 'in': 'query', 'schema': {'type': 'string'}, 'description': 'Station callsign'},
                    {'name': 'start', 'in': 'query', 'required': True, 'schema': {'type': 'string', 'format': 'date-time'}, 'description': 'Start time (ISO 8601)'},
                    {'name': 'end', 'in': 'query', 'required': True, 'schema': {'type': 'string', 'format': 'date-time'}, 'description': 'End time (ISO 8601)'},
                    {'name': 'fields', 'in': 'query', 'required': True, 'schema': {'type': 'string'}, 'description': 'Comma-separated field names'},
                ],
                'responses': {
                    '200': {
                        'description': 'Successful response',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'type': 'object',
                                    'properties': {
                                        'station_id': {'type': 'integer'},
                                        'callsign': {'type': 'string'},
                                        'start': {'type': 'string', 'format': 'date-time'},
                                        'end': {'type': 'string', 'format': 'date-time'},
                                        'interval': {'type': 'string'},
                                        'fields': {'type': 'array', 'items': {'type': 'string'}},
                                        'history': {'type': 'array', 'items': {'type': 'object'}},
                                        'count': {'type': 'integer'},
                                    },
                                },
                            },
                        },
                    },
                    '400': {'description': 'Validation error'},
                    '401': {'description': 'Unauthorized'},
                    '404': {'description': 'Station not found'},
                },
            },
        },
    )

    # Document existing endpoints
    spec.path(
        path='/wxstations',
        operations={
            'get': {
                'summary': 'List all weather stations',
                'security': [{'ApiKeyAuth': []}],
                'responses': {'200': {'description': 'List of weather stations'}},
            },
        },
    )

    spec.path(
        path='/wxstation_report',
        operations={
            'get': {
                'summary': 'Get latest weather report for a station',
                'security': [{'ApiKeyAuth': []}],
                'parameters': [
                    {'name': 'wx_station_id', 'in': 'query', 'required': True, 'schema': {'type': 'integer'}},
                ],
                'responses': {'200': {'description': 'Weather report'}},
            },
        },
    )

    spec.path(
        path='/wxnearest',
        operations={
            'post': {
                'summary': 'Find nearest weather stations',
                'security': [{'ApiKeyAuth': []}],
                'responses': {'200': {'description': 'Nearest weather stations'}},
            },
        },
    )

    spec.path(
        path='/nearest',
        operations={
            'post': {
                'summary': 'Find nearest repeaters',
                'security': [{'ApiKeyAuth': []}],
                'responses': {'200': {'description': 'Nearest repeaters'}},
            },
        },
    )

    spec.path(
        path='/api/v1/location',
        operations={
            'get': {
                'summary': 'Get APRS location data (native format)',
                'security': [{'ApiKeyAuth': []}],
                'parameters': [
                    {'name': 'callsign', 'in': 'query', 'required': True, 'schema': {'type': 'string'}},
                ],
                'responses': {'200': {'description': 'Location data'}},
            },
        },
    )

    spec.path(
        path='/api/get',
        operations={
            'get': {
                'summary': 'Get APRS location data (aprs.fi compatible)',
                'parameters': [
                    {'name': 'apikey', 'in': 'query', 'required': True, 'schema': {'type': 'string'}},
                    {'name': 'what', 'in': 'query', 'required': True, 'schema': {'type': 'string'}},
                    {'name': 'name', 'in': 'query', 'required': True, 'schema': {'type': 'string'}},
                ],
                'responses': {'200': {'description': 'Location data in aprs.fi format'}},
            },
        },
    )

    spec.path(
        path='/stats',
        operations={
            'get': {
                'summary': 'Get API statistics',
                'responses': {'200': {'description': 'Statistics'}},
            },
        },
    )

    spec.path(
        path='/test',
        operations={
            'get': {
                'summary': 'Test endpoint',
                'security': [{'ApiKeyAuth': []}],
                'responses': {'200': {'description': 'OK'}},
            },
        },
    )

    return spec
```

- [ ] **Step 4: Add openapi endpoint to HaminfoFlask**

Add method to `HaminfoFlask` class:

```python
    def openapi(self):
        """Return OpenAPI specification."""
        spec = create_openapi_spec()
        return jsonify(spec.to_dict())
```

- [ ] **Step 5: Register openapi route in create_app**

Add to `create_app()`:

```python
    app.route('/openapi.json', methods=['GET'])(server.openapi)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_wx_history.py::TestOpenAPIEndpoint -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add haminfo/flask.py tests/test_wx_history.py
git commit -m "feat: add /openapi.json endpoint for API documentation"
```

---

## Chunk 5: Final Verification

### Task 8: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Run linting**

Run: `ruff check .`
Expected: No errors

- [ ] **Step 3: Manual verification**

Start the API server and test the new endpoint:

```bash
# Start server
haminfo_api -c haminfo.conf

# Test endpoint (in another terminal)
curl -H "X-Api-Key: YOUR_KEY" \
  "http://localhost:8080/api/v1/wx/history?station_id=1&start=2026-03-01T00:00:00Z&end=2026-03-02T00:00:00Z&fields=temperature,humidity"

# Test OpenAPI
curl http://localhost:8080/openapi.json | jq .
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete weather history API implementation"
```
