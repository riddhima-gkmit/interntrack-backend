"""Redis client for OTP, rate limiting, and ephemeral state (single shared connection)."""

from redis.asyncio import Redis, from_url

from app.config import settings


class RedisClient:
    """Singleton async Redis client wrapper; one connection shared app-wide."""

    _client: Redis | None = None  # Lazy singleton; created on first get_client(), cleared in close().

    @classmethod
    def get_client(cls) -> Redis:
        """Get or create Redis client."""
        if cls._client is None:
            cls._client = from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,  # Return str instead of bytes for get/set.
            )
        return cls._client

    @classmethod
    async def close(cls) -> None:
        """Close Redis connection and clear singleton (e.g. app shutdown)."""
        if cls._client:
            await cls._client.close()
            cls._client = None

    @classmethod
    async def set(cls, key: str, value: str, expire: int | None = None) -> None:
        """Set value with optional TTL in seconds (ex=expire; None = no expiry)."""
        client = cls.get_client()
        await client.set(key, value, ex=expire)

    @classmethod
    async def get(cls, key: str) -> str | None:
        """Get value by key; returns None if key does not exist."""
        client = cls.get_client()
        return await client.get(key)

    @classmethod
    async def delete(cls, *keys: str) -> None:
        """Delete one or more keys (supports multiple keys in one call)."""
        client = cls.get_client()
        await client.delete(*keys)

    @classmethod
    async def incr(cls, key: str) -> int:
        """Increment value by 1; creates key at 0 if missing. Returns new value (e.g. for attempt/send counts)."""
        client = cls.get_client()
        return await client.incr(key)

    @classmethod
    async def ttl(cls, key: str) -> int:
        """Return TTL in seconds (-1 if no expiry, -2 if key does not exist)."""
        client = cls.get_client()
        return await client.ttl(key)


# Single instance for dependency injection and consistent access (uses class singleton under the hood).
redis_client = RedisClient()
