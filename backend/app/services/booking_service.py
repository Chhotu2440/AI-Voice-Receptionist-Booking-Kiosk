"""Bookings: atomic creation from a hold, cancellation, reschedule and status changes.

A booking is CONFIRMED only inside the transaction that moves capacity from held to booked on the locked
cells, so a success response always corresponds to committed, capacity-checked state.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    EnquiryRequiredError,
    HoldExpiredError,
    HoldNotActiveError,
    NotFoundError,
    PriceChangedError,
    SlotUnavailableError,
    ValidationFailed,
)
from app.core.security import decode_token
from app.core.timeutil import to_local, utcnow
from app.db.retry import run_with_retry
from app.models.booking import (
    AvailabilitySlot,
    Booking,
    BookingItem,
    BookingPricingSnapshot,
    BookingSlot,
    BookingStatusHistory,
    SlotHold,
)
from app.models.catalogue import Occasion, Package
from app.repositories import booking as booking_repo
from app.repositories import catalogue as catalogue_repo
from app.schemas.booking import (
    AdminBookingOut,
    BookingCreate,
    BookingCustomerOut,
    BookingHistoryOut,
    BookingOut,
    StatusUpdate,
)
from app.schemas.pricing import PriceQuoteOut, quote_out
from app.services import (
    audit_service,
    customer_service,
    hold_service,
    idempotency,
    pricing_service,
    schedule_service,
)
from app.services.context import Actor
from app.services.phone import mask_phone
from app.services.pricing_engine import PriceBreakdown
from app.services.refs import new_reference
from app.services.tokens import make_token, verify_token

ACTIVE_STATUSES = ("CONFIRMED", "PENDING_PAYMENT")
MAX_DETAIL_LEN = 200

# --- serialization ----------------------------------------------------------------------------------


def booking_out(
    settings: Settings, b: Booking, package: Package, occasion: Occasion, *, with_token: bool
) -> BookingOut:
    start_l, end_l = to_local(b.start_at), to_local(b.end_at)
    return BookingOut(
        id=b.id,
        reference=b.reference,
        status=b.status,
        payment_status=b.payment_status,
        payment_mode=b.payment_mode,
        channel=b.channel,
        package_id=b.package_id,
        package_name=package.name_en,
        occasion_code=occasion.code,
        guest_count=b.guest_count,
        date=b.business_date,
        start_time=start_l.strftime("%H:%M"),
        end_time=end_l.strftime("%H:%M"),
        start_at=start_l,
        end_at=end_l,
        customer=BookingCustomerOut(name=b.customer.name, phone_masked=mask_phone(b.customer.phone_e164)),
        pricing=PriceQuoteOut.model_validate(b.pricing.breakdown),
        booking_token=make_token(settings, "booking", b.id) if with_token else None,
    )


async def admin_booking_out(session: AsyncSession, settings: Settings, b: Booking) -> AdminBookingOut:
    package = await catalogue_repo.get_package_any(session, b.package_id)
    occasion = await session.get(Occasion, b.occasion_id)
    assert package is not None and occasion is not None
    base = booking_out(settings, b, package, occasion, with_token=False)
    return AdminBookingOut(
        **base.model_dump(),
        customer_id=b.customer_id,
        customer_phone=b.customer.phone_e164,
        occasion_details=b.occasion_details,
        notes=b.notes,
        cancel_reason=b.cancel_reason,
        history=[
            BookingHistoryOut(
                from_status=h.from_status,
                to_status=h.to_status,
                actor_type=h.actor_type,
                reason=h.reason,
                details=h.details,
                created_at=to_local(h.created_at),
            )
            for h in b.history
        ],
    )


def _breakdown_json(p: PriceBreakdown) -> dict[str, Any]:
    return quote_out(p).model_dump(mode="json")


def _apply_pricing(booking: Booking, price: PriceBreakdown, package: Package) -> None:
    booking.pricing = BookingPricingSnapshot(
        day_type=price.day_type,
        price_per_person=price.price_per_person,
        subtotal=price.subtotal,
        discount_total=price.discount_total,
        charges_total=price.charges_total,
        tax_rate=price.tax_rate,
        tax_amount=price.tax_amount,
        prices_include_tax=price.prices_include_tax,
        total=price.total,
        currency=price.currency,
        rules_applied=[str(r) for r in price.rules_applied],
        breakdown=_breakdown_json(price),
        computed_at=utcnow(),
    )
    items = [
        BookingItem(
            item_type="PACKAGE",
            description=f"{package.name_en} ({package.duration_min} min)",
            qty=price.guest_count,
            unit_price=price.price_per_person,
            amount=price.subtotal,
        )
    ]
    items += [
        BookingItem(
            item_type="DISCOUNT",
            description=d.name or "Discount",
            qty=1,
            unit_price=-d.amount,
            amount=-d.amount,
        )
        for d in price.discounts
    ]
    items += [
        BookingItem(item_type="CHARGE", description=c.label, qty=1, unit_price=c.amount, amount=c.amount)
        for c in price.charges
    ]
    booking.items = items


def _history(
    booking: Booking,
    from_s: str | None,
    to_s: str,
    actor: Actor,
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    booking.history.append(
        BookingStatusHistory(
            from_status=from_s,
            to_status=to_s,
            actor_type=actor.type,
            actor_id=actor.id,
            reason=reason,
            details=details,
            created_at=utcnow(),
        )
    )


# --- validation helpers -----------------------------------------------------------------------------


async def _occasion(session: AsyncSession, code: str) -> Occasion:
    occasion = await catalogue_repo.get_occasion(session, code)
    if occasion is None or not occasion.is_active:
        raise ValidationFailed("Unknown occasion.", details={"occasion_code": code})
    return occasion


FREE_TEXT_KEYS = ("special_requirements",)


def validate_details(occasion: Occasion, details: dict[str, str | int]) -> dict[str, str | int]:
    """Only keys declared in the occasion's schema (plus free-text special requirements) are accepted."""
    allowed: dict[str, dict[str, Any]] = {k: {"key": k} for k in FREE_TEXT_KEYS}
    allowed.update({f["key"]: f for f in occasion.extra_fields_schema})
    cleaned: dict[str, str | int] = {}
    for key, value in details.items():
        if key not in allowed:
            raise ValidationFailed(f"Unexpected detail '{key}' for this occasion.", details={"field": key})
        if allowed[key].get("type") == "int":
            if not isinstance(value, int) or not 0 <= value <= 150:
                raise ValidationFailed(f"'{key}' must be a number.", details={"field": key})
        else:
            value = str(value).strip()
            if len(value) > MAX_DETAIL_LEN:
                raise ValidationFailed(f"'{key}' is too long.", details={"field": key})
        cleaned[key] = value
    return cleaned


