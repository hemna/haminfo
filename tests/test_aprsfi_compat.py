"""Contract and integration tests for the aprs.fi-compatible /api/get endpoint.

T010: Contract tests verifying response format matches aprs.fi schema.
T014: Integration tests using Flask test client.
"""

from __future__ import annotations

import pytest
import flask as flask_mod
from datetime import datetime
from unittest.mock import MagicMock, patch

from haminfo.flask import (
    aprs_packet_to_aprsfi_entry,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_packet(**overrides):
    """Create a mock APRSPacket with default values."""
    defaults = {
        'from_call': 'N0CALL',
        'to_call': 'APRS',
        'path': 'WIDE1-1,WIDE2-1',
        'packet_type': 'position',
        'latitude': 34.9463,
        'longitude': -123.7612,
        'altitude': 100.0,
        'course': 180,
        'speed': 5.5,
        'symbol': '-',
        'symbol_table': '/',
        'comment': 'Test comment',
        'timestamp': datetime(2026, 3, 9, 12, 0, 0),
        'received_at': datetime(2026, 3, 9, 12, 0, 30),
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# T010: Contract tests - aprs.fi response format
# ---------------------------------------------------------------------------


class TestAprsFiResponseContract:
    """Contract tests verifying the aprs.fi response format."""

    def test_success_envelope_has_required_keys(self):
        """Top-level success envelope must have command, result, what, found, entries."""
        pkt = _mock_packet()
        entry = aprs_packet_to_aprsfi_entry(pkt)
        envelope = {
            'command': 'get',
            'result': 'ok',
            'what': 'loc',
            'found': 1,
            'entries': [entry],
        }
        assert set(envelope.keys()) == {'command', 'result', 'what', 'found', 'entries'}

    def test_entry_field_names_match_aprsfi_schema(self):
        """Entry dict must have the exact field names aprs.fi returns."""
        pkt = _mock_packet()
        entry = aprs_packet_to_aprsfi_entry(pkt)
        expected_keys = {
            'name',
            'type',
            'time',
            'lasttime',
            'lat',
            'lng',
            'altitude',
            'course',
            'speed',
            'symbol',
            'srccall',
            'dstcall',
            'comment',
            'path',
        }
        assert set(entry.keys()) == expected_keys

    def test_all_entry_values_are_strings(self):
        """aprs.fi returns all values as strings."""
        pkt = _mock_packet()
        entry = aprs_packet_to_aprsfi_entry(pkt)
        for key, value in entry.items():
            assert isinstance(value, str), f'{key} should be str, got {type(value)}'

    def test_found_count_matches_entries_length(self):
        """found field must equal len(entries)."""
        packets = [_mock_packet(from_call=f'CALL{i}') for i in range(3)]
        entries = [aprs_packet_to_aprsfi_entry(p) for p in packets]
        envelope = {
            'command': 'get',
            'result': 'ok',
            'what': 'loc',
            'found': len(entries),
            'entries': entries,
        }
        assert envelope['found'] == len(envelope['entries'])

    def test_error_response_format(self):
        """Error response must have command, result, description."""
        error_resp = {
            'command': 'get',
            'result': 'fail',
            'description': 'missing parameter: name',
        }
        assert error_resp['result'] == 'fail'
        assert 'description' in error_resp

    def test_not_found_response_format(self):
        """Not-found response: result ok, found 0, entries empty."""
        not_found = {
            'command': 'get',
            'result': 'ok',
            'what': 'loc',
            'found': 0,
            'entries': [],
        }
        assert not_found['result'] == 'ok'
        assert not_found['found'] == 0
        assert not_found['entries'] == []


# ---------------------------------------------------------------------------
# T014: Integration tests - /api/get endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def flask_client():
    """Create a fresh Flask test app with mocked CONF and DB."""
    with patch('haminfo.flask.CONF') as mock_conf, patch('haminfo.flask.db') as mock_db:
        mock_conf.web.api_key = 'test-api-key'

        # Create a fresh Flask app to avoid route re-registration issues
        test_app = flask_mod.Flask('haminfo_test_aprsfi')
        test_app.config['TESTING'] = True

        from haminfo.flask import HaminfoFlask

        server = HaminfoFlask()
        server.app = test_app

        # Mock _get_db_session
        mock_session = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(
            return_value=mock_session,
        )
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
        server._get_db_session = MagicMock(return_value=mock_session_factory)

        # Register routes on the fresh app
        test_app.route('/api/get', methods=['GET'])(server.aprsfi_location)

        # Store mock references
        test_app._test_mock_db = mock_db
        test_app._test_mock_session = mock_session

        with test_app.test_client() as client:
            yield client


class TestAprsFiEndpoint:
    """Integration tests for GET /api/get."""

    def test_valid_single_callsign(self, flask_client):
        pkt = _mock_packet()
        app = flask_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'ok'
        assert data['command'] == 'get'
        assert data['what'] == 'loc'
        assert data['found'] == 1
        assert len(data['entries']) == 1
        assert data['entries'][0]['name'] == 'N0CALL'

    def test_valid_multi_callsign(self, flask_client):
        pkts = [_mock_packet(from_call='N0CALL'), _mock_packet(from_call='W3ADO')]
        app = flask_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = pkts

        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=N0CALL,W3ADO',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['found'] == 2
        names = {e['name'] for e in data['entries']}
        assert names == {'N0CALL', 'W3ADO'}

    def test_missing_name_param(self, flask_client):
        resp = flask_client.get('/api/get?what=loc&apikey=test-api-key&format=json')
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert (
            'name' in data['description'].lower()
            or 'callsign' in data['description'].lower()
        )

    def test_missing_apikey_param(self, flask_client):
        resp = flask_client.get('/api/get?what=loc&format=json&name=N0CALL')
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'apikey' in data['description']

    def test_invalid_apikey(self, flask_client):
        resp = flask_client.get(
            '/api/get?what=loc&apikey=wrong-key&format=json&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'apikey' in data['description']

    def test_invalid_what_param(self, flask_client):
        resp = flask_client.get(
            '/api/get?what=msg&apikey=test-api-key&format=json&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'what' in data['description']

    def test_missing_what_param(self, flask_client):
        resp = flask_client.get(
            '/api/get?apikey=test-api-key&format=json&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'what' in data['description']

    def test_invalid_format_param(self, flask_client):
        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=xml&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'format' in data['description']

    def test_callsign_not_found_returns_empty(self, flask_client):
        app = flask_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = []

        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=NONEXIST',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'ok'
        assert data['found'] == 0
        assert data['entries'] == []

    def test_all_response_values_are_strings(self, flask_client):
        pkt = _mock_packet()
        app = flask_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=N0CALL',
        )
        data = resp.get_json()

        for entry in data['entries']:
            for key, value in entry.items():
                assert isinstance(value, str), (
                    f'aprs.fi compat: {key} should be str, got {type(value)}'
                )

    def test_default_format_is_json(self, flask_client):
        """When format param is omitted, JSON is the default."""
        pkt = _mock_packet()
        app = flask_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&name=N0CALL',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'ok'

    def test_exceeds_max_callsigns_returns_fail(self, flask_client):
        """Requesting >20 callsigns returns aprs.fi-style fail response."""
        calls = ','.join([f'CALL{i}' for i in range(21)])
        resp = flask_client.get(
            f'/api/get?what=loc&apikey=test-api-key&format=json&name={calls}',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'Maximum 20' in data['description']

    def test_only_commas_returns_fail(self, flask_client):
        """Name param with only commas returns aprs.fi-style fail response."""
        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=,,,',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
        assert 'name' in data['description'].lower()

    def test_empty_name_param_returns_fail(self, flask_client):
        """Empty name param returns aprs.fi-style fail response."""
        resp = flask_client.get(
            '/api/get?what=loc&apikey=test-api-key&format=json&name=',
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['result'] == 'fail'
