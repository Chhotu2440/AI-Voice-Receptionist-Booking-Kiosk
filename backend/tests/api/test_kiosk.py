"""Kiosk pairing/device auth, the kiosk state machine (KIOSK-*/SM-*) and the WebSocket transport."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import app.models  # noqa: F401
from app.core.config import Settings
from app.core.ratelimit import InMemoryRateLimiter
from app.core.security import create_access_token
from app.core.timeutil import today_local, utcnow
from app.db.base import Base
from app.kiosk.flow import InvalidTransitionError, KioskFlow
from app.kiosk.state import KioskState
from app.kiosk.store import InMemoryKioskStateStore
from app.main import create_app
from app.models.booking import AvailabilitySlot, Booking, SlotHold
from app.models.kiosk import KioskSession
from app.seed import seed_initial_catalogue, seed_reference
from app.services import kiosk_device_service
from app.services.context import Actor
from tests.conftest import make_settings


@pytest.fixture
def settings() -> Settings:
    return make_settings(public_rate_limit_per_minute=10_000, booking_rate_limit_per_minute=10_000)


def monday() -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


# --- pairing & device auth --------------------------------------------------------------------------


async def test_pairing_and_device_token(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.post("/api/v1/admin/kiosks", headers=owner_headers, json={"name": "Reception"})
    assert r.status_code == 201, r.text
    code, kiosk_id = r.json()["pairing_code"], r.json()["kiosk"]["id"]
    assert len(code) == 9 and code[4] == "-" and r.json()["kiosk"]["status"] == "PENDING"

    reg = await client.post("/api/v1/kiosk/register", json={"pairing_code": code.lower()})
    assert reg.status_code == 200, reg.text
    creds = reg.json()
    assert (
        await client.post("/api/v1/kiosk/register", json={"pairing_code": code})
    ).status_code == 401  # one-time

    tok = await client.post(
        "/api/v1/kiosk/token", json={"device_id": creds["device_id"], "device_secret": creds["device_secret"]}
    )
    assert tok.status_code == 200
    device_headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    hb = await client.post(
        "/api/v1/kiosk/heartbeat", headers=device_headers, json={"app_version": "0.1.0", "camera_ok": True}
    )
    assert hb.status_code == 200 and hb.json()["config"]["assistant_name"] == "Zara"

    # Device tokens can't be used as admin tokens, and admin tokens can't act as devices.
    assert (await client.get("/api/v1/auth/me", headers=device_headers)).status_code == 401
    assert (
        await client.post("/api/v1/kiosk/heartbeat", headers=owner_headers, json={"app_version": "x"})
    ).status_code == 401

    listed = (await client.get("/api/v1/admin/kiosks", headers=owner_headers)).json()
    assert listed[0]["online"] is True and listed[0]["app_version"] == "0.1.0"

    wrong = await client.post(
        "/api/v1/kiosk/token", json={"device_id": creds["device_id"], "device_secret": "x" * 40}
    )
    assert wrong.status_code == 401
    await client.patch(f"/api/v1/admin/kiosks/{kiosk_id}", headers=owner_headers, json={"status": "DISABLED"})
    assert (
        await client.post("/api/v1/kiosk/heartbeat", headers=device_headers, json={"app_version": "x"})
    ).status_code == 401
    disabled = await client.post(
        "/api/v1/kiosk/token", json={"device_id": creds["device_id"], "device_secret": creds["device_secret"]}
    )
    assert disabled.status_code == 403


async def test_staff_cannot_manage_kiosks(client: AsyncClient, make_user, login) -> None:  # type: ignore[no-untyped-def]
    staff = await login(*(await make_user("STAFF")))
    assert (await client.post("/api/v1/admin/kiosks", headers=staff, json={"name": "x"})).status_code == 403


async def test_expired_pairing_code(maker: async_sessionmaker[AsyncSession], client: AsyncClient) -> None:
    async with maker() as s:
        device, code = await kiosk_device_service.create(s, "K", Actor.system())
        device.pairing_expires_at = utcnow() - timedelta(seconds=1)
        await s.commit()
    assert (await client.post("/api/v1/kiosk/register", json={"pairing_code": code})).status_code == 401


# --- state machine ----------------------------------------------------------------------------------


@pytest.fixture
async def device_id(maker: async_sessionmaker[AsyncSession]) -> str:
    async with maker() as s:
        device, code = await kiosk_device_service.create(s, "Reception", Actor.system())
        await kiosk_device_service.register(s, code, None)
        return str(device.id)


@pytest.fixture
def flow(maker: async_sessionmaker[AsyncSession], settings: Settings) -> KioskFlow:
    return KioskFlow(maker, settings, InMemoryKioskStateStore())


async def walk_to_packages(
    flow: KioskFlow, dev: str, guests: int = 4, occasion: str = "FRIENDS_FAMILY"
) -> KioskState:
    for name, payload in [
        ("start", {}),
        ("continue", {}),
        ("set_name", {"name": "  Riya   Sharma "}),
        ("set_phone", {"phone": "98765 43210"}),
        ("confirm_phone", {}),
        ("set_guests", {"count": guests}),
        ("set_occasion", {"code": occasion}),
    ]:
        s = await flow.handle(dev, name, payload)
        assert s.error is None, (name, s.error)
    return s


async def walk_to_summary(flow: KioskFlow, dev: str, start: str = "18:00") -> KioskState:
    s = await walk_to_packages(flow, dev)
    expert = next(p for p in s.packages if p.code == "EXPERT")
    s = await flow.handle(dev, "select_package", {"package_id": expert.id})
    assert s.state == "DATE_SELECTION" and len(s.available_dates) == 14
    s = await flow.handle(dev, "select_date", {"date": monday().isoformat()})
    assert s.state == "SLOT_SELECTION" and any(x.start_time == start for x in s.slots)
    s = await flow.handle(dev, "select_slot", {"start_time": start})
    assert s.state == "BOOKING_SUMMARY", s.error
    return s


async def cells(maker: async_sessionmaker[AsyncSession]) -> list[tuple[int, int]]:
    async with maker() as s:
        return [(c.held_qty, c.booked_qty) for c in (await s.execute(select(AvailabilitySlot))).scalars()]


async def test_e2e_touch_booking_via_flow(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    s = await walk_to_summary(flow, device_id)
    assert s.customer_name == "Riya Sharma" and s.phone_e164 == "+919876543210"
    assert [p.code for p in s.packages] == ["BEGINNER", "INTERMEDIATE", "EXPERT"]
    assert s.quote is not None and s.quote.total == 2400 and s.hold_id and s.hold_expires_at
    s = await flow.handle(device_id, "set_consent", {"whatsapp": True})
    s = await flow.handle(device_id, "confirm_booking", {})
    assert s.state == "BOOKING_CONFIRMED", s.error
    assert s.booking is not None and s.booking.reference.startswith("PLT-") and s.booking.channel == "KIOSK"
    session_id = s.session_id

    s = await flow.handle(device_id, "finish", {})
    assert s.state == "IDLE" and s.customer_name is None and s.session_id is None
    async with maker() as db:
        booking = (await db.execute(select(Booking))).scalar_one()
        row = await db.get(KioskSession, uuid.UUID(session_id or ""))
        assert row is not None and row.end_reason == "COMPLETED" and row.booking_id == booking.id
        assert row.furthest_state == "BOOKING_SUMMARY"


async def test_invalid_transitions_rejected(flow: KioskFlow, device_id: str) -> None:
    with pytest.raises(InvalidTransitionError):
        await flow.handle(device_id, "set_name", {"name": "X"})
    await flow.handle(device_id, "start", {})
    with pytest.raises(InvalidTransitionError):
        await flow.handle(device_id, "confirm_booking", {})  # SM-001: can't skip to booking
    with pytest.raises(InvalidTransitionError):
        await flow.handle(device_id, "drop_tables", {})


async def test_validation_errors_keep_state(flow: KioskFlow, device_id: str) -> None:
    for name in ("start", "continue"):
        await flow.handle(device_id, name, {})
    s = await flow.handle(device_id, "set_name", {"name": "R2D2"})
    assert s.state == "CUSTOMER_NAME" and s.error and s.error.code == "VALIDATION_ERROR"
    s = await flow.handle(device_id, "set_name", {"name": "Riya"})
    s = await flow.handle(device_id, "set_phone", {"phone": "12345"})
    assert s.state == "CUSTOMER_PHONE" and s.error and s.error.code == "VALIDATION_ERROR"
    s = await flow.handle(device_id, "confirm_phone", {})
    assert s.error and s.state == "CUSTOMER_PHONE"


async def test_public_snapshot_hides_secrets_and_masks_phone(flow: KioskFlow, device_id: str) -> None:
    for name, payload in [
        ("start", {}),
        ("continue", {}),
        ("set_name", {"name": "Riya"}),
        ("set_phone", {"phone": "9876543210"}),
    ]:
        s = await flow.handle(device_id, name, payload)
    assert s.public()["phone_display"] == "98765 43210"
    s = await walk_to_summary_from_phone(flow, device_id)
    pub = s.public()
    assert "hold_token" not in pub and "phone_e164" not in pub and pub["phone_display"] == "98•••••210"


async def walk_to_summary_from_phone(flow: KioskFlow, dev: str) -> KioskState:
    await flow.handle(dev, "confirm_phone", {})
    await flow.handle(dev, "set_guests", {"count": 4})
    s = await flow.handle(dev, "set_occasion", {"code": "FRIENDS_FAMILY"})
    expert = next(p for p in s.packages if p.code == "EXPERT")
    await flow.handle(dev, "select_package", {"package_id": expert.id})
    await flow.handle(dev, "select_date", {"date": monday().isoformat()})
    return await flow.handle(dev, "select_slot", {"start_time": "18:00"})


async def test_corporate_and_large_groups_go_to_enquiry(flow: KioskFlow, device_id: str) -> None:
    s = await walk_to_packages(flow, device_id, guests=4, occasion="CORPORATE")
    assert s.state == "CUSTOM_EVENT_DETAILS"
    s = await flow.handle(
        device_id,
        "submit_enquiry",
        {
            "preferred_date": (today_local() + timedelta(days=10)).isoformat(),
            "details": {"company_name": "Acme", "special_requirements": "Team building"},
        },
    )
    assert s.state == "SESSION_COMPLETE" and s.enquiry_reference and s.enquiry_reference.startswith("ENQ-")
    s = await flow.handle(device_id, "finish", {})
    s = await walk_to_packages(flow, device_id, guests=25)
    assert s.state == "CUSTOM_EVENT_DETAILS"


async def test_sm002_guest_change_releases_hold_and_clears_choices(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    await walk_to_summary(flow, device_id)
    assert (1, 0) in await cells(maker)
    s = await flow.handle(device_id, "edit", {"field": "guests"})
    assert s.state == "GUEST_COUNT" and s.hold_id is None and s.package_id is None and s.packages == []
    assert all(c == (0, 0) for c in await cells(maker))


async def test_edit_name_returns_to_summary(flow: KioskFlow, device_id: str) -> None:
    await walk_to_summary(flow, device_id)
    s = await flow.handle(device_id, "edit", {"field": "name"})
    assert s.state == "CUSTOMER_NAME" and s.hold_id is not None
    s = await flow.handle(device_id, "set_name", {"name": "Riya Kapoor"})
    assert s.state == "BOOKING_SUMMARY" and s.customer_name == "Riya Kapoor"
    s = await flow.handle(device_id, "edit", {"field": "unknown"})
    assert s.error is not None and s.error.code == "VALIDATION_ERROR" and s.state == "BOOKING_SUMMARY"


async def test_back_releases_hold(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    await walk_to_summary(flow, device_id)
    s = await flow.handle(device_id, "back", {})
    assert s.state == "SLOT_SELECTION" and s.hold_id is None
    assert all(c == (0, 0) for c in await cells(maker))
    s = await flow.handle(device_id, "back", {})
    assert s.state == "DATE_SELECTION" and s.slots == []


async def test_slot_taken_meanwhile_refreshes_slots(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    s = await walk_to_packages(flow, device_id)
    expert = next(p for p in s.packages if p.code == "EXPERT")
    await flow.handle(device_id, "select_package", {"package_id": expert.id})
    s = await flow.handle(device_id, "select_date", {"date": monday().isoformat()})
    assert any(x.start_time == "18:00" for x in s.slots)
    other = KioskFlow(maker, settings, InMemoryKioskStateStore())
    await walk_to_summary(other, device_id)  # another screen grabs 18:00
    s = await flow.handle(device_id, "select_slot", {"start_time": "18:00"})
    assert s.state == "SLOT_SELECTION" and s.error and s.error.code == "SLOT_UNAVAILABLE"
    assert all(x.start_time != "18:00" for x in s.slots)


async def test_hold_expired_at_confirmation(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    s = await walk_to_summary(flow, device_id)
    async with maker() as db:
        hold = await db.get(SlotHold, uuid.UUID(s.hold_id or ""))
        assert hold is not None
        hold.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()
    s = await flow.handle(device_id, "confirm_booking", {})
    assert s.state == "SLOT_SELECTION" and s.error and s.error.code == "HOLD_EXPIRED"
    assert any(x.start_time == "18:00" for x in s.slots)  # released and offered again


async def test_reconnect_without_resume_ends_session(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    s = await walk_to_summary(flow, device_id)
    same = await flow.connect(device_id, s.session_id)
    assert same.state == "BOOKING_SUMMARY"
    fresh = await flow.connect(device_id, None)  # browser crash / reload
    assert fresh.state == "IDLE" and fresh.customer_name is None
    assert all(c == (0, 0) for c in await cells(maker))
    async with maker() as db:
        row = await db.get(KioskSession, uuid.UUID(s.session_id or ""))
        assert row is not None and row.end_reason == "DISCONNECTED"


async def test_staff_assist_and_cancel(
    flow: KioskFlow, device_id: str, maker: async_sessionmaker[AsyncSession]
) -> None:
    await walk_to_summary(flow, device_id)
    s = await flow.handle(device_id, "staff_assist", {})
    assert s.state == "STAFF_ASSISTANCE"
    s = await flow.handle(device_id, "staff_resume", {})
    assert s.state == "BOOKING_SUMMARY"
    s = await flow.handle(device_id, "cancel", {})
    assert s.state == "SESSION_CANCELLED" and s.customer_name is None
    assert all(c == (0, 0) for c in await cells(maker))
    assert (await flow.handle(device_id, "finish", {})).state == "IDLE"


async def test_language_switch(flow: KioskFlow, device_id: str) -> None:
    s = await flow.handle(device_id, "set_language", {"language": "hi"})
    assert s.language == "hi"
    s = await flow.handle(device_id, "start", {})
    assert s.language == "hi"


# --- WebSocket ----------------------------------------------------------------------------------------


def test_websocket_protocol(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'ws.db').as_posix()}"
    engine = create_async_engine(url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    settings = make_settings()

    async def setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as s:
            await seed_reference(s)
            await seed_initial_catalogue(s)
            device, code = await kiosk_device_service.create(s, "WS", Actor.system())
            await kiosk_device_service.register(s, code, None)
            return create_access_token(settings, str(device.id), {"typ": "device"})

    token = asyncio.run(setup())

    application = create_app(settings)
    application.state.sessionmaker = maker
    application.state.rate_limiter = InMemoryRateLimiter()
    with TestClient(application) as tc:
        with tc.websocket_connect("/ws/kiosk") as ws:
            ws.send_json({"type": "auth", "token": "garbage"})
            with pytest.raises(Exception):  # noqa: B017 - server closes with 4401
                ws.receive_json()
        with tc.websocket_connect("/ws/kiosk") as ws:
            ws.send_json({"type": "auth", "token": token})
            first: dict[str, Any] = ws.receive_json()
            assert (
                first["type"] == "state" and first["state"]["state"] == "IDLE" and "start" in first["allowed"]
            )
            ws.send_json({"type": "intent", "id": "1", "name": "start", "payload": {}})
            msg = ws.receive_json()
            assert msg["in_reply_to"] == "1" and msg["state"]["state"] == "GREETING"
            ws.send_json({"type": "intent", "id": "2", "name": "confirm_booking", "payload": {}})
            err = ws.receive_json()
            assert err["type"] == "error" and err["error"]["code"] == "INVALID_STATE_TRANSITION"
            assert ws.receive_json()["state"]["state"] == "GREETING"
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
    asyncio.run(engine.dispose())
