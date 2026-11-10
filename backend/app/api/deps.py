"""FastAPI dependencies: settings, DB session, authentication, RBAC, rate limiting."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ForbiddenError, RateLimitedError, UnauthenticatedError
from app.core.logging import request_id_ctx
from app.core.ratelimit import RateLimiter
from app.core.security import decode_token
from app.db.session import session_scope
from app.models.identity import User
from app.repositories import users as users_repo
from app.services.context import Actor

_bearer = HTTPBearer(auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.sessionmaker):
        yield session


def client_ip(request: Request) -> str | None:
    # Nginx sets X-Real-IP; uvicorn runs with --proxy-headers so request.client is the real peer.
    return request.client.host if request.client else None


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthenticatedError()
    claims = decode_token(settings, credentials.credentials, expected_typ="access")
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise UnauthenticatedError("Invalid credentials.") from exc
    user = await users_repo.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError("Invalid credentials.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*codes: str) -> Callable[[User], Awaitable[User]]:
    async def _checker(user: CurrentUser) -> User:
        if not set(codes).issubset(user.permission_codes):
            raise ForbiddenError()
        return user

    return _checker


def user_actor(user: User, request: Request) -> Actor:
    return Actor(type="USER", id=str(user.id), ip=client_ip(request), request_id=request_id_ctx.get())


def public_actor(request: Request) -> Actor:
    return Actor(type="PUBLIC", ip=client_ip(request), request_id=request_id_ctx.get())


def rate_limit(scope: str, per_minute_setting: str) -> Callable[[Request, Settings], Awaitable[None]]:
    async def _limit(request: Request, settings: SettingsDep) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        limit = int(getattr(settings, per_minute_setting))
        key = f"{scope}:{client_ip(request) or 'unknown'}"
        if not await limiter.hit(key, limit, 60):
            raise RateLimitedError()

    return _limit
