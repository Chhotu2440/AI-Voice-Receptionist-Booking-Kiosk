from __future__ import annotations

import datetime as dt
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ORMModel
from app.services.pricing_engine import PriceBreakdown

RuleType = Literal["BASE_DAYTYPE", "DATE_OVERRIDE", "DATE_RANGE", "PROMO", "GROUP_DISCOUNT"]
DayType = Literal["WEEKDAY", "WEEKEND"]
Price = Decimal


class PriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: uuid.UUID
    date: dt.date
    guest_count: int = Field(ge=1, le=1000)
    occasion_code: str | None = Field(default=None, max_length=32)
    promo_code: str | None = Field(default=None, max_length=32)


class DiscountOut(BaseModel):
    rule_id: uuid.UUID
    name: str
    pct: Decimal
    amount: Decimal


class ChargeOut(BaseModel):
    code: str
    label: str
    amount: Decimal


class TaxOut(BaseModel):
    rate: Decimal
    amount: Decimal
    included: bool


class PriceQuoteOut(BaseModel):
    package_id: uuid.UUID
    date: dt.date
    day_type: DayType
    guest_count: int
    price_per_person: Decimal
    subtotal: Decimal
    discounts: list[DiscountOut]
    discount_total: Decimal
    charges: list[ChargeOut]
    charges_total: Decimal
    tax: TaxOut
    total: Decimal
    currency: str
    rules_applied: list[uuid.UUID]
    quote_id: str | None = None
    quote_expires_at: datetime | None = None


class _RuleFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=100)
    day_type: DayType | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_guests: int | None = Field(default=None, ge=1, le=1000)
    promo_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,32}$")
    price_per_person: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    discount_pct: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    priority: int = Field(default=0, ge=-100, le=100)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None


def check_rule_shape(rule_type: str, r: _RuleFields | dict[str, object]) -> None:
    """Shared validation for create and (merged) update payloads."""
    g = r.get if isinstance(r, dict) else lambda k: getattr(r, k)
    price, pct = g("price_per_person"), g("discount_pct")
    date_from, date_to = g("date_from"), g("date_to")
    if rule_type in ("BASE_DAYTYPE", "DATE_OVERRIDE", "DATE_RANGE"):
        if price is None or pct is not None:
            raise ValueError(f"{rule_type} requires price_per_person and no discount_pct")
    else:
        if pct is None or price is not None:
            raise ValueError(f"{rule_type} requires discount_pct and no price_per_person")
    if rule_type == "BASE_DAYTYPE" and g("day_type") is None:
        raise ValueError("BASE_DAYTYPE requires day_type")
    if rule_type == "DATE_OVERRIDE" and (date_from is None or (date_to is not None and date_to != date_from)):
        raise ValueError("DATE_OVERRIDE requires date_from (date_to must be empty or equal)")
    if rule_type == "DATE_RANGE" and (date_from is None or date_to is None):
        raise ValueError("DATE_RANGE requires date_from and date_to")
    if date_from is not None and date_to is not None and date_to < date_from:  # type: ignore[operator]
        raise ValueError("date_to must be on or after date_from")
    if g("promo_code") is not None and rule_type != "PROMO":
        raise ValueError("promo_code is only allowed on PROMO rules")
    vf, vt = g("valid_from"), g("valid_to")
    for v in (vf, vt):
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError("valid_from/valid_to must include a timezone offset")
    if vf is not None and vt is not None and vt <= vf:  # type: ignore[operator]
        raise ValueError("valid_to must be after valid_from")


class PricingRuleCreate(_RuleFields):
    rule_type: RuleType

    @model_validator(mode="after")
    def _shape(self) -> PricingRuleCreate:
        check_rule_shape(self.rule_type, self)
        return self


class PricingRuleUpdate(BaseModel):
    """Partial update; the merged result is re-validated with the same rules as create."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=100)
    day_type: DayType | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_guests: int | None = Field(default=None, ge=1, le=1000)
    promo_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,32}$")
    price_per_person: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    discount_pct: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    priority: int | None = Field(default=None, ge=-100, le=100)
    is_active: bool | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class PricingRuleOut(ORMModel):
    id: uuid.UUID
    package_id: uuid.UUID | None
    rule_type: str
    name: str
    day_type: str | None
    date_from: date | None
    date_to: date | None
    min_guests: int | None
    promo_code: str | None
    price_per_person: Decimal | None
    discount_pct: Decimal | None
    priority: int
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None


def quote_out(
    b: PriceBreakdown, quote_id: str | None = None, expires_at: datetime | None = None
) -> PriceQuoteOut:
    return PriceQuoteOut(
        package_id=b.package_id,
        date=b.play_date,
        day_type=b.day_type,
        guest_count=b.guest_count,
        price_per_person=b.price_per_person,
        subtotal=b.subtotal,
        discounts=[
            DiscountOut(rule_id=d.rule_id, name=d.name, pct=d.pct, amount=d.amount) for d in b.discounts
        ],
        discount_total=b.discount_total,
        charges=[ChargeOut(code=c.code, label=c.label, amount=c.amount) for c in b.charges],
        charges_total=b.charges_total,
        tax=TaxOut(rate=b.tax_rate, amount=b.tax_amount, included=b.prices_include_tax),
        total=b.total,
        currency=b.currency,
        rules_applied=list(b.rules_applied),
        quote_id=quote_id,
        quote_expires_at=expires_at,
    )
