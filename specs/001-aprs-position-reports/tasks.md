# Tasks: APRS Position Reports API

**Input**: Design documents from `/specs/001-aprs-position-reports/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/location-api.md, quickstart.md
**Note**: No formal spec.md exists. User stories derived from plan.md summary.

**Tests**: Tests ARE included per constitution (Testing Standards principle) and plan.md section II.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `haminfo/` package at repository root, `tests/` at repository root
- Paths reference the actual project structure per plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project structure needed. This feature extends existing files. Setup verifies prerequisites.

- [x] T001 Verify existing `aprs_packet` table model has all required fields for location queries in haminfo/db/models/aprs_packet.py (latitude, longitude, location, altitude, course, speed, symbol, symbol_table, from_call, to_call, path, comment, timestamp, received_at, packet_type)
- [x] T002 [P] Verify existing indexes on `aprs_packet` table support the DISTINCT ON query pattern (from_call, timestamp, packet_type) by reviewing haminfo/db/models/aprs_packet.py index definitions

**Checkpoint**: Prerequisites verified, existing schema confirmed sufficient.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core query layer and response formatting shared by ALL user story endpoints.

**CRITICAL**: No API endpoint work can begin until this phase is complete.

- [x] T003 Add `find_latest_positions_by_callsigns(session, callsigns)` function to haminfo/db/db.py that uses DISTINCT ON to query the most recent position-bearing packet per callsign from the `aprs_packet` table. Must import APRSPacket model. Must handle case-insensitive callsign matching (uppercase). Must filter for packets where latitude and longitude are not null. Must return query results with all fields needed by both API response formats. Reference: data-model.md query pattern.
- [x] T004 Add `find_latest_position_by_callsign(session, callsign)` convenience wrapper in haminfo/db/db.py that calls `find_latest_positions_by_callsigns()` with a single callsign. Return a single APRSPacket or None.
- [x] T005 [P] Add `validate_callsigns(callsigns_str)` input validation function in haminfo/flask.py that parses a comma-separated callsign string, uppercases all values, validates max 20 callsigns, validates non-empty, and returns a list of cleaned callsign strings or raises ValueError with descriptive message. Follow the existing `validate_lat_lon()` pattern (haminfo/flask.py lines 89-125).
- [x] T006 [P] Add `aprs_packet_to_aprsfi_entry(packet)` response formatter function in haminfo/flask.py that converts an APRSPacket model instance to the aprs.fi-compatible dict format. Must map: from_call->name/srccall (uppercase), packet_type->type (position->"l", object->"o", item->"i", default->"l"), timestamp->time (Unix epoch string), received_at->lasttime (Unix epoch string), latitude->lat (string), longitude->lng (string), altitude->altitude (string, default "0"), course->course (string, default "0"), speed->speed (string, default "0"), symbol_table+symbol->symbol (concat), to_call->dstcall (uppercase), comment->comment (default ""), path->path (default ""). Reference: contracts/location-api.md field table and research.md section 2.
- [x] T007 [P] Add `aprs_packet_to_native_entry(packet)` response formatter function in haminfo/flask.py that converts an APRSPacket model instance to the haminfo native JSON format dict. Must include: callsign (from_call uppercase), latitude (float), longitude (float), altitude (float), course (int), speed (float), symbol (symbol_table+symbol), to_call (uppercase), comment, path, timestamp (ISO 8601 string), received_at (ISO 8601 string), packet_type. Reference: contracts/location-api.md Endpoint 2 response.
- [x] T008 [P] Write unit tests for `find_latest_positions_by_callsigns()` and `find_latest_position_by_callsign()` in tests/test_aprs_position_query.py. Test cases: single callsign found, single callsign not found, multiple callsigns (some found some not), case-insensitive matching, returns most recent position when multiple packets exist for same callsign, only returns packets with non-null lat/lon. Use existing conftest.py fixtures (db_session, sample_aprs_packet).
- [x] T009 [P] Write unit tests for `validate_callsigns()`, `aprs_packet_to_aprsfi_entry()`, and `aprs_packet_to_native_entry()` in tests/test_location_api.py. Test cases for validate: valid single, valid multiple, empty string, >20 callsigns, case normalization. Test cases for formatters: all fields present, missing optional fields (altitude, course, speed default to "0"/"0.0"), None comment/path default to empty string, timestamp conversion to Unix epoch string and ISO 8601.

**Checkpoint**: Foundation ready - query layer and formatters tested. API endpoints can now be built.

---

## Phase 3: User Story 1 - aprs.fi-Compatible Location API (Priority: P1) MVP

**Goal**: Expose a `/api/get?what=loc&name=CALLSIGN` endpoint that returns location data in the exact aprs.fi JSON format, enabling the `aprsd-locationdata-plugin` and `aprsd-location-plugin` to use haminfo as their data source.

**Independent Test**: `curl "http://localhost:8080/api/get?what=loc&apikey=KEY&format=json&name=TESTCALL"` returns aprs.fi-compatible JSON with the correct callsign position data.

### Tests for User Story 1

- [x] T010 [P] [US1] Write contract tests for aprs.fi response format in tests/test_aprsfi_compat.py. Verify: top-level keys match (command, result, what, found, entries), entry field names match aprs.fi schema exactly, all values are strings (per aprs.fi convention), found count matches entries length, error response format (result: "fail", description field), not-found response (result: "ok", found: 0, entries: []).

### Implementation for User Story 1

- [x] T011 [US1] Add `require_appkey_param` decorator or inline auth check in haminfo/flask.py that validates the `apikey` query parameter (in addition to the existing `require_appkey` decorator which checks the `X-Api-Key` header). Must use the same `CONF.web.api_key` validation. This enables the aprs.fi-compatible endpoint to accept auth via query param as APRSD plugins expect.
- [x] T012 [US1] Add `aprsfi_location()` method to `HaminfoFlask` class in haminfo/flask.py that handles `GET /api/get`. Must: validate `apikey` query param, validate `what` param equals "loc" (return fail otherwise), validate `name` param exists (return fail otherwise), validate `format` param is "json" or absent (return fail otherwise), parse callsigns via `validate_callsigns()`, query via `find_latest_positions_by_callsigns()`, format each result via `aprs_packet_to_aprsfi_entry()`, return aprs.fi JSON envelope: `{"command": "get", "result": "ok", "what": "loc", "found": N, "entries": [...]}`. All errors return HTTP 200 with `{"command": "get", "result": "fail", "description": "..."}`. Reference: contracts/location-api.md Endpoint 1.
- [x] T013 [US1] Register the `/api/get` route in `create_app()` function in haminfo/flask.py (around line 555) mapping to `server.aprsfi_location` with `methods=['GET']`.
- [x] T014 [US1] Write integration test for the `/api/get` endpoint in tests/test_aprsfi_compat.py. Test with Flask test client: valid single callsign query, valid multi-callsign query, missing name param, missing apikey param, invalid what param, callsign not found (empty entries), verify all response field types are strings per aprs.fi contract.

**Checkpoint**: At this point, the aprs.fi-compatible API is functional. APRSD plugins can be pointed at haminfo.

---

## Phase 4: User Story 2 - Native Haminfo Location API (Priority: P2)

**Goal**: Expose a `/api/v1/location?callsign=CALLSIGN` endpoint using haminfo's standard `data`/`error`/`meta` JSON response format with `X-Api-Key` header auth.

**Independent Test**: `curl -H "X-Api-Key: KEY" "http://localhost:8080/api/v1/location?callsign=TESTCALL"` returns native haminfo JSON with typed fields (floats, ints, ISO timestamps).

### Tests for User Story 2

- [x] T015 [P] [US2] Write integration tests for `/api/v1/location` endpoint in tests/test_location_api.py (append to existing file). Test with Flask test client: valid single callsign, valid multi-callsign, missing callsign param returns 400 with error JSON, missing API key returns 401, callsign not found returns 200 with empty data array, response uses data/error/meta structure, field types are correct (latitude is float not string, timestamp is ISO 8601).

### Implementation for User Story 2

- [x] T016 [US2] Add `location()` method to `HaminfoFlask` class in haminfo/flask.py that handles `GET /api/v1/location`. Must: use `@require_appkey` decorator for `X-Api-Key` header auth, validate `callsign` query param via `validate_callsigns()`, query via `find_latest_positions_by_callsigns()`, format each result via `aprs_packet_to_native_entry()`, return JSON envelope: `{"data": [...], "meta": {"found": N, "requested": [...]}, "error": null}`. Validation errors return 400: `{"data": null, "meta": null, "error": {"code": "INVALID_PARAM", "message": "..."}}`. Auth errors return 401: `{"data": null, "meta": null, "error": {"code": "UNAUTHORIZED", "message": "..."}}`. Reference: contracts/location-api.md Endpoint 2.
- [x] T017 [US2] Register the `/api/v1/location` route in `create_app()` function in haminfo/flask.py mapping to `server.location` with `methods=['GET']`.

**Checkpoint**: Both API endpoints are functional and independently testable.

---

## Phase 5: User Story 3 - Data Retention & Stats (Priority: P3)

**Goal**: Add APRS packet cleanup to prevent unbounded table growth, and enhance the `/stats` endpoint with APRS packet statistics.

**Independent Test**: `haminfo db clean-aprs-packets --days 7` removes old packets; `GET /stats` returns APRS packet counts.

### Tests for User Story 3

- [x] T018 [P] [US3] Write unit tests for `clean_aprs_packets()` and `get_aprs_packet_stats()` in tests/test_aprs_position_query.py (append to existing file). Test cases for cleanup: deletes packets older than N days, keeps packets newer than N days, default 30-day retention, custom days parameter, empty table. Test cases for stats: returns correct total/position/weather/message counts, returns unique callsign count, last_24h counts recent only, empty table returns zeros, unknown packet types counted as other.

### Implementation for User Story 3

- [x] T019 [US3] Add `clean_aprs_packets(session, days=30)` function to haminfo/db/db.py that deletes APRS packets with `received_at` older than the specified number of days. Follow the existing `clean_weather_reports()` pattern (haminfo/db/db.py lines 407-413). Must import timedelta if not already imported.
- [x] T020 [US3] Add `get_aprs_packet_stats(session)` function to haminfo/db/db.py that returns a dict with: total packet count, count per packet_type (position, weather, message, etc.), unique callsign count (COUNT DISTINCT from_call), last 24h packet count. Use efficient COUNT queries.
- [x] T021 [US3] Add `clean_aprs_packets` CLI command to haminfo/cmds/db.py under the `db` group. Must accept `--days` option (default 30, type int). Follow the existing `clean_wx_reports` command pattern (haminfo/cmds/db.py lines 94-105). Must call `haminfo_db.clean_aprs_packets(session, days)`.
- [x] T022 [US3] Update the `stats()` method in `HaminfoFlask` class in haminfo/flask.py to include APRS packet statistics in the response. Call `get_aprs_packet_stats(session)` and add the result under an `aprs_packets` key. Reference: contracts/location-api.md Endpoint 3 response format.

**Checkpoint**: Data retention is operational and stats endpoint includes APRS packet data.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [x] T023 [P] Add caching to `find_latest_positions_by_callsigns()` in haminfo/db/db.py using the existing dogpile.cache infrastructure. Cache per-callsign results for 60 seconds. Follow the existing `FromCache('default')` pattern used in other query functions (e.g., `find_requests()` at haminfo/db/db.py line 382).
- [x] T024 [P] Add response time logging to the `/api/get` and `/api/v1/location` endpoint methods in haminfo/flask.py. Log request callsigns, result count, and elapsed time in milliseconds. Use the existing `LOG` logger.
- [x] T025 [P] Add docstrings and type hints to all new functions in haminfo/db/db.py and haminfo/flask.py per constitution Code Quality principle. Verify with `ruff check haminfo/db/db.py haminfo/flask.py`.
- [x] T026 Run `ruff check .` to verify all new code passes linting with zero errors. Fix any violations.
- [x] T027 Run `pytest` to verify all tests pass (212 tests). Fix any failures.
- [ ] T028 Run quickstart.md validation: verify the documented curl commands work against the running API.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verification only
- **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 - Can start immediately after foundation
- **US2 (Phase 4)**: Depends on Phase 2 - Can run in parallel with US1 (different methods/routes)
- **US3 (Phase 5)**: Depends on Phase 2 (for DB functions) - Can run in parallel with US1/US2
- **Polish (Phase 6)**: Depends on all user story phases being complete

### User Story Dependencies

- **US1 (P1)**: Core MVP. Uses foundational query layer and aprs.fi formatter. No dependency on other stories.
- **US2 (P2)**: Uses foundational query layer and native formatter. No dependency on US1 (different endpoint method and route).
- **US3 (P3)**: Independent DB functions and CLI. No dependency on US1 or US2. Stats enhancement touches `/stats` method (different from US1/US2 endpoints).

### Within Each Phase

- T003 must complete before T004 (T004 wraps T003)
- T005, T006, T007, T008, T009 can all run in parallel (different files/functions)
- T011 must complete before T012 (auth check used by endpoint)
- T012 must complete before T013 (route needs method to exist)
- T019 must complete before T021 (CLI calls DB function)
- T020 must complete before T022 (stats endpoint calls DB function)

### Parallel Opportunities

- All [P] tasks within Phase 2 (T005, T006, T007, T008, T009) can run in parallel
- US1, US2, and US3 can run in parallel after Phase 2 completes
- All [P] tasks within Phase 6 (T023, T024, T025) can run in parallel

---

## Parallel Example: Phase 2 Foundation

```bash
# Launch all independent foundation tasks together:
Task: "Add validate_callsigns() in haminfo/flask.py"              # T005
Task: "Add aprs_packet_to_aprsfi_entry() in haminfo/flask.py"     # T006
Task: "Add aprs_packet_to_native_entry() in haminfo/flask.py"     # T007
Task: "Write unit tests for DB queries in tests/test_aprs_position_query.py"  # T008
Task: "Write unit tests for formatters in tests/test_location_api.py"         # T009
```

## Parallel Example: User Stories (after Phase 2)

```bash
# Launch all three user stories in parallel (different files/methods):
Task: "US1 - aprs.fi compat endpoint in haminfo/flask.py"
Task: "US2 - Native location endpoint in haminfo/flask.py"
Task: "US3 - Cleanup + stats in haminfo/db/db.py and haminfo/cmds/db.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verification)
2. Complete Phase 2: Foundational (query layer + formatters + tests)
3. Complete Phase 3: User Story 1 (aprs.fi-compatible endpoint)
4. **STOP and VALIDATE**: Test with curl against running API, verify APRSD plugin compatibility
5. Deploy if ready - APRSD plugins can now use haminfo

### Incremental Delivery

1. Phase 1 + Phase 2 -> Foundation ready
2. Add US1 -> aprs.fi compat API works -> Deploy (MVP!)
3. Add US2 -> Native API works -> Deploy
4. Add US3 -> Cleanup + stats -> Deploy
5. Phase 6 -> Polish (caching, logging, linting) -> Final deploy

### Parallel Execution

With capacity for parallel work:

1. Complete Phase 1 + Phase 2 together
2. Once Phase 2 is done:
   - Stream A: US1 (aprs.fi compat)
   - Stream B: US2 (native API)
   - Stream C: US3 (cleanup + stats)
3. All stories complete and Phase 6 polish

---

## Notes

- [P] tasks = different files or different functions with no dependencies
- [Story] label maps task to specific user story for traceability
- US1 is the critical MVP - enables APRSD plugin compatibility
- US2 and US3 add value but are not required for the core use case
- No schema changes needed - all work is on existing `aprs_packet` table
- Tests use SQLite in-memory (conftest.py) for unit tests; PostGIS features need separate integration tests
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
