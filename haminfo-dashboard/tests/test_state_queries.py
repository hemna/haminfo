"""Tests for state weather dashboard queries."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


class TestGetStateStations:
    """Tests for get_state_stations function."""

    def test_returns_stations_for_valid_state(self):
        """Should return stations with latest weather data for a state."""
        from haminfo_dashboard.state_queries import get_state_stations

        # Create mock session with test data
        mock_session = MagicMock()

        # Mock station data
        mock_result = [
            {
                'callsign': 'W4TEST',
                'latitude': 37.5,
                'longitude': -77.5,
                'temperature': 72.0,
                'humidity': 65,
                'pressure': 1018.5,
                'wind_speed': 8.0,
                'wind_gust': 15.0,
                'wind_direction': 180,
                'rain_1h': 0.0,
                'last_report': datetime.now() - timedelta(minutes=5),
            }
        ]

        mock_session.execute.return_value.mappings.return_value.all.return_value = (
            mock_result
        )

        result = get_state_stations.__wrapped__(mock_session, 'VA')

        assert len(result) == 1
        assert result[0]['callsign'] == 'W4TEST'
        assert result[0]['temperature'] == 72.0

    def test_returns_empty_for_invalid_state(self):
        """Should return empty list for state with no stations."""
        from haminfo_dashboard.state_queries import get_state_stations

        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []

        result = get_state_stations.__wrapped__(mock_session, 'XX')

        assert result == []

    def test_state_code_case_insensitive(self):
        """Should handle lowercase state codes."""
        from haminfo_dashboard.state_queries import get_state_stations

        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []

        # Should not raise
        get_state_stations.__wrapped__(mock_session, 'va')

        # Verify query was called
        assert mock_session.execute.called


class TestComputeStateAggregates:
    """Tests for compute_state_aggregates function."""

    def test_computes_aggregates_from_stations(self):
        """Should compute min/max/avg from station list."""
        from haminfo_dashboard.state_queries import compute_state_aggregates

        stations = [
            {
                'temperature': 70.0,
                'humidity': 60,
                'pressure': 1015.0,
                'wind_speed': 5.0,
                'wind_gust': 8.0,
            },
            {
                'temperature': 80.0,
                'humidity': 70,
                'pressure': 1020.0,
                'wind_speed': 10.0,
                'wind_gust': 15.0,
            },
            {
                'temperature': 75.0,
                'humidity': 65,
                'pressure': 1018.0,
                'wind_speed': 8.0,
                'wind_gust': 12.0,
            },
        ]

        result = compute_state_aggregates(stations)

        assert result['avg_temp'] == 75.0
        assert result['min_temp'] == 70.0
        assert result['max_temp'] == 80.0
        assert result['avg_humidity'] == 65.0
        assert result['avg_wind'] == pytest.approx(7.67, rel=0.01)

    def test_handles_empty_list(self):
        """Should return None values for empty station list."""
        from haminfo_dashboard.state_queries import compute_state_aggregates

        result = compute_state_aggregates([])

        assert result['avg_temp'] is None
        assert result['min_temp'] is None
        assert result['station_count'] == 0

    def test_handles_null_values(self):
        """Should skip None values in calculations."""
        from haminfo_dashboard.state_queries import compute_state_aggregates

        stations = [
            {
                'temperature': 70.0,
                'humidity': None,
                'pressure': 1015.0,
                'wind_speed': 5.0,
                'wind_gust': None,
            },
            {
                'temperature': None,
                'humidity': 60,
                'pressure': None,
                'wind_speed': None,
                'wind_gust': None,
            },
            {
                'temperature': 80.0,
                'humidity': 70,
                'pressure': 1020.0,
                'wind_speed': 10.0,
                'wind_gust': 15.0,
            },
        ]

        result = compute_state_aggregates(stations)

        assert result['avg_temp'] == 75.0  # (70 + 80) / 2
        assert result['avg_humidity'] == 65.0  # (60 + 70) / 2


class TestGetStateTrends:
    """Tests for get_state_trends function."""

    def test_returns_hourly_trend_data(self):
        """Should return 24h trend data bucketed by hour."""
        from haminfo_dashboard.state_queries import get_state_trends

        mock_session = MagicMock()

        # Mock hourly data
        mock_result = [
            {
                'hour': datetime(2026, 3, 31, 10, 0),
                'avg_temp': 65.0,
                'min_temp': 60.0,
                'max_temp': 70.0,
                'avg_pressure': 1018.0,
                'avg_humidity': 65.0,
                'avg_wind': 8.0,
            },
            {
                'hour': datetime(2026, 3, 31, 11, 0),
                'avg_temp': 68.0,
                'min_temp': 63.0,
                'max_temp': 73.0,
                'avg_pressure': 1017.5,
                'avg_humidity': 62.0,
                'avg_wind': 10.0,
            },
        ]

        mock_session.execute.return_value.mappings.return_value.all.return_value = (
            mock_result
        )

        result = get_state_trends.__wrapped__(mock_session, 'VA')

        assert 'labels' in result
        assert 'temperature' in result
        assert 'pressure' in result
        assert len(result['labels']) == 2
        assert result['temperature']['avg'] == [65.0, 68.0]

    def test_returns_empty_for_no_data(self):
        """Should return empty arrays for state with no data."""
        from haminfo_dashboard.state_queries import get_state_trends

        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []

        result = get_state_trends.__wrapped__(mock_session, 'XX')

        assert result['labels'] == []
        assert result['temperature']['avg'] == []


class TestDetectStateAlerts:
    """Tests for detect_state_alerts function."""

    def test_detects_high_wind_alert(self):
        """Should detect high wind warning when wind > 40 mph."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        stations = [
            {
                'callsign': 'W4TEST',
                'wind_speed': 45.0,
                'wind_gust': 55.0,
                'temperature': 75.0,
                'humidity': 50,
                'pressure': 1015.0,
                'rain_1h': 0.0,
            },
        ]

        alerts = detect_state_alerts(stations)

        assert len(alerts) > 0
        assert any(a['type'] == 'high_wind' for a in alerts)

    def test_detects_extreme_heat(self):
        """Should detect heat warning when temp > 100F."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        stations = [
            {
                'callsign': 'W5HOT',
                'temperature': 105.0,
                'humidity': 30,
                'wind_speed': 5.0,
                'wind_gust': None,
                'pressure': 1010.0,
                'rain_1h': 0.0,
            },
        ]

        alerts = detect_state_alerts(stations)

        assert len(alerts) > 0
        assert any(a['type'] == 'extreme_heat' for a in alerts)

    def test_no_alerts_for_normal_conditions(self):
        """Should return empty list for normal weather."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        stations = [
            {
                'callsign': 'W4NORM',
                'temperature': 72.0,
                'humidity': 55,
                'wind_speed': 8.0,
                'wind_gust': 12.0,
                'pressure': 1018.0,
                'rain_1h': 0.0,
            },
        ]

        alerts = detect_state_alerts(stations)

        assert alerts == []

    def test_handles_empty_stations(self):
        """Should return empty list for no stations."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        alerts = detect_state_alerts([])

        assert alerts == []
