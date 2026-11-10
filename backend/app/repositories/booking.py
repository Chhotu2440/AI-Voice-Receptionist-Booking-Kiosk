"""Data access for capacity cells, holds, customers, bookings and enquiries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import business_date_of
from app.models.booking import (
    AvailabilitySlot,
    Booking,
    Customer,
    CustomEventEnquiry,
    SlotHold,
    SlotHoldCell,
)

# --- cells ------------------------------------------------------------------------------------------


async def ensure_cells(
    session: AsyncSession, resource_id: uuid.UUID, starts: Sequence[datetime], capacity: int
) -> None:
    """Create missing cells (no-op for existing ones). Run in its own short transaction before locking.

    Only cells that don't exist yet are inserted, so the common case (cells already there) takes no
    insert locks at all; concurrent first-time inserts can deadlock on MySQL and are retried by the caller."""
    if not starts:
        return
    existing = set(
        (
            await session.execute(
                select(AvailabilitySlot.start_at).where(
                    AvailabilitySlot.resource_id == resource_id, AvailabilitySlot.start_at.in_(list(starts))
                )
            )
        )
        .scalars()
        .all()
    )
    starts = sorted(s for s in starts if s not in existing)
    if not starts:
        return
    rows = [
        {
            "resource_id": resource_id,
            "business_date": business_date_of(s),
            "start_at": s,
            "capacity": capacity,
            "held_qty": 0,
            "booked_qty": 0,
        }
        for s in starts
    ]
    dialect = session.get_bind().dialect.name
    if dialect == "mysql":
        stmt = mysql_insert(AvailabilitySlot).values(rows)
        stmt = stmt.on_duplicate_key_update(resource_id=stmt.inserted.resource_id)
        await session.execute(stmt)
    elif dialect == "sqlite":
        await session.execute(sqlite_insert(AvailabilitySlot).values(rows).on_conflict_do_nothing())
    else:  # pragma: no cover - only MySQL (prod) and SQLite (dev/tests) are supported
        raise RuntimeError(f"unsupported dialect {dialect}")


async def lock_cells(
    session: AsyncSession, resource_id: uuid.UUID, starts: Sequence[datetime]
) -> list[AvailabilitySlot]:
    """SELECT ... FOR UPDATE in ascending start order (consistent lock order avoids deadlocks)."""
    stmt = (
        select(AvailabilitySlot)
        .where(AvailabilitySlot.resource_id == resource_id, AvailabilitySlot.start_at.in_(list(starts)))
        .order_by(AvailabilitySlot.start_at)
        .with_for_update()
    )
    return list((await session.execute(stmt)).scalars().all())


async def lock_cells_by_id(session: AsyncSession, ids: Sequence[int]) -> list[AvailabilitySlot]:
    stmt = (
        select(AvailabilitySlot)
        .where(AvailabilitySlot.id.in_(list(ids)))
        .order_by(AvailabilitySlot.resource_id, AvailabilitySlot.start_at)
        .with_for_update()
    )
    return list((await session.execute(stmt)).scalars().all())


async def free_units_by_cell(
    session: AsyncSession, resource_id: uuid.UUID, date_from: date, date_to: date
) -> dict[datetime, int]:
    stmt = select(
        AvailabilitySlot.start_at,
        AvailabilitySlot.capacity - AvailabilitySlot.held_qty - AvailabilitySlot.booked_qty,
    ).where(
        AvailabilitySlot.resource_id == resource_id,
        AvailabilitySlot.business_date >= date_from,
        AvailabilitySlot.business_date <= date_to,
    )
    return {start: int(free) for start, free in (await session.execute(stmt)).all()}


async def resize_future_cells(
    session: AsyncSession, resource_id: uuid.UUID, now: datetime, capacity: int
) -> int:
    """Apply a capacity change to future cells where it still fits; returns how many could not be resized."""
    await session.execute(
        update(AvailabilitySlot)
        .where(
            AvailabilitySlot.resource_id == resource_id,
            AvailabilitySlot.start_at >= now,
            AvailabilitySlot.held_qty + AvailabilitySlot.booked_qty <= capacity,
        )
        .values(capacity=capacity)
    )
    stmt = select(func.count()).where(
        AvailabilitySlot.resource_id == resource_id,
        AvailabilitySlot.start_at >= now,
        AvailabilitySlot.capacity != capacity,
    )
    return int((await session.execute(stmt)).scalar_one())


# --- holds ------------------------------------------------------------------------------------------


async def lock_hold(session: AsyncSession, hold_id: uuid.UUID) -> SlotHold | None:
    stmt = select(SlotHold).where(SlotHold.id == hold_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_hold(session: AsyncSession, hold_id: uuid.UUID) -> SlotHold | None:
    return await session.get(SlotHold, hold_id)


async def lock_expired_holds(session: AsyncSession, now: datetime, limit: int) -> list[SlotHold]:
    stmt = (
        select(SlotHold)
        .where(SlotHold.status == "ACTIVE", SlotHold.expires_at <= now)
        .order_by(SlotHold.expires_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(stmt)).scalars().all())


async def lock_expired_holds_on_cells(
    session: AsyncSession, slot_ids: Sequence[int], now: datetime
) -> list[SlotHold]:
    stmt = (
        select(SlotHold)
        .join(SlotHoldCell, SlotHoldCell.hold_id == SlotHold.id)
        .where(
            SlotHoldCell.slot_id.in_(list(slot_ids)),
            SlotHold.status == "ACTIVE",
            SlotHold.expires_at <= now,
        )
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_future_commitments(session: AsyncSession, resource_id: uuid.UUID, now: datetime) -> int:
    holds = select(func.count()).where(
        SlotHold.resource_id == resource_id, SlotHold.status == "ACTIVE", SlotHold.end_at > now
    )
    bookings = select(func.count()).where(
        Booking.resource_id == resource_id,
        Booking.status.in_(("CONFIRMED", "PENDING_PAYMENT")),
        Booking.end_at > now,
    )
    return int((await session.execute(holds)).scalar_one()) + int(
        (await session.execute(bookings)).scalar_one()
    )


# --- customers --------------------------------------------------------------------------------------


async def get_customer_by_phone(session: AsyncSession, phone_e164: str) -> Customer | None:
    stmt = select(Customer).where(Customer.phone_e164 == phone_e164)
    return (await session.execute(stmt)).scalar_one_or_none()


# --- bookings ---------------------------------------------------------------------------------------


async def lock_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    stmt = select(Booking).where(Booking.id == booking_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    return await session.get(Booking, booking_id)


async def search_bookings(
    session: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    statuses: Sequence[str] | None,
    phone_e164: str | None,
    reference: str | None,
    offset: int,
    limit: int,
) -> tuple[Sequence[Booking], int]:
    stmt = select(Booking)
    conditions = []
    if date_from is not None:
        conditions.append(Booking.business_date >= date_from)
    if date_to is not None:
        conditions.append(Booking.business_date <= date_to)
    if statuses:
        conditions.append(Booking.status.in_(list(statuses)))
    if reference:
        conditions.append(Booking.reference == reference.strip().upper())
    if phone_e164:
        stmt = stmt.join(Customer, Customer.id == Booking.customer_id)
        conditions.append(Customer.phone_e164 == phone_e164)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Booking.start_at).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all(), int(total)


# --- enquiries --------------------------------------------------------------------------------------


async def search_enquiries(
    session: AsyncSession, *, statuses: Sequence[str] | None, query: str | None, offset: int, limit: int
) -> tuple[Sequence[CustomEventEnquiry], int]:
    stmt = select(CustomEventEnquiry)
    if statuses:
        stmt = stmt.where(CustomEventEnquiry.status.in_(list(statuses)))
    if query:
        stmt = stmt.join(Customer, Customer.id == CustomEventEnquiry.customer_id).where(
            or_(CustomEventEnquiry.reference == query.strip().upper(), Customer.name.contains(query.strip()))
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(CustomEventEnquiry.created_at.desc()).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all(), int(total)
