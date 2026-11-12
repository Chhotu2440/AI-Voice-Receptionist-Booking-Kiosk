"""package content from the owner (2026-11-12): durations, rounds, game modes and challenges

Applies the owner's package details to databases created before them (new databases get the same content
from app/seed.py). Only the three seeded packages (by code) are touched; prices are not changed.
After this, the owner manages everything from the admin dashboard.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.timeutil import utcnow
from app.db.types import UTCDateTime, UUIDBinary, uuid7

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_GAME_FORMATS = [
    ("RESPAWN_CHALLENGE", "Respawn time challenge", "रीस्पॉन टाइम चैलेंज", 3),
    ("LIMITED_LIVES", "Limited lives & bullets", "सीमित लाइफ़ और गोलियाँ", 4),
    ("LAST_MAN_STANDING", "Last Man Standing", "लास्ट मैन स्टैंडिंग", 5),
    ("DEATHMATCH", "Deathmatch", "डेथमैच", 6),
]

# code -> (name_en or None to keep, name_hi, minutes, rounds, features [(en, hi)], game mode codes)
PACKAGES = {
    "BEGINNER": (
        None,
        "बिगिनर",
        20,
        2,
        [
            ("2 solo matches", "2 सोलो मैच"),
            ("Unlimited lives & bullets", "अनलिमिटेड लाइफ़ और गोलियाँ"),
            ("No additional challenges", "कोई अतिरिक्त चैलेंज नहीं"),
        ],
        [],
    ),
    "INTERMEDIATE": (
        None,
        "इंटरमीडिएट",
        45,
        None,
        [("Team-based matches", "टीम वाले मैच")],
        ["RESPAWN_CHALLENGE", "LIMITED_LIVES", "LAST_MAN_STANDING"],
    ),
    "EXPERT": (
        "Advanced",
        "एडवांस्ड",
        60,
        None,
        [("Team-based matches", "टीम वाले मैच")],
        ["LIMITED_LIVES", "LAST_MAN_STANDING", "DEATHMATCH"],
    ),
}

game_formats = sa.table(
    "game_formats",
    sa.column("id", UUIDBinary()),
    sa.column("code", sa.String),
    sa.column("name_en", sa.String),
    sa.column("name_hi", sa.String),
    sa.column("description_en", sa.String),
    sa.column("description_hi", sa.String),
    sa.column("round_minutes", sa.SmallInteger),
    sa.column("sort_order", sa.SmallInteger),
    sa.column("is_active", sa.Boolean),
    sa.column("created_at", UTCDateTime()),
    sa.column("updated_at", UTCDateTime()),
)
packages = sa.table(
    "packages",
    sa.column("id", UUIDBinary()),
    sa.column("code", sa.String),
    sa.column("name_en", sa.String),
    sa.column("name_hi", sa.String),
    sa.column("duration_min", sa.SmallInteger),
    sa.column("games_count", sa.SmallInteger),
    sa.column("formats_count", sa.SmallInteger),
    sa.column("updated_at", UTCDateTime()),
)
features = sa.table(
    "package_features",
    sa.column("id", UUIDBinary()),
    sa.column("package_id", UUIDBinary()),
    sa.column("text_en", sa.String),
    sa.column("text_hi", sa.String),
    sa.column("sort_order", sa.SmallInteger),
)
links = sa.table(
    "package_games",
    sa.column("package_id", UUIDBinary()),
    sa.column("game_format_id", UUIDBinary()),
    sa.column("sort_order", sa.SmallInteger),
)


def upgrade() -> None:
    conn = op.get_bind()
    now = utcnow()
    existing = set(conn.execute(sa.select(game_formats.c.code)).scalars())
    for code, name, name_hi, order in NEW_GAME_FORMATS:
        if code not in existing:
            conn.execute(
                game_formats.insert().values(
                    id=uuid7(),
                    code=code,
                    name_en=name,
                    name_hi=name_hi,
                    description_en="",
                    description_hi="",
                    round_minutes=None,
                    sort_order=order,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
    game_ids = dict(conn.execute(sa.select(game_formats.c.code, game_formats.c.id)).all())

    for code, (name_en, name_hi, minutes, rounds, feats, modes) in PACKAGES.items():
        package_id = conn.execute(
            sa.select(packages.c.id).where(packages.c.code == code)
        ).scalar_one_or_none()
        if package_id is None:
            continue
        values = {
            "name_hi": name_hi,
            "duration_min": minutes,
            "games_count": rounds,
            "formats_count": len(modes) or None,
            "updated_at": now,
        }
        if name_en:
            values["name_en"] = name_en
        conn.execute(packages.update().where(packages.c.id == package_id).values(**values))
        conn.execute(features.delete().where(features.c.package_id == package_id))
        for i, (en, hi) in enumerate(feats):
            conn.execute(
                features.insert().values(
                    id=uuid7(), package_id=package_id, text_en=en, text_hi=hi, sort_order=i
                )
            )
        conn.execute(links.delete().where(links.c.package_id == package_id))
        for i, mode in enumerate(modes):
            conn.execute(
                links.insert().values(package_id=package_id, game_format_id=game_ids[mode], sort_order=i)
            )


def downgrade() -> None:
    # Content migration: earlier content isn't restored (edit packages in admin instead). Remove only the
    # game modes this migration added, which also drops their package links (ON DELETE CASCADE).
    conn = op.get_bind()
    conn.execute(
        links.delete().where(
            links.c.game_format_id.in_(
                sa.select(game_formats.c.id).where(game_formats.c.code.in_([c for c, *_ in NEW_GAME_FORMATS]))
            )
        )
    )
    conn.execute(game_formats.delete().where(game_formats.c.code.in_([c for c, *_ in NEW_GAME_FORMATS])))
