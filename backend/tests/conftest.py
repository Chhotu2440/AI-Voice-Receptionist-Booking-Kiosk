"""Test fixtures.

By default tests run against an in-memory SQLite database (fast, no services needed).
Set TEST_DATABASE_URL (e.g. mysql+asyncmy://root:root@127.0.0.1:3306/plt_test) to run the same
suite against real MySQL 8 — CI does this. Concurrency tests (Sprint 2) will require MySQL.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models
from app.core.config import Settings
from app.core.ratelimit import InMemoryRateLimiter
from app.db.base import Base
from app.main import create_app
from app.seed import seed_initial_catalogue, seed_reference
from app.services import user_service
from app.services.context import Actor

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")
OWNER_EMAIL, OWNER_PASSWORD = "owner@example.com", "correct-horse-battery-9"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "test",
        "database_url": TEST_DB_URL,
        "redis_url": "",
        "jwt_secret": "test-secret-0123456789-0123456789-abcdef",
        "check_migrations_on_ready": False,
        "refresh_cookie_secure": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if TEST_DB_URL.startswith("sqlite"):
        eng = create_async_engine(
            TEST_DB_URL, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    else:
        eng = create_async_engine(TEST_DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    m = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with m() as s:
        await seed_reference(s)
        await seed_initial_catalogue(s)
        await user_service.create_user(s, OWNER_EMAIL, "Owner", OWNER_PASSWORD, ["OWNER"], Actor.system())
    return m


@pytest.fixture
async def session(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with maker() as s:
        yield s


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(maker: async_sessionmaker[AsyncSession], settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.sessionmaker = maker
    application.state.rate_limiter = InMemoryRateLimiter()
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


LoginFn = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
def login(client: AsyncClient) -> LoginFn:
    async def _login(email: str = OWNER_EMAIL, password: str = OWNER_PASSWORD) -> dict[str, str]:
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


@pytest.fixture
async def owner_headers(login: LoginFn) -> dict[str, str]:
    return await login()


@pytest.fixture
def make_user(maker: async_sessionmaker[AsyncSession]) -> Callable[..., Awaitable[tuple[str, str]]]:
    async def _make(role: str, email: str | None = None) -> tuple[str, str]:
        email = email or f"{role.lower()}@example.com"
        password = f"{role.lower()}-password-123"
        async with maker() as s:
            await user_service.create_user(s, email, role.title(), password, [role], Actor.system())
        return email, password

    return _make
