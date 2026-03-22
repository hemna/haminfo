# tests/test_db_clone.py
"""Tests for database clone functionality."""

import pytest
from unittest.mock import patch, MagicMock


class TestParseDbUrl:
    """Test PostgreSQL URL parsing."""

    def test_parse_standard_url(self):
        """Parse a standard PostgreSQL URL."""
        from haminfo.db.clone import parse_db_url

        url = 'postgresql://user:pass@host.example.com:5432/dbname'
        result = parse_db_url(url)

        assert result['user'] == 'user'
        assert result['password'] == 'pass'
        assert result['host'] == 'host.example.com'
        assert result['port'] == '5432'
        assert result['database'] == 'dbname'

    def test_parse_url_default_port(self):
        """Parse URL without explicit port (defaults to 5432)."""
        from haminfo.db.clone import parse_db_url

        url = 'postgresql://user:pass@host.example.com/dbname'
        result = parse_db_url(url)

        assert result['port'] == '5432'

    def test_parse_url_with_special_chars_in_password(self):
        """Parse URL with URL-encoded special characters in password."""
        from haminfo.db.clone import parse_db_url

        # Password is "p@ss:word" URL-encoded as "p%40ss%3Aword"
        url = 'postgresql://user:p%40ss%3Aword@host/dbname'
        result = parse_db_url(url)

        assert result['password'] == 'p@ss:word'

    def test_parse_invalid_url_raises(self):
        """Invalid URL raises ValueError."""
        from haminfo.db.clone import parse_db_url

        with pytest.raises(ValueError, match='Invalid database URL'):
            parse_db_url('not-a-valid-url')

    def test_parse_non_postgresql_url_raises(self):
        """Non-PostgreSQL URL raises ValueError."""
        from haminfo.db.clone import parse_db_url

        with pytest.raises(ValueError, match='Only PostgreSQL'):
            parse_db_url('mysql://user:pass@host/db')


class TestTestDbConnection:
    """Test database connection testing."""

    @patch('haminfo.db.clone.create_engine')
    def test_connection_success(self, mock_create_engine):
        """Successful connection returns True."""
        from haminfo.db.clone import test_db_connection

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_engine.return_value = mock_engine

        result = test_db_connection('postgresql://user:pass@host/db')

        assert result is True

    @patch('haminfo.db.clone.create_engine')
    def test_connection_failure(self, mock_create_engine):
        """Failed connection returns False."""
        from haminfo.db.clone import test_db_connection

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception('Connection refused')
        mock_create_engine.return_value = mock_engine

        result = test_db_connection('postgresql://user:pass@host/db')

        assert result is False


class TestGetTableList:
    """Test table list generation."""

    def test_default_tables(self):
        """Returns all application tables by default."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=None, exclude=None)

        assert 'station' in tables
        assert 'weather_station' in tables
        assert 'weather_report' in tables
        assert 'aprs_packet' in tables
        assert 'request' in tables
        assert 'wx_request' in tables
        assert 'alembic_version' not in tables

    def test_include_filter(self):
        """Include filter limits to specified tables."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=['station', 'weather_station'], exclude=None)

        assert tables == ['station', 'weather_station']

    def test_exclude_filter(self):
        """Exclude filter removes specified tables."""
        from haminfo.db.clone import get_table_list

        tables = get_table_list(include=None, exclude=['request', 'wx_request'])

        assert 'station' in tables
        assert 'request' not in tables
        assert 'wx_request' not in tables

    def test_include_invalid_table_raises(self):
        """Including invalid table raises ValueError."""
        from haminfo.db.clone import get_table_list

        with pytest.raises(ValueError, match='Unknown table'):
            get_table_list(include=['station', 'invalid_table'], exclude=None)


class TestBuildPgDumpCommand:
    """Test pg_dump command construction."""

    def test_basic_command(self):
        """Build basic pg_dump command."""
        from haminfo.db.clone import build_pg_dump_command

        db_info = {
            'host': 'prod.example.com',
            'port': '5432',
            'user': 'haminfo',
            'database': 'haminfo',
        }
        tables = ['station', 'weather_station']

        cmd = build_pg_dump_command(db_info, tables)

        assert cmd[0] == 'pg_dump'
        assert '--data-only' in cmd
        assert '--no-owner' in cmd
        assert '--no-privileges' in cmd
        assert '-h' in cmd
        assert 'prod.example.com' in cmd
        assert '-p' in cmd
        assert '5432' in cmd
        assert '-U' in cmd
        assert 'haminfo' in cmd
        assert '--table=station' in cmd
        assert '--table=weather_station' in cmd


class TestBuildPsqlCommand:
    """Test psql command construction."""

    def test_basic_command(self):
        """Build basic psql command."""
        from haminfo.db.clone import build_psql_command

        db_info = {
            'host': 'localhost',
            'port': '5432',
            'user': 'haminfo',
            'database': 'haminfo',
        }

        cmd = build_psql_command(db_info)

        assert cmd[0] == 'psql'
        assert '--quiet' in cmd
        assert '-h' in cmd
        assert 'localhost' in cmd
        assert '-p' in cmd
        assert '5432' in cmd
        assert '-U' in cmd
        assert 'haminfo' in cmd
        assert '-d' in cmd
