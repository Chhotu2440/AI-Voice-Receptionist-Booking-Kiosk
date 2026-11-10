"""ARQ worker (process: `worker`): `arq app.workers.settings.WorkerSettings`."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import build_engine, build_sessionmaker
from app.services import hold_service

log = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["engine"] = build_engine(settings)
    ctx["sessionmaker"] = build_sessionmaker(ctx["engine"])


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def expire_holds(ctx: dict[str, Any]) -> int:
    async with ctx["sessionmaker"]() as session:
        released = await hold_service.expire_due_holds(session)
    if released:
        log.info("holds_expired", extra={"count": released})
    return released


class WorkerSettings:
    functions: ClassVar[list[Any]] = [expire_holds]
    cron_jobs: ClassVar[list[Any]] = [cron(expire_holds, second={0, 15, 30, 45}, run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")
    max_jobs = 4
