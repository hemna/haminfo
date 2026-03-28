# tests/test_dashboard_api.py
"""Tests for dashboard API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from unittest.mock import patch

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation


@pytest.fixture
def dashboard_app(engine):
    """Create Flask test application with dashboard blueprint."""
    from sqlalchemy.orm import scoped_session, sessionmaker

    from haminfo.flask import app as flask_app
    from haminfo.dashboard import dashboard_bp

    flask_app.config['TESTING'] = True

    # Create the scoped session that will be used by both Flask and fixtures
    test_session_factory = scoped_session(sessionmaker(bind=engine))

    # Store it so other fixtures can access it
    flask_app.test_session_factory = test_session_factory

    # Register dashboard blueprint if not already registered
    registered_blueprints = [bp.name for bp in flask_app.blueprints.values()]
    if 'dashboard' not in registered_blueprints:
        flask_app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    # Patch the DB session to use our test engine
    with patch('haminfo.db.db.get_engine', return_value=engine):
        with patch('haminfo.db.db.setup_session', return_value=test_session_factory):
            yield flask_app

            # Clean up the scoped session and delete test data
            test_session_factory.remove()

            # Delete all test data created during the test
            with engine.connect() as conn:
                conn.execute(APRSPacket.__table__.delete())
                conn.commit()


@pytest.fixture
def dashboard_client(dashboard_app):
    """Create Flask test client for dashboard."""
    return dashboard_app.test_client()


@pytest.fixture
def sample_packets(dashboard_app, engine):
    """Create sample APRS packets for testing."""
    # Use a fresh connection for inserting test data
    from sqlalchemy.orm import Session

    with engine.connect() as conn:
        session = Session(bind=conn)
        now = datetime.utcnow()

        packets = []
        # Add packets from different stations (each at different times)
        for i in range(5):
            packet = APRSPacket(
                from_call=f'N{i}CALL',
                to_call='APRS',
                timestamp=now - timedelta(hours=i + 1),
                received_at=now - timedelta(hours=i + 1),
                raw=f'N{i}CALL>APRS:test{i}',
                packet_type='position',
                latitude=40.0 + i * 0.1,
                longitude=-105.0 + i * 0.1,
            )
            session.add(packet)
            packets.append(packet)

        # Add extra packets for N0CALL to make it top station
        # Use different timestamps to avoid unique constraint violation
        for i in range(3):
            packet = APRSPacket(
                from_call='N0CALL',
                to_call='APRS',
                timestamp=now - timedelta(minutes=(i + 1) * 5),
                received_at=now - timedelta(minutes=(i + 1) * 5),
                raw=f'N0CALL>APRS:extra{i}',
                packet_type='position',
                latitude=40.5,
                longitude=-105.5,
            )
            session.add(packet)

        session.commit()
        session.close()

    yield packets

    # Clean up
    with engine.connect() as conn:
        conn.execute(APRSPacket.__table__.delete())
        conn.commit()


class TestStatsEndpoint:
    """Tests for /api/dashboard/stats endpoint."""

    def test_stats_json_returns_200(self, dashboard_client, sample_packets):
        """Stats JSON endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/stats/json')
        assert response.status_code == 200

    def test_stats_json_returns_required_fields(self, dashboard_client, sample_packets):
        """Stats JSON returns required fields."""
        response = dashboard_client.get('/dashboard/api/dashboard/stats/json')
        data = response.get_json()

        assert 'total_packets_24h' in data
        assert 'unique_stations' in data
        assert 'countries' in data
        assert 'weather_stations' in data

    def test_stats_json_counts_packets(self, dashboard_client, sample_packets):
        """Stats JSON counts packets correctly."""
        response = dashboard_client.get('/dashboard/api/dashboard/stats/json')
        data = response.get_json()

        # We created 8 packets total (5 from different stations + 3 extra from N0CALL)
        assert data['total_packets_24h'] == 8


class TestTopStationsEndpoint:
    """Tests for /api/dashboard/top-stations endpoint."""

    def test_top_stations_json_returns_200(self, dashboard_client, sample_packets):
        """Top stations JSON endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/top-stations/json')
        assert response.status_code == 200

    def test_top_stations_json_returns_list(self, dashboard_client, sample_packets):
        """Top stations JSON returns a list."""
        response = dashboard_client.get('/dashboard/api/dashboard/top-stations/json')
        data = response.get_json()
        assert isinstance(data, list)

    def test_top_stations_respects_limit(self, dashboard_client, sample_packets):
        """Top stations respects limit parameter."""
        response = dashboard_client.get(
            '/dashboard/api/dashboard/top-stations/json?limit=3'
        )
        data = response.get_json()
        assert len(data) <= 3

    def test_top_stations_orders_by_count(self, dashboard_client, sample_packets):
        """Top stations ordered by packet count."""
        response = dashboard_client.get('/dashboard/api/dashboard/top-stations/json')
        data = response.get_json()

        if len(data) >= 1:
            # N0CALL has 4 packets total (1 from first loop + 3 extra)
            assert data[0]['callsign'] == 'N0CALL'


class TestCountriesEndpoint:
    """Tests for /api/dashboard/countries endpoint."""

    def test_countries_json_returns_200(self, dashboard_client, sample_packets):
        """Countries JSON endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/countries/json')
        assert response.status_code == 200

    def test_countries_json_returns_list(self, dashboard_client, sample_packets):
        """Countries JSON returns a list."""
        response = dashboard_client.get('/dashboard/api/dashboard/countries/json')
        data = response.get_json()
        assert isinstance(data, list)


