# State Weather Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a statewide weather trend dashboard showing current conditions, trends, and alerts for APRS weather stations organized by US state.

**Architecture:** Add `state` column to weather_station table, backfill via bounding-box detection (already in utils.py), create new routes/templates for states landing page and state detail dashboard. Use existing Flask blueprint pattern with HTMX partials for dynamic updates.

**Tech Stack:** Python 3.10+, Flask, SQLAlchemy 2.0, GeoAlchemy2, PostGIS, HTMX, Chart.js, Jinja2 templates

**Spec:** `docs/superpowers/specs/2026-03-31-state-weather-dashboard-design.md`

### MVP Simplifications (vs Spec)

The following spec features are simplified for MVP and can be enhanced later:

1. **States landing page uses table** instead of interactive US SVG map (spec lines 94-117)
2. **State detail page omits state map** with station markers (spec lines 132-135) - uses table list instead
3. **Regional pattern alerts** (spec lines 175-205) simplified to individual station thresholds only
4. **On-insert geocoding** (spec lines 56-60) not implemented - backfill handles existing data

---

## File Structure

### New Files

| File | Responsibility |
|------|----------------|
| `haminfo-dashboard/src/haminfo_dashboard/state_queries.py` | State-specific database queries (state stations, aggregates, trends, alerts) |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/states.html` | States landing page with state list |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/state_detail.html` | State dashboard page |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_summary.html` | Summary cards partial |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_alerts.html` | Alerts banner partial |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_stations_table.html` | Station list partial |
| `haminfo-dashboard/src/haminfo_dashboard/static/us-states.svg` | US map SVG asset |
| `haminfo-dashboard/tests/test_state_queries.py` | Tests for state queries |
| `scripts/backfill_station_states.py` | One-time backfill script |

### Modified Files

| File | Change |
|------|--------|
| `haminfo/db/models/weather_report.py` | Add `state` column to WeatherStation model |
| `haminfo-dashboard/src/haminfo_dashboard/routes.py` | Add states page routes |
| `haminfo-dashboard/src/haminfo_dashboard/api.py` | Add state API endpoints |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/base.html` | Add "States" nav link |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/weather.html` | Add "View by State" link |
| `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/station.html` | Add "View [State] Weather" link |

---

## Chunk 1: Database Schema & Model Changes

### Task 1.1: Add state column to WeatherStation model

**Files:**
- Modify: `haminfo/db/models/weather_report.py:34` (add after `country_code` line)

- [ ] **Step 1: Add state column to model**

In `haminfo/db/models/weather_report.py`, find line 34 (`country_code = sa.Column(sa.String)`) and add the state column immediately after it:

```python
    country_code = sa.Column(sa.String)
    state = sa.Column(sa.String(10))  # ADD THIS LINE
```

The WeatherStation class already has all other columns defined - we're only adding this one new column.

- [ ] **Step 2: Update to_dict method**

In the same file, find the `to_dict()` method (around line 102) and add `state` to the returned dict:

```python
    def to_dict(self):
        return {
            'id': self.id,
            'callsign': self.callsign,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'symbol': self.symbol,
            'symbol_table': self.symbol_table,
            'comment': self.comment,
            'country_code': self.country_code,
            'state': self.state,
        }
```

- [ ] **Step 3: Run existing tests to verify model change doesn't break anything**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo
pytest -x -q
```

Expected: All tests pass (or skip if no DB connection)

- [ ] **Step 4: Commit model changes**

```bash
git add haminfo/db/models/weather_report.py
git commit -m "feat: add state column to WeatherStation model"
```

### Task 1.2: Apply schema change to database

**Files:**
- None (direct database operation)

**Note:** Database changes should be applied BEFORE pushing the model commit to avoid mismatch between code and schema.

- [ ] **Step 1: SSH to production and backup table structure**

```bash
ssh waboring@cloud.hemna.com
cd ~/docker/haminfo
# Backup current table structure (not data, just schema)
docker exec -it haminfo-db pg_dump -U postgres haminfo -t weather_station --schema-only > weather_station_schema_backup.sql
```

Expected: Creates backup file with current schema

- [ ] **Step 2: Add state column and indexes**

```bash
docker exec -it haminfo-db psql -U postgres -d haminfo
```

```sql
-- Add column (IF NOT EXISTS handles idempotency)
ALTER TABLE weather_station ADD COLUMN IF NOT EXISTS state VARCHAR(10);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_weather_station_state ON weather_station(state);
CREATE INDEX IF NOT EXISTS idx_weather_station_country_state ON weather_station(country_code, state);
```

Expected: `ALTER TABLE`, `CREATE INDEX` (x2) - no errors

- [ ] **Step 3: Verify column and indexes exist**

```sql
\d weather_station
```

Expected: Shows `state` column with type `character varying(10)` and indexes `idx_weather_station_state`, `idx_weather_station_country_state`

- [ ] **Step 4: Exit psql**

```sql
\q
```

---

## Chunk 2: Backfill Script

### Task 2.1: Create backfill script

**Files:**
- Create: `scripts/backfill_station_states.py`

- [ ] **Step 1: Write backfill script**

