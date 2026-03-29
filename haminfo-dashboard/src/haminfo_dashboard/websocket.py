# haminfo_dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations

from datetime import datetime, timezone

from flask_socketio import SocketIO, emit, join_room, leave_room
import gevent

from haminfo_dashboard.utils import get_packet_human_info, get_packet_addressee

socketio: SocketIO | None = None
_poll_greenlet = None
_last_packet_time: datetime | None = None


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
        start_polling()

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        leave_room('live_feed')

    @socketio.on('filter')
    def handle_filter(data):
        """Handle filter change from client."""
        country = data.get('country')
        emit('filter_applied', {'country': country})


def start_polling():
    """Start background polling for new packets using gevent."""
    global _poll_greenlet
    if _poll_greenlet is None or _poll_greenlet.dead:
        _poll_greenlet = gevent.spawn(poll_packets)


def poll_packets():
    """Poll database for new packets and broadcast."""
    global _last_packet_time

    from haminfo.db.db import setup_session
    from haminfo.db.models.aprs_packet import APRSPacket

    session_factory = setup_session()

    while True:
        try:
            session = session_factory()
            try:
                # Build query - apply filter BEFORE limit
                query = session.query(APRSPacket)

                if _last_packet_time:
                    query = query.filter(APRSPacket.received_at > _last_packet_time)

                query = query.order_by(APRSPacket.received_at.desc()).limit(10)

                packets = query.all()

                for packet in reversed(packets):
                    packet_data = {
                        'from_call': packet.from_call,
                        'to_call': packet.to_call,
                        'path': packet.path,
                        'packet_type': packet.packet_type,
                        'latitude': packet.latitude,
                        'longitude': packet.longitude,
                        'speed': packet.speed,
                        'comment': packet.comment,
                        'raw': packet.raw,
                        'received_at': packet.received_at.isoformat()
                        if packet.received_at
                        else None,
                    }
                    packet_data['human_info'] = get_packet_human_info(packet_data)
                    packet_data['addressee'] = get_packet_addressee(packet_data)
                    broadcast_packet(packet_data)

                    if packet.received_at and (
                        _last_packet_time is None
                        or packet.received_at > _last_packet_time
                    ):
                        _last_packet_time = packet.received_at

            finally:
                session.close()
        except Exception as e:
            print(f'Polling error: {e}')

        gevent.sleep(2)


def broadcast_packet(packet_data: dict):
    """Broadcast new packet to all connected clients."""
    if socketio:
        socketio.emit('packet', packet_data, room='live_feed')
