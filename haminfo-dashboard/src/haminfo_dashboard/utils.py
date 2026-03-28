# haminfo_dashboard/utils.py
"""Utility functions for dashboard."""

from __future__ import annotations

# Callsign prefix to country mapping (common prefixes)
CALLSIGN_PREFIXES = {
    '9M': ('MY', 'Malaysia'),
    '9W': ('MY', 'Malaysia'),
    'VK': ('AU', 'Australia'),
    'ZL': ('NZ', 'New Zealand'),
    'JA': ('JP', 'Japan'),
    'JH': ('JP', 'Japan'),
    'JR': ('JP', 'Japan'),
    'HL': ('KR', 'South Korea'),
    'BV': ('TW', 'Taiwan'),
    'W': ('US', 'United States'),
    'K': ('US', 'United States'),
    'N': ('US', 'United States'),
    'AA': ('US', 'United States'),
    'AB': ('US', 'United States'),
    'AC': ('US', 'United States'),
    'AD': ('US', 'United States'),
    'AE': ('US', 'United States'),
    'AF': ('US', 'United States'),
    'AG': ('US', 'United States'),
    'AI': ('US', 'United States'),
    'AJ': ('US', 'United States'),
    'AK': ('US', 'United States'),
    'AL': ('US', 'United States'),
    'VE': ('CA', 'Canada'),
    'VA': ('CA', 'Canada'),
    'G': ('GB', 'United Kingdom'),
    'M': ('GB', 'United Kingdom'),
    '2E': ('GB', 'United Kingdom'),
    'F': ('FR', 'France'),
    'DL': ('DE', 'Germany'),
    'DO': ('DE', 'Germany'),
    'PA': ('NL', 'Netherlands'),
    'PD': ('NL', 'Netherlands'),
    'I': ('IT', 'Italy'),
    'EA': ('ES', 'Spain'),
    'OH': ('FI', 'Finland'),
    'SM': ('SE', 'Sweden'),
    'LA': ('NO', 'Norway'),
    'OZ': ('DK', 'Denmark'),
    'SP': ('PL', 'Poland'),
    'OK': ('CZ', 'Czech Republic'),
    'HA': ('HU', 'Hungary'),
    'YO': ('RO', 'Romania'),
    'LZ': ('BG', 'Bulgaria'),
    'UR': ('UA', 'Ukraine'),
    'UT': ('UA', 'Ukraine'),
    'UA': ('RU', 'Russia'),
    'RV': ('RU', 'Russia'),
    'RU': ('RU', 'Russia'),
}


def get_country_from_callsign(callsign: str) -> tuple[str, str] | None:
    """Extract country code and name from callsign prefix.

    Args:
        callsign: Ham radio callsign (e.g., '9M2PJU-9')

    Returns:
        Tuple of (country_code, country_name) or None if unknown
    """
    if not callsign:
        return None

    # Remove SSID suffix
    base_call = callsign.split('-')[0].upper()

    # Try progressively shorter prefixes (longest match wins)
    for length in range(min(3, len(base_call)), 0, -1):
        prefix = base_call[:length]
        if prefix in CALLSIGN_PREFIXES:
            return CALLSIGN_PREFIXES[prefix]

    return None


def _format_gps_info(packet: dict) -> str:
    """Format GPS/position packet info like APRSD.
    
    Format: Lat:XX.XXX Lon:XX.XXX [Altitude XXX] [Speed XXXMPH] [Course XXX]
    """
    parts = []
    lat = packet.get('latitude')
    lon = packet.get('longitude')
    
    if lat is not None:
        parts.append(f'Lat:{lat:03.3f}')
    if lon is not None:
        parts.append(f'Lon:{lon:03.3f}')
    
    altitude = packet.get('altitude')
    if altitude:
        parts.append(f'Alt:{altitude:.0f}ft')
    
    speed = packet.get('speed')
    if speed:
        # Convert km/h to MPH for consistency with APRSD
        mph = speed * 0.621371
        parts.append(f'Spd:{mph:.0f}MPH')
    
    course = packet.get('course')
    if course:
        parts.append(f'Crs:{course:.0f}')
    
    return ' '.join(parts) if parts else None


