"""Tests for SQL query validation module."""

from __future__ import annotations

import pytest

from haminfo.utils.sql_validator import (
    validate_query,
    validate_table_name,
    SQLValidationError,
    MAX_RESULT_LIMIT,
)


class TestValidateQuery:
    """Tests for validate_query function."""

    def test_valid_select_query(self):
        result = validate_query('SELECT * FROM station LIMIT 10')
        assert 'SELECT' in result
        assert 'LIMIT' in result

    def test_valid_select_with_where(self):
        result = validate_query(
            "SELECT callsign, frequency FROM station WHERE state = 'CA' LIMIT 10"
        )
        assert 'WHERE' in result

    def test_adds_limit_if_missing(self):
        result = validate_query('SELECT * FROM station')
        assert f'LIMIT {MAX_RESULT_LIMIT}' in result

    def test_preserves_existing_limit(self):
        result = validate_query('SELECT * FROM station LIMIT 5')
        assert 'LIMIT 5' in result
        # Should not have added another LIMIT
        assert result.count('LIMIT') == 1

    def test_rejects_empty_query(self):
        with pytest.raises(SQLValidationError, match='Empty query'):
            validate_query('')

    def test_rejects_whitespace_only(self):
        with pytest.raises(SQLValidationError, match='Empty query'):
            validate_query('   ')

    def test_rejects_drop_table(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: DROP'):
            validate_query('DROP TABLE station')

    def test_rejects_delete(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: DELETE'):
            validate_query('DELETE FROM station WHERE id = 1')

    def test_rejects_update(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: UPDATE'):
            validate_query("UPDATE station SET callsign = 'HACKED'")

    def test_rejects_insert(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: INSERT'):
            validate_query("INSERT INTO station (callsign) VALUES ('TEST')")

    def test_rejects_truncate(self):
        with pytest.raises(
            SQLValidationError, match='Forbidden SQL operation: TRUNCATE'
        ):
            validate_query('TRUNCATE TABLE station')

    def test_rejects_alter(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: ALTER'):
            validate_query('ALTER TABLE station ADD COLUMN evil TEXT')

    def test_rejects_create(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: CREATE'):
            validate_query('CREATE TABLE evil (id INT)')

    def test_rejects_grant(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation: GRANT'):
            validate_query('GRANT ALL ON station TO evil_user')

    def test_rejects_non_select(self):
        with pytest.raises(SQLValidationError, match='Only SELECT queries'):
            validate_query('EXPLAIN SELECT * FROM station')

    def test_rejects_multiple_statements(self):
        # DROP is caught by keyword check before multi-statement check
        with pytest.raises(SQLValidationError):
            validate_query('SELECT 1; DROP TABLE station')

    def test_rejects_multiple_select_statements(self):
        with pytest.raises(SQLValidationError, match='Multiple SQL statements'):
            validate_query('SELECT 1; SELECT 2')

    def test_allows_semicolon_in_string(self):
        # Semicolons inside quotes should not trigger multi-statement rejection
        result = validate_query(
            "SELECT * FROM station WHERE callsign = 'W;6ABC' LIMIT 10"
        )
        assert 'W;6ABC' in result

    def test_rejects_long_query(self):
        long_query = 'SELECT * FROM station WHERE ' + "callsign = 'A' OR " * 200
        with pytest.raises(SQLValidationError, match='exceeds maximum length'):
            validate_query(long_query)

    def test_rejects_pg_sleep(self):
        with pytest.raises(SQLValidationError, match='dangerous SQL pattern'):
            validate_query('SELECT pg_sleep(10)')

    def test_rejects_into_outfile(self):
        with pytest.raises(SQLValidationError, match='dangerous SQL pattern'):
            validate_query("SELECT * INTO OUTFILE '/etc/passwd' FROM station")

    def test_case_insensitive_keyword_detection(self):
        with pytest.raises(SQLValidationError, match='Forbidden SQL operation'):
            validate_query('drop TABLE station')

    def test_does_not_false_positive_on_column_names(self):
        """Ensure 'UPDATED_AT' doesn't match 'UPDATE'."""
        result = validate_query('SELECT updated_at FROM station LIMIT 10')
        assert 'updated_at' in result

    def test_strips_sql_comments(self):
        result = validate_query('-- This is a comment\nSELECT * FROM station LIMIT 10')
        assert 'SELECT' in result


class TestValidateTableName:
    """Tests for validate_table_name function."""

    def test_allowed_tables(self):
        # Only actual table names are allowed (not plural forms)
        allowed = [
            'station',
            'weather_station',
            'weather_report',
            'aprs_packet',
            'request',
            'wx_request',
        ]
        for table in allowed:
            assert validate_table_name(table) is True

    def test_plural_tables_not_allowed(self):
        # Plural forms don't correspond to actual tables
        not_allowed = ['stations', 'weather_stations', 'weather_reports']
        for table in not_allowed:
            with pytest.raises(SQLValidationError, match='not in the allowed list'):
                validate_table_name(table)

    def test_disallowed_table(self):
        with pytest.raises(SQLValidationError, match='not in the allowed list'):
            validate_table_name('pg_shadow')

    def test_case_insensitive(self):
        assert validate_table_name('STATION') is True
        assert validate_table_name('Station') is True


class TestSQLValidationError:
    """Tests for SQLValidationError exception."""

    def test_error_message(self):
        err = SQLValidationError('test error', 'SELECT BAD')
        assert str(err) == 'test error'
        assert err.query == 'SELECT BAD'

    def test_error_without_query(self):
        err = SQLValidationError('test error')
        assert err.query == ''
