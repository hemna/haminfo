# APRS Packet Decoder Feature

**Date**: 2026-04-04  
**Status**: Approved  

## Overview

Add a global packet decoder tool to the haminfo dashboard that allows users to paste a raw APRS packet and see a detailed breakdown of its contents. The decoder is accessible from any page via a header icon and keyboard shortcut.

## User Story

As a ham radio operator viewing the dashboard, I want to paste a raw APRS packet and instantly see it decoded with a visual breakdown, so I can understand packet contents without manually parsing the APRS format.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Input location | Header nav icon + ⌘K shortcut | Globally accessible, unobtrusive, follows modern app patterns |
| Display format | Annotated raw packet + structured tables | Shows both the raw format (educational) and clean data (practical) |
| Decoding location | Server-side (Python) | Uses existing `aprslib`, consistent with codebase, reliable parsing |
| Error handling | Error message in modal | Clear feedback without disrupting page flow |
| History | None (MVP) | Keep scope minimal for first version |
| Implementation pattern | HTMX + server-rendered HTML | Matches existing dashboard patterns |

## UI Components

### Header Decode Button

Added to the right side of the header navigation in `base.html`:

```html
<div class="decode-trigger" onclick="openDecodeModal()" title="Decode APRS Packet (⌘K)">
  <span class="decode-icon">📡</span>
  <span class="decode-label">Decode</span>
  <span class="decode-shortcut">⌘K</span>
</div>
```

Styling matches existing nav elements with the dashboard's dark theme.

### Decoder Modal

Overlay modal containing:

1. **Header**: Title "Decode APRS Packet" with close button
2. **Input area**: Textarea for pasting raw packet, placeholder with example format
3. **Decode button**: Triggers HTMX POST, disabled when input is empty
4. **Results area**: Initially hidden, populated via HTMX swap after decode

### Results Display

Two-part layout:

**Part 1: Annotated Raw Packet**
- Raw packet string with color-coded segments
- Each segment (source, destination, path, data type, timestamp, position, weather/telemetry) has a distinct background color
- Legend showing what each color represents
- Segments are visually distinct with padding and border-radius