def _format_weather_info(packet: dict) -> str:
    """Format weather packet info like APRSD.
    
    Format: Temp XXXF Humidity X% Wind XXXMPH@XXX Pressure XXXmb Rain X.XXin/24hr
    """
    parts = []
    
    temp = packet.get('temperature')
    if temp is not None:
        # Convert C to F
        temp_f = temp * 9/5 + 32
        parts.append(f'Temp:{temp_f:.0f}F')
    
    humidity = packet.get('humidity')
    if humidity is not None:
        parts.append(f'Hum:{humidity:.0f}%')
    
    wind_speed = packet.get('wind_speed')
    wind_dir = packet.get('wind_direction')
    if wind_speed is not None:
        if wind_dir is not None:
            parts.append(f'Wind:{wind_speed:.0f}MPH@{wind_dir}')
        else:
            parts.append(f'Wind:{wind_speed:.0f}MPH')
    
    pressure = packet.get('pressure')
    if pressure:
        parts.append(f'Press:{pressure:.0f}mb')
    
    rain_24h = packet.get('rain_24h')
    if rain_24h:
        parts.append(f'Rain:{rain_24h:.2f}in/24h')
    
    return ' '.join(parts) if parts else None


def _format_message_info(packet: dict) -> str:
    """Format message packet info."""
    to_call = packet.get('to_call', '')
    comment = packet.get('comment', '')
    
    # Clean up comment - remove raw APRS if it looks like garbage
    if comment and not _is_raw_aprs(comment):
        return f'Msg to {to_call}: {comment[:50]}'
    return f'Msg to {to_call}'


def _is_raw_aprs(text: str) -> bool:
    """Check if text looks like raw APRS packet data (garbage to users)."""
    if not text:
        return False
    # Raw APRS often starts with special chars or has path info
    raw_indicators = [
        text.startswith('!'),
        text.startswith('/'),
        text.startswith('@'),
        text.startswith('='),
        text.startswith(';'),
        text.startswith(')'),
        text.startswith('`'),
        text.startswith("'"),
        text.startswith('_'),
        text.startswith('$GP'),  # GPS NMEA
        '>APR' in text,  # Path info
        'WIDE' in text and ',' in text,  # Digipeater path
        'qA' in text,    # APRS-IS path
        text.count('>') > 1,  # Multiple path hops
    ]
    return any(raw_indicators)


def format_packet_summary(packet: dict) -> str:
    """Format packet data for live feed display.
    
    Uses APRSD-style formatting for human-readable output.
    Format: FROM -> TO : PacketType : human_info
    """
    from_call = packet.get('from_call', '?')
    to_call = packet.get('to_call', '?')
    packet_type = packet.get('packet_type') or 'unknown'
    
    # Build human info based on packet type
    human_info = None
    type_label = packet_type.title() if packet_type != 'unknown' else 'Packet'
    
    if packet_type == 'position':
        human_info = _format_gps_info(packet)
        type_label = 'GPS'
        
    elif packet_type == 'weather':
        human_info = _format_weather_info(packet)
        type_label = 'WX'
        
    elif packet_type == 'message':
        human_info = _format_message_info(packet)
        type_label = 'Msg'
        
    elif packet_type == 'status':
        comment = packet.get('comment', '')
        if comment and not _is_raw_aprs(comment):
            human_info = comment[:60]
        type_label = 'Status'
        
    elif packet_type == 'telemetry':
        # For telemetry, show GPS info if available
        human_info = _format_gps_info(packet)
        type_label = 'Telem'
        
    elif packet_type == 'object':
        gps_info = _format_gps_info(packet)
        comment = packet.get('comment', '')
        if gps_info:
            if comment and not _is_raw_aprs(comment):
                human_info = f'{gps_info} {comment[:30]}'
            else:
                human_info = gps_info
        type_label = 'Obj'
        
    elif packet_type == 'mic-e':
        human_info = _format_gps_info(packet)
        type_label = 'MicE'
        
    else:
        # Unknown type - try to extract something useful
        gps_info = _format_gps_info(packet)
        if gps_info:
            human_info = gps_info
        else:
            comment = packet.get('comment', '')
            if comment and not _is_raw_aprs(comment):
                human_info = comment[:50]
    
    # Build final string
    if human_info:
        return f'{from_call} -> {to_call} : {type_label} : {human_info}'
    else:
        return f'{from_call} -> {to_call} : {type_label}'
