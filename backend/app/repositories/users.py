"""Data access for users, roles and refresh tokens."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import RefreshToken, Role, User


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.strip().lower(), User.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_users(session: AsyncSession, offset: int, limit: int) -> tuple[Sequence[User], int]:
    base = select(User).where(User.deleted_at.is_(None))
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(User.created_at).offset(offset).limit(limit))).scalars().all()
    return rows, total


async def get_roles_by_codes(session: AsyncSession, codes: Sequence[str]) -> list[Role]:
    rows = (await session.execute(select(Role).where(Role.code.in_(list(codes))))).scalars().all()
    return list(rows)


async def get_refresh_by_hash(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
