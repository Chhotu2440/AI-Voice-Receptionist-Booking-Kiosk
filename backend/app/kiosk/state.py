"""Kiosk conversation state (docs/05). The backend owns it; touch (and later voice) only submit intents."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.booking import BookingOut, DateStatusOut, SlotOut
from app.schemas.pricing import PriceQuoteOut
from app.services.phone import mask_phone

KioskStateName = Literal[
    "IDLE",
    "GREETING",
    "CUSTOMER_NAME",
    "CUSTOMER_PHONE",
    "GUEST_COUNT",
    "OCCASION",
    "CUSTOM_EVENT_DETAILS",
    "PACKAGE_DISCOVERY",
    "DATE_SELECTION",
    "SLOT_SELECTION",
    "BOOKING_SUMMARY",
    "BOOKING_CONFIRMED",
    "SESSION_COMPLETE",
    "STAFF_ASSISTANCE",
    "SESSION_CANCELLED",
]

# Linear order used for "back" and for clearing dependent data on edits.
FLOW: list[str] = [
    "GREETING",
    "CUSTOMER_NAME",
    "CUSTOMER_PHONE",
    "GUEST_COUNT",
    "OCCASION",
    "PACKAGE_DISCOVERY",
    "DATE_SELECTION",
    "SLOT_SELECTION",
    "BOOKING_SUMMARY",
]


class PackageCard(BaseModel):
    id: str
    code: str
    name_en: str
    name_hi: str
    description_en: str
    description_hi: str
    duration_min: int
    games_count: int | None
    formats_count: int | None
    features: list[dict[str, str]]
    games: list[dict[str, str]] = []  # {"en", "hi", "about_en", "about_hi"}: game modes included
    recommended: bool
    eligible: bool
    min_guests: int
    max_guests: int
    price_per_person: str | None
    estimated_total: str | None
    day_type: str | None


class KioskError(BaseModel):
    code: str
    message: str


class KioskState(BaseModel):
    session_id: str | None = None
    state: KioskStateName = "IDLE"
    version: int = 0
    language: Literal["en", "hi"] = "en"
    updated_at: dt.datetime | None = None

    customer_name: str | None = None
    phone_e164: str | None = None
    phone_confirmed: bool = False
    guest_count: int | None = None
    occasion_code: str | None = None
    occasion_details: dict[str, str | int] = Field(default_factory=dict)
    packages: list[PackageCard] = Field(default_factory=list)
    package_id: str | None = None
    available_dates: list[DateStatusOut] = Field(default_factory=list)
    play_date: dt.date | None = None
    slots: list[SlotOut] = Field(default_factory=list)
    start_time: str | None = None
    hold_id: str | None = None
    hold_token: str | None = None  # server-side only, never sent to the screen
    hold_expires_at: dt.datetime | None = None
    hold_can_extend: bool = False
    quote: PriceQuoteOut | None = None
    # Booking confirmation on WhatsApp is pre-selected (owner decision 2026-11-11); the customer can untick it
    # and the choice is recorded per booking in customer_consents.
    whatsapp_consent: bool = True
    booking: BookingOut | None = None
    enquiry_reference: str | None = None
    resume_state: str | None = None
    furthest_index: int = 0
    intent_seq: int = 0
    error: KioskError | None = None

    def public(self) -> dict[str, Any]:
        """Snapshot for the screen: no hold token, no booking token, phone masked once confirmed."""
        data = self.model_dump(mode="json", exclude={"hold_token"})
        if self.phone_e164 and (self.phone_confirmed or self.state != "CUSTOMER_PHONE"):
            data["phone_display"] = mask_phone(self.phone_e164)
        elif self.phone_e164:
            local = self.phone_e164[-10:]
            data["phone_display"] = f"{local[:5]} {local[5:]}"
        else:
            data["phone_display"] = None
        data.pop("phone_e164", None)
        if data.get("booking"):
            data["booking"].pop("booking_token", None)
        return data
