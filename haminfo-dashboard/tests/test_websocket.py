# tests/test_websocket.py
"""Tests for WebSocket module."""

import pytest
from unittest.mock import MagicMock, patch

import haminfo_dashboard.websocket as websocket_module


@pytest.fixture
def mock_socketio():
    """Fixture to mock the socketio instance."""
    mock_sio = MagicMock()
    original = websocket_module.socketio
    websocket_module.socketio = mock_sio
    yield mock_sio
    websocket_module.socketio = original


class TestBroadcastPacket:
    """Tests for broadcast_packet function."""

    def test_broadcast_to_live_feed_always(self, mock_socketio):
        """Test that packets always go to live_feed room."""
        from haminfo_dashboard.websocket import broadcast_packet

        packet = {'from_call': 'W1ABC', 'latitude': None, 'longitude': None}
        broadcast_packet(packet)

        # Should emit to live_feed
        mock_socketio.emit.assert_any_call('packet', packet, room='live_feed')

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_broadcast_to_country_room_with_coords(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that packets with coords go to country room."""
        from haminfo_dashboard.websocket import broadcast_packet
        from haminfo_dashboard.geo_cache import LocationInfo

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.return_value = LocationInfo('US', 'CA')

        packet = {'from_call': 'W1ABC', 'latitude': 34.05, 'longitude': -118.24}
        broadcast_packet(packet)

        # Should emit to country room
        mock_socketio.emit.assert_any_call('packet', packet, room='country:US')

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_broadcast_to_state_room_for_us(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that US packets also go to state room."""
        from haminfo_dashboard.websocket import broadcast_packet
        from haminfo_dashboard.geo_cache import LocationInfo

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.return_value = LocationInfo('US', 'CA')

        packet = {'from_call': 'W1ABC', 'latitude': 34.05, 'longitude': -118.24}
        broadcast_packet(packet)

        # Should emit to state room
        mock_socketio.emit.assert_any_call('packet', packet, room='state:CA')

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_no_country_room_for_ocean(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that ocean coordinates don't emit to country room."""
        from haminfo_dashboard.websocket import broadcast_packet
        from haminfo_dashboard.geo_cache import LocationInfo

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.return_value = LocationInfo(None, None)

        packet = {'from_call': 'W1ABC', 'latitude': 0.0, 'longitude': 0.0}
        broadcast_packet(packet)

        # Should only emit to live_feed, not country room
        calls = [call.kwargs.get('room') for call in mock_socketio.emit.call_args_list]
        assert 'live_feed' in calls
        assert not any(room and room.startswith('country:') for room in calls)

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_handles_geo_lookup_error(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that geo lookup errors don't break broadcast."""
        from haminfo_dashboard.websocket import broadcast_packet

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.side_effect = Exception('DB error')

        packet = {'from_call': 'W1ABC', 'latitude': 34.05, 'longitude': -118.24}

        # Should not raise
        broadcast_packet(packet)

        # Should still emit to live_feed
        mock_socketio.emit.assert_called_with('packet', packet, room='live_feed')

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_non_us_no_state_room(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that non-US packets don't emit to state room."""
        from haminfo_dashboard.websocket import broadcast_packet
        from haminfo_dashboard.geo_cache import LocationInfo

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        # Germany - no state code
        mock_get_location.return_value = LocationInfo('DE', None)

        packet = {'from_call': 'DL1ABC', 'latitude': 52.52, 'longitude': 13.405}
        broadcast_packet(packet)

        # Should emit to country room
        mock_socketio.emit.assert_any_call('packet', packet, room='country:DE')

        # Should NOT emit to any state room
        calls = [call.kwargs.get('room') for call in mock_socketio.emit.call_args_list]
        assert not any(room and room.startswith('state:') for room in calls)

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_session_closed_after_use(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that database session is properly closed."""
        from haminfo_dashboard.websocket import broadcast_packet
        from haminfo_dashboard.geo_cache import LocationInfo

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.return_value = LocationInfo('US', 'CA')

        packet = {'from_call': 'W1ABC', 'latitude': 34.05, 'longitude': -118.24}
        broadcast_packet(packet)

        # Session should be closed
        mock_session.close.assert_called_once()

    @patch('haminfo_dashboard.websocket._get_session')
    @patch('haminfo_dashboard.geo_cache.get_location_info')
    def test_session_closed_on_error(
        self, mock_get_location, mock_get_session, mock_socketio
    ):
        """Test that database session is closed even when error occurs."""
        from haminfo_dashboard.websocket import broadcast_packet

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_location.side_effect = Exception('DB error')

        packet = {'from_call': 'W1ABC', 'latitude': 34.05, 'longitude': -118.24}
        broadcast_packet(packet)

        # Session should still be closed
        mock_session.close.assert_called_once()
