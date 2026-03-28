# haminfo_dashboard/cache.py
"""Memcached caching for dashboard queries."""

from __future__ import annotations

import functools
import json
import logging
from hashlib import md5
from typing import Any, Callable, Optional

LOG = logging.getLogger(__name__)

# Global cache client
_client: Optional[Any] = None
_default_ttl: int = 300


def init_cache(url: Optional[str], ttl: int = 300) -> None:
    """Initialize memcached connection.

    Args:
        url: Memcached server URL (e.g., 'localhost:11211')
        ttl: Default TTL in seconds
    """
    global _client, _default_ttl
    _default_ttl = ttl

    if not url:
        LOG.warning('No memcached URL configured, caching disabled')
        return

    try:
        import pylibmc
        _client = pylibmc.Client([url], binary=True, behaviors={
            'tcp_nodelay': True,
            'ketama': True,
            'connect_timeout': 1000,  # 1 second
            'send_timeout': 1000000,  # 1 second
            'receive_timeout': 1000000,  # 1 second
            'retry_timeout': 5,
        })
        # Test connection
        _client.get('__test__')
        LOG.info(f'Memcached connected: {url}')
    except ImportError:
        LOG.warning('pylibmc not installed, caching disabled')
        _client = None
    except Exception as e:
        LOG.warning(f'Memcached connection failed: {e}, caching disabled')
        _client = None


def _make_key(key: str) -> str:
    """Convert key to memcached-safe format using MD5 hash."""
    return md5(key.encode('utf-8')).hexdigest()


def get(key: str) -> Optional[Any]:
    """Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found/error
    """
    if _client is None:
        return None

    try:
        safe_key = _make_key(key)
        data = _client.get(safe_key)
        if data is not None:
            return json.loads(data)
    except Exception as e:
        LOG.debug(f'Cache get error for {key}: {e}')

    return None


def set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set value in cache.

    Args:
        key: Cache key
        value: Value to cache (must be JSON serializable)
        ttl: TTL in seconds (uses default if not specified)

    Returns:
        True if successful, False otherwise
    """
    if _client is None:
        return False

    try:
        safe_key = _make_key(key)
        data = json.dumps(value)
        _client.set(safe_key, data, time=ttl or _default_ttl)
        return True
    except Exception as e:
        LOG.debug(f'Cache set error for {key}: {e}')
        return False


def cached(key_template: str, ttl: Optional[int] = None) -> Callable:
    """Decorator for caching function results.

    Args:
        key_template: Cache key template with {arg} placeholders
        ttl: TTL in seconds (uses default if not specified)

    Example:
        @cached('dashboard:stats')
        def get_stats(session):
            ...

        @cached('dashboard:station:{callsign}')
        def get_station(session, callsign):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from template and function arguments
            # Skip 'session' argument for key building
            sig = func.__code__.co_varnames[:func.__code__.co_argcount]
            key_args = {}
            for i, name in enumerate(sig):
                if name != 'session' and i < len(args):
                    key_args[name] = args[i]
            key_args.update({k: v for k, v in kwargs.items() if k != 'session'})

            # Format key template
            try:
                cache_key = key_template.format(**key_args)
            except KeyError:
                cache_key = key_template

            # Try to get from cache
            result = get(cache_key)
            if result is not None:
                LOG.debug(f'Cache hit: {cache_key}')
                return result

            # Cache miss - call function
            LOG.debug(f'Cache miss: {cache_key}')
            result = func(*args, **kwargs)

            # Store in cache
            if result is not None:
                set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


def delete(key: str) -> bool:
    """Delete value from cache.

    Args:
        key: Cache key

    Returns:
        True if successful, False otherwise
    """
    if _client is None:
        return False

    try:
        safe_key = _make_key(key)
        _client.delete(safe_key)
        return True
    except Exception as e:
        LOG.debug(f'Cache delete error for {key}: {e}')
        return False


def flush_all() -> bool:
    """Flush all cached values.

    Returns:
        True if successful, False otherwise
    """
    if _client is None:
        return False

    try:
        _client.flush_all()
        return True
    except Exception as e:
        LOG.debug(f'Cache flush error: {e}')
        return False
