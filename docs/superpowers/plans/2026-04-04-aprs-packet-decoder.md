# APRS Packet Decoder Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global APRS packet decoder to the dashboard that lets users paste raw packets and see annotated, color-coded breakdowns.

**Architecture:** Header icon + keyboard shortcut opens a modal. User pastes packet, HTMX POSTs to server, `aprslib.parse()` decodes it, server renders HTML partial with annotated raw packet and structured tables.

**Tech Stack:** Python/Flask, aprslib, HTMX, Jinja2 templates

**Spec:** `docs/superpowers/specs/2026-04-04-aprs-packet-decoder-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `haminfo_dashboard/decoder.py` (new) | Packet decoding logic, annotation generation, field categorization |
| `haminfo_dashboard/api.py` (modify) | Add `/api/dashboard/decode` endpoint |
| `templates/dashboard/base.html` (modify) | Header icon, modal markup, CSS, keyboard shortcut JS |
| `templates/dashboard/partials/decode_result.html` (new) | Success result template |
| `templates/dashboard/partials/decode_error.html` (new) | Error result template |
| `tests/test_decoder.py` (new) | Unit tests for decoder logic |

---

## Chunk 1: Backend Decoder Logic

### Task 1: Create decoder module with tests

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/decoder.py`
- Create: `haminfo-dashboard/tests/test_decoder.py`

- [ ] **Step 1: Write failing test for basic packet parsing**

Create `haminfo-dashboard/tests/test_decoder.py`:

```python
"""Tests for APRS packet decoder."""
import pytest
from haminfo_dashboard.decoder import decode_packet


class TestDecodePacket:
    """Tests for decode_packet function."""

    def test_decode_position_packet(self):
        """Test decoding a basic position packet."""
        raw = "W3ADO-1>APRS,WIDE1-1,qAR,W3XYZ:@092345z3955.00N/07520.00W_"
        result = decode_packet(raw)

        assert result['success'] is True
        assert result['error'] is None
        assert result['parsed']['from'] == 'W3ADO-1'
        assert result['parsed']['to'] == 'APRS'
        assert 'latitude' in result['parsed']
        assert 'longitude' in result['parsed']

    def test_decode_invalid_packet(self):
        """Test decoding invalid packet returns error."""
        raw = "this is not a valid aprs packet"
        result = decode_packet(raw)

        assert result['success'] is False
        assert result['error'] is not None
        assert 'parsed' not in result or result['parsed'] is None

    def test_decode_empty_packet(self):
        """Test decoding empty string returns error."""
        result = decode_packet("")

        assert result['success'] is False
        assert 'empty' in result['error'].lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd haminfo-dashboard && python -m pytest tests/test_decoder.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'haminfo_dashboard.decoder'`

- [ ] **Step 3: Write minimal decoder implementation**

Create `haminfo-dashboard/src/haminfo_dashboard/decoder.py`:

```python
"""APRS packet decoder for the dashboard.

Uses aprslib to parse raw APRS packets and generates annotated output
with color-coded segments for display.
"""
from typing import Any, Optional
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
        annotations.append({
            'start': 0,
            'end': source_end,
            'field': 'source',
            'color': 'source',
        })

        # Find destination (between > and first , or :)
        rest = raw[source_end + 1:]
        dest_end = len(rest)
        for delim in [',', ':']:
            if delim in rest:
                dest_end = min(dest_end, rest.index(delim))

        annotations.append({
            'start': source_end + 1,
            'end': source_end + 1 + dest_end,
            'field': 'destination',
            'color': 'destination',
        })

        # Find path (between destination and :)
        if ':' in raw:
            colon_pos = raw.index(':')
            path_start = source_end + 1 + dest_end
            if path_start < colon_pos and raw[path_start] == ',':
                annotations.append({
                    'start': path_start + 1,
                    'end': colon_pos,
                    'field': 'path',
                    'color': 'path',
                })

            # Data type indicator (first char after :)
            if colon_pos + 1 < len(raw):
                data_type_char = raw[colon_pos + 1]
                if data_type_char in '@/!=;)\'`':
                    annotations.append({
                        'start': colon_pos + 1,
                        'end': colon_pos + 2,
                        'field': 'data_type',
                        'color': 'datatype',
                    })

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

    # Weather section
    weather_fields = ['temperature', 'humidity', 'pressure', 'wind_direction',
                      'wind_speed', 'wind_gust', 'rain_1h', 'rain_24h',
                      'rain_since_midnight', 'luminosity']
    weather_data = {k: parsed.get(k) for k in weather_fields if k in parsed}
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd haminfo-dashboard && python -m pytest tests/test_decoder.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Add more comprehensive tests**

