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
    'AH': ('US', 'United States'),
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


def normalize_packet_type(
    packet_type: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
    raw: str | None = None,
) -> str:
    """Normalize APRSD packet types to dashboard-friendly display types.

    APRSD returns various packet types that need to be normalized for
    consistent dashboard display:
    - 'beacon' with position -> 'position'
    - 'telemetry-message' -> 'telemetry'
    - 'bulletin' -> 'message'
    - 'unknown' with position -> 'position'
    - 'unknown' with telemetry data -> 'telemetry'

    If latitude/longitude are not provided but raw packet is available,
    will attempt to re-parse the raw packet to extract position data
    or detect telemetry packets.

    Args:
        packet_type: The packet type from APRSD or database
        latitude: Latitude if available (for position detection)
        longitude: Longitude if available (for position detection)
        raw: Raw APRS packet string (for fallback parsing)

    Returns:
        Normalized packet type for display
    """
    if not packet_type:
        packet_type = 'unknown'

    # Track if we detected telemetry from raw parsing
    is_telemetry_from_raw = False

    # If we don't have lat/lon but have raw packet, try to parse it
    if raw:
        try:
            import aprslib

            parsed = aprslib.parse(raw)
            if latitude is None and longitude is None:
                latitude = parsed.get('latitude')
                longitude = parsed.get('longitude')

            # Check if aprslib identified this as telemetry
            aprslib_format = parsed.get('format', '')
            if aprslib_format == 'telemetry' or parsed.get('telemetry'):
                is_telemetry_from_raw = True
        except Exception:
            pass

    # Normalize based on type and available data
    if packet_type == 'beacon':
        if latitude is not None and longitude is not None:
            return 'position'
        return 'beacon'
    elif packet_type == 'telemetry-message':
        return 'telemetry'
    elif packet_type == 'bulletin':
        return 'message'
    elif packet_type == 'unknown':
        # Check telemetry first (more specific)
        if is_telemetry_from_raw:
            return 'telemetry'
        if latitude is not None and longitude is not None:
            return 'position'

    return packet_type


def get_packet_addressee(packet: dict) -> str | None:
    """Extract the message addressee from a packet.

    For message packets, this returns the callsign the message is addressed to
    (extracted from the raw packet), which is different from to_call (usually 'APRS').

    Args:
        packet: Dict with packet data including 'raw' field

    Returns:
        Addressee callsign for message packets, None otherwise
    """
    raw = packet.get('raw', '')
    packet_type = packet.get('packet_type', '')

    # Only parse message/ack packets
    if packet_type not in ('message', 'ack') or not raw:
        return None

    try:
        import aprslib

        parsed = aprslib.parse(raw)
        # aprslib uses 'addresse' (note spelling) for message destination
        return parsed.get('addresse')
    except Exception:
        return None


def get_packet_human_info(packet: dict) -> str:
    """Generate APRSD-style human_info from packet data.

    Parses the raw packet using aprslib to extract full packet details
    and formats them like APRSD's compact log format.

    Args:
        packet: Dict with packet data including 'raw' field

    Returns:
        Human-readable packet info string
    """
    raw = packet.get('raw', '')
    packet_type = packet.get('packet_type') or 'unknown'

    # Try to parse raw packet with aprslib for full details
    if raw:
        try:
            import aprslib

            parsed = aprslib.parse(raw)

            # Weather packet
            if parsed.get('weather') or packet_type == 'weather':
                return _format_weather_human_info(parsed)

            # Position/GPS packet
            if (
                parsed.get('latitude') is not None
                and parsed.get('longitude') is not None
            ):
                return _format_gps_human_info(parsed)

            # Message packet
            if parsed.get('message_text'):
                return f'Msg: {parsed.get("message_text", "")}'

            # Status packet
            if parsed.get('status'):
                return f'Status: {parsed.get("status", "")}'

            # Object packet
            if parsed.get('object_name'):
                name = parsed.get('object_name', '')
                if parsed.get('latitude') is not None:
                    return f"Object '{name}' at {parsed['latitude']:.4f}, {parsed['longitude']:.4f}"
                return f'Object: {name}'

            # Telemetry packet
            if parsed.get('telemetry'):
                telem = parsed.get('telemetry', {})
                vals = telem.get('vals', [])
                if vals:
                    return f'Telemetry: {", ".join(str(v) for v in vals[:5])}'
                return 'Telemetry data'

            # Fall back to comment if available
            comment = parsed.get('comment', '')
            if comment:
                clean = _clean_comment(comment)
                if clean:
                    return clean[:60]

        except Exception:
            pass  # Fall through to basic formatting

    # Fallback: use stored packet fields
    return _format_basic_human_info(packet)