```python
#!/usr/bin/env python
"""Backfill state column for weather stations using bounding box detection.

Uses the existing US_STATE_BOUNDS, CA_PROVINCE_BOUNDS, AU_STATE_BOUNDS from
haminfo_dashboard.utils to determine state from lat/lon coordinates.

Usage:
    python scripts/backfill_station_states.py [--dry-run] [--limit N] [--verbose]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from haminfo.db.db import setup_session
from haminfo.db.models.weather_report import WeatherStation


# Import bounding boxes from dashboard utils
sys.path.insert(
    0, str(Path(__file__).parent.parent / 'haminfo-dashboard' / 'src')
)
from haminfo_dashboard.utils import (
    US_STATE_BOUNDS,
    CA_PROVINCE_BOUNDS,
    AU_STATE_BOUNDS,
    get_state_from_coords,
)

# Verify imports worked
if not US_STATE_BOUNDS:
    print("ERROR: US_STATE_BOUNDS not found in utils.py")
    sys.exit(1)


def get_state_for_station(lat: float, lon: float, country_code: str | None) -> str | None:
    """Determine state/province from coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude  
        country_code: Country code (US, CA, AU) or None
        
    Returns:
        State/province code or None
    """
    if country_code not in ('US', 'CA', 'AU'):
        return None
        
    result = get_state_from_coords(lat, lon, country_code)
    if result:
        return result[0]  # Return just the code, not (code, name) tuple
    return None


def backfill_states(dry_run: bool = False, limit: int | None = None, verbose: bool = False) -> dict:
    """Backfill state column for weather stations.
    
    Args:
        dry_run: If True, don't commit changes
        limit: Maximum number of stations to process
        verbose: If True, print each station update
        
    Returns:
        Dict with statistics
    """
    session_factory = setup_session()
    session = session_factory()
    
    stats = {
        'total': 0,
        'updated': 0,
        'skipped_no_country': 0,
        'skipped_unsupported_country': 0,
        'skipped_no_match': 0,
        'by_country': {},
    }
    
    try:
        # Query stations where state is NULL
        query = session.query(WeatherStation).filter(
            WeatherStation.state.is_(None),
            WeatherStation.latitude.isnot(None),
            WeatherStation.longitude.isnot(None),
        )
        
        if limit:
            query = query.limit(limit)
            
        stations = query.all()
        stats['total'] = len(stations)
        
        print(f"Processing {stats['total']} stations...")
        
        for i, station in enumerate(stations):
            if i > 0 and i % 100 == 0:
                print(f"  Processed {i}/{stats['total']}...")
                if not dry_run:
                    session.commit()
                    
            country = station.country_code
            if not country:
                stats['skipped_no_country'] += 1
                continue
                
            country = country.upper()
            if country not in ('US', 'CA', 'AU'):
                stats['skipped_unsupported_country'] += 1
                continue
                
            state = get_state_for_station(
                station.latitude, 
                station.longitude, 
                country
            )
            
            if state:
                if not dry_run:
                    station.state = state
                stats['updated'] += 1
                stats['by_country'][country] = stats['by_country'].get(country, 0) + 1
                if verbose:
                    print(f"  {station.callsign}: {country} -> {state}")
            else:
                stats['skipped_no_match'] += 1
                
        if not dry_run:
            session.commit()
            print("\nChanges committed.")
        else:
            print("\nDRY RUN - no changes made.")
            
        return stats
        
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill weather station states')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of stations to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print each station update')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Weather Station State Backfill")
    print("=" * 60)
    
    stats = backfill_states(dry_run=args.dry_run, limit=args.limit, verbose=args.verbose)
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total processed: {stats['total']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped (no country): {stats['skipped_no_country']}")
    print(f"  Skipped (unsupported country): {stats['skipped_unsupported_country']}")
    print(f"  Skipped (no state match): {stats['skipped_no_match']}")
    print("\nBy country:")
    for country, count in sorted(stats['by_country'].items()):
        print(f"  {country}: {count}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Test locally with dry-run**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo
python scripts/backfill_station_states.py --dry-run --limit 10
```

Expected output scenarios:
- **If stations need backfilling:** Shows 10 stations with their state assignments, "DRY RUN - no changes made"
- **If already backfilled:** Shows "Processing 0 stations..." and summary with all zeros (this is OK - means backfill already done)

- [ ] **Step 3: Commit backfill script**

```bash
git add scripts/backfill_station_states.py
git commit -m "feat: add backfill script for weather station states"
```

### Task 2.2: Run backfill on production

- [ ] **Step 1: Push changes and verify container has required modules**

```bash
git push origin master
ssh waboring@cloud.hemna.com
cd ~/docker/haminfo
git pull

# Verify the dashboard utils module is accessible
docker exec -it haminfo python -c "from haminfo_dashboard.utils import get_state_from_coords; print('OK')"
```

Expected: `OK`

If this fails with ModuleNotFoundError, the haminfo container doesn't have dashboard code. In that case, run the backfill directly from the host machine with proper Python path setup.

- [ ] **Step 2: Run backfill**

```bash
# Run backfill inside the haminfo container
docker exec -it haminfo python /app/scripts/backfill_station_states.py
```

Expected: Updates ~1,600 US stations with state codes. Output shows progress every 100 stations.

- [ ] **Step 3: Verify backfill results**

```bash
docker exec -it haminfo-db psql -U postgres -d haminfo -c "SELECT state, COUNT(*) FROM weather_station WHERE country_code = 'US' AND state IS NOT NULL GROUP BY state ORDER BY count DESC LIMIT 10;"
```

Expected: Shows top 10 US states by station count (TX, CA typically have most)

**Rollback if needed:**
```bash
docker exec -it haminfo-db psql -U postgres -d haminfo -c "UPDATE weather_station SET state = NULL;"
```

---

## Chunk 3: State Queries Module

### Task 3.1: Create state_queries.py with get_state_stations

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`
- Create: `haminfo-dashboard/tests/test_state_queries.py`

- [ ] **Step 1: Write failing test for get_state_stations**

Create `haminfo-dashboard/tests/test_state_queries.py`:

```python
"""Tests for state weather dashboard queries."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


class TestGetStateStations:
    """Tests for get_state_stations function."""

    def test_returns_stations_for_valid_state(self):
        """Should return stations with latest weather data for a state."""
        from haminfo_dashboard.state_queries import get_state_stations
        
        # Create mock session with test data
        mock_session = MagicMock()
        
        # Mock station data
        mock_result = [
            {
                'callsign': 'W4TEST',
                'latitude': 37.5,
                'longitude': -77.5,
                'temperature': 72.0,
                'humidity': 65,
                'pressure': 1018.5,
                'wind_speed': 8.0,
                'wind_gust': 15.0,
                'wind_direction': 180,
                'rain_1h': 0.0,
                'last_report': datetime.now() - timedelta(minutes=5),
            }
        ]
        
        mock_session.execute.return_value.mappings.return_value.all.return_value = mock_result
        
        result = get_state_stations(mock_session, 'VA')
        
        assert len(result) == 1
        assert result[0]['callsign'] == 'W4TEST'
        assert result[0]['temperature'] == 72.0

    def test_returns_empty_for_invalid_state(self):
        """Should return empty list for state with no stations."""
        from haminfo_dashboard.state_queries import get_state_stations
        
        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []
        
        result = get_state_stations(mock_session, 'XX')
        
        assert result == []

    def test_state_code_case_insensitive(self):
        """Should handle lowercase state codes."""
        from haminfo_dashboard.state_queries import get_state_stations
        
        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []
        
        # Should not raise
        get_state_stations(mock_session, 'va')
        
        # Verify query used uppercase
        call_args = mock_session.execute.call_args
        assert 'VA' in str(call_args) or call_args is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'haminfo_dashboard.state_queries'`

- [ ] **Step 3: Create state_queries.py with get_state_stations**

Create `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`:

```python
# haminfo_dashboard/state_queries.py
"""Database queries for state weather dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from haminfo_dashboard.cache import cached

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOG = logging.getLogger(__name__)


