"""Admin authentication: password login with lockout, rotating refresh tokens with reuse detection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.core.timeutil import utcnow
from app.db.types import uuid7
from app.models.identity import RefreshToken, User
from app.repositories import users as users_repo
from app.services import audit_service
from app.services.context import Actor

INVALID_LOGIN = "Invalid email or password."


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


def _issue(
    session: AsyncSession,
    settings: Settings,
    user: User,
    family_id: uuid.UUID,
    actor: Actor,
    user_agent: str | None,
) -> IssuedTokens:
    now = utcnow()
    refresh = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            family_id=family_id,
            issued_at=now,
            expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
            ip=actor.ip,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    access = create_access_token(settings, str(user.id))
    return IssuedTokens(access, refresh, settings.access_token_ttl_seconds, user)


async def login(
    session: AsyncSession,
    settings: Settings,
    email: str,
    password: str,
    actor: Actor,
    user_agent: str | None,
) -> IssuedTokens:
    now = utcnow()
    user = await users_repo.get_by_email(session, email)

    if user is not None and user.locked_until is not None and user.locked_until > now:
        verify_password(password, None)  # keep timing similar
        raise UnauthenticatedError("Too many failed attempts. Please try again later.")

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(seconds=settings.login_lockout_seconds)
                user.failed_login_count = 0
                audit_service.record(session, actor, "auth.lockout", "user", user.id)
            await session.commit()
        raise UnauthenticatedError(INVALID_LOGIN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    tokens = _issue(session, settings, user, uuid7(), actor, user_agent)
    audit_service.record(
        session, Actor("USER", str(user.id), actor.ip, actor.request_id), "auth.login", "user", user.id
    )
    await session.commit()
    return tokens


async def refresh(
    session: AsyncSession, settings: Settings, refresh_token: str, actor: Actor, user_agent: str | None
) -> IssuedTokens:
    now = utcnow()
    row = await users_repo.get_refresh_by_hash(session, hash_token(refresh_token))
    if row is None:
        raise UnauthenticatedError("Invalid credentials.")
    if row.used_at is not None or row.revoked_at is not None:
        # Reuse of a rotated/revoked token: assume theft and revoke the whole family.
        await users_repo.revoke_family(session, row.family_id, now)
        audit_service.record(session, actor, "auth.refresh_reuse_detected", "user", row.user_id)
        await session.commit()
        raise UnauthenticatedError("Your session has expired. Please sign in again.")
    if row.expires_at <= now:
        raise UnauthenticatedError("Your session has expired. Please sign in again.")

    user = await users_repo.get_by_id(session, row.user_id)
    if user is None or not user.is_active:
        await users_repo.revoke_family(session, row.family_id, now)
        await session.commit()
        raise UnauthenticatedError("Invalid credentials.")

    row.used_at = now
    tokens = _issue(session, settings, user, row.family_id, actor, user_agent)
    await session.commit()
    return tokens


async def logout(session: AsyncSession, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    row = await users_repo.get_refresh_by_hash(session, hash_token(refresh_token))
    if row is not None:
        await users_repo.revoke_family(session, row.family_id, utcnow())
        await session.commit()
