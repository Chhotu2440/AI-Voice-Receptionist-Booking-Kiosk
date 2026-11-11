"""Public booking flow: availability -> hold -> booking, plus event enquiries.

Channel is WEB until kiosk device authentication (KIOSK-01) is in place; the kiosk will then call the
same services with channel KIOSK. Unsafe POSTs require an Idempotency-Key header.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, SettingsDep, public_actor, rate_limit
from app.schemas.booking import (
    AvailabilityRequest,
    BookingCreate,
    BookingOut,
    DateStatusOut,
    DaySlotsOut,
    EnquiryCreate,
    EnquiryOut,
    HoldCreate,
    HoldOut,
    HoldStatusOut,
)
from app.services import (
    availability_service,
    booking_service,
    enquiry_service,
    hold_service,
    idempotency,
    notification_service,
)

PUBLIC_CHANNEL = "WEB"

router = APIRouter(
    tags=["booking"], dependencies=[Depends(rate_limit("public", "public_rate_limit_per_minute"))]
)
write_limit = Depends(rate_limit("booking-write", "booking_rate_limit_per_minute"))

IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
HoldTokenHeader = Annotated[str | None, Header(alias="X-Hold-Token")]
BookingTokenHeader = Annotated[str | None, Header(alias="X-Booking-Token")]


@router.post("/availability/slots", response_model=DaySlotsOut)
async def availability_slots(body: AvailabilityRequest, session: SessionDep) -> DaySlotsOut:
    return await availability_service.slots_for_day(session, body.package_id, body.date, body.guest_count)


@router.get("/availability/dates", response_model=list[DateStatusOut])
async def availability_dates(
    session: SessionDep,
    package_id: uuid.UUID,
    guests: Annotated[int, Query(ge=1, le=1000)],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> list[DateStatusOut]:
    return await availability_service.dates(session, package_id, guests, date_from, date_to)


@router.post("/slot-holds", response_model=HoldOut, status_code=201, dependencies=[write_limit])
async def create_hold(
    body: HoldCreate, session: SessionDep, settings: SettingsDep, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    code, payload = await hold_service.create_hold(
        session,
        settings,
        body,
        channel=PUBLIC_CHANNEL,
        idempotency_key=idempotency.validate_key(idempotency_key),
    )
    return JSONResponse(status_code=code, content=payload)


@router.get("/slot-holds/{hold_id}", response_model=HoldStatusOut)
async def get_hold(
    hold_id: uuid.UUID, session: SessionDep, settings: SettingsDep, x_hold_token: HoldTokenHeader = None
) -> HoldStatusOut:
    return await hold_service.get_status(session, settings, hold_id, x_hold_token)


@router.post("/slot-holds/{hold_id}/extend", response_model=HoldStatusOut)
async def extend_hold(
    hold_id: uuid.UUID, session: SessionDep, settings: SettingsDep, x_hold_token: HoldTokenHeader = None
) -> HoldStatusOut:
    return await hold_service.extend_hold(session, settings, hold_id, x_hold_token)


@router.delete("/slot-holds/{hold_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(
    hold_id: uuid.UUID, session: SessionDep, settings: SettingsDep, x_hold_token: HoldTokenHeader = None
) -> Response:
    await hold_service.release_hold(session, settings, hold_id, x_hold_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bookings", response_model=BookingOut, status_code=201, dependencies=[write_limit])
async def create_booking(
    body: BookingCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    code, payload = await booking_service.create_booking(
        session,
        settings,
        body,
        channel=PUBLIC_CHANNEL,
        idempotency_key=idempotency.validate_key(idempotency_key),
        actor=public_actor(request),
    )
    notification_service.schedule_send(request.app.state.sessionmaker, settings)
    return JSONResponse(status_code=code, content=payload)


@router.get("/bookings/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    x_booking_token: BookingTokenHeader = None,
) -> BookingOut:
    return await booking_service.get_for_customer(session, settings, booking_id, x_booking_token)


@router.post("/event-enquiries", response_model=EnquiryOut, status_code=201, dependencies=[write_limit])
async def create_enquiry(
    body: EnquiryCreate, request: Request, session: SessionDep, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    code, payload = await enquiry_service.create(
        session,
        body,
        channel=PUBLIC_CHANNEL,
        idempotency_key=idempotency.validate_key(idempotency_key),
        actor=public_actor(request),
    )
    return JSONResponse(status_code=code, content=payload)