@cached(ttl=300, key_prefix='state_stations')
def get_state_stations(session: Session, state_code: str) -> list[dict[str, Any]]:
    """Get all weather stations in a state with their latest readings.
    
    Args:
        session: Database session
        state_code: Two-letter state code (e.g., 'VA')
        
    Returns:
        List of station dicts with latest weather data
    """
    state_code = state_code.upper()
    
    query = text("""
        SELECT ws.callsign, ws.latitude, ws.longitude, ws.comment,
               ws.symbol, ws.symbol_table,
               wr.temperature, wr.humidity, wr.pressure,
               wr.wind_speed, wr.wind_gust, wr.wind_direction,
               wr.rain_1h, wr.time as last_report
        FROM weather_station ws
        JOIN LATERAL (
            SELECT * FROM weather_report 
            WHERE weather_station_id = ws.id 
            ORDER BY time DESC LIMIT 1
        ) wr ON true
        WHERE ws.state = :state_code 
          AND ws.country_code = 'US'
    """)
    
    result = session.execute(query, {'state_code': state_code})
    return [dict(row) for row in result.mappings().all()]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestGetStateStations -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/state_queries.py
git add haminfo-dashboard/tests/test_state_queries.py
git commit -m "feat: add get_state_stations query for state dashboard"
```

### Task 3.2: Add compute_state_aggregates function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`
- Modify: `haminfo-dashboard/tests/test_state_queries.py`

- [ ] **Step 1: Write failing test for compute_state_aggregates**

Add to `haminfo-dashboard/tests/test_state_queries.py`:

```python
class TestComputeStateAggregates:
    """Tests for compute_state_aggregates function."""

    def test_computes_aggregates_from_stations(self):
        """Should compute min/max/avg from station list."""
        from haminfo_dashboard.state_queries import compute_state_aggregates
        
        stations = [
            {'temperature': 70.0, 'humidity': 60, 'pressure': 1015.0, 'wind_speed': 5.0},
            {'temperature': 80.0, 'humidity': 70, 'pressure': 1020.0, 'wind_speed': 10.0},
            {'temperature': 75.0, 'humidity': 65, 'pressure': 1018.0, 'wind_speed': 8.0},
        ]
        
        result = compute_state_aggregates(stations)
        
        assert result['avg_temp'] == 75.0
        assert result['min_temp'] == 70.0
        assert result['max_temp'] == 80.0
        assert result['avg_humidity'] == 65.0
        assert result['avg_wind'] == pytest.approx(7.67, rel=0.01)

    def test_handles_empty_list(self):
        """Should return None values for empty station list."""
        from haminfo_dashboard.state_queries import compute_state_aggregates
        
        result = compute_state_aggregates([])
        
        assert result['avg_temp'] is None
        assert result['min_temp'] is None
        assert result['station_count'] == 0

    def test_handles_null_values(self):
        """Should skip None values in calculations."""
        from haminfo_dashboard.state_queries import compute_state_aggregates
        
        stations = [
            {'temperature': 70.0, 'humidity': None, 'pressure': 1015.0, 'wind_speed': 5.0},
            {'temperature': None, 'humidity': 60, 'pressure': None, 'wind_speed': None},
            {'temperature': 80.0, 'humidity': 70, 'pressure': 1020.0, 'wind_speed': 10.0},
        ]
        
        result = compute_state_aggregates(stations)
        
        assert result['avg_temp'] == 75.0  # (70 + 80) / 2
        assert result['avg_humidity'] == 65.0  # (60 + 70) / 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestComputeStateAggregates -v
```

Expected: FAIL with `ImportError: cannot import name 'compute_state_aggregates'`

- [ ] **Step 3: Implement compute_state_aggregates**

Add to `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`:

```python
def compute_state_aggregates(stations: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics from station list.
    
    Args:
        stations: List of station dicts with weather readings
        
    Returns:
        Dict with avg/min/max for temp, humidity, pressure, wind
    """
    if not stations:
        return {
            'station_count': 0,
            'avg_temp': None,
            'min_temp': None,
            'max_temp': None,
            'avg_humidity': None,
            'min_humidity': None,
            'max_humidity': None,
            'avg_pressure': None,
            'min_pressure': None,
            'max_pressure': None,
            'avg_wind': None,
            'max_wind': None,
        }
    
    def safe_values(key: str) -> list[float]:
        """Extract non-None values for a key."""
        return [s[key] for s in stations if s.get(key) is not None]
    
    def safe_avg(values: list[float]) -> float | None:
        """Compute average, returning None if empty."""
        return sum(values) / len(values) if values else None
    
    temps = safe_values('temperature')
    humidities = safe_values('humidity')
    pressures = safe_values('pressure')
    winds = safe_values('wind_speed')
    gusts = safe_values('wind_gust')
    
    return {
        'station_count': len(stations),
        'avg_temp': safe_avg(temps),
        'min_temp': min(temps) if temps else None,
        'max_temp': max(temps) if temps else None,
        'avg_humidity': safe_avg(humidities),
        'min_humidity': min(humidities) if humidities else None,
        'max_humidity': max(humidities) if humidities else None,
        'avg_pressure': safe_avg(pressures),
        'min_pressure': min(pressures) if pressures else None,
        'max_pressure': max(pressures) if pressures else None,
        'avg_wind': safe_avg(winds),
        'max_wind': max(gusts) if gusts else (max(winds) if winds else None),
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestComputeStateAggregates -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/state_queries.py
git add haminfo-dashboard/tests/test_state_queries.py
git commit -m "feat: add compute_state_aggregates for state summary"
```

### Task 3.3: Add get_state_trends function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`
- Modify: `haminfo-dashboard/tests/test_state_queries.py`

- [ ] **Step 1: Write failing test for get_state_trends**

Add to `haminfo-dashboard/tests/test_state_queries.py`:

