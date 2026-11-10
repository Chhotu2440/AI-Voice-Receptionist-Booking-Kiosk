"""Locations, business hours, schedule exceptions and bookable resources."""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import UUIDBinary, enum_check

EXCEPTION_TYPES = ("HOLIDAY", "SPECIAL_HOURS", "BLACKOUT", "MANUAL_BLOCK")
CAPACITY_MODES = ("EXCLUSIVE", "SHARED_SEATS")


class BusinessLocation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "business_locations"

    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(64), default="")
    postal_code: Mapped[str] = mapped_column(String(12), default="")
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    phone: Mapped[str] = mapped_column(String(32), default="")
    whatsapp: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    maps_url: Mapped[str] = mapped_column(String(512), default="")
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)


class BusinessHours(UUIDPrimaryKey, Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        UniqueConstraint("location_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("is_closed = 1 OR close_time > open_time", name="open_before_close"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("business_locations.id", ondelete="CASCADE")
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class ScheduleException(UUIDPrimaryKey, Timestamps, Base):
    """HOLIDAY/BLACKOUT close the whole day (or a time range when times are set);
    SPECIAL_HOURS replaces the opening hours; MANUAL_BLOCK blocks a time range."""

    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        enum_check("type", EXCEPTION_TYPES, "type"),
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="time_range",
        ),
        Index("ix_schedule_exceptions_location_date", "location_id", "exception_date"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("business_locations.id", ondelete="CASCADE")
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("resources.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32))
    exception_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Resource(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "resources"
    __table_args__ = (
        enum_check("capacity_mode", CAPACITY_MODES, "capacity_mode"),
        CheckConstraint("default_capacity >= 1", name="capacity_positive"),
        CheckConstraint("max_players >= 1", name="max_players_positive"),
        CheckConstraint("slot_interval_min BETWEEN 5 AND 240", name="interval_range"),
        CheckConstraint("buffer_min BETWEEN 0 AND 120", name="buffer_range"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("business_locations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    capacity_mode: Mapped[str] = mapped_column(String(16), default="EXCLUSIVE")
    default_capacity: Mapped[int] = mapped_column(SmallInteger, default=1)
    max_players: Mapped[int] = mapped_column(SmallInteger)
    slot_interval_min: Mapped[int] = mapped_column(SmallInteger, default=30)
    buffer_min: Mapped[int] = mapped_column(SmallInteger, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
