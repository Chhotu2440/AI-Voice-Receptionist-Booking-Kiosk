"""Prepare a throwaway SQLite database for the kiosk Playwright tests (never used for real data).

DATABASE_URL=sqlite+aiosqlite:///./e2e.db E2E_ADMIN_PASSWORD=... python scripts/e2e_setup.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.db.session import build_engine, build_sessionmaker  # noqa: E402
from app.seed import seed_initial_catalogue, seed_reference  # noqa: E402
from app.services import user_service  # noqa: E402
from app.services.context import Actor  # noqa: E402


async def seed() -> None:
    engine = build_engine(get_settings())
    maker = build_sessionmaker(engine)
    async with maker() as s:
        await seed_reference(s)
        await seed_initial_catalogue(s)
        await user_service.create_user(
            s,
            os.environ.get("E2E_ADMIN_EMAIL", "e2e-owner@example.com"),
            "E2E Owner",
            os.environ["E2E_ADMIN_PASSWORD"],
            ["OWNER"],
            Actor.system(),
        )
    await engine.dispose()


def main() -> None:
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        raise SystemExit("e2e_setup only runs against a throwaway SQLite database")
    db_file = Path(url.split("///", 1)[1])
    db_file.unlink(missing_ok=True)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    asyncio.run(seed())
    print("e2e database ready")


if __name__ == "__main__":
    main()
