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


def _get_data_summary(packet: dict) -> str:
    """Extract meaningful data summary from packet, filtering raw APRS garbage."""
    packet_type = packet.get('packet_type') or 'unknown'

    if packet_type == 'position':
        lat = packet.get('latitude')
        lon = packet.get('longitude')
        if lat is not None and lon is not None:
            speed = packet.get('speed')
            if speed:
                return f'{lat:.4f}, {lon:.4f} @ {speed:.0f}km/h'
            return f'{lat:.4f}, {lon:.4f}'
        comment = packet.get('comment', '')
        if comment and not _is_raw_aprs(comment):
            return comment[:40]
        return 'position'

    elif packet_type == 'weather':
        parts = []
        temp = packet.get('temperature')
        humid = packet.get('humidity')
        if temp is not None:
            parts.append(f'{temp:.1f}C')
        if humid is not None:
            parts.append(f'{humid:.0f}%')
        if parts:
            return ', '.join(parts)
        return 'wx'

    elif packet_type == 'status':
        comment = packet.get('comment', '')
        if comment and not _is_raw_aprs(comment):
            return comment[:45]
        return 'status'

    elif packet_type == 'message':
        return 'message'

    elif packet_type == 'telemetry':
        return 'telemetry'

    elif packet_type == 'object':
        comment = packet.get('comment', '')
        if comment and not _is_raw_aprs(comment):
            return comment[:40]
        return 'object'

    elif packet_type == 'query':
        return 'query'

    else:
        # Unknown type - try to show something useful
        comment = packet.get('comment', '')
        if comment and not _is_raw_aprs(comment):
            return comment[:50]
        lat = packet.get('latitude')
        lon = packet.get('longitude')
        if lat is not None and lon is not None:
            return f'{lat:.4f}, {lon:.4f}'
        return packet_type


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
        'WIDE' in text,  # Digipeater path
        'qA' in text,    # APRS-IS path
        text.count('>') > 1,  # Multiple path hops
    ]
    return any(raw_indicators)


def format_packet_summary(packet: dict) -> str:
    """Format packet data for live feed display.
    
    Returns format: from_call -> to_call : data_summary
    """
    from_call = packet.get('from_call', '?')
    to_call = packet.get('to_call', '?')
    data = _get_data_summary(packet)
    
    return f'{from_call} -> {to_call} : {data}'