def _check_quote(settings: Settings, quote_id: str, hold: SlotHold, price: PriceBreakdown) -> None:
    try:
        claims = decode_token(settings, quote_id, expected_typ="quote")
    except Exception as exc:  # expired or tampered quote: the client must re-quote
        raise PriceChangedError("Your price quote has expired. Please review the current total.") from exc
    same_request = (
        claims.get("pkg") == str(hold.package_id)
        and claims.get("date") == hold.business_date.isoformat()
        and claims.get("guests") == hold.guest_count
    )
    if not same_request:
        raise ValidationFailed("The quote does not match this reservation.")
    if claims.get("total") != str(price.total):
        raise PriceChangedError(details={"quoted_total": claims.get("total"), "total": str(price.total)})


async def _revalidate_slot(session: AsyncSession, hold: SlotHold, package: Package) -> None:
    """The schedule may have changed since the hold (e.g. a manual block): re-derive the cells."""
    resource = await schedule_service.primary_resource(session)
    local_start = to_local(hold.start_at)
    candidate = await hold_service.resolve_candidate(
        session, resource, package, hold.business_date, local_start.time()
    )
    if candidate.start_at != hold.start_at or len(candidate.cells) != len(hold.cells):
        raise SlotUnavailableError()


def _move_held_to_booked(hold: SlotHold, cells: list[AvailabilitySlot]) -> list[BookingSlot]:
    by_id = {c.id: c for c in cells}
    slots = []
    for hc in hold.cells:
        cell = by_id[hc.slot_id]
        cell.held_qty -= hold.units
        cell.booked_qty += hold.units
        slots.append(BookingSlot(slot_id=cell.id, units=hold.units))
    return slots


