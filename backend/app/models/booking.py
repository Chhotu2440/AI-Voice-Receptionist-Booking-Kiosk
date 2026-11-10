"""Capacity cells, holds, customers, bookings, enquiries and idempotency records."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import Money, Percent, UTCDateTime, UUIDBinary, enum_check

BigId = BigInteger().with_variant(Integer(), "sqlite")
SmallId = SmallInteger().with_variant(Integer(), "sqlite")

HOLD_STATUSES = ("ACTIVE", "RELEASED", "EXPIRED", "CONVERTED")
BOOKING_STATUSES = ("CONFIRMED", "CANCELLED", "COMPLETED", "NO_SHOW", "PENDING_PAYMENT")
PAYMENT_STATUSES = ("NOT_REQUIRED", "PENDING", "PARTIALLY_PAID", "PAID", "REFUNDED", "FAILED")
PAYMENT_MODES = ("PAY_AT_VENUE", "DEPOSIT", "FULL")
CHANNELS = ("KIOSK", "WEB", "STAFF", "LEGACY_DAYSCHEDULE")
ENQUIRY_STATUSES = ("NEW", "CONTACTED", "QUOTED", "WON", "LOST")


class AvailabilitySlot(Base):
    """One grid cell of one resource. The row lock on this table is the oversell guarantee."""

    __tablename__ = "availability_slots"
    __table_args__ = (
        UniqueConstraint("resource_id", "start_at"),
        Index("ix_availability_slots_resource_date", "resource_id", "business_date"),
        CheckConstraint(
            "held_qty >= 0 AND booked_qty >= 0 AND held_qty + booked_qty <= capacity", name="capacity"
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("resources.id", ondelete="CASCADE")
    )
    business_date: Mapped[date] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime())
    capacity: Mapped[int] = mapped_column(SmallInteger)
    held_qty: Mapped[int] = mapped_column(SmallInteger, default=0)
    booked_qty: Mapped[int] = mapped_column(SmallInteger, default=0)


class SlotHold(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "slot_holds"
    __table_args__ = (
        enum_check("status", HOLD_STATUSES, "status"),
        enum_check("channel", CHANNELS, "channel"),
        CheckConstraint("guest_count >= 1 AND units >= 1", name="positive"),
        Index("ix_slot_holds_status_expires", "status", "expires_at"),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("resources.id"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("packages.id"))
    guest_count: Mapped[int] = mapped_column(SmallInteger)
    units: Mapped[int] = mapped_column(SmallInteger)
    business_date: Mapped[date] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime())
    end_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    channel: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    extended: Mapped[bool] = mapped_column(Boolean, default=False)
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Not unique: a reschedule converts a second hold into the same booking.
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)

    cells: Mapped[list[SlotHoldCell]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class SlotHoldCell(Base):
    __tablename__ = "slot_hold_cells"

    hold_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("slot_holds.id", ondelete="CASCADE"), primary_key=True
    )
    slot_id: Mapped[int] = mapped_column(BigId, ForeignKey("availability_slots.id"), primary_key=True)


class Customer(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_last_booking_at", "last_booking_at"),)

    name: Mapped[str] = mapped_column(String(80))
    phone_e164: Mapped[str] = mapped_column(String(16), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_booking_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class CustomerConsent(Base):
    """Append-only consent log; the latest row per (customer, purpose) is current."""

    __tablename__ = "customer_consents"
    __table_args__ = (Index("ix_customer_consents_customer_purpose", "customer_id", "purpose"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("customers.id", ondelete="CASCADE")
    )
    purpose: Mapped[str] = mapped_column(String(32))
    granted: Mapped[bool] = mapped_column(Boolean)
    notice_version: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Booking(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        enum_check("status", BOOKING_STATUSES, "status"),
        enum_check("payment_status", PAYMENT_STATUSES, "payment_status"),
        enum_check("payment_mode", PAYMENT_MODES, "payment_mode"),
        enum_check("channel", CHANNELS, "channel"),
        Index("ix_bookings_date_status", "business_date", "status"),
        Index("ix_bookings_customer_start", "customer_id", "start_at"),
        Index("ix_bookings_status_start", "status", "start_at"),
    )

    reference: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("customers.id"))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("resources.id"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("packages.id"))
    occasion_id: Mapped[int] = mapped_column(
        SmallInteger().with_variant(Integer(), "sqlite"), ForeignKey("occasions.id")
    )
    occasion_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    guest_count: Mapped[int] = mapped_column(SmallInteger)
    business_date: Mapped[date] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime())
    end_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(24))
    payment_status: Mapped[str] = mapped_column(String(24))
    payment_mode: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(24))
    notes: Mapped[str] = mapped_column(Text, default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)

    customer: Mapped[Customer] = relationship(lazy="selectin")
    items: Mapped[list[BookingItem]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    slots: Mapped[list[BookingSlot]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    pricing: Mapped[BookingPricingSnapshot] = relationship(cascade="all, delete-orphan", lazy="selectin")
    history: Mapped[list[BookingStatusHistory]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="BookingStatusHistory.id"
    )


class BookingSlot(Base):
    __tablename__ = "booking_slots"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True
    )
    slot_id: Mapped[int] = mapped_column(BigId, ForeignKey("availability_slots.id"), primary_key=True)
    units: Mapped[int] = mapped_column(SmallInteger)


class BookingItem(Base):
    __tablename__ = "booking_items"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(16))  # PACKAGE | DISCOUNT | CHARGE
    description: Mapped[str] = mapped_column(String(160))
    qty: Mapped[int] = mapped_column(SmallInteger)
    unit_price: Mapped[Decimal] = mapped_column(Money())
    amount: Mapped[Decimal] = mapped_column(Money())


class BookingPricingSnapshot(Base):
    """Immutable copy of the price at booking time (replaced only by an explicit reschedule)."""

    __tablename__ = "booking_pricing_snapshots"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True
    )
    day_type: Mapped[str] = mapped_column(String(16))
    price_per_person: Mapped[Decimal] = mapped_column(Money())
    subtotal: Mapped[Decimal] = mapped_column(Money())
    discount_total: Mapped[Decimal] = mapped_column(Money())
    charges_total: Mapped[Decimal] = mapped_column(Money())
    tax_rate: Mapped[Decimal] = mapped_column(Percent())
    tax_amount: Mapped[Decimal] = mapped_column(Money())
    prices_include_tax: Mapped[bool] = mapped_column(Boolean)
    total: Mapped[Decimal] = mapped_column(Money())
    currency: Mapped[str] = mapped_column(String(3))
    rules_applied: Mapped[list[str]] = mapped_column(JSON)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CustomEventEnquiry(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "custom_event_enquiries"
    __table_args__ = (
        enum_check("status", ENQUIRY_STATUSES, "status"),
        Index("ix_custom_event_enquiries_status_created", "status", "created_at"),
    )

    reference: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), ForeignKey("customers.id"))
    occasion_id: Mapped[int] = mapped_column(
        SmallInteger().with_variant(Integer(), "sqlite"), ForeignKey("occasions.id")
    )
    guest_count: Mapped[int] = mapped_column(SmallInteger)
    preferred_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="NEW")
    channel: Mapped[str] = mapped_column(String(24))
    staff_notes: Mapped[str] = mapped_column(Text, default="")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)

    customer: Mapped[Customer] = relationship(lazy="selectin")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
