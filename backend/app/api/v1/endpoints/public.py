"""Public/kiosk catalogue and pricing endpoints. Read-only; rate limited per IP."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, SettingsDep, rate_limit
from app.core.exceptions import ValidationFailed
from app.repositories import catalogue as catalogue_repo
from app.schemas.catalogue import OccasionOut, PackageOut, PublicPackageOut
from app.schemas.pricing import ChargeOut, DiscountOut, PriceQuoteOut, PriceRequest, TaxOut
from app.schemas.schedule import BusinessHoursDay, BusinessInfoPublic
from app.services import package_service, pricing_service, schedule_service
from app.services.pricing_engine import PriceBreakdown

router = APIRouter(
    tags=["catalogue"], dependencies=[Depends(rate_limit("public", "public_rate_limit_per_minute"))]
)


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


@router.get("/packages", response_model=list[PublicPackageOut])
async def list_packages(
    session: SessionDep,
    date_: Annotated[date | None, Query(alias="date")] = None,
    guests: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> list[PublicPackageOut]:
    rows = await package_service.list_public(session, date_, guests)
    return [
        PublicPackageOut(**PackageOut.model_validate(p).model_dump(), pricing=preview) for p, preview in rows
    ]


@router.get("/packages/{package_id}", response_model=PackageOut)
async def get_package(package_id: uuid.UUID, session: SessionDep) -> PackageOut:
    return PackageOut.model_validate(await package_service.get_active(session, package_id))


@router.get("/occasions", response_model=list[OccasionOut])
async def list_occasions(session: SessionDep) -> list[OccasionOut]:
    return [
        OccasionOut.model_validate(o) for o in await catalogue_repo.list_occasions(session, active_only=True)
    ]


@router.get("/business-info", response_model=BusinessInfoPublic)
async def business_info(session: SessionDep) -> BusinessInfoPublic:
    location = await schedule_service.primary_location(session)
    hours = await schedule_service.get_hours(session)
    return BusinessInfoPublic.model_validate(
        {
            **{k: getattr(location, k) for k in BusinessInfoPublic.model_fields if k != "hours"},
            "hours": [BusinessHoursDay.model_validate(h) for h in hours],
        }
    )


@router.post("/pricing/calculate", response_model=PriceQuoteOut)
async def calculate_price(body: PriceRequest, session: SessionDep, settings: SettingsDep) -> PriceQuoteOut:
    if body.occasion_code is not None:
        occasion = await catalogue_repo.get_occasion(session, body.occasion_code)
        if occasion is None or not occasion.is_active:
            raise ValidationFailed("Unknown occasion.", details={"occasion_code": body.occasion_code})
    breakdown, quote_id, expires_at = await pricing_service.quote(
        session, settings, body.package_id, body.date, body.guest_count, promo_code=body.promo_code
    )
    return quote_out(breakdown, quote_id, expires_at)
