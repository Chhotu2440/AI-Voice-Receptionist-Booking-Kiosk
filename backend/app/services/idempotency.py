"""Idempotency for unsafe POSTs (holds, bookings, enquiries).

Usage inside ONE transaction, as its first statement:

    replay = await idempotency.begin(session, "booking", key, payload)
    if replay: return replay
    ... do the work ...
    idempotency.finish(row, 201, body)   # same transaction, then commit

The key row is inserted at the start, so a concurrent request with the same key blocks on the primary key
(MySQL) until the first commits, then sees the stored response. If the first request fails, its key row is
rolled back with everything else and the client can safely retry with the same key.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyMismatchError, RequestInProgressError, ValidationFailed
from app.core.timeutil import utcnow
from app.models.booking import IdempotencyKey

TTL = timedelta(hours=24)


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict[str, Any]


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def validate_key(key: str | None) -> str:
    if not key or not (8 <= len(key) <= 64) or not key.replace("-", "").isalnum():
        raise ValidationFailed(
            "An Idempotency-Key header (8-64 letters, digits or dashes) is required.",
            details={"header": "Idempotency-Key"},
        )
    return key


async def begin(
    session: AsyncSession, scope: str, key: str, payload: dict[str, Any]
) -> tuple[IdempotencyKey | None, Replay | None]:
    request_hash = _hash(payload)
    row = IdempotencyKey(scope=scope, key=key, request_hash=request_hash, expires_at=utcnow() + TTL)
    session.add(row)
    try:
        await session.flush()
        return row, None
    except IntegrityError:
        await session.rollback()

    existing = await session.get(IdempotencyKey, (scope, key))
    if existing is None:
        raise RequestInProgressError()
    if existing.request_hash != request_hash:
        raise IdempotencyMismatchError()
    if existing.response_body is None or existing.response_status is None:
        raise RequestInProgressError()
    return None, Replay(existing.response_status, existing.response_body)


def finish(row: IdempotencyKey, status_code: int, body: dict[str, Any]) -> None:
    row.response_status = status_code
    row.response_body = json.loads(json.dumps(body, default=str))


async def abandon(session: AsyncSession, row: IdempotencyKey | None) -> None:
    """Drop the key row when committing a partial outcome (e.g. an expired-hold release) before raising."""
    if row is not None:
        await session.delete(row)