def _format_weather_human_info(parsed: dict) -> str:
    """Format weather packet like APRSD: Temp 72F Humidity 55% Wind 10MPH@180 ..."""
    parts = []

    # Get weather data - may be nested or at top level
    weather = parsed.get('weather', {})
    temp = weather.get('temperature') or parsed.get('temperature')
    humidity = weather.get('humidity') or parsed.get('humidity')
    wind_speed = weather.get('wind_speed') or parsed.get('wind_speed')
    wind_dir = weather.get('wind_direction') or parsed.get('wind_direction')
    pressure = weather.get('pressure') or parsed.get('pressure')
    rain_24h = weather.get('rain_24h') or parsed.get('rain_24h')

    if temp is not None:
        # aprslib returns temp in Celsius (converted from APRS Fahrenheit)
        parts.append(f'Temp:{temp:.0f}C')

    if humidity is not None:
        parts.append(f'Humidity:{humidity}%')

    if wind_speed is not None:
        if wind_dir is not None:
            parts.append(f'Wind:{wind_speed:.0f}MPH@{wind_dir}')
        else:
            parts.append(f'Wind:{wind_speed:.0f}MPH')

    if pressure is not None and pressure > 0:
        parts.append(f'Press:{pressure:.0f}mb')

    if rain_24h is not None and rain_24h > 0:
        parts.append(f'Rain:{rain_24h:.2f}in/24h')

    return ' '.join(parts) if parts else 'Weather report'


def _format_gps_human_info(parsed: dict) -> str:
    """Format GPS/position packet like APRSD: Lat:XX.XXX Lon:XX.XXX Alt:XXXft Spd:XXXMPH"""
    parts = []

    lat = parsed.get('latitude')
    lon = parsed.get('longitude')

    if lat is not None:
        parts.append(f'Lat:{lat:.3f}')
    if lon is not None:
        parts.append(f'Lon:{lon:.3f}')

    altitude = parsed.get('altitude')
    if altitude:
        parts.append(f'Alt:{altitude:.0f}ft')

    speed = parsed.get('speed')
    if speed and speed > 0:
        # aprslib returns speed in km/h, convert to MPH
        mph = speed * 0.621371
        parts.append(f'Spd:{mph:.0f}MPH')

    course = parsed.get('course')
    if course and course > 0:
        parts.append(f'Crs:{course:.0f}')

    # Add comment if present and clean
    comment = parsed.get('comment', '')
    if comment:
        clean = _clean_comment(comment)
        if clean and len(' '.join(parts)) < 40:
            parts.append(clean[:30])

    return ' '.join(parts) if parts else 'Position report'


def _format_basic_human_info(packet: dict) -> str:
    """Basic formatting using stored packet fields (fallback)."""
    packet_type = packet.get('packet_type') or 'unknown'
    lat = packet.get('latitude')
    lon = packet.get('longitude')
    comment = packet.get('comment', '') or ''

    if packet_type == 'weather':
        return 'Weather report'

    if lat is not None and lon is not None:
        parts = [f'Lat:{lat:.3f}', f'Lon:{lon:.3f}']
        speed = packet.get('speed')
        if speed and speed > 0:
            mph = speed * 0.621371
            parts.append(f'Spd:{mph:.0f}MPH')
        altitude = packet.get('altitude')
        if altitude:
            parts.append(f'Alt:{altitude:.0f}ft')
        return ' '.join(parts)

    clean = _clean_comment(comment)
    if clean:
        return clean[:50]

    return packet_type.title() if packet_type != 'unknown' else 'Packet'


