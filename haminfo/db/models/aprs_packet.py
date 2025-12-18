from __future__ import annotations
from datetime import datetime
import time

import sqlalchemy as sa
from geoalchemy2 import Geography

from haminfo.db.models.modelbase import ModelBase


class APRSPacket(ModelBase):
    """
    Model for storing APRS packets, modeled after APRSD's packet.core structure.

    This model stores the core fields from APRSD's packet object that gets
    serialized to JSON and sent via MQTT.
    """
    __tablename__ = 'aprs_packet'

    id = sa.Column(sa.Integer,
                   sa.Sequence('aprs_packet_id_seq'),
                   primary_key=True,
                   unique=True)

    # Core APRS packet fields (from APRSD packet.core)
    from_call = sa.Column(sa.String, nullable=False, index=True)
    to_call = sa.Column(sa.String, index=True)
    path = sa.Column(sa.String)  # Digipeater path

    # Timestamp from the packet
    timestamp = sa.Column(sa.DateTime, nullable=False, index=True)
    # When we received/stored this packet
    received_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Raw packet string
    raw = sa.Column(sa.Text, nullable=False)

    # Packet type (position, weather, message, status, telemetry, object, item, etc.)
    packet_type = sa.Column(sa.String, index=True)

    # Position data (for position/weather/object/item packets)
    latitude = sa.Column(sa.Float)
    longitude = sa.Column(sa.Float)
    location = sa.Column(Geography('POINT'))
    altitude = sa.Column(sa.Float)
    course = sa.Column(sa.Integer)  # 0-360 degrees
    speed = sa.Column(sa.Float)  # knots or km/h
    maidenhead = sa.Column(sa.String)  # Maidenhead grid square

    # Symbol information
    symbol = sa.Column(sa.CHAR)
    symbol_table = sa.Column(sa.CHAR)

    # Comment/status text (for position, status, object, item packets)
    comment = sa.Column(sa.Text)
    status = sa.Column(sa.Text)  # Status text for status packets

    # Object/Item packet fields
    object_name = sa.Column(sa.String)  # Object/item name
    object_killed = sa.Column(sa.Boolean, default=False)  # Kill bit (alive/dead)

    # Weather data (for weather packets)
    temperature = sa.Column(sa.Float)
    humidity = sa.Column(sa.Integer)
    pressure = sa.Column(sa.Float)
    wind_direction = sa.Column(sa.Integer)
    wind_speed = sa.Column(sa.Float)
    wind_gust = sa.Column(sa.Float)
    rain_1h = sa.Column(sa.Float)
    rain_24h = sa.Column(sa.Float)
    rain_since_midnight = sa.Column(sa.Float)
    # Additional weather fields
    solar_radiation = sa.Column(sa.Float)
    uv_index = sa.Column(sa.Integer)
    luminosity = sa.Column(sa.Float)
    snow = sa.Column(sa.Float)

    # Telemetry data (for telemetry packets)
    telemetry_analog = sa.Column(sa.String)  # JSON array of analog values
    telemetry_digital = sa.Column(sa.String)  # Binary string of digital bits
    telemetry_sequence = sa.Column(sa.Integer)  # Sequence number

    # Message data (for message packets)
    message_text = sa.Column(sa.Text)
    message_id = sa.Column(sa.String)
    message_ack = sa.Column(sa.String)  # Message acknowledgment ID
    message_reject = sa.Column(sa.Boolean, default=False)  # Message rejection

    # Query/Response data
    query_type = sa.Column(sa.String)  # Query type (MESSAGE, POSITION, etc.)
    query_response = sa.Column(sa.Text)  # Response data

    # Third-party packet data
    third_party = sa.Column(sa.Text)  # Third-party packet data

    # Capcode (for paging)
    capcode = sa.Column(sa.String)

    # Additional metadata
    format = sa.Column(sa.String)  # Packet format (ax25, nmea, mic-e, compressed, etc.)
    source = sa.Column(sa.String)  # Source of packet (aprs-is, rf, etc.)
    compressed = sa.Column(sa.Boolean, default=False)  # Compressed position format
    mic_e = sa.Column(sa.Boolean, default=False)  # Mic-E format

    def __repr__(self):
        return (
            f"<APRSPacket(id={self.id}, from_call='{self.from_call}', "
            f"to_call='{self.to_call}', packet_type='{self.packet_type}', "
            f"timestamp='{self.timestamp}')>"
        )

    def to_dict(self):
        """Convert the packet to a dictionary"""
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

        This matches the structure that APRSD sends via MQTT.
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

        # Extract core fields (matching APRSD packet.core)
        from_call = packet_json.get("from_call", "").replace('\x00', '')
        to_call = packet_json.get("to_call", "").replace('\x00', '')
        path = packet_json.get("path", "")
        raw = packet_json.get("raw", "").replace('\x00', '')

        # Extract position data
        latitude = packet_json.get("latitude")
        longitude = packet_json.get("longitude")
        location = None
        if latitude and longitude:
            location = f"POINT({longitude} {latitude})"

        # Extract symbol info
        symbol = packet_json.get("symbol")
        if symbol:
            symbol_str = str(symbol).replace('\x00', '')
            symbol = symbol_str[0] if len(symbol_str) > 0 else None
        symbol_table = packet_json.get("symbol_table")
        if symbol_table:
            symbol_table_str = str(symbol_table).replace('\x00', '')
            symbol_table = symbol_table_str[0] if len(symbol_table_str) > 0 else None

        # Extract comment
        comment = packet_json.get("comment")
        if comment:
            comment = str(comment).replace('\x00', '')

        # Extract weather data if present
        temperature = packet_json.get("temperature")
        humidity = packet_json.get("humidity")
        pressure = packet_json.get("pressure")
        wind_direction = packet_json.get("wind_direction")
        wind_speed = packet_json.get("wind_speed")
        wind_gust = packet_json.get("wind_gust")
        rain_1h = packet_json.get("rain_1h")
        rain_24h = packet_json.get("rain_24h")
        rain_since_midnight = packet_json.get("rain_since_midnight")

        # Determine packet type based on content (APRSD packet.core logic)
        packet_type = packet_json.get("packet_type")
        if not packet_type:
            if temperature is not None or humidity is not None or pressure is not None:
                packet_type = "weather"
            elif packet_json.get("telemetry_analog") or packet_json.get("telemetry_digital"):
                packet_type = "telemetry"
            elif packet_json.get("object_name"):
                packet_type = "object"
            elif packet_json.get("message_text"):
                packet_type = "message"
            elif packet_json.get("status"):
                packet_type = "status"
            elif packet_json.get("query_type"):
                packet_type = "query"
            elif latitude is not None and longitude is not None:
                packet_type = "position"
            else:
                packet_type = "unknown"

        # Extract additional weather fields
        solar_radiation = packet_json.get("solar_radiation")
        uv_index = packet_json.get("uv_index")
        luminosity = packet_json.get("luminosity")
        snow = packet_json.get("snow")

        # Extract object/item fields
        object_name = packet_json.get("object_name")
        if object_name:
            object_name = str(object_name).replace('\x00', '')
        object_killed = packet_json.get("object_killed", False)

        # Extract status
        status = packet_json.get("status")
        if status:
            status = str(status).replace('\x00', '')

        # Extract telemetry data
        telemetry_analog = packet_json.get("telemetry_analog")
        telemetry_digital = packet_json.get("telemetry_digital")
        telemetry_sequence = packet_json.get("telemetry_sequence")

        # Extract message fields
        message_text = packet_json.get("message_text")
        if message_text:
            message_text = str(message_text).replace('\x00', '')
        message_id = packet_json.get("message_id")
        message_ack = packet_json.get("message_ack")
        message_reject = packet_json.get("message_reject", False)

        # Extract query/response fields
        query_type = packet_json.get("query_type")
        query_response = packet_json.get("query_response")
        if query_response:
            query_response = str(query_response).replace('\x00', '')

        # Extract third-party data
        third_party = packet_json.get("third_party")
        if third_party:
            third_party = str(third_party).replace('\x00', '')

        # Extract other fields
        maidenhead = packet_json.get("maidenhead")
        capcode = packet_json.get("capcode")
        format_type = packet_json.get("format")
        compressed = packet_json.get("compressed", False)
        mic_e = packet_json.get("mic_e", False)

        return APRSPacket(
            from_call=from_call,
            to_call=to_call,
            path=path,
            timestamp=packet_time,
            received_at=datetime.utcnow(),
            raw=raw,
            packet_type=packet_type,
            format=format_type,
            latitude=latitude,
            longitude=longitude,
            location=location,
            altitude=packet_json.get("altitude"),
            course=packet_json.get("course"),
            speed=packet_json.get("speed"),
            maidenhead=maidenhead,
            symbol=symbol,
            symbol_table=symbol_table,
            comment=comment,
            status=status,
            object_name=object_name,
            object_killed=object_killed,
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            wind_direction=wind_direction,
            wind_speed=wind_speed,
            wind_gust=wind_gust,
            rain_1h=rain_1h,
            rain_24h=rain_24h,
            rain_since_midnight=rain_since_midnight,
            solar_radiation=solar_radiation,
            uv_index=uv_index,
            luminosity=luminosity,
            snow=snow,
            telemetry_analog=telemetry_analog,
            telemetry_digital=telemetry_digital,
            telemetry_sequence=telemetry_sequence,
            message_text=message_text,
            message_id=message_id,
            message_ack=message_ack,
            message_reject=message_reject,
            query_type=query_type,
            query_response=query_response,
            third_party=third_party,
            capcode=capcode,
            source=packet_json.get("source"),
            compressed=compressed,
            mic_e=mic_e,
        )
