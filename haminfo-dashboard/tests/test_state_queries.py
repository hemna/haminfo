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

        # Mock station data - temperatures in Fahrenheit (will be converted to Celsius)
        # 72°F = 22.2°C
        mock_result = [
            {
                'callsign': 'W4TEST',
                'latitude': 37.5,
                'longitude': -77.5,
                'temperature': 72.0,  # Fahrenheit (will be converted)
                'humidity': 65,
                'pressure': 1018.5,
                'wind_speed': 13.0,  # km/h
                'wind_gust': 24.0,  # km/h
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
        # 72°F = (72-32)*5/9 = 22.22°C
        assert abs(result[0]['temperature'] - 22.22) < 0.1

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

        # All values in metric units: temp in Celsius, wind in km/h
        stations = [
            {
                'temperature': 21.0,  # 70°F -> 21.1°C
                'humidity': 60,
                'pressure': 1015.0,
                'wind_speed': 8.0,  # km/h
                'wind_gust': 13.0,
            },
            {
                'temperature': 27.0,  # 80°F -> 26.7°C
                'humidity': 70,
                'pressure': 1020.0,
                'wind_speed': 16.0,
                'wind_gust': 24.0,
            },
            {
                'temperature': 24.0,  # 75°F -> 23.9°C
                'humidity': 65,
                'pressure': 1018.0,
                'wind_speed': 13.0,
                'wind_gust': 19.0,
            },
        ]

        result = compute_state_aggregates(stations)

        assert result['avg_temp'] == 24.0  # (21 + 27 + 24) / 3
        assert result['min_temp'] == 21.0
        assert result['max_temp'] == 27.0
        assert result['avg_humidity'] == 65.0
        assert result['avg_wind'] == pytest.approx(12.33, rel=0.01)  # (8 + 16 + 13) / 3

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

        # Values in metric units
        stations = [
            {
                'temperature': 21.0,  # Celsius
                'humidity': None,
                'pressure': 1015.0,
                'wind_speed': 8.0,
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
                'temperature': 27.0,  # Celsius
                'humidity': 70,
                'pressure': 1020.0,
                'wind_speed': 16.0,
                'wind_gust': 24.0,
            },
        ]

        result = compute_state_aggregates(stations)

        assert result['avg_temp'] == 24.0  # (21 + 27) / 2
        assert result['avg_humidity'] == 65.0  # (60 + 70) / 2


class TestGetStateTrends:
    """Tests for get_state_trends function."""

    def test_returns_hourly_trend_data(self):
        """Should return 24h trend data bucketed by hour."""
        from haminfo_dashboard.state_queries import get_state_trends

        mock_session = MagicMock()

        # Mock hourly data - temperatures in Fahrenheit (will be converted to Celsius)
        # 65°F = 18.33°C, 68°F = 20°C
        mock_result = [
            {
                'hour': datetime(2026, 3, 31, 10, 0),
                'avg_temp': 65.0,  # Fahrenheit
                'min_temp': 60.0,
                'max_temp': 70.0,
                'avg_pressure': 1018.0,
                'avg_humidity': 65.0,
                'avg_wind': 13.0,  # km/h
            },
            {
                'hour': datetime(2026, 3, 31, 11, 0),
                'avg_temp': 68.0,  # Fahrenheit
                'min_temp': 63.0,
                'max_temp': 73.0,
                'avg_pressure': 1017.5,
                'avg_humidity': 62.0,
                'avg_wind': 16.0,
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
        # 65°F = 18.33°C, 68°F = 20°C
        assert abs(result['temperature']['avg'][0] - 18.33) < 0.1
        assert result['temperature']['avg'][1] == 20.0

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
        """Should detect high wind warning when wind > 40 (threshold in code)."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        # Wind speed > 40 triggers high_wind alert
        # (Note: thresholds are in inconsistent units in the code)
        stations = [
            {
                'callsign': 'W4TEST',
                'wind_speed': 45.0,
                'wind_gust': 55.0,
                'temperature': 24.0,  # Celsius
                'humidity': 50,
                'pressure': 1015.0,
                'rain_1h': 0.0,
            },
        ]

        alerts = detect_state_alerts(stations)

        assert len(alerts) > 0
        assert any(a['type'] == 'high_wind' for a in alerts)

    def test_detects_extreme_heat(self):
        """Should detect heat warning when temp > 37.8°C (100°F)."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        # Temperature in Celsius - 40.5°C > 37.8°C threshold
        stations = [
            {
                'callsign': 'W5HOT',
                'temperature': 40.5,  # Celsius
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

        # Normal conditions - below all thresholds
        stations = [
            {
                'callsign': 'W4NORM',
                'temperature': 22.0,  # Celsius (~72°F) - below 37.8°C
                'humidity': 55,
                'wind_speed': 8.0,  # Below 40 threshold
                'wind_gust': 12.0,  # Below 75 threshold
                'pressure': 1018.0,
                'rain_1h': 0.0,  # Below 1.0 threshold
            },
        ]

        alerts = detect_state_alerts(stations)

        assert alerts == []

    def test_handles_empty_stations(self):
        """Should return empty list for no stations."""
        from haminfo_dashboard.state_queries import detect_state_alerts

        alerts = detect_state_alerts([])

        assert alerts == []
