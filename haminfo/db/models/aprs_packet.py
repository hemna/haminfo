from __future__ import annotations
from datetime import datetime
import time

import sqlalchemy as sa
from geoalchemy2 import Geography

from haminfo.db.models.modelbase import ModelBase


class APRSPacket(ModelBase):
    """
    Lean model for storing APRS packets optimized for position lookups.

    This model stores only the fields needed for:
    - Position lookups by callsign (REPEAT API)
    - Real-time monitoring
    - Basic packet statistics

    The raw packet is preserved for future decoding if additional
    fields are ever needed.

    Removed fields (not used by any queries or APIs):
    - Weather: temperature, humidity, pressure, wind_*, rain_*, solar_radiation,
      uv_index, luminosity, snow
    - Telemetry: telemetry_analog, telemetry_digital, telemetry_sequence
    - Message: message_text, message_id, message_ack, message_reject
    - Object: object_name, object_killed, status
    - Query: query_type, query_response
    - Other: third_party, capcode, format, source, compressed, mic_e, maidenhead

    PostgreSQL-specific indexes (created via migration, not model):
    - ix_aprs_packet_from_call_ts_pos: Composite partial index for position lookups
    - idx_aprs_packet_location: GIST spatial index on location column
    """

    __tablename__ = 'aprs_packet'

    # Core APRS packet fields - use constrained string lengths
    # Primary key is (from_call, timestamp) for TimescaleDB hypertable
    from_call = sa.Column(sa.String(9), nullable=False, primary_key=True, index=True)
    to_call = sa.Column(sa.String(9), index=True)
    path = sa.Column(sa.String(100))  # Digipeater path

    # Timestamps - timestamp is part of composite primary key for hypertable
    timestamp = sa.Column(sa.DateTime, nullable=False, primary_key=True, index=True)
    received_at = sa.Column(
        sa.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Raw packet string - preserved for debugging and future decoding
    raw = sa.Column(sa.Text, nullable=False)

    # Packet type for filtering (position, weather, message, etc.)
    packet_type = sa.Column(sa.String(20), index=True)

    # Position data
    latitude = sa.Column(sa.Float)
    longitude = sa.Column(sa.Float)
    location = sa.Column(Geography('POINT'))
    altitude = sa.Column(sa.Float)
    course = sa.Column(sa.SmallInteger)  # 0-360 degrees
    speed = sa.Column(sa.Float)  # knots

    # Symbol information for map display
    symbol = sa.Column(sa.CHAR(1))
    symbol_table = sa.Column(sa.CHAR(1))

    # Comment text
    comment = sa.Column(sa.Text)

    def __repr__(self):
        return (
            f"<APRSPacket(from_call='{self.from_call}', "
            f"to_call='{self.to_call}', packet_type='{self.packet_type}', "
            f"timestamp='{self.timestamp}')>"
        )

    def to_dict(self):
        """Convert the packet to a dictionary."""
        dict_ = {}
        for key in self.__mapper__.c.keys():
            value = getattr(self, key)
            # Convert datetime to string for JSON serialization
            if isinstance(value, datetime):
                value = value.isoformat()
            dict_[key] = value
        return dict_

    @staticmethod
    def from_json(packet_json):
        """
        Create an APRSPacket from JSON data (APRSD packet.core structure).

        Only extracts fields needed for position lookups and monitoring.
        The raw packet is preserved for future decoding if needed.
        """
        # Handle timestamp
        ts_str = packet_json.get('timestamp', None)
        if not ts_str:
            ts_str = time.time()

        if isinstance(ts_str, (int, float)):
            packet_time = datetime.fromtimestamp(ts_str)
        else:
            # Try to parse string timestamp
            try:
                packet_time = datetime.fromisoformat(str(ts_str))
            except (ValueError, TypeError):
                packet_time = datetime.utcnow()

        # Extract core fields
        from_call = packet_json.get('from_call', '').replace('\x00', '')
        to_call = packet_json.get('to_call', '').replace('\x00', '')
        path = packet_json.get('path', '')
        if isinstance(path, list):
            path = ','.join(path)
        raw = packet_json.get('raw', '').replace('\x00', '')

        # Extract position data
        latitude = packet_json.get('latitude')
        longitude = packet_json.get('longitude')
        location = None
        if latitude is not None and longitude is not None:
            location = f'POINT({longitude} {latitude})'

        # Extract symbol info
        symbol = packet_json.get('symbol')
        if symbol:
            symbol_str = str(symbol).replace('\x00', '')
            symbol = symbol_str[0] if len(symbol_str) > 0 else None
        symbol_table = packet_json.get('symbol_table')
        if symbol_table:
            symbol_table_str = str(symbol_table).replace('\x00', '')
            symbol_table = symbol_table_str[0] if len(symbol_table_str) > 0 else None

        # Extract comment
        comment = packet_json.get('comment')
        if comment:
            comment = str(comment).replace('\x00', '')

        # Determine packet type based on content
        packet_type = packet_json.get('packet_type')
        if not packet_type:
            # Check for weather indicators
            if any(
                packet_json.get(f) is not None
                for f in ('temperature', 'humidity', 'pressure')
            ):
                packet_type = 'weather'
            elif packet_json.get('telemetry_analog') or packet_json.get(
                'telemetry_digital'
            ):
                packet_type = 'telemetry'
            elif packet_json.get('object_name'):
                packet_type = 'object'
            elif packet_json.get('message_text'):
                packet_type = 'message'
            elif packet_json.get('status'):
                packet_type = 'status'
            elif packet_json.get('query_type'):
                packet_type = 'query'
            elif latitude is not None and longitude is not None:
                packet_type = 'position'
            else:
                packet_type = 'unknown'

        return APRSPacket(
            from_call=from_call,
            to_call=to_call,
            path=path,
            timestamp=packet_time,
            received_at=datetime.utcnow(),
            raw=raw,
            packet_type=packet_type,
            latitude=latitude,
            longitude=longitude,
            location=location,
            altitude=packet_json.get('altitude'),
            course=packet_json.get('course'),
            speed=packet_json.get('speed'),
            symbol=symbol,
            symbol_table=symbol_table,
            comment=comment,
        )
