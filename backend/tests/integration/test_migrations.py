"""Migrations must build exactly the schema the ORM models describe (guards against forgotten migrations)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.db.base import Base

BACKEND = Path(__file__).resolve().parents[2]


def _sync_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if url is None:
        return None
    return url.replace("+asyncmy", "+pymysql")


def test_upgrade_head_matches_models(tmp_path: Path) -> None:
    url = _sync_url() or f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    engine = create_engine(url)
    with engine.begin() as conn:
        if conn.dialect.name == "mysql":
            pytest.skip("MySQL schema is recreated by other fixtures; covered by the CI migrate job")
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")

        tables = set(inspect(conn).get_table_names())
        assert set(Base.metadata.tables) <= tables

        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        assert diff == [], f"models and migrations differ: {diff}"

        command.downgrade(cfg, "base")
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
    engine.dispose()
