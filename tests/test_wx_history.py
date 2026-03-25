"""Tests for weather history API."""

from __future__ import annotations

from datetime import datetime, timezone

from haminfo.db.db import get_wx_history


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
        assert (
            'station_id' in response.json['error'].lower()
            or 'callsign' in response.json['error'].lower()
        )

    def test_requires_start_and_end(self, client, api_key_header):
        """Test that start and end are required."""
        response = client.get(
            '/api/v1/wx/history?station_id=1&fields=temperature',
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert (
            'start' in response.json['error'].lower()
            or 'end' in response.json['error'].lower()
        )

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

    def test_successful_response_structure(
        self, client, api_key_header, wx_station_with_reports
    ):
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
