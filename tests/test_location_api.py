"""Unit tests for location API validation and response formatters."""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from haminfo.flask import (
    validate_callsigns,
    aprs_packet_to_aprsfi_entry,
    aprs_packet_to_native_entry,
    ValidationError,
)


class TestValidateCallsigns:
    """Tests for validate_callsigns()."""

    def test_valid_single(self):
        result = validate_callsigns('N0CALL')
        assert result == ['N0CALL']

    def test_valid_multiple(self):
        result = validate_callsigns('N0CALL,W3ADO,K3ABC')
        assert result == ['N0CALL', 'W3ADO', 'K3ABC']

    def test_case_normalization(self):
        result = validate_callsigns('n0call,w3ado')
        assert result == ['N0CALL', 'W3ADO']

    def test_trims_whitespace(self):
        result = validate_callsigns(' N0CALL , W3ADO ')
        assert result == ['N0CALL', 'W3ADO']

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            validate_callsigns('')

    def test_none_raises(self):
        with pytest.raises(ValidationError):
            validate_callsigns(None)

    def test_only_commas_raises(self):
        with pytest.raises(ValidationError):
            validate_callsigns(',,,')

    def test_exceeds_max_callsigns(self):
        calls = ','.join([f'CALL{i}' for i in range(21)])
        with pytest.raises(ValidationError, match='Maximum 20'):
            validate_callsigns(calls)

    def test_exactly_max_callsigns(self):
        calls = ','.join([f'CALL{i}' for i in range(20)])
        result = validate_callsigns(calls)
        assert len(result) == 20


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


class TestAprsPacketToAprsFiEntry:
    """Tests for aprs_packet_to_aprsfi_entry()."""

    def test_all_fields_present(self):
        pkt = _mock_packet()
        result = aprs_packet_to_aprsfi_entry(pkt)

        assert result['name'] == 'N0CALL'
        assert result['srccall'] == 'N0CALL'
        assert result['dstcall'] == 'APRS'
        assert result['type'] == 'l'
        assert result['lat'] == '34.9463'
        assert result['lng'] == '-123.7612'
        assert result['altitude'] == '100'
        assert result['course'] == '180'
        assert result['speed'] == '5.5'
        assert result['symbol'] == '/-'
        assert result['comment'] == 'Test comment'
        assert result['path'] == 'WIDE1-1,WIDE2-1'

        # All values must be strings
        for key, value in result.items():
            assert isinstance(value, str), f'{key} should be str, got {type(value)}'

    def test_timestamps_as_unix_epoch(self):
        pkt = _mock_packet()
        result = aprs_packet_to_aprsfi_entry(pkt)
        # Verify they're Unix epoch strings (numeric)
        assert result['time'].isdigit()
        assert result['lasttime'].isdigit()

    def test_missing_optional_fields_default(self):
        pkt = _mock_packet(altitude=None, course=None, speed=None)
        result = aprs_packet_to_aprsfi_entry(pkt)
        assert result['altitude'] == '0'
        assert result['course'] == '0'
        assert result['speed'] == '0'

    def test_none_comment_path_default(self):
        pkt = _mock_packet(comment=None, path=None)
        result = aprs_packet_to_aprsfi_entry(pkt)
        assert result['comment'] == ''
        assert result['path'] == ''

    def test_packet_type_mapping(self):
        for ptype, expected in [('position', 'l'), ('object', 'o'), ('item', 'i')]:
            pkt = _mock_packet(packet_type=ptype)
            result = aprs_packet_to_aprsfi_entry(pkt)
            assert result['type'] == expected

    def test_unknown_packet_type_defaults_to_l(self):
        pkt = _mock_packet(packet_type='weather')
        result = aprs_packet_to_aprsfi_entry(pkt)
        assert result['type'] == 'l'

    def test_callsign_uppercased(self):
        pkt = _mock_packet(from_call='n0call', to_call='aprs')
        result = aprs_packet_to_aprsfi_entry(pkt)
        assert result['name'] == 'N0CALL'
        assert result['dstcall'] == 'APRS'


