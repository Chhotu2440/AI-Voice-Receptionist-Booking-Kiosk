"""Staff account management."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.models.identity import Role, User
from app.repositories import users as users_repo
from app.services import audit_service
from app.services.context import Actor

MIN_PASSWORD_LENGTH = 12


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.strip() != password or len(set(password)) < 5:
        raise ValidationFailed("Password is too weak.")


def _snapshot(user: User) -> dict[str, object]:
    return {"email": user.email, "name": user.name, "is_active": user.is_active, "roles": user.role_codes}


async def _resolve_roles(session: AsyncSession, codes: Sequence[str]) -> list[Role]:
    roles = await users_repo.get_roles_by_codes(session, codes)
    missing = set(codes) - {r.code for r in roles}
    if missing:
        raise ValidationFailed("Unknown role.", details={"roles": sorted(missing)})
    return roles


async def create_user(
    session: AsyncSession, email: str, name: str, password: str, role_codes: Sequence[str], actor: Actor
) -> User:
    validate_password(password)
    if await users_repo.get_by_email(session, email) is not None:
        raise ConflictError("A user with this email already exists.")
    user = User(
        email=email.strip().lower(),
        name=name.strip(),
        password_hash=hash_password(password),
        roles=await _resolve_roles(session, role_codes),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A user with this email already exists.") from exc
    audit_service.record(session, actor, "user.create", "user", user.id, None, _snapshot(user))
    await session.commit()
    return user


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    is_active: bool | None = None,
    role_codes: Sequence[str] | None = None,
    password: str | None = None,
) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if actor.id == str(user.id) and (
        is_active is False or (role_codes is not None and "OWNER" not in role_codes)
    ):
        raise ValidationFailed("You can't deactivate yourself or remove your own owner role.")
    before = _snapshot(user)
    if name is not None:
        user.name = name.strip()
    if role_codes is not None:
        user.roles = await _resolve_roles(session, role_codes)
    revoke = False
    if is_active is not None:
        user.is_active = is_active
        revoke = not is_active
    if password is not None:
        validate_password(password)
        user.password_hash = hash_password(password)
        revoke = True
    if revoke:
        await users_repo.revoke_all_for_user(session, user.id, utcnow())
    audit_service.record(session, actor, "user.update", "user", user.id, before, _snapshot(user))
    await session.commit()
    return user
