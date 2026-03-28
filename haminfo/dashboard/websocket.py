# haminfo/dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations
from flask_socketio import SocketIO, emit, join_room, leave_room

socketio: SocketIO | None = None


def init_socketio(app):
    """Initialize SocketIO with Flask app."""
    global socketio
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='gevent')
    register_handlers()
    return socketio


def register_handlers():
    """Register SocketIO event handlers."""

    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        join_room('live_feed')
        emit('status', {'connected': True})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        leave_room('live_feed')

    @socketio.on('filter')
    def handle_filter(data):
        """Handle filter change from client."""
        country = data.get('country')
        # Store filter preference in session or handle accordingly
        emit('filter_applied', {'country': country})


def broadcast_packet(packet_data: dict):
    """Broadcast new packet to all connected clients."""
    if socketio:
        socketio.emit('packet', packet_data, room='live_feed')
