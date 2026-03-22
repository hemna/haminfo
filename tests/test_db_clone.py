# tests/test_db_clone.py
"""Tests for database clone functionality."""

import pytest


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
