# Dashboard Memcached Integration

**Date:** 2026-03-28  
**Status:** Approved  

## Overview

Add memcached support to the APRS Dashboard to improve initial page load times and reduce database load. The dashboard will use the existing memcached container already running in production.

## Current State

- Memcached container (`haminfo-memcached`) already running in production
- haminfo API uses dogpile.cache with pylibmc backend, 5-minute TTL
- Dashboard has simple in-process Python dict caching with 30-second TTL
- Dashboard cache resets on container restart
- Dashboard doesn't depend on memcached in docker-compose

## Design

### Approach

Use pylibmc directly with a thin wrapper for serialization. This keeps the implementation simple, fast, and easy to debug without the complexity of dogpile.cache.

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Dashboard     │────▶│    cache.py     │────▶│   Memcached     │
│   queries.py    │     │  (pylibmc wrap) │     │   Container     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         │ cache miss                                    │
         ▼                                               │
┌─────────────────┐                                      │
│   PostgreSQL    │◀─────────────────────────────────────┘
│   (TimescaleDB) │         cache hit returns directly
└─────────────────┘
```

### Components

#### 1. cache.py - New module

```python
# Core functions:
init_cache(url: str) -> None
get(key: str) -> Any | None
set(key: str, value: Any, ttl: int = 300) -> None
cached(key: str, ttl: int = 300) -> Callable  # decorator
```

- JSON serialization for complex objects
- Graceful fallback if memcached unavailable (log warning, skip caching)
- MD5 key mangling for memcached compatibility

#### 2. queries.py - Modified

Remove all in-process cache globals:
- `_stats_cache`, `_stats_cache_time`
- `_countries_cache`, `_countries_cache_time`
- `_top_stations_cache`, `_top_stations_cache_time`
- `_hourly_cache`, `_hourly_cache_time`

Replace with `@cached()` decorator on query functions.

Add caching to currently uncached queries:
- `get_weather_stations()`
- `get_weather_countries()`
- `get_station_detail()`
- `get_map_stations()`

#### 3. app.py - Modified

Initialize cache on app startup:
```python
from haminfo_dashboard.cache import init_cache
init_cache(CONF.memcached.url)
```

#### 4. docker-compose.yml - Modified

Add memcached dependency to dashboard service:
```yaml
haminfo-dashboard:
  depends_on:
    - haminfo-memcached
```

### Cache Key Strategy

Keys namespaced with `dashboard:` prefix to avoid collisions:

| Query | Cache Key | TTL |
|-------|-----------|-----|
| `get_dashboard_stats()` | `dashboard:stats` | 300s |
| `get_top_stations(limit)` | `dashboard:top_stations:{limit}` | 300s |
| `get_country_breakdown(limit)` | `dashboard:countries:{limit}` | 300s |
| `get_hourly_distribution()` | `dashboard:hourly` | 300s |
| `get_weather_stations(...)` | `dashboard:wx_stations:{limit}:{offset}:{country}:{has_recent}` | 300s |
| `get_weather_countries()` | `dashboard:wx_countries` | 300s |
| `get_station_detail(callsign)` | `dashboard:station:{callsign}` | 300s |
| `get_map_stations(...)` | `dashboard:map:{bbox}:{type}:{limit}` | 300s |

### Error Handling

- Memcached unavailable at startup: log warning, continue without caching
- Memcached fails during operation: catch exception, log, return None (cache miss)
- Caching failures never cause dashboard failures - performance optimization only

### Configuration

Reuse existing `[memcached]` config section:
```ini
[memcached]
url = haminfo-memcached:11211
expire_time = 300
```

### Files Changed

| File | Action |
|------|--------|
| `haminfo-dashboard/src/haminfo_dashboard/cache.py` | Create |
| `haminfo-dashboard/src/haminfo_dashboard/queries.py` | Modify |
| `haminfo-dashboard/src/haminfo_dashboard/app.py` | Modify |
| `haminfo-dashboard/pyproject.toml` | Modify (add pylibmc) |
| Production `docker-compose.yml` | Modify |

## Testing

1. Verify dashboard loads with memcached running
2. Verify dashboard loads with memcached stopped (graceful fallback)
3. Check cache hits via `echo "stats" | nc localhost 11211`
4. Compare page load times before/after

## Rollback

Remove `@cached` decorators and cache initialization. Dashboard falls back to direct DB queries (original behavior before in-process caching was added).