Add to `haminfo-dashboard/tests/test_decoder.py`:

```python
    def test_decode_weather_packet(self):
        """Test decoding a weather packet extracts weather data."""
        raw = "W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_090/005g010t072r001h85b10234"
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'weather' in result['sections']
        weather = result['sections']['weather']
        assert weather.get('wind_direction') == 90
        assert weather.get('wind_speed') == 5
        assert weather.get('wind_gust') == 10
        assert weather.get('temperature') == 72

    def test_decode_message_packet(self):
        """Test decoding a message packet."""
        raw = "W3ADO-1>APRS::W3XYZ    :Hello World{123"
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'message' in result['sections']
        msg = result['sections']['message']
        assert 'W3XYZ' in msg.get('addressee', '')

    def test_annotations_include_source(self):
        """Test that annotations include source callsign."""
        raw = "W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_"
        result = decode_packet(raw)

        assert result['success'] is True
        source_annotations = [a for a in result['annotations'] if a['field'] == 'source']
        assert len(source_annotations) == 1
        assert source_annotations[0]['start'] == 0
        assert source_annotations[0]['end'] == 7  # "W3ADO-1"

    def test_sections_always_has_station(self):
        """Test that sections always includes station info."""
        raw = "W3ADO-1>APRS:>Status message"
        result = decode_packet(raw)

        assert result['success'] is True
        assert 'station' in result['sections']
        assert result['sections']['station']['from'] == 'W3ADO-1'
```

- [ ] **Step 6: Run all decoder tests**

```bash
cd haminfo-dashboard && python -m pytest tests/test_decoder.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 7: Commit decoder module**

```bash
cd haminfo-dashboard && git add src/haminfo_dashboard/decoder.py tests/test_decoder.py
git commit -m "feat: Add APRS packet decoder module with tests"
```

---

## Chunk 2: API Endpoint

### Task 2: Add decode API endpoint

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/api.py`
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/decode_result.html`
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/decode_error.html`

- [ ] **Step 1: Create decode_result.html template**

Create `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/decode_result.html`:

