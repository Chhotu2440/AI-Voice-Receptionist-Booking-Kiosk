"""Async engine and session management (ADR-006: async SQLAlchemy + asyncmy)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": settings.db_echo, "pool_pre_ping": True}
    if settings.database_url.startswith("mysql"):
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=1800,
        )
    return create_async_engine(settings.database_url, **kwargs)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """One session per request. Services own commits; anything uncommitted is rolled back."""
    async with maker() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()
