"""API application factory (process: `api`)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import InMemoryRateLimiter, RedisRateLimiter
from app.db.session import build_engine, build_sessionmaker

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.app_env != "test":
        configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Tests may pre-populate state (e.g. an SQLite engine); only build what is missing.
        if getattr(app.state, "sessionmaker", None) is None:
            app.state.engine = build_engine(settings)
            app.state.sessionmaker = build_sessionmaker(app.state.engine)
        if getattr(app.state, "rate_limiter", None) is None:
            if settings.redis_url:
                app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
                app.state.rate_limiter = RedisRateLimiter(app.state.redis)
            else:
                app.state.redis = None
                app.state.rate_limiter = InMemoryRateLimiter()
        log.info("startup", extra={"env": settings.app_env})
        try:
            yield
        finally:
            # Graceful shutdown: close pools so in-flight connections are returned cleanly.
            if getattr(app.state, "redis", None) is not None:
                await app.state.redis.aclose()
            if getattr(app.state, "engine", None) is not None:
                await app.state.engine.dispose()
            log.info("shutdown")

    docs = settings.expose_docs and not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/v1/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.sessionmaker = None
    app.state.rate_limiter = None
    app.state.redis = None
    app.state.engine = None

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app