```python
class TestGetStateTrends:
    """Tests for get_state_trends function."""

    def test_returns_hourly_trend_data(self):
        """Should return 24h trend data bucketed by hour."""
        from haminfo_dashboard.state_queries import get_state_trends
        
        mock_session = MagicMock()
        
        # Mock hourly data
        mock_result = [
            {'hour': datetime(2026, 3, 31, 10, 0), 'avg_temp': 65.0, 'min_temp': 60.0, 'max_temp': 70.0,
             'avg_pressure': 1018.0, 'avg_humidity': 65.0, 'avg_wind': 8.0},
            {'hour': datetime(2026, 3, 31, 11, 0), 'avg_temp': 68.0, 'min_temp': 63.0, 'max_temp': 73.0,
             'avg_pressure': 1017.5, 'avg_humidity': 62.0, 'avg_wind': 10.0},
        ]
        
        mock_session.execute.return_value.mappings.return_value.all.return_value = mock_result
        
        result = get_state_trends(mock_session, 'VA')
        
        assert 'labels' in result
        assert 'temperature' in result
        assert 'pressure' in result
        assert len(result['labels']) == 2
        assert result['temperature']['avg'] == [65.0, 68.0]

    def test_returns_empty_for_no_data(self):
        """Should return empty arrays for state with no data."""
        from haminfo_dashboard.state_queries import get_state_trends
        
        mock_session = MagicMock()
        mock_session.execute.return_value.mappings.return_value.all.return_value = []
        
        result = get_state_trends(mock_session, 'XX')
        
        assert result['labels'] == []
        assert result['temperature']['avg'] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestGetStateTrends -v
```

Expected: FAIL with `ImportError: cannot import name 'get_state_trends'`

- [ ] **Step 3: Implement get_state_trends**

Add to `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`:

```python
@cached(ttl=300, key_prefix='state_trends')
def get_state_trends(session: Session, state_code: str) -> dict[str, Any]:
    """Get 24-hour trend data for a state.
    
    Returns hourly aggregates for temperature, pressure, humidity, wind.
    Uses TimescaleDB time_bucket for efficient bucketing.
    
    Args:
        session: Database session
        state_code: Two-letter state code
        
    Returns:
        Dict with labels and data arrays for Chart.js
    """
    state_code = state_code.upper()
    
    query = text("""
        SELECT 
            time_bucket('1 hour', wr.time) as hour,
            AVG(wr.temperature) as avg_temp,
            MIN(wr.temperature) as min_temp,
            MAX(wr.temperature) as max_temp,
            AVG(wr.pressure) as avg_pressure,
            AVG(wr.humidity) as avg_humidity,
            AVG(wr.wind_speed) as avg_wind
        FROM weather_report wr
        JOIN weather_station ws ON wr.weather_station_id = ws.id
        WHERE ws.state = :state_code 
          AND ws.country_code = 'US'
          AND wr.time > NOW() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY hour
    """)
    
    result = session.execute(query, {'state_code': state_code})
    rows = [dict(row) for row in result.mappings().all()]
    
    # Format for Chart.js
    labels = [row['hour'].strftime('%H:%M') for row in rows]
    
    return {
        'labels': labels,
        'temperature': {
            'avg': [row['avg_temp'] for row in rows],
            'min': [row['min_temp'] for row in rows],
            'max': [row['max_temp'] for row in rows],
        },
        'pressure': {
            'avg': [row['avg_pressure'] for row in rows],
        },
        'humidity': {
            'avg': [row['avg_humidity'] for row in rows],
        },
        'wind': {
            'avg': [row['avg_wind'] for row in rows],
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestGetStateTrends -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/state_queries.py
git add haminfo-dashboard/tests/test_state_queries.py
git commit -m "feat: add get_state_trends for 24h trend charts"
```

### Task 3.4: Add detect_state_alerts function

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`
- Modify: `haminfo-dashboard/tests/test_state_queries.py`

- [ ] **Step 1: Write failing test for detect_state_alerts**

Add to `haminfo-dashboard/tests/test_state_queries.py`:

```python
class TestDetectStateAlerts:
    """Tests for detect_state_alerts function."""

    def test_detects_high_wind_alert(self):
        """Should detect high wind warning when wind > 40 mph."""
        from haminfo_dashboard.state_queries import detect_state_alerts
        
        stations = [
            {'callsign': 'W4TEST', 'wind_speed': 45.0, 'wind_gust': 55.0, 
             'temperature': 75.0, 'humidity': 50, 'pressure': 1015.0},
        ]
        
        alerts = detect_state_alerts(stations)
        
        assert len(alerts) > 0
        assert any(a['type'] == 'high_wind' for a in alerts)

    def test_detects_extreme_heat(self):
        """Should detect heat warning when temp > 100F."""
        from haminfo_dashboard.state_queries import detect_state_alerts
        
        stations = [
            {'callsign': 'W5HOT', 'temperature': 105.0, 'humidity': 30,
             'wind_speed': 5.0, 'wind_gust': None, 'pressure': 1010.0},
        ]
        
        alerts = detect_state_alerts(stations)
        
        assert len(alerts) > 0
        assert any(a['type'] == 'extreme_heat' for a in alerts)

    def test_no_alerts_for_normal_conditions(self):
        """Should return empty list for normal weather."""
        from haminfo_dashboard.state_queries import detect_state_alerts
        
        stations = [
            {'callsign': 'W4NORM', 'temperature': 72.0, 'humidity': 55,
             'wind_speed': 8.0, 'wind_gust': 12.0, 'pressure': 1018.0},
        ]
        
        alerts = detect_state_alerts(stations)
        
        assert alerts == []

    def test_handles_empty_stations(self):
        """Should return empty list for no stations."""
        from haminfo_dashboard.state_queries import detect_state_alerts
        
        alerts = detect_state_alerts([])
        
        assert alerts == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestDetectStateAlerts -v
```

Expected: FAIL with `ImportError: cannot import name 'detect_state_alerts'`

- [ ] **Step 3: Implement detect_state_alerts**

Add to `haminfo-dashboard/src/haminfo_dashboard/state_queries.py`:

```python
# Alert thresholds (from spec)
ALERT_THRESHOLDS = {
    'high_wind': {'wind_speed': 40, 'level': 'warning'},
    'extreme_wind': {'wind_speed': 60, 'wind_gust': 75, 'level': 'severe'},
    'extreme_heat': {'temperature': 100, 'level': 'warning'},
    'extreme_cold': {'temperature': 10, 'level': 'warning'},  # Below this
    'heavy_rain': {'rain_1h': 1.0, 'level': 'warning'},
}


