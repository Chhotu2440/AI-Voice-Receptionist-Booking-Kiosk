"""Package catalogue: public listing with live prices, and admin management."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    DomainError,
    GuestCountInvalidError,
    NotFoundError,
    ValidationFailed,
)
from app.core.timeutil import utcnow
from app.models.catalogue import GameFormat, Occasion, Package, PackageFeature, PackageGame
from app.repositories import catalogue as catalogue_repo
from app.schemas.catalogue import (
    FeatureIn,
    GameFormatIn,
    GameFormatUpdate,
    OccasionUpdate,
    PackageCreate,
    PackagePricePreview,
    PackageUpdate,
)
from app.services import audit_service, pricing_service
from app.services.context import Actor
from app.services.pricing_engine import day_type_for

PACKAGE_FIELDS = (
    "code",
    "name_en",
    "name_hi",
    "description_en",
    "description_hi",
    "duration_min",
    "games_count",
    "formats_count",
    "min_guests",
    "max_guests",
    "is_recommended",
    "sort_order",
    "is_active",
)


def _snapshot(p: Package) -> dict[str, Any]:
    data = {f: getattr(p, f) for f in PACKAGE_FIELDS}
    data["features"] = [f.text_en for f in p.features]
    data["games"] = [g.code for g in p.games]
    return data


def _features(items: Sequence[FeatureIn]) -> list[PackageFeature]:
    return [PackageFeature(text_en=f.text_en, text_hi=f.text_hi, sort_order=i) for i, f in enumerate(items)]


async def _game_links(session: AsyncSession, codes: Sequence[str]) -> list[PackageGame]:
    """Resolve game codes (in the owner's order) to links; unknown or switched-off codes are rejected."""
    wanted = [c.strip().upper() for c in codes]
    if len(set(wanted)) != len(wanted):
        raise ValidationFailed("A game is listed twice.")
    if not wanted:
        return []
    rows = (
        (await session.execute(select(GameFormat).where(GameFormat.code.in_(wanted), GameFormat.is_active)))
        .scalars()
        .all()
    )
    by_code = {g.code: g for g in rows}
    missing = [c for c in wanted if c not in by_code]
    if missing:
        raise ValidationFailed(f"Unknown or switched-off games: {', '.join(missing)}")
    return [
        PackageGame(game_format_id=by_code[c].id, game=by_code[c], sort_order=i) for i, c in enumerate(wanted)
    ]


async def list_public(
    session: AsyncSession, play_date: date | None, guest_count: int | None
) -> list[tuple[Package, PackagePricePreview | None]]:
    packages, _ = await catalogue_repo.list_packages(session, active_only=True)
    if play_date is None:
        return [(p, None) for p in packages]

    await pricing_service.ensure_bookable_date(session, play_date)
    config = await pricing_service.load_config(session)
    result: list[tuple[Package, PackagePricePreview | None]] = []
    for p in packages:
        eligible = guest_count is None or p.min_guests <= guest_count <= p.max_guests
        probe_guests = guest_count if (guest_count is not None and eligible) else p.min_guests
        try:
            q = await pricing_service.price_for_package(session, p, play_date, probe_guests, config=config)
        except GuestCountInvalidError:
            eligible = False
            preview = None
        except DomainError:
            preview = None  # no price configured for that date: show the package without a price
        else:
            preview = PackagePricePreview(
                date=play_date.isoformat(),
                day_type=day_type_for(play_date, config.weekend_days),
                price_per_person=q.price_per_person,
                guest_count=guest_count,
                estimated_total=q.total if (guest_count is not None and eligible) else None,
                eligible=eligible,
            )
        result.append((p, preview))
    return result


async def get_active(session: AsyncSession, package_id: uuid.UUID) -> Package:
    p = await catalogue_repo.get_package(session, package_id)
    if p is None or not p.is_active:
        raise NotFoundError("Package not found.")
    return p


async def get_any(session: AsyncSession, package_id: uuid.UUID) -> Package:
    p = await catalogue_repo.get_package(session, package_id)
    if p is None:
        raise NotFoundError("Package not found.")
    return p


async def create(session: AsyncSession, data: PackageCreate, actor: Actor) -> Package:
    if await catalogue_repo.get_package_by_code(session, data.code) is not None:
        raise ConflictError("A package with this code already exists.")
    fields = data.model_dump(exclude={"features", "game_codes"})
    links = await _game_links(session, data.game_codes)
    if links:
        fields["formats_count"] = len(links)
    package = Package(**fields, features=_features(data.features), game_links=links)
    session.add(package)
    await session.flush()
    audit_service.record(session, actor, "package.create", "package", package.id, None, _snapshot(package))
    await session.commit()
    return package


async def update(session: AsyncSession, package_id: uuid.UUID, data: PackageUpdate, actor: Actor) -> Package:
    package = await get_any(session, package_id)
    before = _snapshot(package)
    patch = data.model_dump(exclude_unset=True, exclude={"features", "game_codes"})
    min_g = patch.get("min_guests", package.min_guests)
    max_g = patch.get("max_guests", package.max_guests)
    if max_g < min_g:
        raise ValidationFailed("max_guests must be >= min_guests")
    for key, value in patch.items():
        setattr(package, key, value)
    if data.features is not None:
        package.features = _features(data.features)
    if data.game_codes is not None:
        package.game_links = await _game_links(session, data.game_codes)
        package.formats_count = len(package.game_links) or None
    audit_service.record(session, actor, "package.update", "package", package.id, before, _snapshot(package))
    await session.commit()
    await session.refresh(package)
    return package


async def soft_delete(session: AsyncSession, package_id: uuid.UUID, actor: Actor) -> None:
    package = await get_any(session, package_id)
    package.deleted_at = utcnow()
    package.is_active = False
    audit_service.record(session, actor, "package.delete", "package", package.id, _snapshot(package))
    await session.commit()


async def update_occasion(session: AsyncSession, code: str, data: OccasionUpdate, actor: Actor) -> Occasion:
    occasion = await catalogue_repo.get_occasion(session, code)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    patch = data.model_dump(exclude_unset=True)
    before = {k: getattr(occasion, k) for k in patch}
    for key, value in patch.items():
        setattr(occasion, key, value)
    audit_service.record(session, actor, "occasion.update", "occasion", code, before, patch)
    await session.commit()
    return occasion


# --- game formats ---------------------------------------------------------------------------------


async def list_games(session: AsyncSession) -> list[GameFormat]:
    rows = await session.execute(select(GameFormat).order_by(GameFormat.sort_order, GameFormat.name_en))
    return list(rows.scalars())


async def create_game(session: AsyncSession, data: GameFormatIn, actor: Actor) -> GameFormat:
    exists = (
        await session.execute(select(GameFormat).where(GameFormat.code == data.code))
    ).scalar_one_or_none()
    if exists is not None:
        raise ConflictError("A game with this code already exists.")
    game = GameFormat(**data.model_dump())
    session.add(game)
    await session.flush()
    audit_service.record(session, actor, "game.create", "game_format", game.id, None, data.model_dump())
    await session.commit()
    return game


async def update_game(
    session: AsyncSession, game_id: uuid.UUID, data: GameFormatUpdate, actor: Actor
) -> GameFormat:
    game = await session.get(GameFormat, game_id)
    if game is None:
        raise NotFoundError("Game not found.")
    patch = data.model_dump(exclude_unset=True)
    before = {k: getattr(game, k) for k in patch}
    for key, value in patch.items():
        setattr(game, key, value)
    audit_service.record(session, actor, "game.update", "game_format", game.id, before, patch)
    await session.commit()
    await session.refresh(game)
    return game
