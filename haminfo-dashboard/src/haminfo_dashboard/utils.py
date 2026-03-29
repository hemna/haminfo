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
    """Format packet data for live feed display.

    Returns a clean, human-readable summary for the live feed.
    Avoids showing raw APRS data which looks like garbage to users.
    """
    packet_type = packet.get('packet_type') or 'unknown'
    from_call = packet.get('from_call', '?')
    to_call = packet.get('to_call', '?')
    lat = packet.get('latitude')
    lon = packet.get('longitude')
    comment = packet.get('comment', '') or ''

    # Clean the comment - remove if it looks like raw APRS data
    clean_comment = _clean_comment(comment)

    if packet_type == 'position':
        if lat is not None and lon is not None:
            speed = packet.get('speed')
            if speed and speed > 0:
                return f'Position {lat:.4f}, {lon:.4f} @ {speed:.0f}km/h'
            return f'Position {lat:.4f}, {lon:.4f}'
        if clean_comment:
            return f'Position: {clean_comment[:40]}'
        return 'Position report'

    elif packet_type == 'weather':
        parts = []
        temp = packet.get('temperature')
        humid = packet.get('humidity')
        if temp is not None:
            parts.append(f'{temp:.1f}C')
        if humid is not None:
            parts.append(f'{humid:.0f}%')
        if parts:
            return f'Weather: {", ".join(parts)}'
        return 'Weather report'

    elif packet_type == 'status':
        if clean_comment:
            return f'Status: {clean_comment[:45]}'
        return 'Status update'

    elif packet_type == 'message':
        return f'Message to {to_call}'

    elif packet_type == 'telemetry':
        return 'Telemetry data'

    elif packet_type == 'object':
        if clean_comment:
            return f'Object: {clean_comment[:40]}'
        return 'Object report'

    elif packet_type == 'query':
        return f'Query to {to_call}'

    else:
        # Unknown type - try to show something useful but clean
        # Priority: position > clean comment > generic message
        if lat is not None and lon is not None:
            speed = packet.get('speed')
            if speed and speed > 0:
                return f'Position {lat:.4f}, {lon:.4f} @ {speed:.0f}km/h'
            return f'Position {lat:.4f}, {lon:.4f}'

        if clean_comment:
            return clean_comment[:50]

        # Generic fallback based on to_call
        if to_call and to_call not in (
            '?',
            'APRS',
            'AP',
            'TCPIP',
            'WIDE1-1',
            'WIDE2-1',
        ):
            return f'Packet to {to_call}'

        return 'Packet received'


def _clean_comment(comment: str) -> str:
    """Clean a comment string, returning empty if it looks like raw APRS data.

    Raw APRS data patterns to filter:
    - Starts with special chars like ; ! = _ @ /
    - Contains sequences like 111111z, {{I, T#, etc.
    - Has many non-alphanumeric characters
    - Very short or mostly punctuation
    """
    if not comment:
        return ''

    comment = comment.strip()

    # Too short to be useful
    if len(comment) < 3:
        return ''

    # Starts with APRS data indicators
    aprs_prefixes = (
        ';',
        '!',
        '=',
        '_',
        '@',
        '/',
        '\\',
        '`',
        "'",
        '{',
        'T#',
        '_0',
        '_1',
    )
    if any(comment.startswith(p) for p in aprs_prefixes):
        return ''

    # Contains telemetry/weather raw data patterns
    raw_patterns = [
        '111111z',
        '{{I',
        'T#',
        'c000',
        's000',
        'g000',
        't0',
        'r000',
        'p000',
        'h00',
        'b1',
    ]
    if any(p in comment for p in raw_patterns):
        return ''

    # Count printable vs special characters
    printable = sum(1 for c in comment if c.isalnum() or c == ' ')
    if len(comment) > 5 and printable < len(comment) * 0.5:
        return ''

    # Looks like coordinates embedded in comment
    if comment.count('/') > 1 and any(c in comment for c in 'NEWS'):
        return ''

    return comment
