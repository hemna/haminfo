"""Pytest configuration and shared fixtures for haminfo tests."""

from __future__ import annotations

import re
import pytest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from haminfo.db.models.modelbase import ModelBase


@pytest.fixture(scope='session')
def engine():
    """Create a SQLite in-memory engine for testing.

    Uses SQLite for speed; PostGIS-specific features are not
    tested here (those need integration tests).

    Geography columns are rendered as TEXT and GeoAlchemy2's spatial
    DDL operations (which call SpatiaLite functions) are disabled via
    monkey-patching the dialect handlers.
    """
    engine = create_engine('sqlite:///:memory:', echo=False)

    # Intercept SQL to neutralize all GeoAlchemy2/PostGIS function calls
    # that SQLite can't handle:
    #   - geography(POINT,...) in DDL -> TEXT
    #   - ST_GeogFromText(?) in INSERT -> ? (pass value through)
    #   - AsBinary(col) in SELECT -> col (read raw value)
    @event.listens_for(engine, 'before_cursor_execute', retval=True)
    def _intercept_geography(conn, cursor, statement, parameters, context, executemany):
        if 'geography(' in statement.lower():
            statement = re.sub(
                r'geography\([^)]*\)',
                'TEXT',
                statement,
                flags=re.IGNORECASE,
            )
        if 'st_geogfromtext(' in statement.lower():
            statement = re.sub(
                r'ST_GeogFromText\(([^)]*)\)',
                r'\1',
                statement,
                flags=re.IGNORECASE,
            )
        if 'asbinary(' in statement.lower():
            statement = re.sub(
                r'AsBinary\(([^)]*)\)',
                r'\1',
                statement,
                flags=re.IGNORECASE,
            )
        return statement, parameters

    # Monkey-patch GeoAlchemy2's SQLite dialect handlers to be no-ops
    # so they don't try to call SpatiaLite functions like CreateSpatialIndex
    import geoalchemy2.admin.dialects.sqlite as ga2_sqlite

    orig_after_create = ga2_sqlite.after_create
    orig_before_create = ga2_sqlite.before_create
    orig_before_drop = ga2_sqlite.before_drop
    orig_after_drop = ga2_sqlite.after_drop

    ga2_sqlite.after_create = lambda *a, **kw: None
    ga2_sqlite.before_create = lambda *a, **kw: None
    ga2_sqlite.before_drop = lambda *a, **kw: None
    ga2_sqlite.after_drop = lambda *a, **kw: None

    # Also patch the select_dialect function to return a no-op handler for sqlite
    import geoalchemy2.admin as ga2_admin

    orig_select_dialect = ga2_admin.select_dialect

    def _patched_select_dialect(dialect_name):
        if dialect_name == 'sqlite':
            # Return a module-like object with no-op methods
            return type(
                'NoOpDialect',
                (),
                {
                    'before_create': staticmethod(lambda *a, **kw: None),
                    'after_create': staticmethod(lambda *a, **kw: None),
                    'before_drop': staticmethod(lambda *a, **kw: None),
                    'after_drop': staticmethod(lambda *a, **kw: None),
                    'reflect_geometry_column': staticmethod(lambda *a, **kw: None),
                },
            )()
        return orig_select_dialect(dialect_name)

    ga2_admin.select_dialect = _patched_select_dialect

    try:
        ModelBase.metadata.create_all(engine)
    finally:
        # Restore original functions
        ga2_sqlite.after_create = orig_after_create
        ga2_sqlite.before_create = orig_before_create
        ga2_sqlite.before_drop = orig_before_drop
        ga2_sqlite.after_drop = orig_after_drop
        ga2_admin.select_dialect = orig_select_dialect

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