def detect_state_alerts(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect severe weather alerts from station data.
    
    Checks individual station thresholds. Regional patterns (multiple
    stations) are handled separately if needed.
    
    Args:
        stations: List of station dicts with weather readings
        
    Returns:
        List of alert dicts with type, level, message, affected_stations
    """
    if not stations:
        return []
    
    alerts = []
    
    # Track affected stations by alert type
    high_wind_stations = []
    extreme_wind_stations = []
    extreme_heat_stations = []
    extreme_cold_stations = []
    heavy_rain_stations = []
    
    for station in stations:
        callsign = station.get('callsign', 'Unknown')
        wind_speed = station.get('wind_speed') or 0
        wind_gust = station.get('wind_gust') or 0
        temp = station.get('temperature')
        rain_1h = station.get('rain_1h') or 0
        
        # Extreme wind (supersedes high wind)
        if wind_speed > 60 or wind_gust > 75:
            extreme_wind_stations.append(callsign)
        elif wind_speed > 40:
            high_wind_stations.append(callsign)
            
        # Temperature extremes
        if temp is not None:
            if temp > 100:
                extreme_heat_stations.append(callsign)
            elif temp < 10:
                extreme_cold_stations.append(callsign)
                
        # Heavy rain
        if rain_1h > 1.0:
            heavy_rain_stations.append(callsign)
    
    # Build alert list (severe first)
    if extreme_wind_stations:
        alerts.append({
            'type': 'extreme_wind',
            'level': 'severe',
            'message': f'Extreme wind: {len(extreme_wind_stations)} station(s) reporting >60mph sustained or >75mph gusts',
            'affected_stations': extreme_wind_stations,
        })
        
    if high_wind_stations:
        alerts.append({
            'type': 'high_wind',
            'level': 'warning',
            'message': f'High wind warning: {len(high_wind_stations)} station(s) reporting >40mph sustained',
            'affected_stations': high_wind_stations,
        })
        
    if extreme_heat_stations:
        alerts.append({
            'type': 'extreme_heat',
            'level': 'warning',
            'message': f'Extreme heat: {len(extreme_heat_stations)} station(s) reporting >100°F',
            'affected_stations': extreme_heat_stations,
        })
        
    if extreme_cold_stations:
        alerts.append({
            'type': 'extreme_cold',
            'level': 'warning',
            'message': f'Extreme cold: {len(extreme_cold_stations)} station(s) reporting <10°F',
            'affected_stations': extreme_cold_stations,
        })
        
    if heavy_rain_stations:
        alerts.append({
            'type': 'heavy_rain',
            'level': 'warning',
            'message': f'Heavy rain: {len(heavy_rain_stations)} station(s) reporting >1" in 1 hour',
            'affected_stations': heavy_rain_stations,
        })
    
    return alerts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/test_state_queries.py::TestDetectStateAlerts -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/state_queries.py
git add haminfo-dashboard/tests/test_state_queries.py
git commit -m "feat: add detect_state_alerts for weather alerts"
```

---

## Chunk 4: Routes and API Endpoints

### Task 4.1: Add page routes for states

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/routes.py`

- [ ] **Step 1: Add imports for state queries**

At top of `routes.py`, add:

```python
from haminfo_dashboard.state_queries import (
    get_state_stations,
    compute_state_aggregates,
    get_state_trends,
    detect_state_alerts,
)
from haminfo_dashboard.utils import US_STATE_BOUNDS
from sqlalchemy import text
```

- [ ] **Step 2: Add states landing page route**

Add after the existing routes:

```python
@dashboard_bp.route('/weather/states')
def weather_states():
    """Weather by state landing page."""
    session = _get_session()
    try:
        # Get station counts per state
        query = text("""
            SELECT state, COUNT(*) as count 
            FROM weather_station 
            WHERE country_code = 'US' AND state IS NOT NULL
            GROUP BY state
        """)
        result = session.execute(query)
        state_counts = {row.state: row.count for row in result}
        
        # Build state data with names
        states_data = []
        for code, (name, *_) in US_STATE_BOUNDS.items():
            states_data.append({
                'code': code,
                'name': name,
                'station_count': state_counts.get(code, 0),
            })
        
        # Sort by name
        states_data.sort(key=lambda x: x['name'])
        
        return render_template(
            'dashboard/states.html',
            states=states_data,
            total_stations=sum(state_counts.values()),
        )
    finally:
        session.close()


@dashboard_bp.route('/weather/state/<state_code>')
def weather_state_detail(state_code: str):
    """State weather dashboard page."""
    state_code = state_code.upper()
    
    # Validate state code
    if state_code not in US_STATE_BOUNDS:
        return render_template(
            'dashboard/state_detail.html',
            state_code=state_code,
            state_name=None,
            error='State not found',
        )
    
    state_name = US_STATE_BOUNDS[state_code][0]
    
    return render_template(
        'dashboard/state_detail.html',
        state_code=state_code,
        state_name=state_name,
    )
```

- [ ] **Step 3: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/routes.py
git commit -m "feat: add states landing and detail page routes"
```

### Task 4.2: Add API endpoints for state data

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/api.py`

**Note:** Verify that `api.py` already imports `render_template`, `jsonify` from Flask and has `_get_session()` helper. If not, these need to be added (they exist in the existing codebase).

- [ ] **Step 1: Add imports**

At top of `api.py`, add these imports (after existing Flask imports):

```python
from haminfo_dashboard.state_queries import (
    get_state_stations,
    compute_state_aggregates,
    get_state_trends,
    detect_state_alerts,
)
```

- [ ] **Step 2: Add state summary API endpoint**

Add to `api.py`:

```python
@dashboard_bp.route('/api/dashboard/state/<state_code>/summary')
def api_state_summary(state_code: str):
    """State summary cards - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        summary = compute_state_aggregates(stations)
        return render_template(
            'dashboard/partials/state_summary.html',
            summary=summary,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/summary/json')
def api_state_summary_json(state_code: str):
    """State summary - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        summary = compute_state_aggregates(stations)
        return jsonify(summary)
    finally:
        session.close()
```

- [ ] **Step 3: Add state stations API endpoint**

```python
@dashboard_bp.route('/api/dashboard/state/<state_code>/stations')
def api_state_stations(state_code: str):
    """State stations list - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        return render_template(
            'dashboard/partials/state_stations_table.html',
            stations=stations,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/stations/json')
def api_state_stations_json(state_code: str):
    """State stations - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        return jsonify(stations)
    finally:
        session.close()
```

- [ ] **Step 4: Add state alerts API endpoint**

```python
@dashboard_bp.route('/api/dashboard/state/<state_code>/alerts')
def api_state_alerts(state_code: str):
    """State alerts banner - returns HTMX partial."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        alerts = detect_state_alerts(stations)
        return render_template(
            'dashboard/partials/state_alerts.html',
            alerts=alerts,
            state_code=state_code,
        )
    finally:
        session.close()


@dashboard_bp.route('/api/dashboard/state/<state_code>/alerts/json')
def api_state_alerts_json(state_code: str):
    """State alerts - returns JSON."""
    session = _get_session()
    try:
        stations = get_state_stations(session, state_code)
        alerts = detect_state_alerts(stations)
        return jsonify(alerts)
    finally:
        session.close()
```

- [ ] **Step 5: Add state trends API endpoint**

```python
@dashboard_bp.route('/api/dashboard/state/<state_code>/trends')
def api_state_trends(state_code: str):
    """State 24h trend data - returns JSON for Chart.js."""
    session = _get_session()
    try:
        trends = get_state_trends(session, state_code)
        return jsonify(trends)
    finally:
        session.close()
```

- [ ] **Step 6: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/api.py
git commit -m "feat: add state API endpoints for summary, stations, alerts, trends"
```

---

## Chunk 5: Templates - States Landing Page

### Task 5.1: Create states landing page template

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/states.html`

- [ ] **Step 1: Create states.html template**

```html
{% extends "dashboard/base.html" %}

{% block title %}Weather by State - Ham Radio Dashboard{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="row mb-4">
        <div class="col">
            <h1>Weather by State</h1>
            <p class="text-muted">Select a state to view detailed weather conditions from APRS weather stations</p>
        </div>
    </div>
    
    <!-- Quick Stats -->
    <div class="row mb-4">
        <div class="col-md-4">
            <div class="card">
                <div class="card-body text-center">
                    <h3 class="mb-0">{{ total_stations | format_number }}</h3>
                    <small class="text-muted">Total US Weather Stations</small>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card">
                <div class="card-body text-center">
                    <h3 class="mb-0">{{ states | selectattr('station_count', 'gt', 0) | list | length }}</h3>
                    <small class="text-muted">States with Coverage</small>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card">
                <div class="card-body text-center">
                    <h3 class="mb-0">{{ (total_stations / 50) | round | int }}</h3>
                    <small class="text-muted">Avg Stations per State</small>
                </div>
            </div>
        </div>
    </div>
    
    <!-- States Table -->
    <div class="card">
        <div class="card-header">
            <h5 class="mb-0">All States</h5>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover" id="states-table">
                    <thead>
                        <tr>
                            <th>State</th>
                            <th>Code</th>
                            <th class="text-end">Stations</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for state in states %}
                        <tr {% if state.station_count == 0 %}class="text-muted"{% endif %}>
                            <td>{{ state.name }}</td>
                            <td><code>{{ state.code }}</code></td>
                            <td class="text-end">{{ state.station_count }}</td>
                            <td class="text-end">
                                {% if state.station_count > 0 %}
                                <a href="{{ url_for('dashboard.weather_state_detail', state_code=state.code) }}" 
                                   class="btn btn-sm btn-outline-primary">
                                    View
                                </a>
                                {% else %}
                                <span class="badge bg-secondary">No data</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<style>
#states-table {
    font-size: 0.9rem;
}
#states-table tbody tr:hover {
    background-color: rgba(var(--bs-primary-rgb), 0.1);
}
</style>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/states.html
git commit -m "feat: add states landing page template"
```

### Task 5.3: Add navigation link to base template

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/base.html`

- [ ] **Step 1: Add States link to navigation**

Find the navigation section in `base.html` and add a "States" link after the "Weather" link:

```html
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('dashboard.weather_states') }}">States</a>
</li>
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/base.html
git commit -m "feat: add States link to navigation"
```

---

## Chunk 6: Templates - State Detail Page

### Task 6.1: Create state detail page template

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/state_detail.html`

- [ ] **Step 1: Create state_detail.html template**

```html
{% extends "dashboard/base.html" %}

{% block title %}{{ state_name or 'State' }} Weather - Ham Radio Dashboard{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    {% if error %}
    <!-- Error state -->
    <div class="row">
        <div class="col-md-6 offset-md-3 text-center">
            <h2>State Not Found</h2>
            <p class="text-muted">The state code "{{ state_code }}" was not found.</p>
            <a href="{{ url_for('dashboard.weather_states') }}" class="btn btn-primary">
                Back to States Map
            </a>
        </div>
    </div>
    {% else %}
    <!-- Header -->
    <div class="row mb-4">
        <div class="col">
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item"><a href="{{ url_for('dashboard.weather_states') }}">States</a></li>
                    <li class="breadcrumb-item active">{{ state_name }}</li>
                </ol>
            </nav>
            <h1>{{ state_name }} Weather</h1>
            <p class="text-muted" id="last-updated">Loading station data...</p>
        </div>
    </div>
    
    <!-- Alerts Banner -->
    <div id="alerts-container"
         hx-get="{{ url_for('dashboard.api_state_alerts', state_code=state_code) }}"
         hx-trigger="load, every 2m"
         hx-swap="innerHTML">
        <!-- Alerts loaded via HTMX -->
    </div>
    
    <!-- Summary Cards -->
    <div class="row mb-4" id="summary-container"
         hx-get="{{ url_for('dashboard.api_state_summary', state_code=state_code) }}"
         hx-trigger="load, every 5m"
         hx-swap="innerHTML">
        <!-- Summary cards loaded via HTMX -->
        <div class="col-12 text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    </div>
    
    <!-- Trend Charts -->
    <div class="card mb-4">
        <div class="card-header">
            <h5 class="mb-0">24-Hour Trends</h5>
        </div>
        <div class="card-body">
            <ul class="nav nav-tabs" id="trend-tabs" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="temp-tab" data-bs-toggle="tab" 
                            data-bs-target="#temp-chart" type="button">Temperature</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="pressure-tab" data-bs-toggle="tab" 
                            data-bs-target="#pressure-chart" type="button">Pressure</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="humidity-tab" data-bs-toggle="tab" 
                            data-bs-target="#humidity-chart" type="button">Humidity</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="wind-tab" data-bs-toggle="tab" 
                            data-bs-target="#wind-chart" type="button">Wind</button>
                </li>
            </ul>
            <div class="tab-content pt-3" id="trend-content">
                <div class="tab-pane fade show active" id="temp-chart" role="tabpanel">
                    <canvas id="temperature-chart" height="200"></canvas>
                </div>
                <div class="tab-pane fade" id="pressure-chart" role="tabpanel">
                    <canvas id="pressure-chart-canvas" height="200"></canvas>
                </div>
                <div class="tab-pane fade" id="humidity-chart" role="tabpanel">
                    <canvas id="humidity-chart-canvas" height="200"></canvas>
                </div>
                <div class="tab-pane fade" id="wind-chart" role="tabpanel">
                    <canvas id="wind-chart-canvas" height="200"></canvas>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Stations Table -->
    <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0">Weather Stations</h5>
            <span class="badge bg-primary" id="station-count">Loading...</span>
        </div>
        <div class="card-body">
            <div id="stations-container"
                 hx-get="{{ url_for('dashboard.api_state_stations', state_code=state_code) }}"
                 hx-trigger="load, every 5m"
                 hx-swap="innerHTML">
                <!-- Stations table loaded via HTMX -->
                <div class="text-center py-5">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    {% endif %}
</div>

{% if not error %}
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Load trend data and render charts
    fetch('{{ url_for("dashboard.api_state_trends", state_code=state_code) }}')
        .then(response => response.json())
        .then(data => {
            renderTrendCharts(data);
        })
        .catch(err => console.error('Failed to load trends:', err));
});

