# haminfo_dashboard/websocket.py
"""WebSocket event handlers for live feed."""

from __future__ import annotations

from datetime import datetime

from flask_socketio import SocketIO, emit, join_room, leave_room
import gevent

from haminfo_dashboard.station_cache import station_cache
from haminfo_dashboard.utils import (
    get_packet_human_info,
    get_packet_addressee,
    normalize_packet_type,
)

socketio: SocketIO | None = None
_poll_greenlet = None
_last_packet_time: datetime | None = None

# Module-level session factory (initialized once, reused)
_session_factory = None


def _get_session():
    """Get a database session, initializing factory on first call."""
    global _session_factory
    if _session_factory is None:
        from haminfo.db.db import setup_session

        _session_factory = setup_session()
    return _session_factory()


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

    @socketio.on('join_country')
    def handle_join_country(data):
        """Handle client joining a country-specific room.

        Leaves the global live_feed room to only receive country-filtered packets.
        """
        country_code = data.get('country_code')
        if country_code:
            # Leave global feed - we only want country-specific packets
            leave_room('live_feed')
            room_name = f'country:{country_code}'
            join_room(room_name)
            emit('country_joined', {'country_code': country_code, 'room': room_name})

    @socketio.on('leave_country')
    def handle_leave_country(data):
        """Handle client leaving a country-specific room."""
        country_code = data.get('country_code')
        if country_code:
            room_name = f'country:{country_code}'
            leave_room(room_name)
            emit('country_left', {'country_code': country_code})


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
                        'packet_type': normalize_packet_type(
                            packet.packet_type,
                            packet.latitude,
                            packet.longitude,
                            packet.raw,
                        ),
                        'latitude': packet.latitude,
                        'longitude': packet.longitude,
                        'speed': packet.speed,
                        'comment': packet.comment,
                        'raw': packet.raw,
                        'received_at': packet.received_at.isoformat()
                        if packet.received_at
                        else None,
                        'country_code': packet.country_code,
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
    """Broadcast new packet to all connected clients.

    Emits to:
    - 'live_feed' room (all clients on homepage/live feed)
    - 'country:<code>' room (clients viewing that country's detail page)
    - 'state:<code>' room (clients viewing that state's detail page, US only)

    Uses the country_code stored in the packet (populated by rust-aprsd at insert time).
    For packets without country_code, falls back to the station's last known location
    from the station_cache.
    """
    if socketio:
        # Always emit to global live feed
        socketio.emit('packet', packet_data, room='live_feed')

        from_call = packet_data.get('from_call')
        country_code = packet_data.get('country_code')
        state_code = None

        # If packet has country_code (has coordinates), update station cache
        if country_code and from_call:
            # For US, look up state code
            if country_code == 'US':
                lat = packet_data.get('latitude')
                lon = packet_data.get('longitude')
                if lat is not None and lon is not None:
                    try:
                        from haminfo_dashboard.geo_cache import get_location_info

                        session = _get_session()
                        try:
                            info = get_location_info(session, lat, lon)
                            state_code = info.state_code
                        finally:
                            session.close()
                    except Exception as e:
                        print(f'State lookup failed: {e}')

            # Update station cache with this position
            station_cache.update(from_call, country_code, state_code)

        # If no country_code in packet, try station cache
        elif from_call:
            cached = station_cache.get(from_call)
            if cached:
                country_code = cached.country_code
                state_code = cached.state_code

        # Emit to country/state rooms if we have location
        if country_code:
            socketio.emit('packet', packet_data, room=f'country:{country_code}')

            if state_code:
                socketio.emit('packet', packet_data, room=f'state:{state_code}')
