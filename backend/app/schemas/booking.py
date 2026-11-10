"""Schemas for availability, holds, bookings and event enquiries."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.pricing import PriceQuoteOut

GuestCount = Field(ge=1, le=1000)


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: uuid.UUID
    date: dt.date
    guest_count: int = GuestCount


class SlotOut(BaseModel):
    start_time: str  # "18:00" local
    end_time: str
    start_at: dt.datetime  # ISO with +05:30
    end_at: dt.datetime
    duration_min: int
    remaining: int  # free units: 1 for an exclusive arena, players for shared mode


class DaySlotsOut(BaseModel):
    date: dt.date
    status: Literal["OPEN", "FULL", "CLOSED"]
    closed_reason: str = ""
    slots: list[SlotOut]


class DateStatusOut(BaseModel):
    date: dt.date
    status: Literal["OPEN", "FULL", "CLOSED"]
    slots_available: int
    closed_reason: str = ""


class HoldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    guest_count: int = GuestCount


class HoldOut(BaseModel):
    hold_id: uuid.UUID
    hold_token: str
    status: str
    package_id: uuid.UUID
    guest_count: int
    date: dt.date
    start_time: str
    end_time: str
    start_at: dt.datetime
    end_at: dt.datetime
    expires_at: dt.datetime
    can_extend: bool


class HoldStatusOut(BaseModel):
    hold_id: uuid.UUID
    status: str
    expires_at: dt.datetime
    seconds_remaining: int
    can_extend: bool


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=10, max_length=20)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v or any(ch.isdigit() for ch in v) or any(ch in "<>{}[]\\/@#$%^*=_|~`" for ch in v):
            raise ValueError("name may contain letters, spaces and . ' - only")
        return v


class ConsentsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whatsapp: bool = False


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hold_id: uuid.UUID
    hold_token: str = Field(min_length=10, max_length=100)
    customer: CustomerIn
    occasion_code: str = Field(max_length=32)
    occasion_details: dict[str, str | int] = Field(default_factory=dict)
    consents: ConsentsIn = Field(default_factory=ConsentsIn)
    quote_id: str | None = Field(default=None, max_length=2000)
    notes: str = Field(default="", max_length=500)


class BookingCustomerOut(BaseModel):
    name: str
    phone_masked: str


class BookingOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    payment_status: str
    payment_mode: str
    channel: str
    package_id: uuid.UUID
    package_name: str
    occasion_code: str
    guest_count: int
    date: dt.date
    start_time: str
    end_time: str
    start_at: dt.datetime
    end_at: dt.datetime
    customer: BookingCustomerOut
    pricing: PriceQuoteOut
    booking_token: str | None = None


class BookingHistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    actor_type: str
    reason: str
    details: dict[str, Any] | None
    created_at: dt.datetime


class AdminBookingOut(BookingOut):
    customer_id: uuid.UUID
    customer_phone: str
    occasion_details: dict[str, Any]
    notes: str
    cancel_reason: str | None
    history: list[BookingHistoryOut]


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=255)


class RescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hold_id: uuid.UUID
    hold_token: str = Field(min_length=10, max_length=100)
    reason: str = Field(default="", max_length=255)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["COMPLETED", "NO_SHOW"]
    reason: str = Field(default="", max_length=255)


class EnquiryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer: CustomerIn
    occasion_code: str = Field(max_length=32)
    guest_count: int = GuestCount
    preferred_date: dt.date | None = None
    details: dict[str, str | int] = Field(default_factory=dict)
    consents: ConsentsIn = Field(default_factory=ConsentsIn)


class EnquiryOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    occasion_code: str
    guest_count: int
    preferred_date: dt.date | None
    created_at: dt.datetime


class AdminEnquiryOut(EnquiryOut):
    customer_name: str
    customer_phone: str
    details: dict[str, Any]
    staff_notes: str
    channel: str


class EnquiryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["NEW", "CONTACTED", "QUOTED", "WON", "LOST"] | None = None
    staff_notes: str | None = Field(default=None, max_length=4000)
