"""Customer upsert by normalized phone, and consent recording."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.booking import Customer, CustomerConsent
from app.repositories import booking as booking_repo
from app.services.phone import normalize_indian_mobile

CONSENT_NOTICE_VERSION = "2026-11-v1"


async def upsert(session: AsyncSession, name: str, raw_phone: str, *, language: str = "en") -> Customer:
    """Find-or-create inside the caller's transaction; a concurrent insert of the same phone is resolved
    with a savepoint so the outer transaction survives."""
    phone = normalize_indian_mobile(raw_phone)
    customer = await booking_repo.get_customer_by_phone(session, phone)
    if customer is None:
        try:
            async with session.begin_nested():
                customer = Customer(name=name, phone_e164=phone, preferred_language=language)
                session.add(customer)
        except IntegrityError:
            customer = await booking_repo.get_customer_by_phone(session, phone)
            assert customer is not None
    customer.name = name
    customer.anonymized_at = None
    return customer


def record_consent(
    session: AsyncSession, customer: Customer, purpose: str, granted: bool, channel: str
) -> None:
    session.add(
        CustomerConsent(
            customer_id=customer.id,
            purpose=purpose,
            granted=granted,
            notice_version=CONSENT_NOTICE_VERSION,
            channel=channel,
            created_at=utcnow(),
        )
    )