Color scheme:
- Source callsign: Green (#3fb950)
- Destination: Yellow (#d29922)
- Path: Blue (#58a6ff)
- Data type indicator: Purple (#bc8cff)
- Timestamp: White/gray (#c9d1d9)
- Position: Red/orange (#ff7b72)
- Weather/Telemetry data: Cyan (#79c0ff)

**Part 2: Structured Tables**

Organized in a 2-column grid:

| Section | Fields |
|---------|--------|
| Station | From, To, Path, Packet Type |
| Position | Latitude, Longitude, Timestamp, Symbol, Altitude (if present) |
| Weather (conditional) | Wind direction/speed/gust, Temperature, Humidity, Pressure, Rain |
| Telemetry (conditional) | Sequence, Analog values, Digital bits |
| Message (conditional) | Addressee, Message text, Message ID |
| Comment | Comment text (if present) |

**Action Buttons**:
- "Copy Raw" - Copies original packet to clipboard
- "View Station" - Links to `/station/<callsign>` page (if callsign valid)

## Backend API

### Endpoint

```
POST /api/dashboard/decode
Content-Type: application/x-www-form-urlencoded
```

### Request

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| raw_packet | string | Yes | Raw APRS packet string to decode |

### Response

**Success (200)**: HTML partial containing annotated packet and structured tables

**Error (200 with error content)**: HTML partial containing error message. Common errors:
- Empty input
- Invalid packet format
- Unrecognized packet type

Note: Returns 200 with error HTML rather than HTTP error codes, allowing HTMX to swap the error display into the modal.

### Parsing Logic

Located in new file `haminfo_dashboard/decoder.py`:

```python
def decode_packet(raw: str) -> dict:
    """
    Decode raw APRS packet using aprslib.
    
    Returns dict with:
    - success: bool
    - error: str (if failed)
    - parsed: dict (aprslib output)
    - annotations: list of (start, end, field_type, color) tuples
    - sections: dict of categorized fields for display
    """
```

The annotation generation maps parsed field values back to their positions in the raw string to enable color-coding.

## Keyboard Shortcut

Global event listener in `base.html`:

```javascript
document.addEventListener('keydown', function(e) {
  // ⌘K (Mac) or Ctrl+K (Windows/Linux)
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    openDecodeModal();
  }
});
```

The modal input is auto-focused when opened.

## Data Flow

```
1. User clicks decode icon or presses ⌘K
   → openDecodeModal() called
   → Modal overlay shown, input focused

2. User pastes packet, clicks Decode (or presses Enter)
   → HTMX POST to /api/dashboard/decode
   → Loading spinner shown in results area

3. Server receives request
   → Validates input (non-empty)
   → Calls aprslib.parse(raw_packet)
   → On success: generates annotations, categorizes fields
   → On error: prepares error message
   → Renders partials/decode_result.html

4. HTMX receives response
   → Swaps HTML into #decode-results
   → Results area becomes visible

5. User can:
   → Copy raw packet
   → Click "View Station" to navigate
   → Close modal (×, Escape, or click overlay)
   → Decode another packet
```

## Error Handling

| Error | Display |
|-------|---------|
| Empty input | Decode button disabled; if somehow submitted, show "Please enter a packet to decode" |
| Parse failure | "Could not decode packet: [aprslib error message]" with suggestion to check format |
| Network error | "Network error. Please try again." |
| Unknown packet type | Show what was parsed, mark unknown sections as "Unknown/Unparsed" |

Error messages appear in the results area with a distinct error styling (red border, error icon).

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `haminfo_dashboard/decoder.py` | Packet decoding logic, annotation generation |
| `templates/dashboard/partials/decode_result.html` | Results template (success case) |
| `templates/dashboard/partials/decode_error.html` | Error template |

### Modified Files

| File | Changes |
|------|---------|
| `templates/dashboard/base.html` | Add decode icon to header, modal markup, CSS for modal and results, keyboard shortcut JS |
| `haminfo_dashboard/api.py` | Add `/api/dashboard/decode` endpoint |

## CSS Additions

Added to `base.html` inline styles (following existing pattern):

```css
/* Decode trigger button */
.decode-trigger { ... }

/* Decode modal */
#decode-modal { ... }
#decode-modal .modal { max-width: 700px; }

/* Annotated packet display */
.packet-annotated { font-family: monospace; line-height: 2.2; }
.packet-segment { padding: 3px 6px; border-radius: 3px; }
.packet-segment-source { background: rgba(63,185,80,0.3); color: #3fb950; }
/* ... other segment colors ... */

/* Structured tables */
.decode-section { ... }
.decode-table { ... }

/* Error state */
.decode-error { border-left: 3px solid #f85149; }
```

## Testing

### Manual Test Cases

1. **Valid position packet**: Paste `W3ADO-1>APRS,WIDE1-1:@092345z3955.00N/07520.00W_090/005` → Should show station info, position, comment
2. **Weather packet**: Paste packet with weather data → Should show weather section with all fields
3. **Message packet**: Paste `:DEST     :message text{123` format → Should show message section
4. **Telemetry packet**: Paste `T#seq,v1,v2,v3,v4,v5,bbbbbbbb` format → Should show telemetry section
5. **Invalid packet**: Paste random text → Should show clear error message
6. **Empty input**: Click decode with no input → Button disabled or shows validation error
7. **Keyboard shortcut**: Press ⌘K → Modal opens, input focused
8. **Close modal**: Press Escape, click ×, click overlay → Modal closes

## Future Enhancements (Out of Scope)

- Decode history (localStorage or server-side)
- JSON API variant for external consumers
- Clickable map showing position
- Link to APRS.fi for comparison
- Batch decode multiple packets
