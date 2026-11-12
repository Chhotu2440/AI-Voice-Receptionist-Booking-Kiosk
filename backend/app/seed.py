"""Idempotent seed data.

* Reference data (always safe): permissions, roles and grants, occasions.
* Initial catalogue (only into an empty database): venue details and packages/prices as published on
  playlasertag.in on 2026-11-10, and the schedule/arena rules confirmed by the owner on 2026-11-10
  (D-01 exclusive games; D-02 max 20 players, 11:00-22:00, 30-min starts, 10-min buffer).
  Everything is editable in the admin dashboard.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogue import (
    GameFormat,
    Occasion,
    Package,
    PackageFeature,
    PackageGame,
    PackagePricingRule,
)
from app.models.identity import Permission, Role
from app.models.schedule import BusinessHours, BusinessLocation, Resource
from app.services.rbac import PERMISSIONS, ROLE_GRANTS, ROLE_NAMES

OCCASIONS = [
    ("FRIENDS_FAMILY", "Friends and Family", "दोस्त और परिवार", False, []),
    (
        "BIRTHDAY",
        "Birthday Party",
        "जन्मदिन पार्टी",
        False,
        [
            {"key": "birthday_person_name", "label_en": "Birthday person's name", "required": False},
            {"key": "birthday_person_age", "label_en": "Age", "required": False, "type": "int"},
            {"key": "special_requirements", "label_en": "Special requirements", "required": False},
        ],
    ),
    (
        "CORPORATE",
        "Corporate Event",
        "कॉर्पोरेट इवेंट",
        True,
        [
            {"key": "company_name", "label_en": "Company name", "required": False},
            {"key": "event_requirements", "label_en": "Event requirements", "required": False},
        ],
    ),
    (
        "SCHOOL_COLLEGE",
        "School/College",
        "स्कूल/कॉलेज",
        True,
        [
            {"key": "institution_name", "label_en": "Institution name", "required": False},
            {"key": "special_requirements", "label_en": "Special requirements", "required": False},
        ],
    ),
    (
        "PRIVATE_PARTY",
        "Private Party",
        "प्राइवेट पार्टी",
        False,
        [
            {"key": "special_requirements", "label_en": "Special requirements", "required": False},
        ],
    ),
    ("OTHER", "Other", "अन्य", False, []),
]

# Package content confirmed by the owner on 2026-11-12 (prices from the website, doc 02).
# (code, name_en, name_hi, minutes, rounds, weekday price, weekend price, [(feature_en, feature_hi)],
#  [game mode codes], recommended)
PACKAGES = [
    (
        "BEGINNER",
        "Beginner",
        "बिगिनर",
        20,
        2,
        "300",
        "400",
        [
            ("2 solo matches", "2 सोलो मैच"),
            ("Unlimited lives & bullets", "अनलिमिटेड लाइफ़ और गोलियाँ"),
            ("No additional challenges", "कोई अतिरिक्त चैलेंज नहीं"),
        ],
        [],
        False,
    ),
    (
        "INTERMEDIATE",
        "Intermediate",
        "इंटरमीडिएट",
        45,
        None,
        "450",
        "550",
        [("Team-based matches", "टीम वाले मैच")],
        ["RESPAWN_CHALLENGE", "LIMITED_LIVES", "LAST_MAN_STANDING"],
        True,
    ),
    (
        "EXPERT",
        "Advanced",
        "एडवांस्ड",
        60,
        None,
        "600",
        "650",
        [("Team-based matches", "टीम वाले मैच")],
        ["LIMITED_LIVES", "LAST_MAN_STANDING", "DEATHMATCH"],
        False,
    ),
]

# Game modes named on playlasertag.in (doc 02). Descriptions and which package includes which mode are
# business content: left empty for the owner to fill in from the admin dashboard (never invented here).
GAME_FORMATS = [
    ("TEAM_MATCH", "Team Match", "टीम मैच"),
    ("SHOOTING", "Shooting", "शूटिंग"),
    ("FRIENDLY_FIRE", "Friendly Fire", "फ्रेंडली फायर"),
    # Challenges and modes per package, from the owner (2026-11-12).
    ("RESPAWN_CHALLENGE", "Respawn time challenge", "रीस्पॉन टाइम चैलेंज"),
    ("LIMITED_LIVES", "Limited lives & bullets", "सीमित लाइफ़ और गोलियाँ"),
    ("LAST_MAN_STANDING", "Last Man Standing", "लास्ट मैन स्टैंडिंग"),
    ("DEATHMATCH", "Deathmatch", "डेथमैच"),
]

MAX_PLAYERS = 20  # D-02, confirmed 2026-11-10
OPEN_TIME, CLOSE_TIME = time(11, 0), time(22, 0)  # D-02, confirmed 2026-11-10


async def seed_reference(session: AsyncSession) -> None:
    existing_perms = {p.code: p for p in (await session.execute(select(Permission))).scalars()}
    for code, desc in PERMISSIONS.items():
        if code not in existing_perms:
            existing_perms[code] = Permission(code=code, description=desc)
            session.add(existing_perms[code])
    await session.flush()

    existing_roles = {r.code: r for r in (await session.execute(select(Role))).scalars()}
    for code, name in ROLE_NAMES.items():
        role = existing_roles.get(code)
        if role is None:
            role = Role(code=code, name=name)
            session.add(role)
        role.permissions = [existing_perms[c] for c in sorted(ROLE_GRANTS[code])]

    existing_occ = {o.code for o in (await session.execute(select(Occasion))).scalars()}
    for i, (code, en, hi, enquiry, fields) in enumerate(OCCASIONS):
        if code not in existing_occ:
            session.add(
                Occasion(
                    code=code,
                    label_en=en,
                    label_hi=hi,
                    always_enquiry=enquiry,
                    extra_fields_schema=fields,
                    sort_order=i,
                )
            )
    await session.commit()


async def seed_initial_catalogue(session: AsyncSession) -> bool:
    """Returns False (and does nothing) if a location or any package already exists."""
    has_location = (await session.execute(select(BusinessLocation.id).limit(1))).first() is not None
    has_package = (await session.execute(select(Package.id).limit(1))).first() is not None
    if has_location or has_package:
        return False

    location = BusinessLocation(
        name="Play Laser Tag",
        address="T-49, Hauz Khas Village, near The Hidden Hour",
        city="New Delhi",
        postal_code="110016",
        timezone="Asia/Kolkata",
        phone="+917042513648",
        whatsapp="+917042513648",
        email="playlazertag@gmail.com",
    )
    session.add(location)
    await session.flush()
    for weekday in range(7):
        session.add(
            BusinessHours(
                location_id=location.id,
                weekday=weekday,
                open_time=OPEN_TIME,
                close_time=CLOSE_TIME,
            )
        )
    session.add(
        Resource(
            location_id=location.id,
            name="Main Arena",
            capacity_mode="EXCLUSIVE",
            default_capacity=1,
            max_players=MAX_PLAYERS,
            slot_interval_min=30,
            buffer_min=10,
        )
    )

    games_by_code: dict[str, GameFormat] = {}
    for i, (gcode, gname, gname_hi) in enumerate(GAME_FORMATS):
        games_by_code[gcode] = GameFormat(code=gcode, name_en=gname, name_hi=gname_hi, sort_order=i)
        session.add(games_by_code[gcode])
    await session.flush()
    for i, (code, name, name_hi, duration, rounds, price_wd, price_we, features, modes, rec) in enumerate(
        PACKAGES
    ):
        package = Package(
            code=code,
            name_en=name,
            name_hi=name_hi,
            duration_min=duration,
            games_count=rounds,
            formats_count=len(modes) or None,
            min_guests=1,
            max_guests=MAX_PLAYERS,
            is_recommended=rec,
            sort_order=i,
            features=[
                PackageFeature(text_en=en, text_hi=hi, sort_order=j) for j, (en, hi) in enumerate(features)
            ],
            game_links=[
                PackageGame(game_format_id=games_by_code[m].id, game=games_by_code[m], sort_order=j)
                for j, m in enumerate(modes)
            ],
        )
        session.add(package)
        await session.flush()
        session.add_all(
            [
                PackagePricingRule(
                    package_id=package.id,
                    rule_type="BASE_DAYTYPE",
                    name=f"{name} weekday",
                    day_type="WEEKDAY",
                    price_per_person=Decimal(price_wd),
                ),
                PackagePricingRule(
                    package_id=package.id,
                    rule_type="BASE_DAYTYPE",
                    name=f"{name} weekend",
                    day_type="WEEKEND",
                    price_per_person=Decimal(price_we),
                ),
            ]
        )
    await session.commit()
    return True