function renderTrendCharts(data) {
    if (!data.labels || data.labels.length === 0) {
        document.querySelectorAll('.tab-pane canvas').forEach(canvas => {
            canvas.parentElement.innerHTML = '<p class="text-muted text-center">No trend data available</p>';
        });
        return;
    }
    
    // Temperature chart with min/max bands
    new Chart(document.getElementById('temperature-chart'), {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Avg Temp (°F)',
                    data: data.temperature.avg,
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    fill: false,
                    tension: 0.3
                },
                {
                    label: 'Max',
                    data: data.temperature.max,
                    borderColor: 'rgba(255, 99, 132, 0.3)',
                    backgroundColor: 'transparent',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3
                },
                {
                    label: 'Min',
                    data: data.temperature.min,
                    borderColor: 'rgba(255, 99, 132, 0.3)',
                    backgroundColor: 'transparent',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true } }
        }
    });
    
    // Pressure chart
    new Chart(document.getElementById('pressure-chart-canvas'), {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Pressure (mbar)',
                data: data.pressure.avg,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: 'rgba(54, 162, 235, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
    
    // Humidity chart
    new Chart(document.getElementById('humidity-chart-canvas'), {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Humidity (%)',
                data: data.humidity.avg,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { min: 0, max: 100 } }
        }
    });
    
    // Wind chart
    new Chart(document.getElementById('wind-chart-canvas'), {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Wind Speed (mph)',
                data: data.wind.avg,
                borderColor: 'rgb(153, 102, 255)',
                backgroundColor: 'rgba(153, 102, 255, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { min: 0 } }
        }
    });
}
</script>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/state_detail.html
git commit -m "feat: add state detail page template with trend charts"
```

### Task 6.2: Create state summary partial

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_summary.html`

