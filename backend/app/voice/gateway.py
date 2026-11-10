"""Voice gateway (/ws/voice), ADR-005: the kiosk streams microphone PCM here; we relay it to the selected
provider, run its tool calls through the kiosk state machine, and stream its audio back.

Kiosk protocol
  client -> server  text  {"type": "auth", "token": "<device JWT>"}                  (first frame)
                    bytes PCM16 mono little-endian at `input_rate`, ~20-40 ms per frame
                    text  {"type": "mute", "muted": bool}
  server -> client  text  {"type": "voice.ready", "provider", "input_rate", "output_rate"}
                    bytes PCM16 assistant audio at `output_rate`
                    text  {"type": "audio.interrupt"}       customer started talking: flush playback now
                    text  {"type": "caption", "role", "text", "final"}
                    text  {"type": "voice.status", "status": "listening|thinking|speaking"}
                    text  {"type": "voice.unavailable", "reason"}   then close: kiosk stays touch-only
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import device_from_token
from app.core.config import Settings
from app.core.exceptions import DomainError
from app.kiosk.flow import KioskFlow
from app.services.kiosk_device_service import DEFAULT_CONFIG
from app.voice.prompts import build_instructions, screen_note
from app.voice.provider import (
    AudioChunk,
    ProviderError,
    SpeechStarted,
    ToolCall,
    Transcript,
    TurnDone,
    VoiceProvider,
)
from app.voice.tools import TOOLS, ToolExecutor, summarize

log = logging.getLogger(__name__)
router = APIRouter()
MAX_AUDIO_FRAME = 64_000

ProviderFactory = Callable[[Settings], VoiceProvider]


def default_provider_factory(settings: Settings) -> VoiceProvider:
    if settings.voice_provider == "openai":
        from app.voice.providers.openai_realtime import OpenAIRealtimeProvider

        return OpenAIRealtimeProvider(settings)
    if settings.voice_provider == "gemini":
        from app.voice.providers.gemini_live import GeminiLiveProvider

        return GeminiLiveProvider(settings)
    from app.voice.providers.scripted import ScriptedProvider

    return ScriptedProvider()


@router.websocket("/ws/voice")
async def voice_socket(ws: WebSocket) -> None:
    app_state = ws.app.state
    settings: Settings = app_state.settings
    flow: KioskFlow = app_state.kiosk_flow
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
        if first.get("type") != "auth":
            raise ValueError("auth required")
        async with app_state.sessionmaker() as db:
            device = await device_from_token(db, settings, str(first.get("token", "")))
            device_id, config = str(device.id), {**DEFAULT_CONFIG, **(device.config or {})}
    except (TimeoutError, ValueError, DomainError):
        await ws.close(code=4401)
        return

    send_lock = asyncio.Lock()

    async def send_json(msg: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_json(msg)

    async def send_bytes(data: bytes) -> None:
        async with send_lock:
            await ws.send_bytes(data)

    state = await flow.current(device_id)
    if state.state == "IDLE":
        await send_json({"type": "voice.unavailable", "reason": "no active session"})
        await ws.close(code=4409)
        return

    factory: ProviderFactory = getattr(app_state, "voice_provider_factory", None) or default_provider_factory
    try:
        provider = factory(settings)
        await provider.connect(
            build_instructions(str(config.get("assistant_name", "Zara")), summarize(state)),
            TOOLS,
            state.language,
        )
    except Exception as exc:  # missing key, network, provider outage -> touch-only, never a crash
        log.warning("voice_unavailable", extra={"provider": settings.voice_provider, "error": str(exc)[:200]})
        await send_json({"type": "voice.unavailable", "reason": "voice is not available right now"})
        await ws.close(code=1011)
        return

    executor = ToolExecutor(flow, app_state.sessionmaker, device_id)
    updates = flow.bus.subscribe(device_id)
    muted = False
    started = time.monotonic()
    await send_json(
        {
            "type": "voice.ready",
            "provider": provider.name,
            "input_rate": provider.input_rate,
            "output_rate": provider.output_rate,
        }
    )
    # Greet (or pick up where the screen is) without waiting for the customer to speak first.
    await provider.send_text(screen_note("session started", summarize(state)))
    await provider.request_response()

    async def from_kiosk() -> None:
        nonlocal muted
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data is not None:
                if not muted and 0 < len(data) <= MAX_AUDIO_FRAME:
                    await provider.send_audio(data)
            elif msg.get("text"):
                ctl = json.loads(msg["text"])
                if ctl.get("type") == "mute":
                    muted = bool(ctl.get("muted"))

    async def from_provider() -> None:
        speaking = False
        async for ev in provider.events():
            if isinstance(ev, AudioChunk):
                if not speaking:
                    speaking = True
                    await send_json({"type": "voice.status", "status": "speaking"})
                await send_bytes(ev.pcm16)
            elif isinstance(ev, SpeechStarted):
                speaking = False
                await send_json({"type": "audio.interrupt"})
                await provider.interrupt()
                await send_json({"type": "voice.status", "status": "listening"})
            elif isinstance(ev, Transcript):
                await send_json({"type": "caption", "role": ev.role, "text": ev.text, "final": ev.final})
            elif isinstance(ev, ToolCall):
                await send_json({"type": "voice.status", "status": "thinking"})
                result = await executor.execute(ev.name, ev.arguments)
                await provider.send_tool_result(ev, result)
                await provider.request_response()
            elif isinstance(ev, TurnDone):
                speaking = False
                await send_json({"type": "voice.status", "status": "listening"})
            elif isinstance(ev, ProviderError):
                log.warning("voice_provider_error", extra={"error": ev.message[:200], "fatal": ev.fatal})
                if ev.fatal:
                    await send_json({"type": "voice.unavailable", "reason": "voice connection lost"})
                    return

    async def from_screen() -> None:
        while True:
            change = await updates.get()
            if change.state.state in ("IDLE", "SESSION_CANCELLED"):
                return  # session over: end the voice session too
            if change.source == "touch":
                await provider.send_text(screen_note(change.intent, summarize(change.state)))
                await provider.request_response()

    async def deadline() -> None:
        await asyncio.sleep(max(1, settings.voice_max_session_seconds - (time.monotonic() - started)))

    tasks = [asyncio.create_task(c) for c in (from_kiosk(), from_provider(), from_screen(), deadline())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        flow.bus.unsubscribe(device_id, updates)
        with contextlib.suppress(Exception):
            await provider.close()
        usage = provider.usage()
        log.info(
            "voice_session_end",
            extra={
                "device_id": device_id,
                "provider": provider.name,
                "seconds": round(time.monotonic() - started, 1),
                "audio_in_tokens": usage.audio_in_tokens,
                "audio_out_tokens": usage.audio_out_tokens,
                "text_in_tokens": usage.text_in_tokens,
                "text_cached_tokens": usage.text_cached_tokens,
                "text_out_tokens": usage.text_out_tokens,
            },
        )
        with contextlib.suppress(Exception):
            await ws.close()
