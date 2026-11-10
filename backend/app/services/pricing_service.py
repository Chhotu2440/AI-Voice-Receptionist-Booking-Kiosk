"""Pricing service: loads rules/settings, enforces the booking window and calls the pure engine.

This is the ONLY place final prices are computed (kiosk, AI tools, web and admin all call it).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    OutsideBookingWindowError,
    ValidationFailed,
)
from app.core.security import sign_payload
from app.core.timeutil import today_local, utcnow
from app.models.catalogue import Package, PackagePricingRule
from app.repositories import catalogue as catalogue_repo
from app.schemas.pricing import PricingRuleCreate, PricingRuleUpdate, check_rule_shape
from app.services import audit_service, settings_service
from app.services.context import Actor
from app.services.pricing_engine import (
    PackageView,
    PriceBreakdown,
    PricingConfig,
    PricingInput,
    RuleView,
    calculate,
)

RULE_FIELDS = (
    "package_id",
    "rule_type",
    "name",
    "day_type",
    "date_from",
    "date_to",
    "min_guests",
    "promo_code",
    "price_per_person",
    "discount_pct",
    "priority",
    "is_active",
    "valid_from",
    "valid_to",
)


def to_rule_view(r: PackagePricingRule) -> RuleView:
    return RuleView(
        id=r.id,
        package_id=r.package_id,
        rule_type=r.rule_type,
        name=r.name,
        day_type=r.day_type,
        date_from=r.date_from,
        date_to=r.date_to,
        min_guests=r.min_guests,
        promo_code=r.promo_code,
        price_per_person=r.price_per_person,
        discount_pct=r.discount_pct,
        priority=r.priority,
        is_active=r.is_active,
        valid_from=r.valid_from,
        valid_to=r.valid_to,
    )


def to_package_view(p: Package) -> PackageView:
    return PackageView(id=p.id, min_guests=p.min_guests, max_guests=p.max_guests)


async def ensure_bookable_date(session: AsyncSession, play_date: date) -> None:
    booking = await settings_service.get_booking_settings(session)
    today = today_local()
    last = today + timedelta(days=booking.max_days_ahead)
    if play_date < today or play_date > last:
        raise OutsideBookingWindowError(
            f"Please choose a date between {today.isoformat()} and {last.isoformat()}.",
            details={"first_date": today.isoformat(), "last_date": last.isoformat()},
        )


async def load_config(session: AsyncSession) -> PricingConfig:
    return settings_service.to_pricing_config(await settings_service.get_pricing_settings(session))


async def price_for_package(
    session: AsyncSession,
    package: Package,
    play_date: date,
    guest_count: int,
    *,
    promo_code: str | None = None,
    config: PricingConfig | None = None,
) -> PriceBreakdown:
    rules = [to_rule_view(r) for r in await catalogue_repo.rules_for_package(session, package.id)]
    return calculate(
        PricingInput(
            package=to_package_view(package),
            play_date=play_date,
            guest_count=guest_count,
            now=utcnow(),
            promo_code=promo_code,
        ),
        rules,
        config or await load_config(session),
    )


async def quote(
    session: AsyncSession,
    settings: Settings,
    package_id: uuid.UUID,
    play_date: date,
    guest_count: int,
    *,
    promo_code: str | None = None,
    enforce_window: bool = True,
) -> tuple[PriceBreakdown, str, datetime]:
    package = await catalogue_repo.get_package(session, package_id)
    if package is None or not package.is_active:
        raise NotFoundError("Package not found.")
    if enforce_window:
        await ensure_bookable_date(session, play_date)
    breakdown = await price_for_package(session, package, play_date, guest_count, promo_code=promo_code)
    expires_at = utcnow() + timedelta(seconds=settings.quote_ttl_seconds)
    quote_id = sign_payload(
        settings,
        "quote",
        {
            "pkg": str(package_id),
            "date": play_date.isoformat(),
            "guests": guest_count,
            "promo": promo_code,
            "total": str(breakdown.total),
        },
        settings.quote_ttl_seconds,
    )
    return breakdown, quote_id, expires_at


# --- admin rule management ---------------------------------------------------------------------------


def _rule_snapshot(r: PackagePricingRule) -> dict[str, Any]:
    return {f: getattr(r, f) for f in RULE_FIELDS}


async def _check_package(session: AsyncSession, package_id: uuid.UUID | None) -> None:
    if package_id is not None and await catalogue_repo.get_package(session, package_id) is None:
        raise ValidationFailed("Package not found.", details={"package_id": str(package_id)})


async def create_rule(session: AsyncSession, data: PricingRuleCreate, actor: Actor) -> PackagePricingRule:
    await _check_package(session, data.package_id)
    rule = PackagePricingRule(**data.model_dump())
    if rule.promo_code:
        rule.promo_code = rule.promo_code.upper()
    rule.created_by = uuid.UUID(actor.id) if actor.type == "USER" and actor.id else None
    session.add(rule)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("The rule conflicts with existing data.") from exc
    audit_service.record(
        session, actor, "pricing_rule.create", "pricing_rule", rule.id, None, _rule_snapshot(rule)
    )
    await session.commit()
    return rule


async def update_rule(
    session: AsyncSession, rule_id: uuid.UUID, data: PricingRuleUpdate, actor: Actor
) -> PackagePricingRule:
    rule = await catalogue_repo.get_rule(session, rule_id)
    if rule is None:
        raise NotFoundError("Pricing rule not found.")
    before = _rule_snapshot(rule)
    patch = data.model_dump(exclude_unset=True)
    merged = {**before, **patch}
    try:
        check_rule_shape(rule.rule_type, merged)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    for key, value in patch.items():
        setattr(rule, key, value.upper() if key == "promo_code" and value else value)
    audit_service.record(
        session, actor, "pricing_rule.update", "pricing_rule", rule.id, before, _rule_snapshot(rule)
    )
    await session.commit()
    return rule


async def deactivate_rule(session: AsyncSession, rule_id: uuid.UUID, actor: Actor) -> None:
    """Rules are never hard-deleted: historical bookings reference them in pricing snapshots."""
    rule = await catalogue_repo.get_rule(session, rule_id)
    if rule is None:
        raise NotFoundError("Pricing rule not found.")
    if rule.is_active:
        rule.is_active = False
        audit_service.record(session, actor, "pricing_rule.deactivate", "pricing_rule", rule.id)
        await session.commit()
