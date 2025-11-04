"""Response caching for API calls and blockchain queries.

This module provides caching functionality to reduce API calls
and improve performance.
"""

from typing import Any, Callable, Optional
from datetime import datetime, timedelta
from functools import wraps
import json


class Cache:
    """Simple in-memory cache with TTL support.

    Provides caching for API responses and blockchain queries
    to reduce external calls and improve performance.

    Attributes:
        cache_data: In-memory cache storage
        default_ttl: Default time-to-live in seconds
    """

    def __init__(self, default_ttl: int = 300) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default cache TTL in seconds
        """
        self.cache_data: dict[str, tuple[Any, datetime]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self.cache_data:
            return None

        value, expiry = self.cache_data[key]
        if datetime.utcnow() > expiry:
            del self.cache_data[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ttl = ttl or self.default_ttl
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self.cache_data[key] = (value, expiry)

    def delete(self, key: str) -> None:
        """Delete value from cache.

        Args:
            key: Cache key
        """
        if key in self.cache_data:
            del self.cache_data[key]

    def clear(self) -> None:
        """Clear all cached values."""
        self.cache_data.clear()

    def cleanup_expired(self) -> None:
        """Remove all expired entries from cache."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expiry) in self.cache_data.items() if now > expiry
        ]
        for key in expired_keys:
            del self.cache_data[key]


def cached(ttl: int = 300, cache_instance: Optional[Cache] = None) -> Callable:
    """Decorator for caching function results.

    Args:
        ttl: Cache TTL in seconds
        cache_instance: Cache instance to use (creates new if None)

    Returns:
        Decorated function
    """
    _cache = cache_instance or Cache(default_ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{json.dumps(args)}:{json.dumps(kwargs)}"

            # Try to get from cache
            result = _cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = await func(*args, **kwargs)
            _cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