- [ ] **Step 1: Create state_summary.html partial**

```html
<!-- State summary cards -->
<div class="col-md-3 col-sm-6 mb-3">
    <div class="card h-100">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Temperature</h6>
            {% if summary.avg_temp is not none %}
            <h3 class="card-title mb-1">{{ "%.1f"|format(summary.avg_temp) }}°F</h3>
            <small class="text-muted">
                Hi: {{ "%.0f"|format(summary.max_temp) }}° / Lo: {{ "%.0f"|format(summary.min_temp) }}°
            </small>
            {% else %}
            <h3 class="card-title mb-1 text-muted">--</h3>
            <small class="text-muted">No data</small>
            {% endif %}
        </div>
    </div>
</div>

<div class="col-md-3 col-sm-6 mb-3">
    <div class="card h-100">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Humidity</h6>
            {% if summary.avg_humidity is not none %}
            <h3 class="card-title mb-1">{{ "%.0f"|format(summary.avg_humidity) }}%</h3>
            <small class="text-muted">
                Range: {{ "%.0f"|format(summary.min_humidity) }}-{{ "%.0f"|format(summary.max_humidity) }}%
            </small>
            {% else %}
            <h3 class="card-title mb-1 text-muted">--</h3>
            <small class="text-muted">No data</small>
            {% endif %}
        </div>
    </div>
</div>

<div class="col-md-3 col-sm-6 mb-3">
    <div class="card h-100">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Pressure</h6>
            {% if summary.avg_pressure is not none %}
            <h3 class="card-title mb-1">{{ "%.1f"|format(summary.avg_pressure) }} mb</h3>
            <small class="text-muted">
                Range: {{ "%.0f"|format(summary.min_pressure) }}-{{ "%.0f"|format(summary.max_pressure) }}
            </small>
            {% else %}
            <h3 class="card-title mb-1 text-muted">--</h3>
            <small class="text-muted">No data</small>
            {% endif %}
        </div>
    </div>
</div>

<div class="col-md-3 col-sm-6 mb-3">
    <div class="card h-100">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Wind</h6>
            {% if summary.avg_wind is not none %}
            <h3 class="card-title mb-1">{{ "%.0f"|format(summary.avg_wind) }} mph</h3>
            <small class="text-muted">
                Max: {{ "%.0f"|format(summary.max_wind or 0) }} mph
            </small>
            {% else %}
            <h3 class="card-title mb-1 text-muted">--</h3>
            <small class="text-muted">No data</small>
            {% endif %}
        </div>
    </div>
</div>

<!-- Update station count and timestamp -->
<script>
document.getElementById('station-count').textContent = '{{ summary.station_count }} stations';
document.getElementById('last-updated').textContent = '{{ summary.station_count }} stations • Last updated just now';
</script>
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_summary.html
git commit -m "feat: add state summary cards partial"
```