class TestHourlyEndpoint:
    """Tests for /api/dashboard/hourly endpoint."""

    def test_hourly_returns_200(self, dashboard_client, sample_packets):
        """Hourly endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/hourly')
        assert response.status_code == 200

    def test_hourly_returns_labels_and_values(self, dashboard_client, sample_packets):
        """Hourly returns labels and values arrays."""
        response = dashboard_client.get('/dashboard/api/dashboard/hourly')
        data = response.get_json()

        assert 'labels' in data
        assert 'values' in data

    def test_hourly_returns_24_items(self, dashboard_client, sample_packets):
        """Hourly returns exactly 24 items."""
        response = dashboard_client.get('/dashboard/api/dashboard/hourly')
        data = response.get_json()

        assert len(data['labels']) == 24
        assert len(data['values']) == 24


class TestMapStationsEndpoint:
    """Tests for /api/dashboard/map/stations endpoint."""

    def test_map_stations_returns_200(self, dashboard_client, sample_packets):
        """Map stations endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/map/stations')
        assert response.status_code == 200

    def test_map_stations_returns_geojson(self, dashboard_client, sample_packets):
        """Map stations returns GeoJSON FeatureCollection."""
        response = dashboard_client.get('/dashboard/api/dashboard/map/stations')
        data = response.get_json()

        assert data['type'] == 'FeatureCollection'
        assert 'features' in data
        assert isinstance(data['features'], list)

    def test_map_stations_features_have_geometry(
        self, dashboard_client, sample_packets
    ):
        """Map stations features have proper geometry."""
        response = dashboard_client.get('/dashboard/api/dashboard/map/stations')
        data = response.get_json()

        if data['features']:
            feature = data['features'][0]
            assert feature['type'] == 'Feature'
            assert 'geometry' in feature
            assert feature['geometry']['type'] == 'Point'
            assert 'coordinates' in feature['geometry']
            assert len(feature['geometry']['coordinates']) == 2

    def test_map_stations_features_have_properties(
        self, dashboard_client, sample_packets
    ):
        """Map stations features have callsign in properties."""
        response = dashboard_client.get('/dashboard/api/dashboard/map/stations')
        data = response.get_json()

        if data['features']:
            feature = data['features'][0]
            assert 'properties' in feature
            assert 'callsign' in feature['properties']


class TestStationDetailEndpoint:
    """Tests for /api/dashboard/station/<callsign> endpoint."""

    def test_station_detail_returns_404_for_unknown(self, dashboard_client):
        """Station detail returns 404 for unknown callsign."""
        response = dashboard_client.get(
            '/dashboard/api/dashboard/station/UNKNOWN123/json'
        )
        assert response.status_code == 404

    def test_station_detail_returns_error_json(self, dashboard_client):
        """Station detail returns error JSON for unknown callsign."""
        response = dashboard_client.get(
            '/dashboard/api/dashboard/station/UNKNOWN123/json'
        )
        data = response.get_json()

        assert 'error' in data
        assert data['callsign'] == 'UNKNOWN123'

    def test_station_detail_returns_200_for_known(
        self, dashboard_client, sample_packets
    ):
        """Station detail returns 200 for known callsign."""
        response = dashboard_client.get('/dashboard/api/dashboard/station/N0CALL/json')
        assert response.status_code == 200

    def test_station_detail_returns_station_info(
        self, dashboard_client, sample_packets
    ):
        """Station detail returns station information."""
        response = dashboard_client.get('/dashboard/api/dashboard/station/N0CALL/json')
        data = response.get_json()

        assert data['callsign'] == 'N0CALL'
        assert 'last_seen' in data
        assert 'packet_count_24h' in data


class TestPacketsEndpoint:
    """Tests for /api/dashboard/packets endpoint."""

    def test_packets_returns_200(self, dashboard_client, sample_packets):
        """Packets endpoint returns 200."""
        response = dashboard_client.get('/dashboard/api/dashboard/packets')
        assert response.status_code == 200

    def test_packets_returns_list(self, dashboard_client, sample_packets):
        """Packets endpoint returns a list."""
        response = dashboard_client.get('/dashboard/api/dashboard/packets')
        data = response.get_json()
        assert isinstance(data, list)

    def test_packets_respects_limit(self, dashboard_client, sample_packets):
        """Packets endpoint respects limit parameter."""
        response = dashboard_client.get('/dashboard/api/dashboard/packets?limit=3')
        data = response.get_json()
        assert len(data) <= 3
