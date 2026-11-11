"""Typed views over `system_settings` keys. Defaults are the documented placeholders (doc 02 §5)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.pricing_engine import WEEKDAY_CODES


class ExtraChargeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z0-9_]{2,32}$")
    label: str = Field(min_length=1, max_length=80)
    mode: Literal["FLAT", "PER_PERSON"]
    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class PricingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekend_days: list[str] = Field(default_factory=lambda: ["FRI", "SAT", "SUN"])
    tax_rate: Decimal = Field(default=Decimal("18.00"), ge=0, le=100, max_digits=5, decimal_places=2)
    prices_include_tax: bool = True
    discount_stacking: Literal["BEST", "STACK"] = "BEST"
    extra_charges: list[ExtraChargeSchema] = Field(default_factory=list, max_length=10)
    currency: Literal["INR"] = "INR"

    @field_validator("weekend_days")
    @classmethod
    def _valid_days(cls, value: list[str]) -> list[str]:
        days = [d.upper() for d in value]
        bad = [d for d in days if d not in WEEKDAY_CODES]
        if bad:
            raise ValueError(f"invalid weekday codes: {bad}; use {list(WEEKDAY_CODES)}")
        if len(set(days)) != len(days):
            raise ValueError("duplicate weekday codes")
        return days


class BookingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_days_ahead: int = Field(default=30, ge=0, le=365)
    same_day_cutoff_min: int = Field(default=15, ge=0, le=720)
    large_group_threshold: int = Field(default=20, ge=1, le=1000)
    hold_ttl_seconds: int = Field(default=300, ge=60, le=1800)


class ModelPrice(BaseModel):
    """USD per 1M tokens (official price pages; update here when providers change prices)."""

    model_config = ConfigDict(extra="forbid")
    audio_in: Decimal = Field(ge=0)
    audio_out: Decimal = Field(ge=0)
    text_in: Decimal = Field(ge=0)
    text_cached: Decimal = Field(ge=0)
    text_out: Decimal = Field(ge=0)


class AiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_cap_usd: Decimal = Field(default=Decimal("10"), ge=0)
    monthly_cap_usd: Decimal = Field(default=Decimal("120"), ge=0)  # ~INR 10,000 (doc 12)
    usd_inr: Decimal = Field(default=Decimal("88"), gt=0)
    price_version: str = "2026-11-10"
    prices: dict[str, ModelPrice] = Field(
        default_factory=lambda: {
            "gemini-3.8-live": ModelPrice(
                audio_in=Decimal("3"),
                audio_out=Decimal("12"),
                text_in=Decimal("0.75"),
                text_cached=Decimal("0.75"),
                text_out=Decimal("4.5"),
            ),
            "gpt-realtime-2.1-mini": ModelPrice(
                audio_in=Decimal("10"),
                audio_out=Decimal("20"),
                text_in=Decimal("0.6"),
                text_cached=Decimal("0.06"),
                text_out=Decimal("2.4"),
            ),
            "gpt-realtime-2.1": ModelPrice(
                audio_in=Decimal("32"),
                audio_out=Decimal("64"),
                text_in=Decimal("4"),
                text_cached=Decimal("0.4"),
                text_out=Decimal("24"),
            ),
        }
    )


SETTINGS_MODELS: dict[str, type[BaseModel]] = {
    "pricing": PricingSettings,
    "booking": BookingSettings,
    "ai": AiSettings,
}
