"""Admin booking management (/admin/bookings, /admin/slot-holds, /admin/enquiries)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, SettingsDep, require_permission, user_actor
from app.models.identity import User
from app.repositories import booking as booking_repo
from app.schemas.booking import (
    AdminBookingOut,
    AdminEnquiryOut,
    BookingCreate,
    BookingOut,
    CancelRequest,
    EnquiryUpdate,
    HoldCreate,
    HoldOut,
    RescheduleRequest,
    StatusUpdate,
)
from app.schemas.common import Page, PageParams
from app.services import booking_service, enquiry_service, hold_service, idempotency, notification_service
from app.services.phone import normalize_indian_mobile

router = APIRouter(prefix="/admin", tags=["admin-bookings"])
Paging = Annotated[PageParams, Depends()]
STAFF = "STAFF"
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]


def perm(*codes: str) -> Any:
    return Depends(require_permission(*codes))


@router.get("/bookings", response_model=Page[AdminBookingOut])
async def list_bookings(
    session: SessionDep,
    settings: SettingsDep,
    paging: Paging,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    status: Annotated[list[str] | None, Query()] = None,
    phone: str | None = None,
    reference: str | None = None,
    _: User = perm("booking.read"),
) -> Page[AdminBookingOut]:
    rows, total = await booking_repo.search_bookings(
        session,
        date_from=date_from,
        date_to=date_to,
        statuses=status,
        phone_e164=normalize_indian_mobile(phone) if phone else None,
        reference=reference,
        offset=paging.offset,
        limit=paging.page_size,
    )
    items = [await booking_service.admin_booking_out(session, settings, b) for b in rows]
    return Page(items=items, page=paging.page, page_size=paging.page_size, total=total)


@router.get("/bookings/{booking_id}", response_model=AdminBookingOut)
async def get_booking(
    booking_id: uuid.UUID, session: SessionDep, settings: SettingsDep, _: User = perm("booking.read")
) -> AdminBookingOut:
    return await booking_service.admin_booking_out(
        session, settings, await booking_service.get_admin(session, booking_id)
    )


@router.post("/slot-holds", response_model=HoldOut, status_code=201)
async def staff_hold(
    body: HoldCreate,
    session: SessionDep,
    settings: SettingsDep,
    idempotency_key: IdempotencyKeyHeader = None,
    user: User = perm("booking.write"),
) -> JSONResponse:
    code, payload = await hold_service.create_hold(
        session,
        settings,
        body,
        channel=STAFF,
        idempotency_key=idempotency.validate_key(idempotency_key),
        created_by=user.id,
    )
    return JSONResponse(status_code=code, content=payload)


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def staff_booking(
    body: BookingCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    idempotency_key: IdempotencyKeyHeader = None,
    user: User = perm("booking.write"),
) -> JSONResponse:
    code, payload = await booking_service.create_booking(
        session,
        settings,
        body,
        channel=STAFF,
        idempotency_key=idempotency.validate_key(idempotency_key),
        actor=user_actor(user, request),
    )
    notification_service.schedule_send(request.app.state.sessionmaker, settings)
    return JSONResponse(status_code=code, content=payload)


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    body: CancelRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: User = perm("booking.write"),
) -> AdminBookingOut:
    booking = await booking_service.cancel(session, booking_id, body.reason, user_actor(user, request))
    return await booking_service.admin_booking_out(session, settings, booking)


@router.post("/bookings/{booking_id}/reschedule", response_model=AdminBookingOut)
async def reschedule_booking(
    booking_id: uuid.UUID,
    body: RescheduleRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: User = perm("booking.write"),
) -> AdminBookingOut:
    booking = await booking_service.reschedule(
        session, settings, booking_id, body.hold_id, body.hold_token, body.reason, user_actor(user, request)
    )
    return await booking_service.admin_booking_out(session, settings, booking)


@router.post("/bookings/{booking_id}/status", response_model=AdminBookingOut)
async def update_status(
    booking_id: uuid.UUID,
    body: StatusUpdate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: User = perm("booking.write"),
) -> AdminBookingOut:
    booking = await booking_service.update_status(session, booking_id, body, user_actor(user, request))
    return await booking_service.admin_booking_out(session, settings, booking)


@router.get("/enquiries", response_model=Page[AdminEnquiryOut])
async def list_enquiries(
    session: SessionDep,
    paging: Paging,
    status: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
    _: User = perm("enquiry.manage"),
) -> Page[AdminEnquiryOut]:
    rows, total = await enquiry_service.search(session, status, q, paging.offset, paging.page_size)
    items = [await enquiry_service.admin_out(session, e) for e in rows]
    return Page(items=items, page=paging.page, page_size=paging.page_size, total=total)


@router.patch("/enquiries/{enquiry_id}", response_model=AdminEnquiryOut)
async def update_enquiry(
    enquiry_id: uuid.UUID,
    body: EnquiryUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("enquiry.manage"),
) -> AdminEnquiryOut:
    enquiry = await enquiry_service.update(session, enquiry_id, body, user_actor(user, request))
    return await enquiry_service.admin_out(session, enquiry)