```html
{# Decode result partial - rendered on successful packet decode #}

<!-- Annotated Raw Packet -->
<div class="decode-annotated-section">
    <div class="decode-section-header">Raw Packet (color-coded)</div>
    <div class="packet-annotated">
        {%- set ns = namespace(last_end=0) -%}
        {%- for ann in annotations -%}
            {%- if ann.start > ns.last_end -%}
                <span class="packet-segment-plain">{{ raw_packet[ns.last_end:ann.start] }}</span>
            {%- endif -%}
            <span class="packet-segment packet-segment-{{ ann.color }}" title="{{ ann.field }}">{{ raw_packet[ann.start:ann.end] }}</span>
            {%- set ns.last_end = ann.end -%}
        {%- endfor -%}
        {%- if ns.last_end < raw_packet|length -%}
            <span class="packet-segment-plain">{{ raw_packet[ns.last_end:] }}</span>
        {%- endif -%}
    </div>
    <div class="packet-legend">
        <span class="legend-item"><span class="legend-color legend-source"></span> Source</span>
        <span class="legend-item"><span class="legend-color legend-destination"></span> Destination</span>
        <span class="legend-item"><span class="legend-color legend-path"></span> Path</span>
        <span class="legend-item"><span class="legend-color legend-datatype"></span> Data Type</span>
        <span class="legend-item"><span class="legend-color legend-position"></span> Position</span>
        <span class="legend-item"><span class="legend-color legend-weather"></span> Weather/Data</span>
    </div>
</div>

<!-- Structured Data Tables -->
<div class="decode-tables">
    {# Station Info - always present #}
    {% if sections.station %}
    <div class="decode-section">
        <div class="decode-section-header" style="color: #58a6ff;">Station</div>
        <table class="decode-table">
            <tr><td class="decode-label">From</td><td class="decode-value"><code>{{ sections.station.from }}</code></td></tr>
            <tr><td class="decode-label">To</td><td class="decode-value"><code>{{ sections.station.to }}</code></td></tr>
            {% if sections.station.path %}
            <tr><td class="decode-label">Path</td><td class="decode-value"><code>{{ sections.station.path|join(', ') if sections.station.path is iterable and sections.station.path is not string else sections.station.path }}</code></td></tr>
            {% endif %}
            <tr><td class="decode-label">Format</td><td class="decode-value">{{ sections.station.format }}</td></tr>
        </table>
    </div>
    {% endif %}

    {# Position Info #}
    {% if sections.position %}
    <div class="decode-section">
        <div class="decode-section-header" style="color: #ff7b72;">Position</div>
        <table class="decode-table">
            {% if sections.position.latitude is not none %}
            <tr><td class="decode-label">Latitude</td><td class="decode-value">{{ "%.5f"|format(sections.position.latitude) }}°</td></tr>
            {% endif %}
            {% if sections.position.longitude is not none %}
            <tr><td class="decode-label">Longitude</td><td class="decode-value">{{ "%.5f"|format(sections.position.longitude) }}°</td></tr>
            {% endif %}
            {% if sections.position.timestamp %}
            <tr><td class="decode-label">Timestamp</td><td class="decode-value">{{ sections.position.timestamp }}</td></tr>
            {% endif %}
            {% if sections.position.symbol %}
            <tr><td class="decode-label">Symbol</td><td class="decode-value">{{ sections.position.symbol_table }}{{ sections.position.symbol }}</td></tr>
            {% endif %}
            {% if sections.position.altitude is not none %}
            <tr><td class="decode-label">Altitude</td><td class="decode-value">{{ sections.position.altitude }} ft</td></tr>
            {% endif %}
            {% if sections.position.speed is not none %}
            <tr><td class="decode-label">Speed</td><td class="decode-value">{{ sections.position.speed }} knots</td></tr>
            {% endif %}
            {% if sections.position.course is not none %}
            <tr><td class="decode-label">Course</td><td class="decode-value">{{ sections.position.course }}°</td></tr>
            {% endif %}
        </table>
    </div>
    {% endif %}

    {# Weather Data #}
    {% if sections.weather %}
    <div class="decode-section decode-section-wide">
        <div class="decode-section-header" style="color: #79c0ff;">Weather</div>
        <div class="decode-weather-grid">
            {% if sections.weather.wind_direction is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Wind Dir</span>
                <span class="decode-weather-value">{{ sections.weather.wind_direction }}°</span>
            </div>
            {% endif %}
            {% if sections.weather.wind_speed is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Wind Spd</span>
                <span class="decode-weather-value">{{ sections.weather.wind_speed }} mph</span>
            </div>
            {% endif %}
            {% if sections.weather.wind_gust is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Gust</span>
                <span class="decode-weather-value">{{ sections.weather.wind_gust }} mph</span>
            </div>
            {% endif %}
            {% if sections.weather.temperature is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Temp</span>
                <span class="decode-weather-value">{{ sections.weather.temperature }}°F</span>
            </div>
            {% endif %}
            {% if sections.weather.humidity is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Humidity</span>
                <span class="decode-weather-value">{{ sections.weather.humidity }}%</span>
            </div>
            {% endif %}
            {% if sections.weather.pressure is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Pressure</span>
                <span class="decode-weather-value">{{ sections.weather.pressure }} mb</span>
            </div>
            {% endif %}
            {% if sections.weather.rain_1h is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Rain 1h</span>
                <span class="decode-weather-value">{{ sections.weather.rain_1h }}"</span>
            </div>
            {% endif %}
            {% if sections.weather.rain_24h is not none %}
            <div class="decode-weather-item">
                <span class="decode-weather-label">Rain 24h</span>
                <span class="decode-weather-value">{{ sections.weather.rain_24h }}"</span>
            </div>
            {% endif %}
        </div>
    </div>
    {% endif %}

    {# Message Data #}
    {% if sections.message %}
    <div class="decode-section decode-section-wide">
        <div class="decode-section-header" style="color: #d29922;">Message</div>
        <table class="decode-table">
            <tr><td class="decode-label">To</td><td class="decode-value"><code>{{ sections.message.addressee }}</code></td></tr>
            <tr><td class="decode-label">Message</td><td class="decode-value">{{ sections.message.message_text }}</td></tr>
            {% if sections.message.msgNo %}
            <tr><td class="decode-label">Msg #</td><td class="decode-value">{{ sections.message.msgNo }}</td></tr>
            {% endif %}
        </table>
    </div>
    {% endif %}

    {# Telemetry Data #}
    {% if sections.telemetry %}
    <div class="decode-section decode-section-wide">
        <div class="decode-section-header" style="color: #bc8cff;">Telemetry</div>
        <table class="decode-table">
            {% for key, value in sections.telemetry.items() %}
            <tr><td class="decode-label">{{ key }}</td><td class="decode-value">{{ value }}</td></tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}

    {# Comment #}
    {% if sections.comment %}
    <div class="decode-section decode-section-wide">
        <div class="decode-section-header" style="color: #8b949e;">Comment</div>
        <div class="decode-comment">{{ sections.comment.text }}</div>
    </div>
    {% endif %}
</div>

<!-- Action Buttons -->
<div class="decode-actions">
    <button class="decode-btn decode-btn-secondary" onclick="copyRawPacket()">
        📋 Copy Raw
    </button>
    {% if sections.station and sections.station.from %}
    <a href="{{ url_for('dashboard.station', callsign=sections.station.from) }}" class="decode-btn decode-btn-primary">
        🔍 View Station
    </a>
    {% endif %}
</div>
```

