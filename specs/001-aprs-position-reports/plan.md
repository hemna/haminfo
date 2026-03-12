# Implementation Plan: APRS Position Reports API

**Branch**: `001-aprs-position-reports` | **Date**: 2026-03-09 | **Spec**: User request (no formal spec)
**Input**: "Add support for ingesting, saving position reports to the DB and export an API, like aprs.fi has for fetching callsign locations by the aprsd-locationdata-extension"

## Summary

Add a location query API endpoint to haminfo that serves as a self-hosted
replacement for the aprs.fi location API. The system already ingests APRS
packets via MQTT (including position reports stored in the `aprs_packet`
table). This feature adds:

1. **Database query layer** for looking up the latest position of one or more
   callsigns from the existing `aprs_packet` table.
2. **REST API endpoint** that returns callsign location data in a format
   compatible with the aprs.fi `?what=loc` JSON response, enabling the
   `aprsd-locationdata-plugin` and `aprsd-location-plugin` to use haminfo
   as their data source instead of aprs.fi.
3. **Data retention cleanup** for old APRS packets to prevent unbounded
   table growth.

## Technical Context

**Language/Version**: Python 3.10+ (supports 3.10-3.13)
**Primary Dependencies**: Flask 1.1.4+, SQLAlchemy 2.0.41+, GeoAlchemy2 0.17.1+, aprsd 4.2.4
**Storage**: PostgreSQL 15 with PostGIS 3.3, memcached (dogpile.cache)
**Testing**: pytest 8.0+, pytest-cov 5.0+
**Target Platform**: Linux server (Docker deployment)
**Project Type**: Web service (REST API) + CLI tool
**Performance Goals**: <200ms p95 for location queries; support up to 20 callsigns per query (matching aprs.fi limit)
**Constraints**: <200ms p95 read latency; queries MUST use existing PostGIS spatial indexes on `aprs_packet.location`; MUST NOT require aprs.fi API key or external network calls
**Scale/Scope**: Thousands of unique callsigns ingested daily; position queries expected at low-to-moderate frequency (~100 req/min)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Code Quality

- [x] All new Python code will use type hints and docstrings
- [x] Ruff linting will be enforced
- [x] Database queries will use SQLAlchemy ORM (parameterized)
- [x] No new dependencies required (all deps already in pyproject.toml)

### II. Testing Standards

- [x] Unit tests for query functions and response formatting
- [x] Integration tests for the API endpoint with test DB fixtures
- [x] Contract tests verifying aprs.fi-compatible JSON response structure
- [x] Tests will use fixtures, not production data

### III. User Experience Consistency

- [x] API will follow existing `/api/v{N}/` pattern: new endpoint at `/api/v1/location`
- [x] Response JSON will use consistent `data`/`error`/`meta` structure
- [x] Additionally return aprs.fi-compatible format at `/api/get` for plugin compatibility
- [x] Callsign input: case-insensitive; output: uppercase
- [x] Timestamps: ISO 8601 (native format) + Unix epoch (aprs.fi compat)
- [x] Coordinates: decimal degrees (lat/lon)

### IV. Performance Requirements

- [x] Query uses existing indexes on `from_call` and `timestamp`
- [x] PostGIS spatial index on `location` column already exists
- [x] Caching via dogpile.cache for frequently queried callsigns
- [x] No N+1 queries: single query per request with DISTINCT ON

**GATE STATUS: PASS** - No violations identified.

## Project Structure

### Documentation (this feature)

```text
specs/001-aprs-position-reports/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── location-api.md  # API endpoint contract
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
haminfo/
├── db/
│   ├── db.py                    # Add: find_latest_position_by_callsign()
│   │                            # Add: find_latest_positions_by_callsigns()
│   │                            # Add: clean_aprs_packets()
│   └── models/
│       └── aprs_packet.py       # Add: class query methods
├── flask.py                     # Add: /api/v1/location endpoint
│                                # Add: /api/get (aprs.fi compat endpoint)
└── cmds/
    └── db.py                    # Add: clean-aprs-packets CLI command

tests/
├── test_aprs_position_query.py  # Unit tests for DB query functions
├── test_location_api.py         # Integration tests for API endpoints
└── test_aprsfi_compat.py        # Contract tests for aprs.fi format
```

**Structure Decision**: This feature extends the existing single-project
structure. No new directories needed. Changes touch existing files in the
`haminfo/db/` and `haminfo/flask.py` modules, with new test files in `tests/`.

## Complexity Tracking

> No violations identified. Feature follows existing patterns established
> by the weather station query system (`find_wxnearest_to`, `/wxnearest`).