# --- create -----------------------------------------------------------------------------------------


async def create_booking(
    session: AsyncSession,
    settings: Settings,
    data: BookingCreate,
    *,
    channel: str,
    idempotency_key: str,
    actor: Actor,
) -> tuple[int, dict[str, Any]]:
    occasion = await _occasion(session, data.occasion_code)
    if occasion.always_enquiry:
        raise EnquiryRequiredError("Corporate and school events are handled by our team as an enquiry.")
    details = validate_details(occasion, data.occasion_details)
    payload = data.model_dump(mode="json") | {"channel": channel}

    async def work() -> tuple[int, dict[str, Any]]:
        key_row, replay = await idempotency.begin(session, "booking", idempotency_key, payload)
        if replay is not None:
            return replay.status_code, replay.body
        assert key_row is not None

        hold = await booking_repo.lock_hold(session, data.hold_id)
        if hold is None or not verify_token(settings, "hold", data.hold_id, data.hold_token):
            raise NotFoundError("Reservation not found.")
        if hold.status != "ACTIVE":
            raise HoldNotActiveError()
        cells = await booking_repo.lock_cells_by_id(session, [c.slot_id for c in hold.cells])
        now = utcnow()
        if hold.expires_at <= now:
            hold_service._release_cells(hold, cells)
            hold.status, hold.released_at = "EXPIRED", now
            await idempotency.abandon(session, key_row)
            await session.commit()
            raise HoldExpiredError()

        package = await catalogue_repo.get_package(session, hold.package_id)
        if package is None or not package.is_active:
            raise SlotUnavailableError("This package is no longer available.")
        await _revalidate_slot(session, hold, package)
        price = await pricing_service.price_for_package(
            session, package, hold.business_date, hold.guest_count
        )
        if data.quote_id:
            _check_quote(settings, data.quote_id, hold, price)

        customer = await customer_service.upsert(session, data.customer.name, data.customer.phone)
        customer.last_booking_at = now
        customer_service.record_consent(
            session, customer, "WHATSAPP_TRANSACTIONAL", data.consents.whatsapp, channel
        )

        booking = Booking(
            reference=new_reference("PLT"),
            customer=customer,
            resource_id=hold.resource_id,
            package_id=package.id,
            occasion_id=occasion.id,
            occasion_details=details,
            guest_count=hold.guest_count,
            business_date=hold.business_date,
            start_at=hold.start_at,
            end_at=hold.end_at,
            status="CONFIRMED",
            payment_status="PENDING",
            payment_mode="PAY_AT_VENUE",
            channel=channel,
            notes=data.notes,
            created_by_user_id=uuid.UUID(actor.id) if actor.type == "USER" and actor.id else None,
            history=[],
        )
        booking.slots = _move_held_to_booked(hold, cells)
        _apply_pricing(booking, price, package)
        _history(booking, None, "CONFIRMED", actor, details={"total": str(price.total)})
        session.add(booking)
        await session.flush()
        hold.status, hold.booking_id = "CONVERTED", booking.id

        body = booking_out(settings, booking, package, occasion, with_token=True).model_dump(mode="json")
        idempotency.finish(key_row, 201, body)
        audit_service.record(
            session, actor, "booking.create", "booking", booking.id, None, {"reference": booking.reference}
        )
        await session.commit()
        return 201, body

    return await run_with_retry(session, work, retry_integrity=True)


# --- read -------------------------------------------------------------------------------------------


async def get_for_customer(
    session: AsyncSession, settings: Settings, booking_id: uuid.UUID, token: str | None
) -> BookingOut:
    booking = await booking_repo.get_booking(session, booking_id)
    if booking is None or not verify_token(settings, "booking", booking_id, token):
        raise NotFoundError("Booking not found.")
    package = await catalogue_repo.get_package_any(session, booking.package_id)
    occasion = await session.get(Occasion, booking.occasion_id)
    assert package is not None and occasion is not None
    return booking_out(settings, booking, package, occasion, with_token=False)


