"""Liveness and readiness probes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])

ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"


def _head_revision() -> str | None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    checks: dict[str, Any] = {}
    ok = True
    try:
        async with request.app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            if request.app.state.settings.check_migrations_on_ready:
                current = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                head = _head_revision()
                checks["migrations"] = "ok" if current == head else f"pending (db={current}, head={head})"
                ok = ok and current == head
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        ok = False

    redis = request.app.state.redis
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
            ok = False
    return JSONResponse(
        status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", **checks}
    )