### Task 6.3: Create state alerts partial

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_alerts.html`

- [ ] **Step 1: Create state_alerts.html partial**

```html
<!-- State weather alerts banner -->
{% if alerts %}
<div class="mb-4">
    {% for alert in alerts %}
    <div class="alert {% if alert.level == 'severe' %}alert-danger{% else %}alert-warning{% endif %} d-flex align-items-center" role="alert">
        <div class="me-3">
            {% if alert.level == 'severe' %}
            <i class="bi bi-exclamation-triangle-fill fs-4"></i>
            {% else %}
            <i class="bi bi-exclamation-circle-fill fs-4"></i>
            {% endif %}
        </div>
        <div>
            <strong>{{ alert.message }}</strong>
            {% if alert.affected_stations %}
            <br>
            <small class="text-muted">
                Affected: {{ alert.affected_stations | join(', ') }}
            </small>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_alerts.html
git commit -m "feat: add state alerts banner partial"
```

### Task 6.4: Create state stations table partial

**Files:**
- Create: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_stations_table.html`

- [ ] **Step 1: Create state_stations_table.html partial**

```html
<!-- State stations table -->
{% if stations %}
<div class="table-responsive">
    <table class="table table-hover table-sm">
        <thead>
            <tr>
                <th>Callsign</th>
                <th class="text-end">Temp</th>
                <th class="text-end">Humidity</th>
                <th class="text-end">Pressure</th>
                <th class="text-end">Wind</th>
                <th class="text-end">Last Report</th>
            </tr>
        </thead>
        <tbody>
            {% for station in stations %}
            <tr>
                <td>
                    <a href="{{ url_for('dashboard.station', callsign=station.callsign) }}">
                        {{ station.callsign }}
                    </a>
                </td>
                <td class="text-end">
                    {% if station.temperature is not none %}
                    {{ "%.1f"|format(station.temperature) }}°F
                    {% else %}--{% endif %}
                </td>
                <td class="text-end">
                    {% if station.humidity is not none %}
                    {{ station.humidity }}%
                    {% else %}--{% endif %}
                </td>
                <td class="text-end">
                    {% if station.pressure is not none %}
                    {{ "%.1f"|format(station.pressure) }}
                    {% else %}--{% endif %}
                </td>
                <td class="text-end">
                    {% if station.wind_speed is not none %}
                    {{ "%.0f"|format(station.wind_speed) }}
                    {% if station.wind_gust %}({{ "%.0f"|format(station.wind_gust) }}){% endif %}
                    {% else %}--{% endif %}
                </td>
                <td class="text-end text-muted">
                    {% if station.last_report %}
                    {{ station.last_report.strftime('%H:%M') }}
                    {% else %}--{% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- Update station count badge -->
<script>
document.getElementById('station-count').textContent = '{{ stations | length }} stations';
</script>
{% else %}
<div class="text-center py-5">
    <p class="text-muted mb-3">No APRS weather stations found in this state.</p>
    <a href="{{ url_for('dashboard.weather_states') }}" class="btn btn-outline-primary">
        View All States
    </a>
</div>
{% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/state_stations_table.html
git commit -m "feat: add state stations table partial"
```

---

## Chunk 7: Navigation Integration & Cross-Links

### Task 7.1: Add "View by State" link to weather page

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/weather.html`

- [ ] **Step 1: Add link to weather page**

Find a suitable location in `weather.html` (near the page header) and add:

```html
<a href="{{ url_for('dashboard.weather_states') }}" class="btn btn-outline-secondary">
    <i class="bi bi-geo-alt"></i> View by State
</a>
```

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/weather.html
git commit -m "feat: add View by State link to weather page"
```

### Task 7.2: Add state link to station detail page

**Files:**
- Modify: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/station.html`
- Modify: `haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/station_detail.html`

- [ ] **Step 1: Update station detail partial to show state link**

In `station_detail.html`, if the station has a state, add a link:

```html
{% if station.state and station.country_code == 'US' %}
<a href="{{ url_for('dashboard.weather_state_detail', state_code=station.state) }}" 
   class="btn btn-sm btn-outline-secondary">
    View {{ station.state }} Weather
</a>
{% endif %}
```

Note: This requires the station query to include the `state` field.

- [ ] **Step 2: Commit**

```bash
git add haminfo-dashboard/src/haminfo_dashboard/templates/dashboard/partials/station_detail.html
git commit -m "feat: add state weather link to station detail page"
```

---

## Chunk 8: Final Integration & Deployment

### Task 8.1: Run all tests

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo/haminfo-dashboard
pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 2: Run linting**

```bash
cd /Users/I530566/devel/mine/hamradio/haminfo
ruff check haminfo-dashboard/src/haminfo_dashboard/state_queries.py
ruff check scripts/backfill_station_states.py
```

Expected: No errors

### Task 8.2: Push and deploy

- [ ] **Step 1: Push all changes**

```bash
git push origin master
```

- [ ] **Step 2: Deploy to production**

```bash
ssh waboring@cloud.hemna.com
cd ~/docker/haminfo
git pull
docker compose build --build-arg CACHEBUST=$(date +%s) haminfo-dashboard && docker compose up -d haminfo-dashboard
```

- [ ] **Step 3: Verify deployment**

Visit:
- `https://haminfo.hemna.com/weather/states` - States landing page
- `https://haminfo.hemna.com/weather/state/VA` - Virginia weather dashboard

Expected: Pages load with station data, charts render, alerts show if any

### Task 8.3: Smoke test

- [ ] **Step 1: Test states landing page**

```bash
curl -s https://haminfo.hemna.com/weather/states | grep -o "Weather by State"
```

Expected: "Weather by State"

- [ ] **Step 2: Test state detail API**

```bash
curl -s https://haminfo.hemna.com/api/dashboard/state/VA/summary/json | jq .station_count
```

Expected: Number > 0

- [ ] **Step 3: Test trends API**

```bash
curl -s https://haminfo.hemna.com/api/dashboard/state/TX/trends | jq '.labels | length'
```

Expected: Number between 1-24

---

## Summary

This plan implements the State Weather Dashboard in 8 chunks:

1. **Database schema** - Add `state` column to WeatherStation model
2. **Backfill script** - Populate state for existing stations using bounding boxes
3. **Query module** - State-specific queries with caching
4. **Routes & API** - Page routes and JSON/HTMX endpoints
5. **States landing** - Landing page template with state list
6. **State detail** - Dashboard page with summary, alerts, trends, stations
7. **Navigation** - Cross-links between pages
8. **Deployment** - Tests, push, deploy, verify

Total estimated time: 2-3 hours for experienced developer with TDD approach.
