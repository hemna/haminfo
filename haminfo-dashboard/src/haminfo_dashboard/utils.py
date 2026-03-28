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


def format_packet_summary(packet: dict) -> str:
    """Format packet data for live feed display."""
    packet_type = packet.get('packet_type', 'unknown')
    from_call = packet.get('from_call', '?')

    if packet_type == 'position':
        lat = packet.get('latitude', 0)
        lon = packet.get('longitude', 0)
        speed = packet.get('speed')
        if speed:
            return f'{from_call} -> Position {lat:.4f}, {lon:.4f} @ {speed}km/h'
        return f'{from_call} -> Position {lat:.4f}, {lon:.4f}'
    elif packet_type == 'weather':
        temp = packet.get('temperature')
        humid = packet.get('humidity')
        return f'{from_call} -> WX Temp:{temp}C Humid:{humid}%'
    elif packet_type == 'status':
        status = packet.get('status', '')[:50]
        return f'{from_call} -> Status "{status}"'
    elif packet_type == 'message':
        to_call = packet.get('to_call', '?')
        return f'{from_call} -> Message to {to_call}'
    else:
        return f'{from_call} -> {packet_type}'
