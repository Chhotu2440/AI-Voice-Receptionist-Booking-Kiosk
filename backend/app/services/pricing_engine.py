"""Pure pricing engine: no I/O, fully deterministic, exhaustively unit-tested.

Resolution rules (documented in docs/08-database-design.md and admin help):

1. A rule is *applicable* when it is active, inside its validity window (valid_from/valid_to vs. now),
   targets this package (or all packages when package_id is NULL), and every optional condition it sets
   matches: day_type, date range, min_guests, promo_code.
     - DATE_OVERRIDE matches only when date_from == play date.
     - DATE_RANGE requires both date_from and date_to and matches dates inside the range (inclusive).
     - PROMO with a promo_code applies only when the customer supplies that code (case-insensitive);
       PROMO without a code is an automatic promotion.
2. Base price per person = the applicable rule with a price, ranked by
   (rule type: DATE_OVERRIDE > DATE_RANGE > BASE_DAYTYPE, package-specific > global, priority desc).
   No base price -> PricingNotConfiguredError (never fall back to a guess).
3. Discounts (PROMO, GROUP_DISCOUNT with discount_pct): "BEST" applies the single largest discount;
   "STACK" compounds all of them in priority order.
4. Extra charges (configured in settings) are added after discounts.
5. Tax: if prices include tax, tax is extracted from the total; otherwise it is added on top.
All money is Decimal, rounded half-up to paise at each line item.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.core.exceptions import GuestCountInvalidError, PricingNotConfiguredError

PAISE = Decimal("0.01")
HUNDRED = Decimal(100)
WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
BASE_RULE_RANK = {"DATE_OVERRIDE": 3, "DATE_RANGE": 2, "BASE_DAYTYPE": 1}
DISCOUNT_RULE_TYPES = ("PROMO", "GROUP_DISCOUNT")

DayType = Literal["WEEKDAY", "WEEKEND"]


def money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class RuleView:
    id: uuid.UUID
    package_id: uuid.UUID | None
    rule_type: str
    name: str = ""
    day_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_guests: int | None = None
    promo_code: str | None = None
    price_per_person: Decimal | None = None
    discount_pct: Decimal | None = None
    priority: int = 0
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True)
class ExtraCharge:
    code: str
    label: str
    mode: Literal["FLAT", "PER_PERSON"]
    amount: Decimal


@dataclass(frozen=True)
class PricingConfig:
    weekend_days: frozenset[int]  # 0 = Monday
    tax_rate: Decimal
    prices_include_tax: bool
    discount_stacking: Literal["BEST", "STACK"] = "BEST"
    extra_charges: tuple[ExtraCharge, ...] = ()
    currency: str = "INR"


@dataclass(frozen=True)
class PackageView:
    id: uuid.UUID
    min_guests: int
    max_guests: int


@dataclass(frozen=True)
class PricingInput:
    package: PackageView
    play_date: date
    guest_count: int
    now: datetime
    promo_code: str | None = None


@dataclass(frozen=True)
class DiscountLine:
    rule_id: uuid.UUID
    name: str
    pct: Decimal
    amount: Decimal


@dataclass(frozen=True)
class ChargeLine:
    code: str
    label: str
    amount: Decimal


@dataclass(frozen=True)
class PriceBreakdown:
    package_id: uuid.UUID
    play_date: date
    day_type: DayType
    guest_count: int
    price_per_person: Decimal
    subtotal: Decimal
    discounts: tuple[DiscountLine, ...]
    discount_total: Decimal
    charges: tuple[ChargeLine, ...]
    charges_total: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    prices_include_tax: bool
    total: Decimal
    currency: str
    base_rule_id: uuid.UUID
    rules_applied: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def day_type_for(d: date, weekend_days: frozenset[int]) -> DayType:
    return "WEEKEND" if d.weekday() in weekend_days else "WEEKDAY"


def validate_guest_count(package: PackageView, guest_count: int) -> None:
    if guest_count < 1 or guest_count < package.min_guests or guest_count > package.max_guests:
        raise GuestCountInvalidError(
            f"This package is for {package.min_guests} to {package.max_guests} players.",
            details={"min_guests": package.min_guests, "max_guests": package.max_guests},
        )


def _is_applicable(rule: RuleView, inp: PricingInput, day_type: DayType) -> bool:
    if not rule.is_active:
        return False
    if rule.valid_from is not None and inp.now < rule.valid_from:
        return False
    if rule.valid_to is not None and inp.now >= rule.valid_to:
        return False
    if rule.package_id is not None and rule.package_id != inp.package.id:
        return False
    if rule.day_type is not None and rule.day_type != day_type:
        return False
    if rule.min_guests is not None and inp.guest_count < rule.min_guests:
        return False

    d = inp.play_date
    if rule.rule_type == "DATE_OVERRIDE":
        return rule.date_from == d
    if rule.rule_type == "DATE_RANGE" and (rule.date_from is None or rule.date_to is None):
        return False
    if rule.date_from is not None and d < rule.date_from:
        return False
    if rule.date_to is not None and d > rule.date_to:
        return False

    if rule.rule_type == "PROMO" and rule.promo_code:
        return (
            inp.promo_code is not None and inp.promo_code.strip().upper() == rule.promo_code.strip().upper()
        )
    return True


def _base_rank(rule: RuleView) -> tuple[int, int, int]:
    return (BASE_RULE_RANK[rule.rule_type], 1 if rule.package_id is not None else 0, rule.priority)


def calculate(inp: PricingInput, rules: list[RuleView], cfg: PricingConfig) -> PriceBreakdown:
    validate_guest_count(inp.package, inp.guest_count)
    day_type = day_type_for(inp.play_date, cfg.weekend_days)
    applicable = [r for r in rules if _is_applicable(r, inp, day_type)]

    base_candidates = [
        r for r in applicable if r.rule_type in BASE_RULE_RANK and r.price_per_person is not None
    ]
    if not base_candidates:
        raise PricingNotConfiguredError(details={"play_date": inp.play_date.isoformat()})
    base_rule = max(base_candidates, key=_base_rank)
    assert base_rule.price_per_person is not None
    price_per_person = money(base_rule.price_per_person)
    subtotal = money(price_per_person * inp.guest_count)

    discount_rules = sorted(
        (r for r in applicable if r.rule_type in DISCOUNT_RULE_TYPES and r.discount_pct),
        key=lambda r: (r.priority, r.discount_pct or 0),
        reverse=True,
    )
    if cfg.discount_stacking == "BEST" and discount_rules:
        discount_rules = [max(discount_rules, key=lambda r: (r.discount_pct or 0, r.priority))]

    discounts: list[DiscountLine] = []
    running = subtotal
    for rule in discount_rules:
        assert rule.discount_pct is not None
        amount = money(running * rule.discount_pct / HUNDRED)
        if amount <= 0:
            continue
        discounts.append(DiscountLine(rule.id, rule.name, rule.discount_pct, amount))
        running -= amount
    discount_total = money(sum((d.amount for d in discounts), Decimal(0)))

    charges = tuple(
        ChargeLine(
            c.code,
            c.label,
            money(c.amount * inp.guest_count if c.mode == "PER_PERSON" else c.amount),
        )
        for c in cfg.extra_charges
    )
    charges_total = money(sum((c.amount for c in charges), Decimal(0)))

    taxable = subtotal - discount_total + charges_total
    if cfg.prices_include_tax:
        total = money(taxable)
        tax_amount = money(total * cfg.tax_rate / (HUNDRED + cfg.tax_rate))
    else:
        tax_amount = money(taxable * cfg.tax_rate / HUNDRED)
        total = money(taxable + tax_amount)

    return PriceBreakdown(
        package_id=inp.package.id,
        play_date=inp.play_date,
        day_type=day_type,
        guest_count=inp.guest_count,
        price_per_person=price_per_person,
        subtotal=subtotal,
        discounts=tuple(discounts),
        discount_total=discount_total,
        charges=charges,
        charges_total=charges_total,
        tax_rate=cfg.tax_rate,
        tax_amount=tax_amount,
        prices_include_tax=cfg.prices_include_tax,
        total=total,
        currency=cfg.currency,
        base_rule_id=base_rule.id,
        rules_applied=(base_rule.id, *(d.rule_id for d in discounts)),
    )
