"""Custom event enquiries (birthdays, corporate, schools, large groups) routed to staff."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.timeutil import to_local, today_local
from app.db.retry import run_with_retry
from app.models.booking import CustomEventEnquiry
from app.models.catalogue import Occasion
from app.repositories import booking as booking_repo
from app.repositories import catalogue as catalogue_repo
from app.schemas.booking import AdminEnquiryOut, EnquiryCreate, EnquiryOut, EnquiryUpdate
from app.services import audit_service, booking_service, customer_service, idempotency
from app.services.context import Actor
from app.services.refs import new_reference


def enquiry_out(e: CustomEventEnquiry, occasion: Occasion) -> EnquiryOut:
    return EnquiryOut(
        id=e.id,
        reference=e.reference,
        status=e.status,
        occasion_code=occasion.code,
        guest_count=e.guest_count,
        preferred_date=e.preferred_date,
        created_at=to_local(e.created_at),
    )


async def admin_out(session: AsyncSession, e: CustomEventEnquiry) -> AdminEnquiryOut:
    occasion = await session.get(Occasion, e.occasion_id)
    assert occasion is not None
    return AdminEnquiryOut(
        **enquiry_out(e, occasion).model_dump(),
        customer_name=e.customer.name,
        customer_phone=e.customer.phone_e164,
        details=e.details,
        staff_notes=e.staff_notes,
        channel=e.channel,
    )


async def create(
    session: AsyncSession, data: EnquiryCreate, *, channel: str, idempotency_key: str, actor: Actor
) -> tuple[int, dict[str, Any]]:
    occasion = await catalogue_repo.get_occasion(session, data.occasion_code)
    if occasion is None or not occasion.is_active:
        raise ValidationFailed("Unknown occasion.", details={"occasion_code": data.occasion_code})
    details = booking_service.validate_details(occasion, data.details)
    if data.preferred_date is not None and data.preferred_date < today_local():
        raise ValidationFailed(
            "The preferred date can't be in the past.", details={"field": "preferred_date"}
        )
    payload = data.model_dump(mode="json") | {"channel": channel}
    occasion_id = occasion.id  # plain value: a retried transaction expires ORM objects

    async def work() -> tuple[int, dict[str, Any]]:
        key_row, replay = await idempotency.begin(session, "enquiry", idempotency_key, payload)
        if replay is not None:
            return replay.status_code, replay.body
        assert key_row is not None
        occasion = await session.get(Occasion, occasion_id)
        assert occasion is not None
        customer = await customer_service.upsert(session, data.customer.name, data.customer.phone)
        customer_service.record_consent(
            session, customer, "WHATSAPP_TRANSACTIONAL", data.consents.whatsapp, channel
        )
        enquiry = CustomEventEnquiry(
            reference=new_reference("ENQ"),
            customer=customer,
            occasion_id=occasion_id,
            guest_count=data.guest_count,
            preferred_date=data.preferred_date,
            details=details,
            status="NEW",
            channel=channel,
        )
        session.add(enquiry)
        await session.flush()
        body = enquiry_out(enquiry, occasion).model_dump(mode="json")
        idempotency.finish(key_row, 201, body)
        audit_service.record(
            session, actor, "enquiry.create", "enquiry", enquiry.id, None, {"reference": enquiry.reference}
        )
        await session.commit()
        return 201, body

    return await run_with_retry(session, work, retry_integrity=True)


async def search(
    session: AsyncSession, statuses: Sequence[str] | None, query: str | None, offset: int, limit: int
) -> tuple[Sequence[CustomEventEnquiry], int]:
    return await booking_repo.search_enquiries(
        session, statuses=statuses, query=query, offset=offset, limit=limit
    )


async def update(
    session: AsyncSession, enquiry_id: uuid.UUID, data: EnquiryUpdate, actor: Actor
) -> CustomEventEnquiry:
    enquiry = await session.get(CustomEventEnquiry, enquiry_id)
    if enquiry is None:
        raise NotFoundError("Enquiry not found.")
    patch = data.model_dump(exclude_unset=True, exclude_none=True)
    before = {k: getattr(enquiry, k) for k in patch}
    for key, value in patch.items():
        setattr(enquiry, key, value)
    audit_service.record(session, actor, "enquiry.update", "enquiry", enquiry.id, before, patch)
    await session.commit()
    return enquiry
