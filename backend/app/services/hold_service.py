"""Temporary slot holds: create, view, extend, release and expire.

Concurrency contract (docs/06 §5):
1. Validate everything that doesn't need locks (package, guests, window, schedule, price).
2. Ensure the grid cells exist (own short transaction).
3. One transaction: idempotency key -> lock cells FOR UPDATE in start order -> verify free capacity
   (releasing any expired holds found on those cells) -> held_qty += units -> insert hold.
The CHECK constraint `held_qty + booked_qty <= capacity` is the final guard against oversell.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    DateClosedError,
    EnquiryRequiredError,
    GuestCountInvalidError,
    HoldExpiredError,
    HoldNotActiveError,
    NotFoundError,
    SlotUnavailableError,
)
from app.core.timeutil import to_local, utcnow
from app.db.retry import run_with_retry
from app.models.booking import AvailabilitySlot, SlotHold, SlotHoldCell
from app.models.catalogue import Package
from app.models.schedule import Resource
from app.repositories import booking as booking_repo
from app.schemas.booking import HoldCreate, HoldOut, HoldStatusOut
from app.services import idempotency, package_service, pricing_service, schedule_service, settings_service
from app.services.slot_engine import Candidate, candidate_at
from app.services.tokens import make_token, verify_token


def hold_out(settings: Settings, hold: SlotHold) -> dict[str, Any]:
    start_l, end_l = to_local(hold.start_at), to_local(hold.end_at)
    return HoldOut(
        hold_id=hold.id,
        hold_token=make_token(settings, "hold", hold.id),
        status=hold.status,
        package_id=hold.package_id,
        guest_count=hold.guest_count,
        date=hold.business_date,
        start_time=start_l.strftime("%H:%M"),
        end_time=end_l.strftime("%H:%M"),
        start_at=start_l,
        end_at=end_l,
        expires_at=to_local(hold.expires_at),
        can_extend=hold.status == "ACTIVE" and not hold.extended,
    ).model_dump(mode="json")


def hold_status(hold: SlotHold, now: datetime) -> HoldStatusOut:
    status = hold.status
    if status == "ACTIVE" and hold.expires_at <= now:
        status = "EXPIRED"
    return HoldStatusOut(
        hold_id=hold.id,
        status=status,
        expires_at=to_local(hold.expires_at),
        seconds_remaining=max(0, int((hold.expires_at - now).total_seconds())) if status == "ACTIVE" else 0,
        can_extend=status == "ACTIVE" and not hold.extended,
    )


async def validate_group(
    session: AsyncSession, resource: Resource, package: Package, guest_count: int
) -> None:
    booking = await settings_service.get_booking_settings(session)
    if guest_count > booking.large_group_threshold or guest_count > resource.max_players:
        raise EnquiryRequiredError(
            details={"max_players": min(resource.max_players, booking.large_group_threshold)}
        )
    if not package.min_guests <= guest_count <= package.max_guests:
        raise GuestCountInvalidError(
            f"This package is for {package.min_guests} to {package.max_guests} players.",
            details={"min_guests": package.min_guests, "max_guests": package.max_guests},
        )


async def resolve_candidate(
    session: AsyncSession, resource: Resource, package: Package, play_date: Any, start_time: Any
) -> Candidate:
    schedule = (await schedule_service.day_schedules(session, resource, play_date, play_date))[play_date]
    if not schedule.is_open:
        raise DateClosedError(details={"reason": schedule.closed_reason})
    candidate = candidate_at(
        play_date,
        start_time,
        schedule,
        interval_min=resource.slot_interval_min,
        duration_min=package.duration_min,
        buffer_min=resource.buffer_min,
    )
    if candidate is None:
        raise SlotUnavailableError("That start time isn't offered for this package.")
    return candidate


def _release_cells(hold: SlotHold, cells: list[AvailabilitySlot]) -> None:
    ids = {c.slot_id for c in hold.cells}
    for cell in cells:
        if cell.id in ids:
            cell.held_qty -= hold.units


async def _sweep_expired_on(session: AsyncSession, cells: list[AvailabilitySlot], now: datetime) -> bool:
    """Release expired holds that occupy any of `cells` (locking every cell those holds cover)."""
    expired = await booking_repo.lock_expired_holds_on_cells(session, [c.id for c in cells], now)
    if not expired:
        return False
    known = {c.id for c in cells}
    extra_ids = sorted({hc.slot_id for h in expired for hc in h.cells} - known)
    all_cells = cells + (await booking_repo.lock_cells_by_id(session, extra_ids) if extra_ids else [])
    for hold in expired:
        _release_cells(hold, all_cells)
        hold.status, hold.released_at = "EXPIRED", now
    return True


async def create_hold(
    session: AsyncSession,
    settings: Settings,
    data: HoldCreate,
    *,
    channel: str,
    idempotency_key: str,
    created_by: uuid.UUID | None = None,
) -> tuple[int, dict[str, Any]]:
    resource = await schedule_service.primary_resource(session)
    package = await package_service.get_active(session, data.package_id)
    await validate_group(session, resource, package, data.guest_count)
    await pricing_service.ensure_bookable_date(session, data.date)
    candidate = await resolve_candidate(session, resource, package, data.date, data.start_time)
    booking_settings = await settings_service.get_booking_settings(session)
    if candidate.start_at < utcnow() + timedelta(minutes=booking_settings.same_day_cutoff_min):
        raise SlotUnavailableError("That time is too soon to book. Please choose a later slot.")
    await pricing_service.price_for_package(session, package, data.date, data.guest_count)  # must be priced

    units = schedule_service.units_for(resource, data.guest_count)
    capacity = schedule_service.resource_capacity(resource)
    await booking_repo.ensure_cells(session, resource.id, candidate.cells, capacity)
    await session.commit()

    payload = {**data.model_dump(mode="json"), "channel": channel}

    async def work() -> tuple[int, dict[str, Any]]:
        key_row, replay = await idempotency.begin(session, "hold", idempotency_key, payload)
        if replay is not None:
            return replay.status_code, replay.body
        assert key_row is not None
        now = utcnow()
        cells = await booking_repo.lock_cells(session, resource.id, candidate.cells)
        if len(cells) != len(candidate.cells):
            raise SlotUnavailableError()

        def fits() -> bool:
            return all(c.capacity - c.held_qty - c.booked_qty >= units for c in cells)

        if not fits() and not (await _sweep_expired_on(session, cells, now) and fits()):
            raise SlotUnavailableError()

        for cell in cells:
            cell.held_qty += units
        hold = SlotHold(
            resource_id=resource.id,
            package_id=package.id,
            guest_count=data.guest_count,
            units=units,
            business_date=data.date,
            start_at=candidate.start_at,
            end_at=candidate.end_at,
            status="ACTIVE",
            channel=channel,
            expires_at=now + timedelta(seconds=booking_settings.hold_ttl_seconds),
            created_by_user_id=created_by,
            cells=[SlotHoldCell(slot_id=c.id) for c in cells],
        )
        session.add(hold)
        await session.flush()
        body = hold_out(settings, hold)
        idempotency.finish(key_row, 201, body)
        await session.commit()
        return 201, body

    return await run_with_retry(session, work)


async def _authorized_hold(
    session: AsyncSession, settings: Settings, hold_id: uuid.UUID, token: str | None, *, lock: bool
) -> SlotHold:
    hold = await (booking_repo.lock_hold if lock else booking_repo.get_hold)(session, hold_id)
    if hold is None or not verify_token(settings, "hold", hold_id, token):
        raise NotFoundError("Reservation not found.")
    return hold


async def get_status(
    session: AsyncSession, settings: Settings, hold_id: uuid.UUID, token: str | None
) -> HoldStatusOut:
    hold = await _authorized_hold(session, settings, hold_id, token, lock=False)
    return hold_status(hold, utcnow())


async def extend_hold(
    session: AsyncSession, settings: Settings, hold_id: uuid.UUID, token: str | None
) -> HoldStatusOut:
    """One extension per hold, by one TTL from now, only while still active."""
    hold = await _authorized_hold(session, settings, hold_id, token, lock=True)
    now = utcnow()
    if hold.status != "ACTIVE":
        raise HoldNotActiveError()
    if hold.expires_at <= now:
        raise HoldExpiredError()
    if hold.extended:
        raise HoldNotActiveError("This reservation has already been extended once.")
    ttl = (await settings_service.get_booking_settings(session)).hold_ttl_seconds
    hold.expires_at = now + timedelta(seconds=ttl)
    hold.extended = True
    await session.commit()
    return hold_status(hold, now)


async def release_hold(
    session: AsyncSession, settings: Settings, hold_id: uuid.UUID, token: str | None
) -> None:
    """Idempotent: releasing a non-active hold is a no-op."""

    async def work() -> None:
        hold = await _authorized_hold(session, settings, hold_id, token, lock=True)
        if hold.status != "ACTIVE":
            await session.rollback()
            return
        cells = await booking_repo.lock_cells_by_id(session, [c.slot_id for c in hold.cells])
        _release_cells(hold, cells)
        hold.status, hold.released_at = "RELEASED", utcnow()
        await session.commit()

    await run_with_retry(session, work)


async def expire_due_holds(session: AsyncSession, *, limit: int = 200) -> int:
    """Release expired holds (called by the worker every 15 s; holds are also swept lazily)."""

    async def work() -> int:
        now = utcnow()
        holds = await booking_repo.lock_expired_holds(session, now, limit)
        if not holds:
            await session.rollback()
            return 0
        cell_ids = sorted({c.slot_id for h in holds for c in h.cells})
        cells = await booking_repo.lock_cells_by_id(session, cell_ids)
        for hold in holds:
            _release_cells(hold, cells)
            hold.status, hold.released_at = "EXPIRED", now
        await session.commit()
        return len(holds)

    return await run_with_retry(session, work)