async def get_admin(session: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await booking_repo.get_booking(session, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found.")
    return booking


# --- cancel / reschedule / status ---------------------------------------------------------------------


async def cancel(session: AsyncSession, booking_id: uuid.UUID, reason: str, actor: Actor) -> Booking:
    async def work() -> Booking:
        booking = await booking_repo.lock_booking(session, booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.status not in ACTIVE_STATUSES:
            raise ConflictError(f"A {booking.status.lower()} booking can't be cancelled.")
        cells = await booking_repo.lock_cells_by_id(session, [s.slot_id for s in booking.slots])
        units = {s.slot_id: s.units for s in booking.slots}
        for cell in cells:
            cell.booked_qty -= units[cell.id]
        previous = booking.status
        booking.status, booking.cancelled_at, booking.cancel_reason = "CANCELLED", utcnow(), reason
        _history(booking, previous, "CANCELLED", actor, reason)
        audit_service.record(
            session,
            actor,
            "booking.cancel",
            "booking",
            booking.id,
            {"status": previous},
            {"status": "CANCELLED", "reason": reason},
        )
        await session.commit()
        return booking

    return await run_with_retry(session, work)


async def reschedule(
    session: AsyncSession,
    settings: Settings,
    booking_id: uuid.UUID,
    hold_id: uuid.UUID,
    hold_token: str,
    reason: str,
    actor: Actor,
) -> Booking:
    """Move a booking onto a new hold (same package and group size). Re-prices for the new date; the old and
    new totals are recorded in the status history."""

    async def work() -> Booking:
        booking = await booking_repo.lock_booking(session, booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.status not in ACTIVE_STATUSES:
            raise ConflictError(f"A {booking.status.lower()} booking can't be rescheduled.")
        hold = await booking_repo.lock_hold(session, hold_id)
        if hold is None or not verify_token(settings, "hold", hold_id, hold_token):
            raise NotFoundError("Reservation not found.")
        if hold.status != "ACTIVE":
            raise HoldNotActiveError()
        if hold.expires_at <= utcnow():
            raise HoldExpiredError()
        if hold.package_id != booking.package_id or hold.guest_count != booking.guest_count:
            raise ValidationFailed("The new slot must be for the same package and group size.")

        old_units = {s.slot_id: s.units for s in booking.slots}
        cells = await booking_repo.lock_cells_by_id(
            session, sorted(set(old_units) | {c.slot_id for c in hold.cells})
        )
        by_id = {c.id: c for c in cells}
        for slot_id, units in old_units.items():
            by_id[slot_id].booked_qty -= units

        package = await catalogue_repo.get_package(session, booking.package_id)
        if package is None:
            raise SlotUnavailableError("This package is no longer available.")
        await _revalidate_slot(session, hold, package)
        price = await pricing_service.price_for_package(
            session, package, hold.business_date, hold.guest_count
        )
        old = {
            "date": booking.business_date.isoformat(),
            "start": to_local(booking.start_at).strftime("%H:%M"),
            "total": str(booking.pricing.total),
        }

        booking.slots = _move_held_to_booked(hold, cells)
        booking.business_date, booking.start_at, booking.end_at = (
            hold.business_date,
            hold.start_at,
            hold.end_at,
        )
        _apply_pricing(booking, price, package)
        new = {
            "date": hold.business_date.isoformat(),
            "start": to_local(hold.start_at).strftime("%H:%M"),
            "total": str(price.total),
        }
        _history(
            booking, booking.status, booking.status, actor, reason or "Rescheduled", {"from": old, "to": new}
        )
        hold.status, hold.booking_id = "CONVERTED", booking.id
        audit_service.record(session, actor, "booking.reschedule", "booking", booking.id, old, new)
        await session.commit()
        return booking

    return await run_with_retry(session, work)


async def update_status(
    session: AsyncSession, booking_id: uuid.UUID, data: StatusUpdate, actor: Actor
) -> Booking:
    booking = await booking_repo.lock_booking(session, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found.")
    if booking.status not in ACTIVE_STATUSES:
        raise ConflictError(f"A {booking.status.lower()} booking can't change to {data.status.lower()}.")
    if utcnow() < booking.start_at:
        raise ConflictError("A booking can only be marked completed or no-show after its start time.")
    previous = booking.status
    booking.status = data.status
    _history(booking, previous, data.status, actor, data.reason)
    audit_service.record(
        session, actor, "booking.status", "booking", booking.id, {"status": previous}, {"status": data.status}
    )
    await session.commit()
    return booking
