from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.api.deps import CurrentUser, SessionDep, SettingsDep, public_actor, rate_limit
from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.schemas.auth import LoginRequest, MeOut, TokenResponse
from app.services import auth_service
from app.services.auth_service import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "plt_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, settings: Settings, tokens: IssuedTokens) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", "login_rate_limit_per_minute"))],
)
async def login(
    body: LoginRequest, request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> TokenResponse:
    tokens = await auth_service.login(
        session, settings, body.email, body.password, public_actor(request), request.headers.get("user-agent")
    )
    return _set_refresh_cookie(response, settings, tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("refresh", "public_rate_limit_per_minute"))],
)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    plt_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not plt_refresh:
        raise UnauthenticatedError()
    tokens = await auth_service.refresh(
        session, settings, plt_refresh, public_actor(request), request.headers.get("user-agent")
    )
    return _set_refresh_cookie(response, settings, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: SessionDep,
    plt_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    await auth_service.logout(session, plt_refresh)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return response


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        role_codes=user.role_codes,
        last_login_at=user.last_login_at,
        permissions=sorted(user.permission_codes),
    )
