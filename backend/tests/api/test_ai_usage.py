"""VOICE-06: per-session usage and cost, spend caps, admin usage report."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import TestClient

from app.core.timeutil import utcnow
from app.models.ai import AiUsageLog
from app.schemas.settings import AiSettings
from app.services import ai_usage_service
from app.voice.provider import ToolCall, UsageRecord
from app.voice.providers.scripted import ScriptedProvider
from tests.api.test_voice import _app
from tests.conftest import make_settings


def test_cost_matches_measured_bakeoff_numbers() -> None:
    prices = AiSettings().prices
    gemini = UsageRecord(audio_in_tokens=16219, audio_out_tokens=1226, text_in_tokens=37511)
    assert ai_usage_service.cost_usd(gemini, prices["gemini-3.8-live"]) == Decimal("0.09150")
    openai = UsageRecord(
        audio_in_tokens=2858,
        audio_out_tokens=1809,
        text_in_tokens=54827,
        text_cached_tokens=51264,
        text_out_tokens=1385,
    )
    assert ai_usage_service.cost_usd(openai, prices["gpt-realtime-2.1-mini"]) == Decimal("0.07330")
    assert ai_usage_service.cost_usd(gemini, None) == Decimal(
        0
    )  # unknown model: logged at zero, never crashes


async def test_caps_block_voice_after_budget(maker: async_sessionmaker[AsyncSession]) -> None:
    async with maker() as s:
        ok = await ai_usage_service.check_caps(s)
        assert ok.allowed
        await ai_usage_service.record(
            s,
            device_id="01a1c6bf-e3fa-7524-ab0e-60b56ed2a368",
            kiosk_session_id=None,
            provider="gemini",
            model="gemini-3.8-live",
            started_at=utcnow(),
            usage=UsageRecord(audio_in_tokens=4_000_000),  # $12
            tool_calls=0,
            tools_blocked=0,
            end_reason="TEST",
        )
        blocked = await ai_usage_service.check_caps(s)
        assert not blocked.allowed and blocked.reason == "daily voice budget reached"
        assert blocked.today_usd == Decimal("12.00000")


async def test_admin_usage_report_and_ai_settings(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.get("/api/v1/admin/ai/usage", headers=owner_headers)
    assert (
        r.status_code == 200 and r.json()["voice_sessions"] == 0 and r.json()["caps"]["voice_allowed"] is True
    )
    s = await client.get("/api/v1/admin/settings/ai", headers=owner_headers)
    assert s.json()["monthly_cap_usd"] == "120"
    upd = await client.put(
        "/api/v1/admin/settings/ai", headers=owner_headers, json={**s.json(), "daily_cap_usd": "5"}
    )
    assert upd.status_code == 200 and upd.json()["daily_cap_usd"] == "5"


async def test_staff_cannot_change_ai_budget(client: AsyncClient, make_user, login) -> None:  # type: ignore[no-untyped-def]
    staff = await login(*(await make_user("MANAGER")))
    assert (
        await client.put("/api/v1/admin/settings/ai", headers=staff, json={"daily_cap_usd": "999"})
    ).status_code == 403


def test_gateway_records_usage_and_respects_caps(tmp_path: Path) -> None:
    settings = make_settings()
    provider = ScriptedProvider(script=[ToolCall("c1", "continue_from_greeting", {})], frames_per_step=1)
    application, token, engine = _app(tmp_path, settings, provider)
    with TestClient(application) as tc:
        kiosk_cm = tc.websocket_connect("/ws/kiosk")
        kiosk = kiosk_cm.__enter__()
        kiosk.send_json({"type": "auth", "token": token})
        kiosk.receive_json()
        kiosk.send_json({"type": "intent", "id": "1", "name": "start", "payload": {}})
        kiosk.receive_json()
        with tc.websocket_connect("/ws/voice") as voice:
            voice.send_json({"type": "auth", "token": token})
            assert voice.receive_json()["type"] == "voice.ready"
            voice.send_bytes(b"\x00\x00" * 320)
            assert kiosk.receive_json()["state"]["state"] == "CUSTOMER_NAME"
            kiosk_cm.__exit__(None, None, None)  # the kiosk screen goes away first -> voice ends
            time.sleep(0.5)  # let the server finish the voice session's cleanup (usage record)

    maker = application.state.sessionmaker

    async def rows() -> list[AiUsageLog]:
        async with maker() as s:
            return list((await s.execute(select(AiUsageLog))).scalars())

    logged = asyncio.run(rows())
    assert len(logged) == 1 and logged[0].provider == "scripted" and logged[0].tool_calls == 1
    assert logged[0].end_reason == "KIOSK_CLOSED" and logged[0].audio_in_tokens == 1

    async def exhaust_budget() -> None:
        async with maker() as s:
            row = (await s.execute(select(AiUsageLog))).scalar_one()
            row.cost_usd = Decimal("500")
            await s.commit()

    asyncio.run(exhaust_budget())
    with TestClient(application) as tc, tc.websocket_connect("/ws/voice") as voice:
        voice.send_json({"type": "auth", "token": token})
        assert voice.receive_json() == {"type": "voice.unavailable", "reason": "daily voice budget reached"}
    asyncio.run(engine.dispose())
