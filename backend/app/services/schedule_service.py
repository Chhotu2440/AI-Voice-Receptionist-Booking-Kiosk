"""Business information, opening hours, schedule exceptions and resources.

Note: slot generation (Sprint 2) consumes these. Changing hours/exceptions will trigger slot regeneration
for affected dates once the slot grid exists; booked slots are never modified by configuration changes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.schedule import BusinessHours, BusinessLocation, Resource, ScheduleException
from app.repositories import schedule as schedule_repo
from app.schemas.schedule import (
    BusinessHoursPut,
    BusinessInfoUpdate,
    ResourceIn,
    ResourceUpdate,
    ScheduleExceptionIn,
)
from app.services import audit_service
from app.services.context import Actor

MAX_EXCEPTION_RANGE_DAYS = 400


async def primary_location(session: AsyncSession) -> BusinessLocation:
    location = await schedule_repo.get_primary_location(session)
    if location is None:
        raise NotFoundError("Business location is not configured. Run the seed command.")
    return location


async def get_hours(session: AsyncSession) -> Sequence[BusinessHours]:
    location = await primary_location(session)
    return await schedule_repo.get_hours(session, location.id)


async def put_hours(session: AsyncSession, data: BusinessHoursPut, actor: Actor) -> Sequence[BusinessHours]:
    location = await primary_location(session)
    existing = {h.weekday: h for h in await schedule_repo.get_hours(session, location.id)}
    before = {str(k): [str(v.open_time), str(v.close_time), v.is_closed] for k, v in existing.items()}
    for day in data.days:
        row = existing.get(day.weekday)
        if row is None:
            row = BusinessHours(location_id=location.id, weekday=day.weekday)
            session.add(row)
        row.open_time, row.close_time, row.is_closed = day.open_time, day.close_time, day.is_closed
    after = {str(d.weekday): [str(d.open_time), str(d.close_time), d.is_closed] for d in data.days}
    audit_service.record(
        session, actor, "business_hours.update", "business_hours", location.id, before, after
    )
    await session.commit()
    return await schedule_repo.get_hours(session, location.id)


async def list_exceptions(
    session: AsyncSession, date_from: date, date_to: date
) -> Sequence[ScheduleException]:
    if date_to < date_from:
        raise ValidationFailed("date_to must be on or after date_from")
    if (date_to - date_from) > timedelta(days=MAX_EXCEPTION_RANGE_DAYS):
        raise ValidationFailed(f"Range is limited to {MAX_EXCEPTION_RANGE_DAYS} days.")
    location = await primary_location(session)
    return await schedule_repo.list_exceptions(session, location.id, date_from, date_to)


async def create_exception(
    session: AsyncSession, data: ScheduleExceptionIn, actor: Actor
) -> ScheduleException:
    location = await primary_location(session)
    if data.resource_id is not None:
        resource = await schedule_repo.get_resource(session, data.resource_id)
        if resource is None or resource.location_id != location.id:
            raise ValidationFailed("Resource not found.")
    row = ScheduleException(
        location_id=location.id,
        resource_id=data.resource_id,
        type=data.type,
        exception_date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        reason=data.reason,
        created_by=uuid.UUID(actor.id) if actor.type == "USER" and actor.id else None,
    )
    session.add(row)
    await session.flush()
    audit_service.record(
        session, actor, "schedule_exception.create", "schedule_exception", row.id, None, data.model_dump()
    )
    await session.commit()
    return row


async def delete_exception(session: AsyncSession, exception_id: uuid.UUID, actor: Actor) -> None:
    row = await schedule_repo.get_exception(session, exception_id)
    if row is None:
        raise NotFoundError("Schedule exception not found.")
    snapshot: dict[str, Any] = {
        "type": row.type,
        "date": row.exception_date,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "reason": row.reason,
    }
    await session.delete(row)
    audit_service.record(
        session, actor, "schedule_exception.delete", "schedule_exception", exception_id, snapshot
    )
    await session.commit()


async def list_resources(session: AsyncSession) -> Sequence[Resource]:
    location = await primary_location(session)
    return await schedule_repo.list_resources(session, location.id)


def _resource_snapshot(r: Resource) -> dict[str, Any]:
    return {
        k: getattr(r, k)
        for k in (
            "name",
            "capacity_mode",
            "default_capacity",
            "max_players",
            "slot_interval_min",
            "buffer_min",
            "is_active",
        )
    }


async def create_resource(session: AsyncSession, data: ResourceIn, actor: Actor) -> Resource:
    location = await primary_location(session)
    row = Resource(location_id=location.id, **data.model_dump())
    session.add(row)
    await session.flush()
    audit_service.record(session, actor, "resource.create", "resource", row.id, None, _resource_snapshot(row))
    await session.commit()
    return row


async def update_resource(
    session: AsyncSession, resource_id: uuid.UUID, data: ResourceUpdate, actor: Actor
) -> Resource:
    row = await schedule_repo.get_resource(session, resource_id)
    if row is None:
        raise NotFoundError("Resource not found.")
    before = _resource_snapshot(row)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit_service.record(
        session, actor, "resource.update", "resource", row.id, before, _resource_snapshot(row)
    )
    await session.commit()
    return row


async def update_business_info(
    session: AsyncSession, data: BusinessInfoUpdate, actor: Actor
) -> BusinessLocation:
    location = await primary_location(session)
    patch = data.model_dump(exclude_unset=True)
    before = {k: getattr(location, k) for k in patch}
    for key, value in patch.items():
        setattr(location, key, value)
    audit_service.record(
        session, actor, "business_info.update", "business_location", location.id, before, patch
    )
    await session.commit()
    return location