- [ ] **Step 2: Create decode_error.html template**

Create `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/decode_error.html`:

```html
{# Decode error partial - rendered when packet decode fails #}
<div class="decode-error">
    <div class="decode-error-icon">⚠️</div>
    <div class="decode-error-message">{{ error }}</div>
    <div class="decode-error-hint">
        Check that the packet follows APRS format, e.g.:<br>
        <code>CALLSIGN>DEST,PATH:data</code>
    </div>
</div>
```

- [ ] **Step 3: Add API endpoint to api.py**

Add to the end of `haminfo-dashboard/src/haminfo_dashboard/api.py` (before any `if __name__` block):

```python
@dashboard_bp.route('/api/dashboard/decode', methods=['POST'])
def api_decode_packet():
    """Decode a raw APRS packet and return HTML partial with results."""
    from haminfo_dashboard.decoder import decode_packet

    raw_packet = request.form.get('raw_packet', '').strip()

    result = decode_packet(raw_packet)

    if result['success']:
        return render_template(
            'dashboard/partials/decode_result.html',
            raw_packet=raw_packet,
            annotations=result['annotations'],
            sections=result['sections'],
            parsed=result['parsed'],
        )
    else:
        return render_template(
            'dashboard/partials/decode_error.html',
            error=result['error'],
        )
```

