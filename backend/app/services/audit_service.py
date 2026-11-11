"""Audit trail. Entries are added in the caller's transaction so they commit (or roll back) atomically."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.identity import User
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


async def search(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Audit viewer: newest first, with the acting user's name resolved for USER entries."""
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at < date_to)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit))).scalars().all()
    )
    user_ids = set()
    for r in rows:
        if r.actor_type == "USER" and r.actor_id:
            try:
                user_ids.add(uuid.UUID(r.actor_id))
            except ValueError:
                pass
    names: dict[str, str] = {}
    if user_ids:
        for uid, name in (
            await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        ).all():
            names[str(uid)] = name
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "actor_type": r.actor_type,
            "actor_id": r.actor_id,
            "actor_name": names.get(r.actor_id or "", None),
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "before": r.before,
            "after": r.after,
            "ip": r.ip,
        }
        for r in rows
    ]
    return items, int(total)
