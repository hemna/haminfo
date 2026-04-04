"""APRS packet decoder for the dashboard.

Uses aprslib to parse raw APRS packets and generates annotated output
with color-coded segments for display.
"""

from typing import Any

import aprslib


def decode_packet(raw: str) -> dict[str, Any]:
    """
    Decode a raw APRS packet string.

    Args:
        raw: Raw APRS packet string (e.g., "W3ADO>APRS:@092345z3955.00N/...")

    Returns:
        Dict with:
        - success: bool - whether parsing succeeded
        - error: str | None - error message if failed
        - parsed: dict | None - parsed packet fields from aprslib
        - annotations: list - color annotation tuples for raw packet display
        - sections: dict - categorized fields for structured display
    """
    if not raw or not raw.strip():
        return {
            'success': False,
            'error': 'Empty packet. Please paste an APRS packet to decode.',
            'parsed': None,
            'annotations': [],
            'sections': {},
        }

    try:
        parsed = aprslib.parse(raw)
    except (aprslib.ParseError, aprslib.UnknownFormat) as e:
        return {
            'success': False,
            'error': f'Could not decode packet: {str(e)}',
            'parsed': None,
            'annotations': [],
            'sections': {},
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error decoding packet: {str(e)}',
            'parsed': None,
            'annotations': [],
            'sections': {},
        }

    # Generate annotations and categorize sections
    annotations = _generate_annotations(raw, parsed)
    sections = _categorize_sections(parsed)

    return {
        'success': True,
        'error': None,
        'parsed': parsed,
        'annotations': annotations,
        'sections': sections,
    }


def _generate_annotations(raw: str, parsed: dict) -> list[dict]:
    """
    Generate color annotations for the raw packet string.

    Returns list of dicts with:
    - start: int - start index in raw string
    - end: int - end index in raw string
    - field: str - field name (source, destination, path, etc.)
    - color: str - CSS color class suffix
    """
    annotations = []

    # Find source callsign (before >)
    if '>' in raw:
        source_end = raw.index('>')
        annotations.append(
            {
                'start': 0,
                'end': source_end,
                'field': 'source',
                'color': 'source',
            }
        )

        # Find destination (between > and first , or :)
        rest = raw[source_end + 1 :]
        dest_end = len(rest)
        for delim in [',', ':']:
            if delim in rest:
                dest_end = min(dest_end, rest.index(delim))

        annotations.append(
            {
                'start': source_end + 1,
                'end': source_end + 1 + dest_end,
                'field': 'destination',
                'color': 'destination',
            }
        )

        # Find path (between destination and :)
        if ':' in raw:
            colon_pos = raw.index(':')
            path_start = source_end + 1 + dest_end
            if path_start < colon_pos and raw[path_start] == ',':
                annotations.append(
                    {
                        'start': path_start + 1,
                        'end': colon_pos,
                        'field': 'path',
                        'color': 'path',
                    }
                )

            # Data type indicator (first char after :)
            if colon_pos + 1 < len(raw):
                data_type_char = raw[colon_pos + 1]
                if data_type_char in "@/!=;)'`":
                    annotations.append(
                        {
                            'start': colon_pos + 1,
                            'end': colon_pos + 2,
                            'field': 'data_type',
                            'color': 'datatype',
                        }
                    )

    return annotations


def _categorize_sections(parsed: dict) -> dict[str, dict]:
    """
    Categorize parsed fields into display sections.

    Returns dict with sections:
    - station: from, to, path, format
    - position: latitude, longitude, symbol, altitude, timestamp
    - weather: temperature, humidity, pressure, wind, rain
    - telemetry: sequence, analog, digital
    - message: addressee, message_text, msgNo
    - comment: comment text
    """
    sections = {}

    # Station section (always present)
    sections['station'] = {
        'from': parsed.get('from', ''),
        'to': parsed.get('to', ''),
        'path': parsed.get('path', []),
        'format': parsed.get('format', 'unknown'),
    }

    # Position section
    if 'latitude' in parsed or 'longitude' in parsed:
        sections['position'] = {
            'latitude': parsed.get('latitude'),
            'longitude': parsed.get('longitude'),
            'symbol': parsed.get('symbol', ''),
            'symbol_table': parsed.get('symbol_table', '/'),
            'altitude': parsed.get('altitude'),
            'course': parsed.get('course'),
            'speed': parsed.get('speed'),
        }
        # Add timestamp if present
        if 'timestamp' in parsed:
            sections['position']['timestamp'] = parsed.get('timestamp')

    # Weather section - aprslib puts weather data under 'weather' key
    weather_fields = [
        'temperature',
        'humidity',
        'pressure',
        'wind_direction',
        'wind_speed',
        'wind_gust',
        'rain_1h',
        'rain_24h',
        'rain_since_midnight',
        'luminosity',
    ]
    # Check both top-level and nested weather dict
    weather_source = (
        parsed.get('weather', {}) if isinstance(parsed.get('weather'), dict) else {}
    )
    weather_data = {}
    for k in weather_fields:
        # Try weather dict first, then top-level
        if k in weather_source:
            weather_data[k] = weather_source[k]
        elif k in parsed:
            weather_data[k] = parsed[k]
    if weather_data:
        sections['weather'] = weather_data

    # Telemetry section
    if 'telemetry' in parsed:
        sections['telemetry'] = parsed['telemetry']

    # Message section
    if 'message_text' in parsed or 'addresse' in parsed:
        sections['message'] = {
            'addressee': parsed.get('addresse', ''),
            'message_text': parsed.get('message_text', ''),
            'msgNo': parsed.get('msgNo', ''),
        }

    # Comment section
    if 'comment' in parsed and parsed['comment']:
        sections['comment'] = {'text': parsed['comment']}

    return sections