- [ ] **Step 4: Run existing tests to ensure no regressions**

```bash
cd haminfo-dashboard && python -m pytest tests/ -v --ignore=tests/test_tile_cache.py
```

Expected: All tests PASS

- [ ] **Step 5: Commit API endpoint and templates**

```bash
cd haminfo-dashboard && git add src/haminfo_dashboard/api.py \
    src/haminfo_dashboard/templates/dashboard/partials/decode_result.html \
    src/haminfo_dashboard/templates/dashboard/partials/decode_error.html
git commit -m "feat: Add /api/dashboard/decode endpoint with result templates"
```

---

## Chunk 3: Frontend UI

### Task 3: Add header icon, modal, and CSS to base.html

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/base.html`

- [ ] **Step 1: Read current base.html structure**

Review the header section and existing modal patterns in `base.html` to understand where to add the decode trigger and modal.

- [ ] **Step 2: Add CSS for decoder UI**

Add to the `<style>` section in `base.html`, after existing modal styles:

```css
/* Decode Trigger Button */
.decode-trigger {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
}
.decode-trigger:hover {
    background: var(--bg-primary);
    border-color: var(--accent-green);
}
.decode-icon { font-size: 14px; }
.decode-label { font-size: 12px; color: var(--text-secondary); }
.decode-shortcut {
    font-size: 10px;
    color: var(--text-muted);
    padding: 2px 4px;
    border: 1px solid var(--border-color);
    border-radius: 3px;
    font-family: monospace;
}

/* Decode Modal */
#decode-modal .modal {
    max-width: 720px;
    width: 95%;
}
#decode-modal .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
}
#decode-modal .modal-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
}
#decode-modal .modal-close {
    background: none;
    border: none;
    font-size: 24px;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0;
    line-height: 1;
}
#decode-modal .modal-close:hover { color: var(--text-primary); }
#decode-modal .modal-body {
    padding: 20px;
    max-height: 70vh;
    overflow-y: auto;
}

/* Decode Input */
.decode-input-section { margin-bottom: 16px; }
.decode-textarea {
    width: 100%;
    min-height: 80px;
    padding: 12px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 13px;
    resize: vertical;
}
.decode-textarea:focus {
    outline: none;
    border-color: var(--accent-green);
}
.decode-textarea::placeholder { color: var(--text-muted); }
.decode-submit-row {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
}
.decode-submit-btn {
    padding: 8px 20px;
    background: var(--accent-green);
    color: #000;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s;
}
.decode-submit-btn:hover { opacity: 0.9; }
.decode-submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* Decode Results */
#decode-results { margin-top: 20px; }
#decode-results:empty { display: none; }

