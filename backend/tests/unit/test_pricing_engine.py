"""Pricing engine unit tests (PRC-*). Prices mirror the website seed (Mon-Thu weekday, Fri-Sun weekend)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import GuestCountInvalidError, PricingNotConfiguredError
from app.services.pricing_engine import (
    ExtraCharge,
    PackageView,
    PricingConfig,
    PricingInput,
    RuleView,
    calculate,
    day_type_for,
    money,
)

D = Decimal
EXPERT = PackageView(id=uuid.uuid4(), min_guests=1, max_guests=16)
OTHER = PackageView(id=uuid.uuid4(), min_guests=1, max_guests=16)
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
FRI_SAT_SUN = frozenset({4, 5, 6})

MON = date(2026, 11, 16)
THU = date(2026, 11, 19)
FRI = date(2026, 11, 20)
SAT = date(2026, 11, 21)
SUN = date(2026, 11, 22)


def cfg(**kw: object) -> PricingConfig:
    base: dict[str, object] = {
        "weekend_days": FRI_SAT_SUN,
        "tax_rate": D("18"),
        "prices_include_tax": True,
    }
    base.update(kw)
    return PricingConfig(**base)  # type: ignore[arg-type]


def rule(rule_type: str = "BASE_DAYTYPE", package: PackageView | None = EXPERT, **kw: object) -> RuleView:
    return RuleView(id=uuid.uuid4(), package_id=package.id if package else None, rule_type=rule_type, **kw)  # type: ignore[arg-type]


BASE = [
    rule(day_type="WEEKDAY", price_per_person=D("600")),
    rule(day_type="WEEKEND", price_per_person=D("650")),
]


def quote(
    d: date,
    guests: int = 4,
    rules: list[RuleView] | None = None,
    c: PricingConfig | None = None,
    promo: str | None = None,
    package: PackageView = EXPERT,
    now: datetime = NOW,
):
    return calculate(
        PricingInput(package=package, play_date=d, guest_count=guests, now=now, promo_code=promo),
        BASE if rules is None else rules,
        c or cfg(),
    )


# --- day type -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("d", "expected"),
    [(MON, "WEEKDAY"), (THU, "WEEKDAY"), (FRI, "WEEKEND"), (SAT, "WEEKEND"), (SUN, "WEEKEND")],
)
def test_day_type_fri_to_sun_is_weekend(d: date, expected: str) -> None:
    assert day_type_for(d, FRI_SAT_SUN) == expected


def test_day_type_sat_sun_configuration() -> None:
    assert day_type_for(FRI, frozenset({5, 6})) == "WEEKDAY"


# --- base price -------------------------------------------------------------------------------------


def test_prc001_friday_uses_weekend_price() -> None:
    q = quote(FRI)
    assert q.day_type == "WEEKEND"
    assert q.price_per_person == D("650.00")
    assert q.subtotal == D("2600.00")


def test_weekday_price() -> None:
    q = quote(MON, guests=3)
    assert (q.price_per_person, q.subtotal, q.total) == (D("600.00"), D("1800.00"), D("1800.00"))


def test_tax_extracted_when_inclusive() -> None:
    q = quote(MON, guests=1)
    # 600 * 18/118 = 91.525... -> 91.53
    assert q.tax_amount == D("91.53")
    assert q.total == D("600.00")
    assert q.prices_include_tax is True


def test_tax_added_when_exclusive() -> None:
    q = quote(MON, guests=1, c=cfg(prices_include_tax=False))
    assert q.tax_amount == D("108.00")
    assert q.total == D("708.00")


def test_zero_tax_rate() -> None:
    q = quote(MON, guests=2, c=cfg(tax_rate=D("0"), prices_include_tax=False))
    assert q.tax_amount == D("0.00") and q.total == D("1200.00")


def test_prc003_date_override_beats_daytype() -> None:
    rules = [*BASE, rule("DATE_OVERRIDE", date_from=SAT, price_per_person=D("700"), name="Diwali")]
    q = quote(SAT, rules=rules)
    assert q.price_per_person == D("700.00")
    assert q.base_rule_id == rules[-1].id


def test_date_override_only_on_its_date() -> None:
    rules = [*BASE, rule("DATE_OVERRIDE", date_from=SAT, price_per_person=D("700"))]
    assert quote(SUN, rules=rules).price_per_person == D("650.00")


def test_date_range_beats_daytype_and_respects_bounds() -> None:
    rules = [
        *BASE,
        rule(
            "DATE_RANGE", date_from=date(2026, 12, 20), date_to=date(2026, 12, 31), price_per_person=D("699")
        ),
    ]
    assert quote(date(2026, 12, 20), rules=rules).price_per_person == D("699.00")
    assert quote(date(2026, 12, 31), rules=rules).price_per_person == D("699.00")
    assert quote(date(2027, 1, 1), rules=rules).price_per_person == D("650.00")  # Friday


def test_date_range_without_both_bounds_is_ignored() -> None:
    rules = [*BASE, rule("DATE_RANGE", date_from=MON, price_per_person=D("1"))]
    assert quote(MON, rules=rules).price_per_person == D("600.00")


def test_override_beats_range() -> None:
    rules = [
        *BASE,
        rule("DATE_RANGE", date_from=MON, date_to=SUN, price_per_person=D("610")),
        rule("DATE_OVERRIDE", date_from=THU, price_per_person=D("620")),
    ]
    assert quote(THU, rules=rules).price_per_person == D("620.00")
    assert quote(MON, rules=rules).price_per_person == D("610.00")


def test_package_specific_beats_global_at_same_type() -> None:
    rules = [
        rule(package=None, day_type="WEEKDAY", price_per_person=D("100"), priority=99),
        rule(day_type="WEEKDAY", price_per_person=D("600")),
    ]
    assert quote(MON, rules=rules).price_per_person == D("600.00")


def test_global_rule_used_when_no_package_rule() -> None:
    rules = [rule(package=None, day_type="WEEKDAY", price_per_person=D("500"))]
    assert quote(MON, rules=rules, package=OTHER).price_per_person == D("500.00")


def test_priority_breaks_ties() -> None:
    rules = [
        rule(day_type="WEEKDAY", price_per_person=D("600"), priority=0),
        rule(day_type="WEEKDAY", price_per_person=D("590"), priority=5),
    ]
    assert quote(MON, rules=rules).price_per_person == D("590.00")


def test_other_package_rules_ignored() -> None:
    rules = [rule(package=OTHER, day_type="WEEKDAY", price_per_person=D("1"))]
    with pytest.raises(PricingNotConfiguredError):
        quote(MON, rules=rules)


def test_no_price_configured_raises() -> None:
    with pytest.raises(PricingNotConfiguredError):
        quote(FRI, rules=[rule(day_type="WEEKDAY", price_per_person=D("600"))])


def test_inactive_rule_ignored() -> None:
    rules = [*BASE, rule("DATE_OVERRIDE", date_from=MON, price_per_person=D("1"), is_active=False)]
    assert quote(MON, rules=rules).price_per_person == D("600.00")


def test_validity_window() -> None:
    future = rule("DATE_OVERRIDE", date_from=MON, price_per_person=D("1"), valid_from=NOW + timedelta(days=1))
    expired = rule("DATE_OVERRIDE", date_from=MON, price_per_person=D("2"), valid_to=NOW)
    assert quote(MON, rules=[*BASE, future, expired]).price_per_person == D("600.00")
    assert quote(MON, rules=[*BASE, future], now=NOW + timedelta(days=2)).price_per_person == D("1.00")


# --- discounts --------------------------------------------------------------------------------------


def test_group_discount_applies_at_threshold() -> None:
    rules = [*BASE, rule("GROUP_DISCOUNT", min_guests=10, discount_pct=D("10"), name="Group 10+")]
    assert quote(MON, guests=9, rules=rules).discount_total == D("0.00")
    q = quote(MON, guests=10, rules=rules)
    assert q.subtotal == D("6000.00")
    assert q.discount_total == D("600.00")
    assert q.total == D("5400.00")
    assert q.rules_applied == (rules[0].id, rules[2].id)  # weekday base + group discount


def test_promo_requires_matching_code_case_insensitive() -> None:
    rules = [*BASE, rule("PROMO", promo_code="LASER10", discount_pct=D("10"))]
    assert quote(MON, rules=rules).discount_total == D("0.00")
    assert quote(MON, rules=rules, promo="wrong").discount_total == D("0.00")
    assert quote(MON, rules=rules, promo=" laser10 ").discount_total == D("240.00")


def test_promo_without_code_is_automatic() -> None:
    rules = [*BASE, rule("PROMO", discount_pct=D("5"), day_type="WEEKDAY")]
    assert quote(MON, rules=rules).discount_total == D("120.00")
    assert quote(SAT, rules=rules).discount_total == D("0.00")


def test_best_discount_only_by_default() -> None:
    rules = [
        *BASE,
        rule("PROMO", discount_pct=D("5")),
        rule("GROUP_DISCOUNT", min_guests=2, discount_pct=D("10")),
    ]
    q = quote(MON, guests=4, rules=rules)
    assert len(q.discounts) == 1 and q.discounts[0].pct == D("10")
    assert q.discount_total == D("240.00")


def test_stacked_discounts_compound() -> None:
    rules = [
        *BASE,
        rule("PROMO", discount_pct=D("10"), priority=2),
        rule("GROUP_DISCOUNT", min_guests=2, discount_pct=D("10"), priority=1),
    ]
    q = quote(MON, guests=4, rules=rules, c=cfg(discount_stacking="STACK"))
    # 2400 -> -240 -> 2160 -> -216 -> 1944
    assert [d.amount for d in q.discounts] == [D("240.00"), D("216.00")]
    assert q.total == D("1944.00")


def test_hundred_percent_discount_gives_zero_total() -> None:
    rules = [*BASE, rule("PROMO", promo_code="FREE", discount_pct=D("100"))]
    q = quote(MON, rules=rules, promo="FREE")
    assert q.total == D("0.00") and q.tax_amount == D("0.00")


def test_discount_rule_for_other_package_ignored() -> None:
    rules = [*BASE, rule("PROMO", package=OTHER, discount_pct=D("50"))]
    assert quote(MON, rules=rules).discount_total == D("0.00")


def test_global_discount_applies_to_all_packages() -> None:
    rules = [*BASE, rule("PROMO", package=None, discount_pct=D("50"))]
    assert quote(MON, rules=rules).discount_total == D("1200.00")


# --- extra charges ------------------------------------------------------------------------------------


def test_extra_charges_flat_and_per_person_inclusive_tax() -> None:
    c = cfg(
        extra_charges=(
            ExtraCharge("PARTY_SETUP", "Party setup", "FLAT", D("500")),
            ExtraCharge("SOCKS", "Grip socks", "PER_PERSON", D("50")),
        )
    )
    q = quote(MON, guests=4, c=c)
    assert q.charges_total == D("700.00")
    assert q.total == D("3100.00")
    assert q.tax_amount == money(D("3100") * 18 / 118)


def test_charges_added_after_discount_exclusive_tax() -> None:
    rules = [*BASE, rule("PROMO", discount_pct=D("10"))]
    c = cfg(prices_include_tax=False, extra_charges=(ExtraCharge("X", "X", "FLAT", D("100")),))
    q = quote(MON, guests=1, rules=rules, c=c)
    # 600 - 60 + 100 = 640; tax 115.20; total 755.20
    assert (q.tax_amount, q.total) == (D("115.20"), D("755.20"))


# --- guests & rounding -------------------------------------------------------------------------------


@pytest.mark.parametrize("guests", [0, -1, 17])
def test_guest_count_outside_package_limits(guests: int) -> None:
    with pytest.raises(GuestCountInvalidError):
        quote(MON, guests=guests)


def test_package_minimum_enforced() -> None:
    pkg = PackageView(id=EXPERT.id, min_guests=4, max_guests=16)
    with pytest.raises(GuestCountInvalidError):
        quote(MON, guests=3, package=pkg)
    assert quote(MON, guests=4, package=pkg).subtotal == D("2400.00")


def test_rounding_half_up_on_paise() -> None:
    rules = [rule(day_type="WEEKDAY", price_per_person=D("333.33")), rule("PROMO", discount_pct=D("12.5"))]
    q = quote(MON, guests=3, rules=rules)
    assert q.subtotal == D("999.99")
    assert q.discount_total == D("125.00")  # 124.99875 -> 125.00
    assert q.total == D("874.99")


def test_breakdown_is_deterministic() -> None:
    assert quote(SAT) == quote(SAT)
