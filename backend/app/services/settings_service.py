"""Business settings stored in `system_settings`, validated through typed schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.audit import SystemSetting
from app.schemas.settings import SETTINGS_MODELS, AiSettings, BookingSettings, PricingSettings
from app.services import audit_service
from app.services.context import Actor
from app.services.pricing_engine import WEEKDAY_CODES, ExtraCharge, PricingConfig


async def _load[M: BaseModel](session: AsyncSession, key: str, model: type[M]) -> M:
    row = await session.get(SystemSetting, key)
    return model.model_validate(row.value) if row is not None else model()


async def get_pricing_settings(session: AsyncSession) -> PricingSettings:
    return await _load(session, "pricing", PricingSettings)


async def get_booking_settings(session: AsyncSession) -> BookingSettings:
    return await _load(session, "booking", BookingSettings)


async def get_ai_settings(session: AsyncSession) -> AiSettings:
    return await _load(session, "ai", AiSettings)


async def get_section(session: AsyncSession, key: str) -> BaseModel:
    model = SETTINGS_MODELS.get(key)
    if model is None:
        raise NotFoundError("Unknown settings section.")
    return await _load(session, key, model)


async def update_section(session: AsyncSession, key: str, data: dict[str, Any], actor: Actor) -> BaseModel:
    model = SETTINGS_MODELS.get(key)
    if model is None:
        raise NotFoundError("Unknown settings section.")
    try:
        new_value = model.model_validate(data)
    except ValidationError as exc:
        raise ValidationFailed(
            details={"errors": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}
        ) from exc
    row = await session.get(SystemSetting, key)
    before = row.value if row is not None else None
    payload = new_value.model_dump(mode="json")
    if row is None:
        session.add(SystemSetting(key=key, value=payload, updated_by=actor.id))
    else:
        row.value = payload
        row.updated_by = actor.id
    audit_service.record(session, actor, "settings.update", "system_settings", key, before, payload)
    await session.commit()
    return new_value


def to_pricing_config(s: PricingSettings) -> PricingConfig:
    return PricingConfig(
        weekend_days=frozenset(WEEKDAY_CODES.index(d) for d in s.weekend_days),
        tax_rate=s.tax_rate,
        prices_include_tax=s.prices_include_tax,
        discount_stacking=s.discount_stacking,
        extra_charges=tuple(ExtraCharge(c.code, c.label, c.mode, c.amount) for c in s.extra_charges),
        currency=s.currency,
    )
