# ADR-0001: aprs.fi Error Handling Convention

## Status

Accepted

## Context

The haminfo application integrates with aprs.fi to fetch APRS packet data. The aprs.fi API can fail in various ways:

- Network connectivity issues
- API rate limiting (HTTP 429)
- Authentication failures (HTTP 401/403)
- Service unavailability (HTTP 5xx)
- Invalid/malformed responses
- Timeout conditions

Currently, error handling is inconsistent across the codebase, with some functions silently swallowing errors, others logging but not propagating, and others raising exceptions that may crash long-running processes.

## Decision

We will adopt the following error handling convention for aprs.fi API interactions:

### 1. Error Classification

Errors are classified into three categories:

| Category | Examples | Action |
|----------|----------|--------|
| **Transient** | Network timeout, 429, 503 | Log warning, retry with exponential backoff |
| **Permanent** | 401, 403, 404 | Log error, return empty result, alert operator |
| **Data** | Malformed JSON, missing fields | Log warning, skip record, continue processing |

### 2. Return Value Convention

API functions should return structured results rather than raise exceptions:

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class APIResult:
    success: bool
    data: Optional[List[dict]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
```

### 3. Logging Requirements

- **Transient errors**: Log at WARNING level with retry count
- **Permanent errors**: Log at ERROR level with full context
- **Data errors**: Log at WARNING level with the problematic record identifier

### 4. Retry Strategy

For transient errors, use exponential backoff:

- Initial delay: 1 second
- Max delay: 60 seconds
- Max retries: 3
- Jitter: +/- 10%

### 5. Circuit Breaker

Implement a circuit breaker pattern to prevent cascading failures:

- Open circuit after 5 consecutive failures
- Half-open after 30 seconds
- Close circuit after 3 consecutive successes

## Consequences

### Positive

- Consistent error handling across all aprs.fi integrations
- Long-running processes (MQTT ingest, scheduled fetches) won't crash on transient errors
- Operators get clear visibility into API health through structured logging
- Easier debugging with error classification

### Negative

- More code complexity in API wrapper layer
- Need to update all existing aprs.fi callers to use new convention
- Circuit breaker state needs to be managed (in-memory is acceptable for single-process deployments)

## Implementation Notes

1. Create `haminfo/api/aprsfi.py` as the canonical wrapper for all aprs.fi interactions
2. Existing direct API calls should migrate to use this wrapper
3. Add metrics/counters for monitoring error rates (optional enhancement)

## Related

- RepeaterBook API uses similar patterns (see `fetch_repeaterbook.py`)
- Weather station fetching could adopt similar conventions
