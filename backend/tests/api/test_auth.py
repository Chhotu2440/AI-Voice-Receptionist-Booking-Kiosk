"""Authentication, RBAC and session security tests (SEC-*)."""

from __future__ import annotations

from datetime import timedelta

import jwt
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ratelimit import InMemoryRateLimiter
from app.core.timeutil import utcnow
from app.models.audit import AuditLog
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, make_settings


async def call_with_refresh(client: AsyncClient, action: str, token: str):  # type: ignore[no-untyped-def]
    client.cookies.clear()
    client.cookies.set("plt_refresh", token, path="/api/v1/auth")
    try:
        return await client.post(f"/api/v1/auth/{action}")
    finally:
        client.cookies.clear()


async def test_login_success_sets_httponly_refresh_cookie(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL.upper(), "password": OWNER_PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    cookie = r.headers["set-cookie"].lower()
    assert "plt_refresh=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie


async def test_me_returns_permissions(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.get("/api/v1/auth/me", headers=owner_headers)
    assert r.status_code == 200
    me = r.json()
    assert me["role_codes"] == ["OWNER"]
    assert "user.manage" in me["permissions"] and "pricing.write" in me["permissions"]


async def test_wrong_password_and_unknown_user_same_error(client: AsyncClient) -> None:
    a = await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "nope-nope-nope"})
    b = await client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"] == "Invalid email or password."
    assert a.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_account_lockout_after_failures(
    client: AsyncClient, app: FastAPI, maker: async_sessionmaker[AsyncSession]
) -> None:
    app.state.rate_limiter = InMemoryRateLimiter()
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "bad-password-x"})
        assert r.status_code == 401
    app.state.rate_limiter = InMemoryRateLimiter()  # isolate account lockout from the IP rate limit
    r = await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 401
    assert "Too many failed attempts" in r.json()["error"]["message"]
    async with maker() as s:
        n = (await s.execute(select(func.count()).where(AuditLog.action == "auth.lockout"))).scalar_one()
    assert n == 1


async def test_sec004_login_rate_limited(client: AsyncClient) -> None:
    statuses = []
    for i in range(6):
        r = await client.post(
            "/api/v1/auth/login", json={"email": f"x{i}@example.com", "password": "whatever-1"}
        )
        statuses.append(r.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


async def test_refresh_rotates_and_detects_reuse(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    first = r.cookies["plt_refresh"]

    r2 = await call_with_refresh(client, "refresh", first)
    assert r2.status_code == 200
    second = r2.cookies["plt_refresh"]
    assert second != first

    # Replaying the already-used token revokes the whole family...
    r3 = await call_with_refresh(client, "refresh", first)
    assert r3.status_code == 401
    # ...so the legitimately rotated token no longer works either.
    r4 = await call_with_refresh(client, "refresh", second)
    assert r4.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    token = r.cookies["plt_refresh"]
    assert (await call_with_refresh(client, "logout", token)).status_code == 204
    assert (await call_with_refresh(client, "refresh", token)).status_code == 401


async def test_missing_invalid_and_expired_tokens(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/api/v1/auth/me", headers=bad)).status_code == 401

    s = make_settings()
    now = utcnow()
    expired = jwt.encode(
        {
            "sub": "x",
            "iss": s.jwt_issuer,
            "iat": int((now - timedelta(hours=1)).timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
            "typ": "access",
        },
        s.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]


async def test_token_signed_with_other_secret_rejected(client: AsyncClient) -> None:
    forged = jwt.encode(
        {"sub": "x", "iss": "playlasertag", "iat": 0, "exp": 9999999999, "typ": "access"},
        "attacker-secret-attacker-secret-1234",
        algorithm="HS256",
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_quote_token_cannot_be_used_as_access_token(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    pkgs = (await client.get("/api/v1/packages")).json()
    from app.core.timeutil import today_local

    r = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pkgs[0]["id"], "date": today_local().isoformat(), "guest_count": 2},
    )
    quote_id = r.json()["quote_id"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {quote_id}"})
    assert r.status_code == 401


async def test_rbac_staff_cannot_edit_pricing_or_users(client: AsyncClient, make_user, login) -> None:  # type: ignore[no-untyped-def]
    email, password = await make_user("STAFF")
    headers = await login(email, password)
    assert (await client.get("/api/v1/admin/schedule/hours", headers=headers)).status_code == 200
    r = await client.get("/api/v1/admin/pricing-rules", headers=headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert (await client.get("/api/v1/admin/users", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/admin/packages", headers=headers, json={})).status_code in (403, 422)


async def test_manager_can_edit_pricing_but_not_booking_settings(
    client: AsyncClient, make_user, login
) -> None:  # type: ignore[no-untyped-def]
    email, password = await make_user("MANAGER")
    headers = await login(email, password)
    r = await client.put(
        "/api/v1/admin/settings/pricing",
        headers=headers,
        json={"weekend_days": ["SAT", "SUN"], "tax_rate": "18.00"},
    )
    assert r.status_code == 200, r.text
    r = await client.put("/api/v1/admin/settings/booking", headers=headers, json={"max_days_ahead": 60})
    assert r.status_code == 403


async def test_user_management_and_deactivation_revokes_sessions(
    client: AsyncClient,
    owner_headers: dict[str, str],
    login,  # type: ignore[no-untyped-def]
) -> None:
    r = await client.post(
        "/api/v1/admin/users",
        headers=owner_headers,
        json={
            "email": "desk@example.com",
            "name": "Desk",
            "password": "desk-password-1234",
            "roles": ["STAFF"],
        },
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    assert r.json()["role_codes"] == ["STAFF"]

    dup = await client.post(
        "/api/v1/admin/users",
        headers=owner_headers,
        json={
            "email": "DESK@example.com",
            "name": "Desk",
            "password": "desk-password-1234",
            "roles": ["STAFF"],
        },
    )
    assert dup.status_code == 409

    weak = await client.post(
        "/api/v1/admin/users",
        headers=owner_headers,
        json={"email": "w@example.com", "name": "W", "password": "aaaaaaaaaaaa", "roles": ["STAFF"]},
    )
    assert weak.status_code == 422

    login_r = await client.post(
        "/api/v1/auth/login", json={"email": "desk@example.com", "password": "desk-password-1234"}
    )
    refresh = login_r.cookies["plt_refresh"]
    r = await client.patch(f"/api/v1/admin/users/{user_id}", headers=owner_headers, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await call_with_refresh(client, "refresh", refresh)).status_code == 401
    staff_access = {"Authorization": f"Bearer {login_r.json()['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=staff_access)).status_code == 401


async def test_owner_cannot_lock_themselves_out(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    me = (await client.get("/api/v1/auth/me", headers=owner_headers)).json()
    r = await client.patch(
        f"/api/v1/admin/users/{me['id']}", headers=owner_headers, json={"is_active": False}
    )
    assert r.status_code == 422
