"""Fixed-window rate limiter. Redis-backed in staging/prod; in-memory only for dev/test."""

from __future__ import annotations

import time
from typing import Protocol

from redis.asyncio import Redis


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Record one hit. Returns True if the request is allowed."""
        ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = int(time.time() // window_seconds)
        rkey = f"rl:{key}:{bucket}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(rkey)
            pipe.expire(rkey, window_seconds + 1)
            count, _ = await pipe.execute()
        return int(count) <= limit


class InMemoryRateLimiter:
    """Single-process limiter for dev/test. Not safe for multiple workers."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = int(time.time() // window_seconds)
        rkey = f"{key}:{bucket}"
        if len(self._counts) > 10_000:
            self._counts.clear()
        self._counts[rkey] = self._counts.get(rkey, 0) + 1
        return self._counts[rkey] <= limit