class TestAprsPacketToNativeEntry:
    """Tests for aprs_packet_to_native_entry()."""

    def test_all_fields_present(self):
        pkt = _mock_packet()
        result = aprs_packet_to_native_entry(pkt)

        assert result['callsign'] == 'N0CALL'
        assert result['latitude'] == 34.9463
        assert isinstance(result['latitude'], float)
        assert result['longitude'] == -123.7612
        assert isinstance(result['longitude'], float)
        assert result['altitude'] == 100.0
        assert isinstance(result['altitude'], float)
        assert result['course'] == 180
        assert isinstance(result['course'], int)
        assert result['speed'] == 5.5
        assert isinstance(result['speed'], float)
        assert result['symbol'] == '/-'
        assert result['to_call'] == 'APRS'
        assert result['comment'] == 'Test comment'
        assert result['path'] == 'WIDE1-1,WIDE2-1'
        assert result['packet_type'] == 'position'

    def test_timestamps_iso_format(self):
        pkt = _mock_packet()
        result = aprs_packet_to_native_entry(pkt)
        assert result['timestamp'].endswith('Z')
        assert 'T' in result['timestamp']
        assert result['received_at'].endswith('Z')

    def test_none_optional_fields(self):
        pkt = _mock_packet(altitude=None, course=None, speed=None)
        result = aprs_packet_to_native_entry(pkt)
        assert result['altitude'] is None
        assert result['course'] is None
        assert result['speed'] is None

    def test_callsign_uppercased(self):
        pkt = _mock_packet(from_call='n0call')
        result = aprs_packet_to_native_entry(pkt)
        assert result['callsign'] == 'N0CALL'


# ---------------------------------------------------------------------------
# T015: Integration tests for /api/v1/location endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def native_client():
    """Create a fresh Flask test app with mocked CONF and DB for /api/v1/location."""
    import flask as flask_mod
    from unittest.mock import patch

    with patch('haminfo.flask.CONF') as mock_conf, patch('haminfo.flask.db') as mock_db:
        mock_conf.web.api_key = 'test-native-key'

        # Create a fresh Flask app to avoid route re-registration issues
        test_app = flask_mod.Flask('haminfo_test_native')
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

        # Register route
        test_app.route('/api/v1/location', methods=['GET'])(server.location)

        test_app._test_mock_db = mock_db
        test_app._test_mock_session = mock_session

        with test_app.test_client() as client:
            yield client


class TestNativeLocationEndpoint:
    """Integration tests for GET /api/v1/location."""

    def test_valid_single_callsign(self, native_client):
        pkt = _mock_packet()
        app = native_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = native_client.get(
            '/api/v1/location?callsign=N0CALL',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['error'] is None
        assert data['meta']['found'] == 1
        assert data['meta']['requested'] == ['N0CALL']
        assert len(data['data']) == 1
        assert data['data'][0]['callsign'] == 'N0CALL'

    def test_valid_multi_callsign(self, native_client):
        pkts = [_mock_packet(from_call='N0CALL'), _mock_packet(from_call='W3ADO')]
        app = native_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = pkts

        resp = native_client.get(
            '/api/v1/location?callsign=N0CALL,W3ADO',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['meta']['found'] == 2
        callsigns = {e['callsign'] for e in data['data']}
        assert callsigns == {'N0CALL', 'W3ADO'}

    def test_missing_callsign_param_returns_400(self, native_client):
        resp = native_client.get(
            '/api/v1/location',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()

        assert resp.status_code == 400
        assert data['data'] is None
        assert data['meta'] is None
        assert data['error']['code'] == 'INVALID_PARAM'

    def test_missing_api_key_returns_401(self, native_client):
        resp = native_client.get('/api/v1/location?callsign=N0CALL')

        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, native_client):
        resp = native_client.get(
            '/api/v1/location?callsign=N0CALL',
            headers={'X-Api-Key': 'wrong-key'},
        )

        assert resp.status_code == 401

    def test_callsign_not_found_returns_200_empty(self, native_client):
        app = native_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = []

        resp = native_client.get(
            '/api/v1/location?callsign=NONEXIST',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['data'] == []
        assert data['meta']['found'] == 0
        assert data['error'] is None

    def test_response_uses_data_error_meta_structure(self, native_client):
        pkt = _mock_packet()
        app = native_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = native_client.get(
            '/api/v1/location?callsign=N0CALL',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()

        assert 'data' in data
        assert 'meta' in data
        assert 'error' in data

    def test_field_types_are_correct(self, native_client):
        pkt = _mock_packet()
        app = native_client.application
        app._test_mock_db.find_latest_positions_by_callsigns.return_value = [pkt]

        resp = native_client.get(
            '/api/v1/location?callsign=N0CALL',
            headers={'X-Api-Key': 'test-native-key'},
        )
        data = resp.get_json()
        entry = data['data'][0]

        # Native endpoint returns typed values, not strings
        assert isinstance(entry['latitude'], float)
        assert isinstance(entry['longitude'], float)
        assert isinstance(entry['altitude'], float)
        assert isinstance(entry['course'], int)
        assert isinstance(entry['speed'], float)
        # ISO 8601 timestamp
        assert 'T' in entry['timestamp']
        assert entry['timestamp'].endswith('Z')
