"""Where live kiosk session state lives between intents: Redis in staging/prod (shared by API workers and,
later, the voice gateway), in-memory for dev/tests. TTL keeps abandoned state from lingering (PII)."""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

from app.kiosk.state import KioskState

STATE_TTL_SECONDS = 30 * 60


class KioskStateStore(Protocol):
    async def get(self, device_id: str) -> KioskState | None: ...
    async def put(self, device_id: str, state: KioskState) -> None: ...
    async def delete(self, device_id: str) -> None: ...


class InMemoryKioskStateStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, device_id: str) -> KioskState | None:
        raw = self._data.get(device_id)
        return KioskState.model_validate_json(raw) if raw else None

    async def put(self, device_id: str, state: KioskState) -> None:
        self._data[device_id] = state.model_dump_json()

    async def delete(self, device_id: str) -> None:
        self._data.pop(device_id, None)


class RedisKioskStateStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, device_id: str) -> KioskState | None:
        raw = await self._redis.get(f"kiosk:state:{device_id}")
        return KioskState.model_validate_json(raw) if raw else None

    async def put(self, device_id: str, state: KioskState) -> None:
        await self._redis.set(f"kiosk:state:{device_id}", state.model_dump_json(), ex=STATE_TTL_SECONDS)

    async def delete(self, device_id: str) -> None:
        await self._redis.delete(f"kiosk:state:{device_id}")
