"""Availability: which start times can take a group, per date. Read-only (no locks).

Holds that expired but haven't been swept yet (worker runs every 15 s) still count as taken here;
they are released before anyone is refused at hold time, so this can only under-report briefly.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailed
from app.core.timeutil import to_local, today_local, utcnow
from app.repositories import booking as booking_repo
from app.schemas.booking import DateStatusOut, DaySlotsOut, SlotOut
from app.services import hold_service, package_service, pricing_service, schedule_service, settings_service
from app.services.slot_engine import bookable, candidates, remaining_units

MAX_RANGE_DAYS = 31


async def _context(session: AsyncSession, package_id: uuid.UUID, guest_count: int):  # type: ignore[no-untyped-def]
    resource = await schedule_service.primary_resource(session)
    package = await package_service.get_active(session, package_id)
    await hold_service.validate_group(session, resource, package, guest_count)
    booking = await settings_service.get_booking_settings(session)
    earliest = utcnow() + timedelta(minutes=booking.same_day_cutoff_min)
    return resource, package, booking, earliest


async def _days(
    session: AsyncSession, package_id: uuid.UUID, guest_count: int, date_from: date, date_to: date
) -> list[DaySlotsOut]:
    resource, package, _booking, earliest = await _context(session, package_id, guest_count)
    units = schedule_service.units_for(resource, guest_count)
    capacity = schedule_service.resource_capacity(resource)
    schedules = await schedule_service.day_schedules(session, resource, date_from, date_to)
    free = await booking_repo.free_units_by_cell(session, resource.id, date_from, date_to)

    days: list[DaySlotsOut] = []
    for d, schedule in schedules.items():
        if not schedule.is_open:
            days.append(DaySlotsOut(date=d, status="CLOSED", closed_reason=schedule.closed_reason, slots=[]))
            continue
        slots = []
        for c in candidates(
            d,
            schedule,
            interval_min=resource.slot_interval_min,
            duration_min=package.duration_min,
            buffer_min=resource.buffer_min,
        ):
            if bookable(c, free, units=units, default_capacity=capacity, earliest_start=earliest):
                start_l, end_l = to_local(c.start_at), to_local(c.end_at)
                slots.append(
                    SlotOut(
                        start_time=start_l.strftime("%H:%M"),
                        end_time=end_l.strftime("%H:%M"),
                        start_at=start_l,
                        end_at=end_l,
                        duration_min=package.duration_min,
                        remaining=remaining_units(c, free, capacity),
                    )
                )
        days.append(DaySlotsOut(date=d, status="OPEN" if slots else "FULL", slots=slots))
    return days


async def slots_for_day(
    session: AsyncSession, package_id: uuid.UUID, play_date: date, guest_count: int
) -> DaySlotsOut:
    await pricing_service.ensure_bookable_date(session, play_date)
    return (await _days(session, package_id, guest_count, play_date, play_date))[0]


async def dates(
    session: AsyncSession,
    package_id: uuid.UUID,
    guest_count: int,
    date_from: date | None,
    date_to: date | None,
) -> list[DateStatusOut]:
    booking = await settings_service.get_booking_settings(session)
    first, last = today_local(), today_local() + timedelta(days=booking.max_days_ahead)
    start = max(date_from or first, first)
    end = min(date_to or (start + timedelta(days=13)), last)
    if end < start:
        return []
    if (end - start).days >= MAX_RANGE_DAYS:
        raise ValidationFailed(f"Please ask for at most {MAX_RANGE_DAYS} days at a time.")
    return [
        DateStatusOut(
            date=d.date, status=d.status, slots_available=len(d.slots), closed_reason=d.closed_reason
        )
        for d in await _days(session, package_id, guest_count, start, end)
    ]
