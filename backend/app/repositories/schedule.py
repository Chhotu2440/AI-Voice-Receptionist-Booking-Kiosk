"""Data access for locations, hours, exceptions and resources."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import BusinessHours, BusinessLocation, Resource, ScheduleException


async def get_primary_location(session: AsyncSession) -> BusinessLocation | None:
    """Single-venue deployment: the first location created is the primary one."""
    stmt = select(BusinessLocation).order_by(BusinessLocation.created_at).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_hours(session: AsyncSession, location_id: uuid.UUID) -> Sequence[BusinessHours]:
    stmt = (
        select(BusinessHours).where(BusinessHours.location_id == location_id).order_by(BusinessHours.weekday)
    )
    return (await session.execute(stmt)).scalars().all()


async def list_exceptions(
    session: AsyncSession, location_id: uuid.UUID, date_from: date, date_to: date
) -> Sequence[ScheduleException]:
    stmt = (
        select(ScheduleException)
        .where(
            ScheduleException.location_id == location_id,
            ScheduleException.exception_date >= date_from,
            ScheduleException.exception_date <= date_to,
        )
        .order_by(ScheduleException.exception_date, ScheduleException.start_time)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_exception(session: AsyncSession, exception_id: uuid.UUID) -> ScheduleException | None:
    return await session.get(ScheduleException, exception_id)


async def list_resources(session: AsyncSession, location_id: uuid.UUID) -> Sequence[Resource]:
    stmt = select(Resource).where(Resource.location_id == location_id).order_by(Resource.name)
    return (await session.execute(stmt)).scalars().all()


async def get_resource(session: AsyncSession, resource_id: uuid.UUID) -> Resource | None:
    return await session.get(Resource, resource_id)