# US state bounding boxes (min_lat, max_lat, min_lon, max_lon)
US_STATE_BOUNDS = {
    'AL': ('Alabama', 30.2, 35.0, -88.5, -84.9),
    'AK': ('Alaska', 51.2, 71.4, -179.1, -130.0),
    'AZ': ('Arizona', 31.3, 37.0, -114.8, -109.0),
    'AR': ('Arkansas', 33.0, 36.5, -94.6, -89.6),
    'CA': ('California', 32.5, 42.0, -124.4, -114.1),
    'CO': ('Colorado', 37.0, 41.0, -109.1, -102.0),
    'CT': ('Connecticut', 41.0, 42.1, -73.7, -71.8),
    'DE': ('Delaware', 38.5, 39.8, -75.8, -75.0),
    'FL': ('Florida', 24.5, 31.0, -87.6, -80.0),
    'GA': ('Georgia', 30.4, 35.0, -85.6, -80.8),
    'HI': ('Hawaii', 18.9, 22.2, -160.2, -154.8),
    'ID': ('Idaho', 42.0, 49.0, -117.2, -111.0),
    'IL': ('Illinois', 37.0, 42.5, -91.5, -87.5),
    'IN': ('Indiana', 37.8, 41.8, -88.1, -84.8),
    'IA': ('Iowa', 40.4, 43.5, -96.6, -90.1),
    'KS': ('Kansas', 37.0, 40.0, -102.1, -94.6),
    'KY': ('Kentucky', 36.5, 39.1, -89.6, -82.0),
    'LA': ('Louisiana', 29.0, 33.0, -94.0, -89.0),
    'ME': ('Maine', 43.1, 47.5, -71.1, -67.0),
    'MD': ('Maryland', 37.9, 39.7, -79.5, -75.0),
    'MA': ('Massachusetts', 41.2, 42.9, -73.5, -70.0),
    'MI': ('Michigan', 41.7, 48.2, -90.4, -82.4),
    'MN': ('Minnesota', 43.5, 49.4, -97.2, -89.5),
    'MS': ('Mississippi', 30.2, 35.0, -91.7, -88.1),
    'MO': ('Missouri', 36.0, 40.6, -95.8, -89.1),
    'MT': ('Montana', 44.4, 49.0, -116.0, -104.0),
    'NE': ('Nebraska', 40.0, 43.0, -104.1, -95.3),
    'NV': ('Nevada', 35.0, 42.0, -120.0, -114.0),
    'NH': ('New Hampshire', 42.7, 45.3, -72.6, -70.7),
    'NJ': ('New Jersey', 38.9, 41.4, -75.6, -73.9),
    'NM': ('New Mexico', 31.3, 37.0, -109.1, -103.0),
    'NY': ('New York', 40.5, 45.0, -79.8, -71.9),
    'NC': ('North Carolina', 33.8, 36.6, -84.3, -75.5),
    'ND': ('North Dakota', 45.9, 49.0, -104.0, -96.6),
    'OH': ('Ohio', 38.4, 42.0, -84.8, -80.5),
    'OK': ('Oklahoma', 33.6, 37.0, -103.0, -94.4),
    'OR': ('Oregon', 42.0, 46.3, -124.6, -116.5),
    'PA': ('Pennsylvania', 39.7, 42.3, -80.5, -75.0),
    'RI': ('Rhode Island', 41.1, 42.0, -71.9, -71.1),
    'SC': ('South Carolina', 32.0, 35.2, -83.4, -78.5),
    'SD': ('South Dakota', 42.5, 46.0, -104.1, -96.4),
    'TN': ('Tennessee', 35.0, 36.7, -90.3, -81.6),
    'TX': ('Texas', 25.8, 36.5, -106.6, -93.5),
    'UT': ('Utah', 37.0, 42.0, -114.1, -109.0),
    'VT': ('Vermont', 42.7, 45.0, -73.4, -71.5),
    'VA': ('Virginia', 36.5, 39.5, -83.7, -75.2),
    'WA': ('Washington', 45.5, 49.0, -124.8, -116.9),
    'WV': ('West Virginia', 37.2, 40.6, -82.6, -77.7),
    'WI': ('Wisconsin', 42.5, 47.1, -92.9, -86.8),
    'WY': ('Wyoming', 41.0, 45.0, -111.1, -104.1),
    'DC': ('District of Columbia', 38.8, 39.0, -77.1, -76.9),
}

# Canadian province bounding boxes
CA_PROVINCE_BOUNDS = {
    'AB': ('Alberta', 49.0, 60.0, -120.0, -110.0),
    'BC': ('British Columbia', 48.3, 60.0, -139.1, -114.0),
    'MB': ('Manitoba', 49.0, 60.0, -102.0, -89.0),
    'NB': ('New Brunswick', 44.6, 48.1, -69.1, -63.8),
    'NL': ('Newfoundland and Labrador', 46.6, 60.4, -67.8, -52.6),
    'NS': ('Nova Scotia', 43.4, 47.0, -66.4, -59.7),
    'NT': ('Northwest Territories', 60.0, 78.8, -136.5, -102.0),
    'NU': ('Nunavut', 51.7, 83.1, -120.7, -61.2),
    'ON': ('Ontario', 41.7, 56.9, -95.2, -74.3),
    'PE': ('Prince Edward Island', 45.9, 47.1, -64.4, -62.0),
    'QC': ('Quebec', 45.0, 62.6, -79.8, -57.1),
    'SK': ('Saskatchewan', 49.0, 60.0, -110.0, -101.4),
    'YT': ('Yukon', 60.0, 69.6, -141.0, -123.8),
}

