"""WhatsApp booking confirmations (INT-01) via Interakt.

Flow:
1. create_booking queues a NotificationLog (status QUEUED) in the SAME transaction when the customer
   consented - so a confirmation is never lost and never sent for a booking that rolled back.
2. send_due() claims due rows (FOR UPDATE SKIP LOCKED, status SENDING), calls Interakt, records the
   message id (SENT) or the error (retry with backoff up to MAX_ATTEMPTS, then FAILED).
   It runs right after a booking (in-process, for speed) and every 15 s in the worker (for retries).
3. Interakt webhooks move SENT -> DELIVERED / READ / FAILED. "Accepted by the API" is not "delivered".
Without INTERAKT_API_KEY the row is marked SKIPPED (visible to staff), never silently dropped.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import to_local, utcnow
from app.integrations.interakt import InteraktClient, SendResult
from app.models.booking import Booking, Customer
from app.models.catalogue import Package
from app.models.notification import NotificationLog, WebhookEvent
from app.services.phone import mask_phone

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF = [timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10)]
STALE_SENDING = timedelta(minutes=5)
STATUS_RANK = {"QUEUED": 0, "SENDING": 1, "SENT": 2, "DELIVERED": 3, "READ": 4, "FAILED": 5, "SKIPPED": 5}


def booking_variables(booking: Booking, customer: Customer, package: Package) -> list[str]:
    """Body variables, in this exact order, for the Interakt template (docs/23 "WhatsApp setup"):
    {{1}} name, {{2}} reference, {{3}} date, {{4}} time, {{5}} package, {{6}} players, {{7}} total,
    {{8}} payment."""
    start = to_local(booking.start_at)
    end = to_local(booking.end_at)
    total = booking.pricing.total
    payment = "Pay at reception" if booking.payment_status == "PENDING" else booking.payment_status.title()
    return [
        customer.name,
        booking.reference,
        start.strftime("%a, %d %b %Y"),
        f"{start:%I:%M %p} - {end:%I:%M %p}".replace(" 0", " ").lstrip("0"),
        package.name_en,
        str(booking.guest_count),
        f"Rs {total:,.0f}" if total == total.to_integral_value() else f"Rs {total:,.2f}",
        payment,
    ]


def queue_booking_confirmation(
    session: AsyncSession, settings: Settings, booking: Booking, customer: Customer, package: Package
) -> NotificationLog:
    entry = NotificationLog(
        booking_id=booking.id,
        customer_id=customer.id,
        template=settings.interakt_booking_template,
        to_masked=mask_phone(customer.phone_e164),
        variables=booking_variables(booking, customer, package),
        status="QUEUED",
        next_attempt_at=utcnow(),
    )
    session.add(entry)
    return entry


def _client(settings: Settings) -> InteraktClient | None:
    return InteraktClient(settings.interakt_api_key.get_secret_value()) if settings.interakt_api_key else None


async def send_due(
    session: AsyncSession, settings: Settings, *, limit: int = 20, client: InteraktClient | None = None
) -> int:
    now = utcnow()
    stmt = (
        select(NotificationLog)
        .where(
            or_(
                (NotificationLog.status == "QUEUED") & (NotificationLog.next_attempt_at <= now),
                (NotificationLog.status == "SENDING")
                & (NotificationLog.last_attempt_at <= now - STALE_SENDING),
            )
        )
        .order_by(NotificationLog.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list((await session.execute(stmt)).scalars())
    if not rows:
        await session.rollback()
        return 0
    client = client or _client(settings)
    for row in rows:
        row.status, row.attempts, row.last_attempt_at = "SENDING", row.attempts + 1, now
        if client is None:
            row.status, row.error = "SKIPPED", "WhatsApp (Interakt) is not configured"
    await session.commit()  # claim before calling out, so a second sender can't pick the same rows

    sent = 0
    for row in rows:
        if row.status != "SENDING" or client is None:
            continue
        customer = await session.get(Customer, row.customer_id) if row.customer_id else None
        if customer is None:
            row.status, row.error = "FAILED", "customer no longer exists"
            continue
        result: SendResult = await client.send_template(
            phone_e164=customer.phone_e164,
            template=row.template,
            language=settings.interakt_template_language,
            body_values=list(row.variables),
            callback_data=str(row.id),
        )
        if result.ok:
            row.status, row.provider_message_id, row.error = "SENT", result.message_id, None
            sent += 1
        elif result.retryable and row.attempts < MAX_ATTEMPTS:
            row.status, row.error = "QUEUED", result.error
            row.next_attempt_at = utcnow() + BACKOFF[min(row.attempts - 1, len(BACKOFF) - 1)]
        else:
            row.status, row.error = "FAILED", result.error
            log.warning("whatsapp_failed", extra={"notification_id": str(row.id), "error": result.error})
    await session.commit()
    return sent


async def send_soon(maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Best-effort immediate send after a booking; the worker retries anything left."""
    try:
        async with maker() as session:
            await send_due(session, settings, limit=5)
    except Exception:  # never let a notification problem affect the booking response
        log.exception("whatsapp_send_soon_failed")


_background: set[asyncio.Task[None]] = set()


def schedule_send(maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Fire-and-forget send_soon() that survives garbage collection; safe to call from any request."""
    if settings.app_env == "test":
        return  # tests call send_due() explicitly; no stray background work against the test database
    task = asyncio.create_task(send_soon(maker, settings))
    _background.add(task)
    task.add_done_callback(_background.discard)


# --- webhooks -------------------------------------------------------------------------------------------

_EVENT_STATUS = {
    "message_api_sent": "SENT",
    "message_api_delivered": "DELIVERED",
    "message_api_read": "READ",
    "message_api_failed": "FAILED",
}


def _find(obj: Any, key: str) -> Any:
    """Depth-first search for `key` (Interakt payload layouts differ between event types)."""
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        for v in obj.values():
            found = _find(v, key)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, key)
            if found not in (None, ""):
                return found
    return None


async def handle_interakt_webhook(session: AsyncSession, payload: dict[str, Any]) -> str:
    event_type = str(payload.get("type") or "")
    status = _EVENT_STATUS.get(event_type)
    message_id = _find(payload.get("data"), "id") if isinstance(payload.get("data"), dict) else None
    callback = _find(payload, "callback_data")
    event_key = f"{message_id or callback or uuid.uuid4().hex}:{event_type}"[:160]
    existing = (
        await session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == "INTERAKT", WebhookEvent.event_key == event_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return "duplicate"
    event = WebhookEvent(
        provider="INTERAKT", event_key=event_key, event_type=event_type or "unknown", payload=payload
    )
    session.add(event)

    row: NotificationLog | None = None
    if callback:
        try:
            row = await session.get(NotificationLog, uuid.UUID(str(callback)))
        except ValueError:
            row = None
    if row is None and message_id:
        row = (
            await session.execute(
                select(NotificationLog).where(NotificationLog.provider_message_id == str(message_id))
            )
        ).scalar_one_or_none()

    if row is not None and status is not None and STATUS_RANK[status] >= STATUS_RANK.get(row.status, 0):
        # Events can arrive out of order; never move backwards (e.g. DELIVERED after READ).
        if not (row.status == "READ" and status == "DELIVERED"):
            row.status = status
        if status in ("DELIVERED", "READ") and row.delivered_at is None:
            row.delivered_at = utcnow()
        if status == "FAILED":
            row.error = str(_find(payload, "failure_reason") or _find(payload, "message_status") or "failed")[
                :500
            ]
        event.processed = True
    await session.commit()
    return "ok" if event.processed else "ignored"
