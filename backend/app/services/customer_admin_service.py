"""Admin customer workflows (doc 16 §data principal rights): search, history, consents, export, anonymize.

Anonymizing keeps the financial record (bookings, price snapshots, consent proofs) but removes everything
that identifies the person: name, phone, email, free-text notes and occasion details, enquiry details,
and the WhatsApp template variables (which contain the name). The audit entry records *that* it happened,
never the erased values.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.timeutil import to_local, utcnow
from app.models.booking import Booking, BookingPricingSnapshot, Customer, CustomerConsent, CustomEventEnquiry
from app.models.catalogue import Package
from app.models.notification import NotificationLog
from app.services import audit_service
from app.services.context import Actor
from app.services.phone import mask_phone, normalize_indian_mobile

ANONYMIZED_NAME = "Anonymized customer"


def _anon_phone(customer_id: uuid.UUID) -> str:
    # Unique (the column is UNIQUE) and obviously not a real number: "+000" + 12 hex chars = 16 chars.
    return "+000" + hashlib.sha256(customer_id.bytes).hexdigest()[:12]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def search(
    session: AsyncSession, q: str | None, offset: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    stats = (
        select(
            Booking.customer_id.label("cid"),
            func.count(Booking.id).label("bookings"),
            func.sum(BookingPricingSnapshot.total).label("spent"),
        )
        .join(BookingPricingSnapshot, BookingPricingSnapshot.booking_id == Booking.id)
        .where(Booking.status != "CANCELLED")
        .group_by(Booking.customer_id)
        .subquery()
    )
    stmt = select(Customer, stats.c.bookings, stats.c.spent).outerjoin(stats, stats.c.cid == Customer.id)
    term = (q or "").strip()
    if term:
        conditions: list[Any] = [Customer.name.ilike(f"%{term}%")]
        digits = "".join(ch for ch in term if ch.isdigit())
        if len(digits) >= 10:
            try:
                conditions.append(Customer.phone_e164 == normalize_indian_mobile(term))
            except ValidationFailed:
                pass
        elif len(digits) >= 4:
            conditions.append(Customer.phone_e164.like(f"%{digits}"))
        stmt = stmt.where(or_(*conditions))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(
                Customer.last_booking_at.is_(None),
                Customer.last_booking_at.desc(),
                Customer.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [_summary(c, n, spent) for c, n, spent in rows], int(total)


def _summary(c: Customer, bookings: int | None, spent: Any) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "phone": c.phone_e164 if not c.anonymized_at else "",
        "phone_masked": mask_phone(c.phone_e164) if not c.anonymized_at else "—",
        "email": c.email,
        "preferred_language": c.preferred_language,
        "first_seen_at": _iso(c.first_seen_at),
        "last_booking_at": _iso(c.last_booking_at),
        "anonymized_at": _iso(c.anonymized_at),
        "bookings": int(bookings or 0),
        "total_spent": str(spent or 0),
    }


async def _get(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


async def detail(session: AsyncSession, customer_id: uuid.UUID) -> dict[str, Any]:
    customer = await _get(session, customer_id)
    bookings = (
        await session.execute(
            select(Booking, Package.name_en)
            .join(Package, Package.id == Booking.package_id)
            .where(Booking.customer_id == customer.id)
            .order_by(Booking.start_at.desc())
        )
    ).all()
    enquiries = (
        (
            await session.execute(
                select(CustomEventEnquiry)
                .where(CustomEventEnquiry.customer_id == customer.id)
                .order_by(CustomEventEnquiry.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    consents = (
        (
            await session.execute(
                select(CustomerConsent)
                .where(CustomerConsent.customer_id == customer.id)
                .order_by(CustomerConsent.created_at.desc(), CustomerConsent.id.desc())
            )
        )
        .scalars()
        .all()
    )
    current: dict[str, bool] = {}
    for c in consents:  # newest first: the first row per purpose is the current state
        current.setdefault(c.purpose, c.granted)
    spent = sum(
        (b.pricing.total for b, _ in bookings if b.status != "CANCELLED" and b.pricing), start=Decimal(0)
    )
    return {
        **_summary(customer, sum(1 for b, _ in bookings if b.status != "CANCELLED"), spent),
        "bookings_list": [
            {
                "id": str(b.id),
                "reference": b.reference,
                "date": b.business_date.isoformat(),
                "start_time": to_local(b.start_at).strftime("%H:%M"),
                "package_name": name,
                "guest_count": b.guest_count,
                "status": b.status,
                "channel": b.channel,
                "total": str(b.pricing.total if b.pricing else 0),
            }
            for b, name in bookings
        ],
        "enquiries": [
            {
                "id": str(e.id),
                "reference": e.reference,
                "status": e.status,
                "guest_count": e.guest_count,
                "preferred_date": e.preferred_date.isoformat() if e.preferred_date else None,
                "created_at": _iso(e.created_at),
            }
            for e in enquiries
        ],
        "consents": current,
        "consent_log": [
            {
                "purpose": c.purpose,
                "granted": c.granted,
                "notice_version": c.notice_version,
                "channel": c.channel,
                "created_at": _iso(c.created_at),
            }
            for c in consents
        ],
    }


async def export(session: AsyncSession, customer_id: uuid.UUID, actor: Actor) -> dict[str, Any]:
    """Everything we hold about the person (right of access). The export itself is audited."""
    data = await detail(session, customer_id)
    bookings = (
        (await session.execute(select(Booking).where(Booking.customer_id == customer_id))).scalars().all()
    )
    enquiries = (
        (
            await session.execute(
                select(CustomEventEnquiry).where(CustomEventEnquiry.customer_id == customer_id)
            )
        )
        .scalars()
        .all()
    )
    notifications = (
        (await session.execute(select(NotificationLog).where(NotificationLog.customer_id == customer_id)))
        .scalars()
        .all()
    )
    audit_service.record(session, actor, "customer.export", "customer", customer_id)
    await session.commit()
    return {
        "exported_at": utcnow().isoformat(),
        "customer": {k: data[k] for k in ("id", "name", "phone", "email", "preferred_language")}
        | {"first_seen_at": data["first_seen_at"], "anonymized_at": data["anonymized_at"]},
        "consent_log": data["consent_log"],
        "bookings": [
            {
                "reference": b.reference,
                "date": b.business_date.isoformat(),
                "start_at": _iso(b.start_at),
                "guest_count": b.guest_count,
                "status": b.status,
                "channel": b.channel,
                "notes": b.notes,
                "occasion_details": b.occasion_details,
                "total": str(b.pricing.total if b.pricing else 0),
            }
            for b in bookings
        ],
        "enquiries": [
            {
                "reference": e.reference,
                "status": e.status,
                "guest_count": e.guest_count,
                "preferred_date": e.preferred_date.isoformat() if e.preferred_date else None,
                "details": e.details,
                "created_at": _iso(e.created_at),
            }
            for e in enquiries
        ],
        "messages": [
            {
                "template": n.template,
                "status": n.status,
                "sent_to": n.to_masked,
                "created_at": _iso(n.created_at),
            }
            for n in notifications
        ],
    }


async def anonymize(
    session: AsyncSession, customer_id: uuid.UUID, reason: str, actor: Actor
) -> dict[str, Any]:
    customer = await _get(session, customer_id)
    if customer.anonymized_at is not None:
        raise ConflictError("This customer is already anonymized.")
    upcoming = (
        await session.execute(
            select(func.count(Booking.id)).where(
                Booking.customer_id == customer.id,
                Booking.status.in_(("CONFIRMED", "PENDING_PAYMENT")),
                Booking.end_at > utcnow(),
            )
        )
    ).scalar_one()
    if upcoming:
        raise ConflictError(
            "This customer has an upcoming booking. Cancel it, or wait until it's played, then anonymize.",
            details={"upcoming_bookings": int(upcoming)},
        )
    customer.name = ANONYMIZED_NAME
    customer.phone_e164 = _anon_phone(customer.id)
    customer.email = None
    customer.anonymized_at = utcnow()
    await session.execute(
        update(Booking).where(Booking.customer_id == customer.id).values(notes="", occasion_details={})
    )
    await session.execute(
        update(CustomEventEnquiry)
        .where(CustomEventEnquiry.customer_id == customer.id)
        .values(details={}, staff_notes="")
    )
    await session.execute(
        update(NotificationLog)
        .where(NotificationLog.customer_id == customer.id)
        .values(variables=[], to_masked="—")
    )
    audit_service.record(
        session, actor, "customer.anonymize", "customer", customer.id, None, {"reason": reason[:255]}
    )
    await session.commit()
    return await detail(session, customer.id)


async def correct(
    session: AsyncSession,
    customer_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None,
    email: str | None,
    preferred_language: str | None,
) -> dict[str, Any]:
    """Right to correction. Phone is the customer's identity key, so it is not editable here."""
    customer = await _get(session, customer_id)
    if customer.anonymized_at is not None:
        raise ConflictError("An anonymized customer can't be edited.")
    changed: list[str] = []
    if name is not None and name != customer.name:
        customer.name, changed = name, [*changed, "name"]
    if email is not None and (email or None) != customer.email:
        customer.email, changed = (email or None), [*changed, "email"]
    if preferred_language is not None and preferred_language != customer.preferred_language:
        customer.preferred_language, changed = preferred_language, [*changed, "preferred_language"]
    if changed:
        # Field names only: the audit log must not become a second copy of personal data.
        audit_service.record(
            session, actor, "customer.correct", "customer", customer.id, None, {"fields": changed}
        )
        await session.commit()
    return await detail(session, customer.id)