# Australian state bounding boxes
AU_STATE_BOUNDS = {
    'NSW': ('New South Wales', -37.5, -28.2, 141.0, 153.6),
    'VIC': ('Victoria', -39.2, -34.0, 140.9, 150.0),
    'QLD': ('Queensland', -29.2, -10.7, 138.0, 153.6),
    'SA': ('South Australia', -38.1, -26.0, 129.0, 141.0),
    'WA': ('Western Australia', -35.1, -13.7, 112.9, 129.0),
    'TAS': ('Tasmania', -43.6, -39.6, 143.8, 148.5),
    'NT': ('Northern Territory', -26.0, -10.9, 129.0, 138.0),
    'ACT': ('Australian Capital Territory', -35.9, -35.1, 148.8, 149.4),
}


# Country bounding boxes for coordinate-based detection
# These are rough bounding boxes - not exact borders
COUNTRY_BOUNDS = {
    'US': ('United States', 24.5, 49.5, -125.0, -66.5),  # Continental US
    'CA': ('Canada', 41.7, 83.1, -141.0, -52.6),
    'AU': ('Australia', -43.6, -10.7, 112.9, 153.6),
    'GB': ('United Kingdom', 49.9, 60.9, -8.6, 1.8),
    'DE': ('Germany', 47.3, 55.1, 5.9, 15.0),
    'FR': ('France', 41.3, 51.1, -5.1, 9.6),
    'JP': ('Japan', 24.0, 46.0, 122.9, 153.9),
    'NZ': ('New Zealand', -47.3, -34.4, 166.4, 178.6),
    'ES': ('Spain', 36.0, 43.8, -9.3, 4.3),
    'IT': ('Italy', 36.6, 47.1, 6.6, 18.5),
    'NL': ('Netherlands', 50.8, 53.5, 3.4, 7.1),
    'PL': ('Poland', 49.0, 54.8, 14.1, 24.1),
    'SE': ('Sweden', 55.3, 69.1, 11.1, 24.2),
    'NO': ('Norway', 58.0, 71.2, 4.6, 31.1),
    'FI': ('Finland', 59.8, 70.1, 20.6, 31.6),
    'MY': ('Malaysia', 0.9, 7.4, 99.6, 119.3),
    'KR': ('South Korea', 33.1, 38.6, 124.6, 131.9),
    'TW': ('Taiwan', 21.9, 25.3, 120.0, 122.0),
}


def get_country_from_coords(
    lat: float | None, lon: float | None
) -> tuple[str, str] | None:
    """Get country from coordinates using bounding boxes.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Tuple of (country_code, country_name) or None if not found
    """
    if lat is None or lon is None:
        return None

    for code, (name, min_lat, max_lat, min_lon, max_lon) in COUNTRY_BOUNDS.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return (code, name)

    return None


def get_state_from_coords(
    lat: float, lon: float, country_code: str
) -> tuple[str, str] | None:
    """Get state/province from coordinates for supported countries.

    Args:
        lat: Latitude
        lon: Longitude
        country_code: ISO country code (US, CA, AU)

    Returns:
        Tuple of (state_code, state_name) or None if not found
    """
    if country_code == 'US':
        bounds = US_STATE_BOUNDS
    elif country_code == 'CA':
        bounds = CA_PROVINCE_BOUNDS
    elif country_code == 'AU':
        bounds = AU_STATE_BOUNDS
    else:
        return None

    for code, (name, min_lat, max_lat, min_lon, max_lon) in bounds.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return (code, name)

    return None


def get_states_for_country(country_code: str) -> list[tuple[str, str]]:
    """Get list of states/provinces for a country.

    Args:
        country_code: ISO country code (US, CA, AU)

    Returns:
        List of (state_code, state_name) tuples, sorted by name
    """
    if country_code == 'US':
        bounds = US_STATE_BOUNDS
    elif country_code == 'CA':
        bounds = CA_PROVINCE_BOUNDS
    elif country_code == 'AU':
        bounds = AU_STATE_BOUNDS
    else:
        return []

    return sorted(
        [(code, name) for code, (name, *_) in bounds.items()], key=lambda x: x[1]
    )
