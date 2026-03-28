# tests/test_routes.py
"""Tests for dashboard routes."""

import pytest
from unittest.mock import patch, MagicMock


class TestPageRoutes:
    """Tests for page routes."""

    def test_index_page(self, client):
        """Test index page loads."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'APRS Dashboard' in response.data

    def test_weather_page(self, client):
        """Test weather page loads."""
        response = client.get('/weather')
        assert response.status_code == 200
        assert b'Weather' in response.data

    def test_map_page(self, client):
        """Test map page loads."""
        response = client.get('/map')
        assert response.status_code == 200
        assert b'Map' in response.data or b'map' in response.data

    def test_station_lookup_page(self, client):
        """Test station lookup page loads."""
        response = client.get('/station/lookup')
        assert response.status_code == 200
        assert (
            b'Station Lookup' in response.data or b'callsign' in response.data.lower()
        )

    def test_station_detail_page(self, client):
        """Test station detail page loads."""
        response = client.get('/station/W1ABC')
        assert response.status_code == 200
        assert b'W1ABC' in response.data


class TestAPIRoutes:
    """Tests for API routes."""

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.api.get_dashboard_stats')
    def test_stats_json_endpoint(self, mock_stats, mock_session, client):
        """Test stats JSON endpoint."""
        mock_stats.return_value = {
            'total_packets_24h': 1000,
            'unique_stations': 50,
            'countries': 10,
            'weather_stations': 5,
        }
        mock_session.return_value = MagicMock()

        response = client.get('/api/dashboard/stats/json')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total_packets_24h'] == 1000
        assert data['unique_stations'] == 50

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.api.get_top_stations')
    def test_top_stations_json_endpoint(self, mock_stations, mock_session, client):
        """Test top stations JSON endpoint."""
        mock_stations.return_value = [
            {'callsign': 'W1ABC', 'count': 100, 'country_code': 'US'},
            {'callsign': '9M2PJU', 'count': 50, 'country_code': 'MY'},
        ]
        mock_session.return_value = MagicMock()

        response = client.get('/api/dashboard/top-stations/json')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert data[0]['callsign'] == 'W1ABC'

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.api.get_hourly_distribution')
    def test_hourly_endpoint(self, mock_hourly, mock_session, client):
        """Test hourly distribution endpoint."""
        mock_hourly.return_value = {
            'labels': ['00:00', '01:00'],
            'values': [10, 20],
        }
        mock_session.return_value = MagicMock()

        response = client.get('/api/dashboard/hourly')
        assert response.status_code == 200
        data = response.get_json()
        assert 'labels' in data
        assert 'values' in data

    @patch('haminfo_dashboard.api._get_session')
    @patch('haminfo_dashboard.api.get_station_detail')
    def test_station_detail_json_not_found(self, mock_detail, mock_session, client):
        """Test station detail returns 404 when not found."""
        mock_detail.return_value = None
        mock_session.return_value = MagicMock()

        response = client.get('/api/dashboard/station/UNKNOWN/json')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data
