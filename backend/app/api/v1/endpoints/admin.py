"""Admin API (/admin/*). Every route requires an admin JWT and a specific permission."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, SettingsDep, require_permission, user_actor
from app.core.exceptions import ForbiddenError
from app.core.timeutil import today_local
from app.models.identity import User
from app.repositories import catalogue as catalogue_repo
from app.repositories import users as users_repo
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.catalogue import (
    GameFormatIn,
    GameFormatOut,
    GameFormatUpdate,
    OccasionOut,
    OccasionUpdate,
    PackageCreate,
    PackageOut,
    PackageUpdate,
)
from app.schemas.common import Page, PageParams
from app.schemas.pricing import (
    PriceQuoteOut,
    PriceRequest,
    PricingRuleCreate,
    PricingRuleOut,
    PricingRuleUpdate,
    quote_out,
)
from app.schemas.schedule import (
    BusinessHoursDay,
    BusinessHoursPut,
    BusinessInfoOut,
    BusinessInfoUpdate,
    ResourceIn,
    ResourceOut,
    ResourceUpdate,
    ScheduleExceptionIn,
    ScheduleExceptionOut,
)
from app.services import (
    package_service,
    pricing_service,
    schedule_service,
    settings_service,
    user_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])

Paging = Annotated[PageParams, Depends()]


def perm(*codes: str) -> Any:
    return Depends(require_permission(*codes))


# --- packages ---------------------------------------------------------------------------------------


@router.get("/packages", response_model=Page[PackageOut])
async def admin_list_packages(
    session: SessionDep, paging: Paging, _: User = perm("catalogue.write")
) -> Page[PackageOut]:
    rows, total = await catalogue_repo.list_packages(
        session, active_only=False, offset=paging.offset, limit=paging.page_size
    )
    return Page(
        items=[PackageOut.model_validate(p) for p in rows],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


@router.post("/packages", response_model=PackageOut, status_code=status.HTTP_201_CREATED)
async def admin_create_package(
    body: PackageCreate, request: Request, session: SessionDep, user: User = perm("catalogue.write")
) -> PackageOut:
    return PackageOut.model_validate(await package_service.create(session, body, user_actor(user, request)))


@router.get("/packages/{package_id}", response_model=PackageOut)
async def admin_get_package(
    package_id: uuid.UUID, session: SessionDep, _: User = perm("catalogue.write")
) -> PackageOut:
    return PackageOut.model_validate(await package_service.get_any(session, package_id))


@router.patch("/packages/{package_id}", response_model=PackageOut)
async def admin_update_package(
    package_id: uuid.UUID,
    body: PackageUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("catalogue.write"),
) -> PackageOut:
    package = await package_service.update(session, package_id, body, user_actor(user, request))
    return PackageOut.model_validate(package)


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_package(
    package_id: uuid.UUID, request: Request, session: SessionDep, user: User = perm("catalogue.write")
) -> None:
    await package_service.soft_delete(session, package_id, user_actor(user, request))


# --- game formats (what is played in each package) -------------------------------------------------


@router.get("/game-formats", response_model=list[GameFormatOut])
async def admin_list_games(session: SessionDep, _: User = perm("catalogue.write")) -> list[GameFormatOut]:
    return [GameFormatOut.model_validate(g) for g in await package_service.list_games(session)]


@router.post("/game-formats", response_model=GameFormatOut, status_code=status.HTTP_201_CREATED)
async def admin_create_game(
    body: GameFormatIn, request: Request, session: SessionDep, user: User = perm("catalogue.write")
) -> GameFormatOut:
    return GameFormatOut.model_validate(
        await package_service.create_game(session, body, user_actor(user, request))
    )


@router.patch("/game-formats/{game_id}", response_model=GameFormatOut)
async def admin_update_game(
    game_id: uuid.UUID,
    body: GameFormatUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("catalogue.write"),
) -> GameFormatOut:
    return GameFormatOut.model_validate(
        await package_service.update_game(session, game_id, body, user_actor(user, request))
    )


# --- occasions --------------------------------------------------------------------------------------


@router.get("/occasions", response_model=list[OccasionOut])
async def admin_list_occasions(session: SessionDep, _: User = perm("catalogue.write")) -> list[OccasionOut]:
    return [
        OccasionOut.model_validate(o) for o in await catalogue_repo.list_occasions(session, active_only=False)
    ]


@router.patch("/occasions/{code}", response_model=OccasionOut)
async def admin_update_occasion(
    code: str,
    body: OccasionUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("catalogue.write"),
) -> OccasionOut:
    return OccasionOut.model_validate(
        await package_service.update_occasion(session, code, body, user_actor(user, request))
    )


# --- pricing ----------------------------------------------------------------------------------------


@router.get("/pricing-rules", response_model=Page[PricingRuleOut])
async def admin_list_rules(
    session: SessionDep,
    paging: Paging,
    package_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    _: User = perm("pricing.write"),
) -> Page[PricingRuleOut]:
    rows, total = await catalogue_repo.list_rules(
        session,
        package_id=package_id,
        include_inactive=include_inactive,
        offset=paging.offset,
        limit=paging.page_size,
    )
    return Page(
        items=[PricingRuleOut.model_validate(r) for r in rows],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


@router.post("/pricing-rules", response_model=PricingRuleOut, status_code=status.HTTP_201_CREATED)
async def admin_create_rule(
    body: PricingRuleCreate, request: Request, session: SessionDep, user: User = perm("pricing.write")
) -> PricingRuleOut:
    return PricingRuleOut.model_validate(
        await pricing_service.create_rule(session, body, user_actor(user, request))
    )


@router.patch("/pricing-rules/{rule_id}", response_model=PricingRuleOut)
async def admin_update_rule(
    rule_id: uuid.UUID,
    body: PricingRuleUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("pricing.write"),
) -> PricingRuleOut:
    return PricingRuleOut.model_validate(
        await pricing_service.update_rule(session, rule_id, body, user_actor(user, request))
    )


@router.delete("/pricing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_deactivate_rule(
    rule_id: uuid.UUID, request: Request, session: SessionDep, user: User = perm("pricing.write")
) -> None:
    await pricing_service.deactivate_rule(session, rule_id, user_actor(user, request))


@router.post("/pricing/preview", response_model=PriceQuoteOut)
async def admin_price_preview(
    body: PriceRequest, session: SessionDep, settings: SettingsDep, _: User = perm("pricing.write")
) -> PriceQuoteOut:
    """Same engine as customers, but without the booking-window restriction (to check future prices)."""
    breakdown, _q, _e = await pricing_service.quote(
        session,
        settings,
        body.package_id,
        body.date,
        body.guest_count,
        promo_code=body.promo_code,
        enforce_window=False,
    )
    return quote_out(breakdown)


# --- settings ---------------------------------------------------------------------------------------

SETTINGS_WRITE_PERMISSION = {"pricing": "pricing.write", "booking": "settings.write", "ai": "ai.config"}


@router.get("/settings/{section}")
async def admin_get_settings(
    section: str, session: SessionDep, _: User = perm("schedule.read")
) -> dict[str, Any]:
    model: BaseModel = await settings_service.get_section(session, section)
    return model.model_dump(mode="json")


@router.put("/settings/{section}")
async def admin_put_settings(
    section: str, body: dict[str, Any], request: Request, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    required = SETTINGS_WRITE_PERMISSION.get(section, "settings.write")
    if required not in user.permission_codes:
        raise ForbiddenError()
    model = await settings_service.update_section(session, section, body, user_actor(user, request))
    return model.model_dump(mode="json")


# --- schedule ---------------------------------------------------------------------------------------


@router.get("/business-info", response_model=BusinessInfoOut)
async def admin_get_business_info(session: SessionDep, _: User = perm("schedule.read")) -> BusinessInfoOut:
    return BusinessInfoOut.model_validate(await schedule_service.primary_location(session))


@router.patch("/business-info", response_model=BusinessInfoOut)
async def admin_update_business_info(
    body: BusinessInfoUpdate, request: Request, session: SessionDep, user: User = perm("settings.write")
) -> BusinessInfoOut:
    return BusinessInfoOut.model_validate(
        await schedule_service.update_business_info(session, body, user_actor(user, request))
    )


@router.get("/schedule/hours", response_model=list[BusinessHoursDay])
async def admin_get_hours(session: SessionDep, _: User = perm("schedule.read")) -> list[BusinessHoursDay]:
    return [BusinessHoursDay.model_validate(h) for h in await schedule_service.get_hours(session)]


@router.put("/schedule/hours", response_model=list[BusinessHoursDay])
async def admin_put_hours(
    body: BusinessHoursPut, request: Request, session: SessionDep, user: User = perm("schedule.write")
) -> list[BusinessHoursDay]:
    rows = await schedule_service.put_hours(session, body, user_actor(user, request))
    return [BusinessHoursDay.model_validate(h) for h in rows]


@router.get("/schedule/exceptions", response_model=list[ScheduleExceptionOut])
async def admin_list_exceptions(
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    _: User = perm("schedule.read"),
) -> list[ScheduleExceptionOut]:
    start = date_from or today_local()
    end = date_to or (start + timedelta(days=90))
    rows = await schedule_service.list_exceptions(session, start, end)
    return [ScheduleExceptionOut.model_validate(r) for r in rows]


@router.post("/schedule/exceptions", response_model=ScheduleExceptionOut, status_code=status.HTTP_201_CREATED)
async def admin_create_exception(
    body: ScheduleExceptionIn, request: Request, session: SessionDep, user: User = perm("schedule.write")
) -> ScheduleExceptionOut:
    return ScheduleExceptionOut.model_validate(
        await schedule_service.create_exception(session, body, user_actor(user, request))
    )


@router.delete("/schedule/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_exception(
    exception_id: uuid.UUID, request: Request, session: SessionDep, user: User = perm("schedule.write")
) -> None:
    await schedule_service.delete_exception(session, exception_id, user_actor(user, request))


@router.get("/resources", response_model=list[ResourceOut])
async def admin_list_resources(session: SessionDep, _: User = perm("schedule.read")) -> list[ResourceOut]:
    return [ResourceOut.model_validate(r) for r in await schedule_service.list_resources(session)]


@router.post("/resources", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def admin_create_resource(
    body: ResourceIn, request: Request, session: SessionDep, user: User = perm("schedule.write")
) -> ResourceOut:
    return ResourceOut.model_validate(
        await schedule_service.create_resource(session, body, user_actor(user, request))
    )


@router.patch("/resources/{resource_id}", response_model=ResourceOut)
async def admin_update_resource(
    resource_id: uuid.UUID,
    body: ResourceUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("schedule.write"),
) -> ResourceOut:
    return ResourceOut.model_validate(
        await schedule_service.update_resource(session, resource_id, body, user_actor(user, request))
    )


# --- users ------------------------------------------------------------------------------------------


def _user_out(u: User) -> UserOut:
    return UserOut.model_validate(u)


@router.get("/users", response_model=Page[UserOut])
async def admin_list_users(
    session: SessionDep, paging: Paging, _: User = perm("user.manage")
) -> Page[UserOut]:
    rows, total = await users_repo.list_users(session, paging.offset, paging.page_size)
    return Page(items=[_user_out(u) for u in rows], page=paging.page, page_size=paging.page_size, total=total)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: UserCreate, request: Request, session: SessionDep, user: User = perm("user.manage")
) -> UserOut:
    created = await user_service.create_user(
        session, body.email, body.name, body.password, body.roles, user_actor(user, request)
    )
    return _user_out(created)


@router.patch("/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("user.manage"),
) -> UserOut:
    updated = await user_service.update_user(
        session,
        user_id,
        user_actor(user, request),
        name=body.name,
        is_active=body.is_active,
        role_codes=body.roles,
        password=body.password,
    )
    return _user_out(updated)
