"""WhatsApp confirmations via Interakt (INT-01): queueing, sending with retries, delivery webhooks."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import today_local, utcnow
from app.integrations.interakt import InteraktClient
from app.models.catalogue import Package
from app.models.notification import NotificationLog
from app.schemas.booking import BookingCreate, HoldCreate
from app.services import booking_service, hold_service, notification_service
from app.services.context import Actor
from tests.conftest import make_settings

SECRET = "hook-secret-0123456789abcdef"


@pytest.fixture
def settings() -> Settings:
    return make_settings(
        interakt_api_key="test-interakt-key",
        interakt_webhook_secret=SECRET,
        public_rate_limit_per_minute=10_000,
        booking_rate_limit_per_minute=10_000,
    )


def monday() -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


async def book(
    maker: async_sessionmaker[AsyncSession], settings: Settings, whatsapp: bool = True, start: str = "18:00"
) -> dict[str, Any]:
    async with maker() as s:
        pkg = (await s.execute(select(Package).where(Package.code == "EXPERT"))).scalar_one()
        _, hold = await hold_service.create_hold(
            s,
            settings,
            HoldCreate(package_id=pkg.id, date=monday(), start_time=start, guest_count=4),  # type: ignore[arg-type]
            channel="WEB",
            idempotency_key=str(uuid.uuid4()),
        )
    async with maker() as s:
        data = BookingCreate(
            hold_id=hold["hold_id"],
            hold_token=hold["hold_token"],
            customer={"name": "Riya Sharma", "phone": "9876543210"},  # type: ignore[arg-type]
            occasion_code="FRIENDS_FAMILY",
            consents={"whatsapp": whatsapp},  # type: ignore[arg-type]
        )
        _, body = await booking_service.create_booking(
            s, settings, data, channel="KIOSK", idempotency_key=str(uuid.uuid4()), actor=Actor("PUBLIC")
        )
    return body


async def logs(maker: async_sessionmaker[AsyncSession]) -> list[NotificationLog]:
    async with maker() as s:
        return list((await s.execute(select(NotificationLog))).scalars())


def mock_client(handler: Any) -> InteraktClient:
    return InteraktClient("test-interakt-key", transport=httpx.MockTransport(handler))


async def test_booking_queues_confirmation_only_with_consent(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    b = await book(maker, settings, whatsapp=True)
    await book(maker, settings, whatsapp=False, start="12:00")
    rows = await logs(maker)
    assert len(rows) == 1 and rows[0].status == "QUEUED" and rows[0].to_masked == "98•••••210"
    v = rows[0].variables
    assert (
        v[0] == "Riya Sharma" and v[1] == b["reference"] and v[3].startswith("6:00 PM") and v[4] == "Advanced"
    )
    assert v[5] == "4" and v[6] == "Rs 2,400" and v[7] == "Pay at reception"


async def test_send_success_records_message_id(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await book(maker, settings)
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200, json={"result": True, "message": "Message created successfully", "id": "msg-123"}
        )

    async with maker() as s:
        assert await notification_service.send_due(s, settings, client=mock_client(handler)) == 1
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.interakt.ai/v1/public/message/"
    assert req.headers["Authorization"] == "Basic test-interakt-key"
    assert body["countryCode"] == "+91" and body["phoneNumber"] == "9876543210" and body["type"] == "Template"
    assert body["template"]["name"] == "booking_confirmation" and len(body["template"]["bodyValues"]) == 8
    row = (await logs(maker))[0]
    assert (
        row.status == "SENT" and row.provider_message_id == "msg-123" and body["callbackData"] == str(row.id)
    )
    async with maker() as s:  # nothing left to send
        assert await notification_service.send_due(s, settings, client=mock_client(handler)) == 0


async def test_retries_then_fails(maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    await book(maker, settings)
    down = mock_client(lambda req: httpx.Response(503, json={}))
    for attempt in range(1, 5):
        async with maker() as s:
            await notification_service.send_due(s, settings, client=down)
        row = (await logs(maker))[0]
        if attempt < 4:
            assert row.status == "QUEUED" and row.attempts == attempt and row.next_attempt_at > utcnow()
            async with maker() as s:  # pretend the backoff elapsed
                r = await s.get(NotificationLog, row.id)
                assert r is not None
                r.next_attempt_at = utcnow() - timedelta(seconds=1)
                await s.commit()
    assert row.status == "FAILED" and row.attempts == 4 and row.error == "HTTP 503"


async def test_rejected_template_fails_without_retry(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await book(maker, settings)
    bad = mock_client(
        lambda req: httpx.Response(400, json={"result": False, "message": "Template not found"})
    )
    async with maker() as s:
        await notification_service.send_due(s, settings, client=bad)
    row = (await logs(maker))[0]
    assert row.status == "FAILED" and row.error == "Template not found" and row.attempts == 1


async def test_not_configured_is_visible_not_silent(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await book(maker, settings)
    async with maker() as s:
        await notification_service.send_due(s, make_settings(interakt_api_key=None))
    row = (await logs(maker))[0]
    assert row.status == "SKIPPED" and "not configured" in (row.error or "")


async def test_webhooks_update_delivery_status(
    client: AsyncClient,
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    owner_headers: dict[str, str],
) -> None:
    await book(maker, settings)
    ok = mock_client(lambda req: httpx.Response(200, json={"result": True, "id": "msg-9"}))
    async with maker() as s:
        await notification_service.send_due(s, settings, client=ok)
    row = (await logs(maker))[0]

    def event(kind: str) -> dict[str, Any]:
        source = {"callback_data": str(row.id)}
        return {"type": kind, "data": {"message": {"id": "msg-9", "meta_data": {"source_data": source}}}}

    assert (
        await client.post("/api/v1/webhooks/interakt/wrong", json=event("message_api_delivered"))
    ).status_code == 404
    url = f"/api/v1/webhooks/interakt/{SECRET}"
    assert (await client.post(url, json=event("message_api_delivered"))).json() == {"status": "ok"}
    assert (await client.post(url, json=event("message_api_delivered"))).json() == {"status": "duplicate"}
    await client.post(url, json=event("message_api_read"))
    await client.post(
        url, json={"type": "message_api_delivered", "data": {"message": {"id": "msg-9", "x": 1}}}
    )
    final = (await logs(maker))[0]
    assert (
        final.status == "READ" and final.delivered_at is not None
    )  # a late "delivered" doesn't move it back

    listed = (await client.get("/api/v1/admin/notifications", headers=owner_headers)).json()
    assert listed["total"] == 1 and listed["items"][0]["status"] == "READ"


async def test_failed_webhook_records_reason(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await book(maker, settings)
    sent = mock_client(lambda r: httpx.Response(200, json={"result": True, "id": "m-f"}))
    async with maker() as s:
        await notification_service.send_due(s, settings, client=sent)
    await client.post(
        f"/api/v1/webhooks/interakt/{SECRET}",
        json={
            "type": "message_api_failed",
            "data": {"message": {"id": "m-f", "failure_reason": "User not on WhatsApp"}},
        },
    )
    row = (await logs(maker))[0]
    assert row.status == "FAILED" and row.error == "User not on WhatsApp"
