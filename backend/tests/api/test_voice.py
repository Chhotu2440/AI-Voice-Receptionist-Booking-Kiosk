"""Voice tools drive the same state machine as touch; the gateway relays audio, tools and barge-in."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import app.models  # noqa: F401
from app.core.config import Settings
from app.core.ratelimit import InMemoryRateLimiter
from app.core.security import create_access_token
from app.core.timeutil import today_local
from app.db.base import Base
from app.kiosk.flow import KioskFlow
from app.kiosk.store import InMemoryKioskStateStore
from app.main import create_app
from app.seed import seed_initial_catalogue, seed_reference
from app.services import kiosk_device_service
from app.services.context import Actor
from app.voice.provider import SpeechStarted, ToolCall
from app.voice.providers.scripted import ScriptedProvider
from app.voice.tools import TOOL_NAMES, TOOLS, ToolExecutor
from tests.conftest import make_settings


@pytest.fixture
def settings() -> Settings:
    return make_settings(public_rate_limit_per_minute=10_000, booking_rate_limit_per_minute=10_000)


def monday() -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


@pytest.fixture
async def device_id(maker: async_sessionmaker[AsyncSession]) -> str:
    async with maker() as s:
        device, code = await kiosk_device_service.create(s, "Voice", Actor.system())
        await kiosk_device_service.register(s, code, None)
        return str(device.id)


async def test_voice_tools_complete_a_booking_up_to_the_summary(
    maker: async_sessionmaker[AsyncSession], settings: Settings, device_id: str
) -> None:
    flow = KioskFlow(maker, settings, InMemoryKioskStateStore())
    seen: list[tuple[str, str]] = []
    q = flow.bus.subscribe(device_id)
    await flow.handle(device_id, "start", {})  # presence or tap starts the session
    tools = ToolExecutor(flow, maker, device_id)

    steps: list[tuple[str, dict[str, Any]]] = [
        ("continue_from_greeting", {}),
        ("set_customer_name", {"name": "Riya"}),
        ("set_customer_phone", {"phone_digits": "9876543210"}),
        ("confirm_customer_phone", {}),
        ("set_guest_count", {"count": 4}),
        ("set_occasion", {"occasion": "BIRTHDAY", "birthday_person_name": "Aarav", "birthday_person_age": 9}),
        ("select_package", {"package_code": "expert"}),
        ("select_date", {"date": monday().isoformat()}),
        ("select_start_time", {"start_time": "18:00"}),
        ("set_whatsapp_consent", {"consent": True}),
    ]
    result: dict[str, Any] = {}
    for name, args in steps:
        result = await tools.execute(name, args)
        assert result["ok"], (name, result)
    st = result["state"]
    assert st["step"] == "BOOKING_SUMMARY" and st["summary"]["total_inr"] == "2400.00"
    assert st["phone"] == "98•••••210" and "confirm_booking" in st["allowed_actions"]
    # The model can't confirm: there is no such tool, and unknown tools are refused.
    assert "confirm_booking" not in TOOL_NAMES
    assert (await tools.execute("confirm_booking", {}))["ok"] is False
    # Every voice-driven change reached subscribers (the screen) tagged as voice.
    while not q.empty():
        ch = q.get_nowait()
        seen.append((ch.source, ch.state.state))
    assert ("voice", "BOOKING_SUMMARY") in seen


async def test_voice_tools_report_errors_without_changing_state(
    maker: async_sessionmaker[AsyncSession], settings: Settings, device_id: str
) -> None:
    flow = KioskFlow(maker, settings, InMemoryKioskStateStore())
    await flow.handle(device_id, "start", {})
    tools = ToolExecutor(flow, maker, device_id)
    skipped = await tools.execute("select_start_time", {"start_time": "18:00"})
    assert skipped["ok"] is False and skipped["state"]["step"] == "GREETING"
    await tools.execute("continue_from_greeting", {})
    await tools.execute("set_customer_name", {"name": "Riya"})
    bad = await tools.execute("set_customer_phone", {"phone_digits": "12345"})
    assert bad["ok"] is False and "valid 10-digit" in bad["error"]
    garbage = await tools.execute("set_guest_count", {"count": "many"})
    assert garbage["ok"] is False
    info = await tools.execute("get_business_information", {})
    assert info["ok"] and info["hours"]["Mon"] == "11:00-22:00"


def test_tool_specs_are_well_formed() -> None:
    assert len(TOOL_NAMES) == len(TOOLS)
    for t in TOOLS:
        assert t.parameters["type"] == "object" and t.description


# --- gateway ------------------------------------------------------------------------------------------


def _app(tmp_path: Path, settings: Settings, provider: ScriptedProvider | None):  # type: ignore[no-untyped-def]
    url = f"sqlite+aiosqlite:///{(tmp_path / 'voice.db').as_posix()}"
    engine = create_async_engine(url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

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
    if provider is not None:
        application.state.voice_provider_factory = lambda _s: provider
    return application, token, engine


def test_gateway_relays_audio_tools_and_barge_in(tmp_path: Path, settings: Settings) -> None:
    provider = ScriptedProvider(
        script=[
            ToolCall("c1", "continue_from_greeting", {}),
            ToolCall("c2", "set_customer_name", {"name": "Riya"}),
            SpeechStarted(),
        ],
        frames_per_step=1,
    )
    application, token, engine = _app(tmp_path, settings, provider)
    with TestClient(application) as tc, tc.websocket_connect("/ws/kiosk") as kiosk:
        kiosk.send_json({"type": "auth", "token": token})
        assert kiosk.receive_json()["state"]["state"] == "IDLE"
        kiosk.send_json({"type": "intent", "id": "1", "name": "start", "payload": {}})
        assert kiosk.receive_json()["state"]["state"] == "GREETING"

        with tc.websocket_connect("/ws/voice") as voice:
            voice.send_json({"type": "auth", "token": token})
            ready = voice.receive_json()
            assert ready == {
                "type": "voice.ready",
                "provider": "scripted",
                "input_rate": 16000,
                "output_rate": 24000,
            }
            assert "Riya" not in provider.instructions and "Play Laser Tag" in provider.instructions
            assert provider.texts and provider.texts[0].startswith("[SCREEN]")  # greet on connect

            # The greeting response: speaking status, audio bytes, caption, listening.
            got: list[Any] = []
            while len(got) < 4:
                msg = voice.receive()
                got.append(msg.get("bytes") or msg.get("text"))
            assert any(isinstance(g, bytes) for g in got)

            voice.send_bytes(b"\x00\x00" * 320)  # -> continue_from_greeting
            assert kiosk.receive_json()["state"]["state"] == "CUSTOMER_NAME"  # screen follows the voice
            voice.send_bytes(b"\x00\x00" * 320)  # -> set_customer_name
            pushed = kiosk.receive_json()["state"]
            assert pushed["state"] == "CUSTOMER_PHONE" and pushed["customer_name"] == "Riya"
            assert [n for n, _ in provider.tool_results] == ["continue_from_greeting", "set_customer_name"]

            voice.send_bytes(b"\x00\x00" * 320)  # -> customer starts talking over the assistant
            for _ in range(30):
                msg = voice.receive()
                if msg.get("text") and '"audio.interrupt"' in msg["text"]:
                    break
            else:
                pytest.fail("no audio.interrupt sent")
            assert provider.interrupted == 1

            # A touch on the screen is reported to the model so it doesn't re-ask.
            kiosk.send_json(
                {"type": "intent", "id": "2", "name": "set_phone", "payload": {"phone": "9876543210"}}
            )
            kiosk.receive_json()
            for _ in range(50):
                if any("set_phone" in t for t in provider.texts):
                    break
                voice.receive()
            assert any("set_phone" in t for t in provider.texts)
    asyncio.run(engine.dispose())


def test_gateway_without_provider_key_falls_back_to_touch(tmp_path: Path) -> None:
    settings = make_settings(voice_provider="openai", openai_api_key=None)
    application, token, engine = _app(tmp_path, settings, None)
    with TestClient(application) as tc, tc.websocket_connect("/ws/kiosk") as kiosk:
        kiosk.send_json({"type": "auth", "token": token})
        kiosk.receive_json()
        kiosk.send_json({"type": "intent", "id": "1", "name": "start", "payload": {}})
        kiosk.receive_json()
        with tc.websocket_connect("/ws/voice") as voice:
            voice.send_json({"type": "auth", "token": token})
            assert voice.receive_json()["type"] == "voice.unavailable"
        # Touch keeps working.
        kiosk.send_json({"type": "intent", "id": "2", "name": "continue", "payload": {}})
        assert kiosk.receive_json()["state"]["state"] == "CUSTOMER_NAME"
    asyncio.run(engine.dispose())


def test_gateway_rejects_bad_token_and_idle_kiosk(tmp_path: Path, settings: Settings) -> None:
    application, token, engine = _app(tmp_path, settings, ScriptedProvider())
    with TestClient(application) as tc:
        with tc.websocket_connect("/ws/voice") as voice:
            voice.send_json({"type": "auth", "token": "nope"})
            with pytest.raises(Exception):  # noqa: B017 - closed with 4401
                voice.receive_json()
        with tc.websocket_connect("/ws/voice") as voice:
            voice.send_json({"type": "auth", "token": token})
            assert voice.receive_json() == {"type": "voice.unavailable", "reason": "no active session"}
    asyncio.run(engine.dispose())