.decode-annotated-section {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 20px;
}
.decode-section-header {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 10px;
    font-weight: 600;
}
.packet-annotated {
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 13px;
    line-height: 2.2;
    word-break: break-all;
}
.packet-segment {
    padding: 3px 6px;
    border-radius: 3px;
    cursor: help;
}
.packet-segment-plain { color: var(--text-muted); }
.packet-segment-source { background: rgba(63,185,80,0.3); color: #3fb950; }
.packet-segment-destination { background: rgba(210,153,34,0.3); color: #d29922; }
.packet-segment-path { background: rgba(88,166,255,0.3); color: #58a6ff; }
.packet-segment-datatype { background: rgba(188,140,255,0.3); color: #bc8cff; }
.packet-segment-timestamp { background: rgba(255,255,255,0.15); color: #c9d1d9; }
.packet-segment-position { background: rgba(255,123,114,0.3); color: #ff7b72; }
.packet-segment-weather { background: rgba(121,192,255,0.3); color: #79c0ff; }

.packet-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 12px;
    font-size: 10px;
}
.legend-item { display: flex; align-items: center; gap: 4px; color: var(--text-muted); }
.legend-color {
    width: 12px;
    height: 12px;
    border-radius: 2px;
}
.legend-source { background: rgba(63,185,80,0.5); }
.legend-destination { background: rgba(210,153,34,0.5); }
.legend-path { background: rgba(88,166,255,0.5); }
.legend-datatype { background: rgba(188,140,255,0.5); }
.legend-position { background: rgba(255,123,114,0.5); }
.legend-weather { background: rgba(121,192,255,0.5); }

/* Decode Tables */
.decode-tables {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}
.decode-section {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 14px;
}
.decode-section-wide { grid-column: span 2; }
.decode-table {
    width: 100%;
    font-size: 12px;
}
.decode-table td { padding: 4px 0; }
.decode-label { color: var(--text-muted); width: 40%; }
.decode-value { color: var(--text-primary); }
.decode-value code {
    background: var(--bg-card);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
}

.decode-weather-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
}
.decode-weather-item { text-align: center; }
.decode-weather-label {
    display: block;
    font-size: 10px;
    color: var(--text-muted);
    margin-bottom: 4px;
}
.decode-weather-value {
    font-size: 16px;
    color: var(--text-primary);
}

.decode-comment {
    color: var(--text-secondary);
    font-style: italic;
}

/* Decode Actions */
.decode-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
}
.decode-btn {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.decode-btn-secondary {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
}
.decode-btn-secondary:hover { border-color: var(--text-muted); }
.decode-btn-primary {
    background: var(--accent-green);
    border: none;
    color: #000;
    font-weight: 600;
}

/* Decode Error */
.decode-error {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-left: 3px solid #f85149;
    border-radius: 6px;
    padding: 20px;
    text-align: center;
}
.decode-error-icon { font-size: 32px; margin-bottom: 12px; }
.decode-error-message {
    color: #f85149;
    font-size: 14px;
    margin-bottom: 12px;
}
.decode-error-hint {
    color: var(--text-muted);
    font-size: 12px;
}
.decode-error-hint code {
    background: var(--bg-card);
    padding: 2px 6px;
    border-radius: 3px;
}

/* Responsive */
@media (max-width: 600px) {
    .decode-tables { grid-template-columns: 1fr; }
    .decode-section-wide { grid-column: span 1; }
    .decode-weather-grid { grid-template-columns: repeat(2, 1fr); }
}
```

- [ ] **Step 3: Add decode trigger to header**

Find the header section in `base.html` (look for `<header class="header">`) and add the decode trigger button. Add it near the `.header-right` section or after the nav links:

```html
<div class="decode-trigger" onclick="openDecodeModal()" title="Decode APRS Packet (⌘K)">
    <span class="decode-icon">📡</span>
    <span class="decode-label">Decode</span>
    <span class="decode-shortcut">⌘K</span>
</div>
```

- [ ] **Step 4: Add decode modal markup**

Add the modal markup before the closing `</body>` tag, after other modals:

```html
<!-- Decode APRS Packet Modal -->
<div id="decode-modal" class="modal-overlay" onclick="if(event.target === this) closeDecodeModal()">
    <div class="modal">
        <div class="modal-header">
            <span class="modal-title">📡 Decode APRS Packet</span>
            <button class="modal-close" onclick="closeDecodeModal()">&times;</button>
        </div>
        <div class="modal-body">
            <div class="decode-input-section">
                <textarea
                    id="decode-input"
                    name="raw_packet"
                    class="decode-textarea"
                    placeholder="Paste raw APRS packet here, e.g.:&#10;W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_090/005g010t072"
                    oninput="updateDecodeButton()"
                ></textarea>
                <div class="decode-submit-row">
                    <button
                        id="decode-submit-btn"
                        class="decode-submit-btn"
                        disabled
                        hx-post="{{ url_for('dashboard.api_decode_packet') }}"
                        hx-include="#decode-input"
                        hx-target="#decode-results"
                        hx-swap="innerHTML"
                        hx-indicator="#decode-loading"
                    >
                        Decode
                    </button>
                </div>
            </div>
            <div id="decode-loading" class="htmx-indicator" style="text-align: center; padding: 20px;">
                <div class="loading-spinner"></div>
            </div>
            <div id="decode-results"></div>
        </div>
    </div>
</div>
```

- [ ] **Step 5: Add JavaScript for modal and keyboard shortcut**

Add to the `<script>` section in `base.html`:

```javascript
// Decode Modal Functions
function openDecodeModal() {
    const modal = document.getElementById('decode-modal');
    modal.classList.add('active');
    document.getElementById('decode-input').focus();
    // Clear previous results
    document.getElementById('decode-results').innerHTML = '';
}

function closeDecodeModal() {
    const modal = document.getElementById('decode-modal');
    modal.classList.remove('active');
}

function updateDecodeButton() {
    const input = document.getElementById('decode-input');
    const btn = document.getElementById('decode-submit-btn');
    btn.disabled = !input.value.trim();
}

function copyRawPacket() {
    const input = document.getElementById('decode-input');
    navigator.clipboard.writeText(input.value).then(() => {
        // Brief visual feedback
        const btn = event.target;
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Copied!';
        setTimeout(() => { btn.innerHTML = originalText; }, 1500);
    });
}

// Keyboard shortcut: Cmd+K (Mac) or Ctrl+K (Windows/Linux)
document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        openDecodeModal();
    }
    // Escape to close
    if (e.key === 'Escape') {
        closeDecodeModal();
    }
});

// Submit on Enter (when not holding Shift for newline)
document.getElementById('decode-input')?.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const btn = document.getElementById('decode-submit-btn');
        if (!btn.disabled) {
            btn.click();
        }
    }
});
```

- [ ] **Step 6: Test the UI manually**

Start the dashboard dev server and test:
1. Click the decode icon in header → modal opens
2. Press ⌘K → modal opens
3. Paste a packet → Decode button enables
4. Click Decode → results appear
5. Press Escape → modal closes
6. Click outside modal → modal closes

- [ ] **Step 7: Commit UI changes**

```bash
cd haminfo-dashboard && git add src/haminfo_dashboard/templates/dashboard/base.html
git commit -m "feat: Add packet decoder modal with keyboard shortcut to dashboard"
```

---

## Chunk 4: Final Testing and Cleanup

### Task 4: Integration testing and polish

- [ ] **Step 1: Test various packet types**

Test these packets manually in the UI:

```
# Position packet
W3ADO-1>APRS,WIDE1-1,qAR,W3XYZ:@092345z3955.00N/07520.00W_

