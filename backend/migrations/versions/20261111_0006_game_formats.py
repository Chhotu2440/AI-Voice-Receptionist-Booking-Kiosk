"""game formats (what is played in each package) + package links

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11 13:47:07.058068
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types
from app.core.timeutil import utcnow
from app.db.types import uuid7

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Game modes named on playlasertag.in (doc 02). Descriptions and package links are left for the owner.
GAME_FORMATS = [
    ("TEAM_MATCH", "Team Match", "टीम मैच"),
    ("SHOOTING", "Shooting", "शूटिंग"),
    ("FRIENDLY_FIRE", "Friendly Fire", "फ्रेंडली फायर"),
]


def upgrade() -> None:
    game_formats = op.create_table(
        "game_formats",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name_en", sa.String(length=64), nullable=False),
        sa.Column("name_hi", sa.String(length=64), nullable=False),
        sa.Column("description_en", sa.String(length=400), nullable=False),
        sa.Column("description_hi", sa.String(length=400), nullable=False),
        sa.Column("round_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", app.db.types.UUIDBinary(length=16), nullable=False),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_formats")),
        sa.UniqueConstraint("code", name=op.f("uq_game_formats_code")),
    )
    op.create_table(
        "package_games",
        sa.Column("package_id", app.db.types.UUIDBinary(length=16), nullable=False),
        sa.Column("game_format_id", app.db.types.UUIDBinary(length=16), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_format_id"],
            ["game_formats.id"],
            name=op.f("fk_package_games_game_format_id_game_formats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
            name=op.f("fk_package_games_package_id_packages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("package_id", "game_format_id", name=op.f("pk_package_games")),
    )
    now = utcnow()
    op.bulk_insert(
        game_formats,
        [
            {
                "id": uuid7(),
                "code": code,
                "name_en": name,
                "name_hi": name_hi,
                "description_en": "",
                "description_hi": "",
                "round_minutes": None,
                "sort_order": i,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for i, (code, name, name_hi) in enumerate(GAME_FORMATS)
        ],
    )


def downgrade() -> None:
    op.drop_table("package_games")
    op.drop_table("game_formats")
