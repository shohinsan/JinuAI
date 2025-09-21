"""Redis Client Wrapper
====================
Provides an asynchronous Redis client with common caching operations,
including connect, disconnect, get, set, delete, exists, and flushdb,
plus utility functions for cache key generation.
"""

import json
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis

from app.utils.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisClient:
    """Redis client wrapper with caching utilities."""

    def __init__(self) -> None:
        """Initialize Redis client."""
        self.redis: Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                health_check_interval=30,
            )  # type: ignore
            await self.redis.ping()
        except Exception:
            self.redis = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()

    async def get(self, key: str) -> Any:
        """Get value from Redis."""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in Redis."""
        if not self.redis:
            return False

        try:
            serialized_value = json.dumps(value, default=str)
            ttl = ttl or settings.REDIS_CACHE_TTL
            await self.redis.setex(key, ttl, serialized_value)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self.redis:
            return False

        try:
            await self.redis.delete(key)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.exists(key))
        except Exception:
            return False

    async def flushdb(self) -> bool:
        """Flush all keys in current database."""
        if not self.redis:
            return False

        try:
            await self.redis.flushdb()
            return True
        except Exception:
            return False


# Global Redis client instance
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Get Redis client dependency."""
    return redis_client


def cache_key(prefix: str, *args: Any) -> str:
    """Generate cache key with prefix and arguments."""
    key_parts = [prefix] + [str(arg) for arg in args]
    return ":".join(key_parts)