# Weather packet
W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_090/005g010t072r001h85b10234

# Message packet
W3ADO-1>APRS::W3XYZ    :Hello World{123

# Status packet
W3ADO-1>APRS:>Monitoring 146.520

# Invalid packet
this is not valid
```

- [ ] **Step 2: Fix any issues found during testing**

Address any UI or parsing issues discovered.

- [ ] **Step 3: Run full test suite**

```bash
cd haminfo-dashboard && python -m pytest tests/ -v --ignore=tests/test_tile_cache.py
```

Expected: All tests PASS

- [ ] **Step 4: Commit any fixes**

```bash
cd haminfo-dashboard && git add -A
git commit -m "fix: Address issues found during packet decoder testing"
```

(Only if there were fixes needed)

- [ ] **Step 5: Final commit for feature completion**

```bash
cd haminfo-dashboard && git log --oneline -5
```

Verify all commits are in place for the feature.

---

## Summary

After completing all tasks, the feature will include:

1. **Backend**: `decoder.py` module with `decode_packet()` function and comprehensive tests
2. **API**: `/api/dashboard/decode` endpoint returning HTML partials
3. **UI**: Header decode icon, modal with textarea input, keyboard shortcut (⌘K)
4. **Display**: Color-coded annotated raw packet + structured data tables
5. **Error handling**: Clear error messages in modal for invalid packets
