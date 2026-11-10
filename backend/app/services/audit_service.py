"""Audit trail. Entries are added in the caller's transaction so they commit (or roll back) atomically."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.services.context import Actor


def _jsonable(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    result: dict[str, Any] = json.loads(json.dumps(data, default=str))
    return result


def record(
    session: AsyncSession,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: object | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_type=actor.type,
            actor_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=_jsonable(before),
            after=_jsonable(after),
            ip=actor.ip,
            request_id=actor.request_id,
        )
    )
