"""Pytest configuration and shared fixtures for haminfo tests."""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from haminfo.db.models.modelbase import ModelBase


@pytest.fixture(scope='session')
def engine():
    """Create a SQLite in-memory engine for testing.

    Uses SQLite for speed; PostGIS-specific features are not
    tested here (those need integration tests).
    """
    engine = create_engine('sqlite:///:memory:', echo=False)
    # Create all tables
    ModelBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Create a fresh database session for each test.

    Each test gets its own transaction that is rolled back
    after the test completes.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def mock_conf():
    """Mock oslo.config CONF object."""
    with patch('haminfo.db.db.CONF') as mock_conf:
        mock_conf.database.connection = 'sqlite:///:memory:'
        mock_conf.database.debug = False
        mock_conf.memcached.url = None
        mock_conf.memcached.expire_time = 300
        yield mock_conf


@pytest.fixture
def sample_repeater_json():
    """Sample RepeaterBook JSON for a station."""
    return {
        'State ID': '51',
        'Rptr ID': '12345',
        'Last Update': '2024-01-15',
        'Frequency': '146.940',
        'Input Freq': '146.340',
        'PL': '100.0',
        'TSQ': '',
        'Lat': '37.7749',
        'Long': '-122.4194',
        'Callsign': 'W6ABC',
        'Country': 'United States',
        'State': 'California',
        'County': 'San Francisco',
        'Nearest City': 'San Francisco',
        'Landmark': 'Twin Peaks',
        'Operational Status': 'On-air',
        'Use': 'OPEN',
        'AllStar Node': 'No',
        'EchoLink Node': 'No',
        'IRLP Node': 'No',
        'Wires Node': 'No',
        'FM Analog': 'Yes',
        'DMR': 'No',
        'D-Star': 'No',
        'ARES': 'Yes',
        'RACES': 'No',
        'SKYWARN': 'Yes',
        'CANWARN': 'No',
    }


@pytest.fixture
def sample_weather_packet():
    """Sample APRS weather packet data."""
    return {
        'from_call': 'WX4TEST',
        'to_call': 'APRS',
        'path': ['WIDE1-1', 'WIDE2-1'],
        'raw': 'WX4TEST>APRS,WIDE1-1:@092345z3456.78N/12345.67W_090/005g010t072r000p000P000h50b10132',
        'latitude': 34.9463,
        'longitude': -123.7612,
        'timestamp': 1704844800,
        'weather': {
            'temperature': 72.0,
            'humidity': 50,
            'pressure': 1013.2,
            'wind_direction': 90,
            'wind_speed': 5.0,
            'wind_gust': 10.0,
            'rain_1h': 0.0,
            'rain_24h': 0.0,
            'rain_since_midnight': 0.0,
        },
    }


@pytest.fixture
def sample_aprs_packet():
    """Sample APRS position packet data."""
    return {
        'from_call': 'N0CALL',
        'to_call': 'APRS',
        'path': ['WIDE1-1', 'WIDE2-1'],
        'raw': 'N0CALL>APRS,WIDE1-1:!3456.78N/12345.67W-PHG2360',
        'packet_type': 'position',
        'latitude': 34.9463,
        'longitude': -123.7612,
        'timestamp': 1704844800,
        'symbol': '-',
        'symbol_table': '/',
        'comment': 'PHG2360',
    }


@pytest.fixture
def mock_flask_app():
    """Create a Flask test application."""
    from haminfo.flask import app

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
