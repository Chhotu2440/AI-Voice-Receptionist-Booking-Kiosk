"""Voice provider bake-off harness (VOICE-01).

Plays scripted customer utterances (synthesized once with OpenAI TTS, cached) into each provider in real
time, exactly like the kiosk would, and runs the real tools against the real booking flow on a throwaway
SQLite copy. Records per turn: what the provider heard (input transcript), what it said, tool calls,
time-to-first-audio, plus final booking step and token usage.

    cd backend
    python scripts/voice_bakeoff.py --providers openai,gemini --script en
    python scripts/voice_bakeoff.py --providers openai --script hinglish

Results: printed summary + JSON in --out (default: ./bakeoff-results/). Uses API keys from .env.
Costs a few cents per run. Never run against a production database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from array import array
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.timeutil import today_local  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.kiosk.flow import KioskFlow  # noqa: E402
from app.kiosk.store import InMemoryKioskStateStore  # noqa: E402
from app.seed import seed_initial_catalogue, seed_reference  # noqa: E402
from app.services import kiosk_device_service  # noqa: E402
from app.services.context import Actor  # noqa: E402
from app.voice.prompts import build_instructions, screen_note  # noqa: E402
from app.voice.provider import (  # noqa: E402
    AudioChunk,
    ProviderError,
    SpeechStarted,
    ToolCall,
    Transcript,
    TurnDone,
    VoiceProvider,
)
from app.voice.tools import TOOLS, ToolExecutor, summarize  # noqa: E402


def next_monday() -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


SCRIPTS: dict[str, list[str]] = {
    "en": [
        "Hi! My name is Riya.",
        "My number is nine eight seven six five, four three two one zero.",
        "Yes, that's correct.",
        "We are four people.",
        "Just for fun with friends.",
        "Which one do you recommend? Actually, let's take the expert package.",
        "Next Monday, please.",
        "Six PM works.",
    ],
    "hinglish": [
        "Namaste, mera naam Amit hai.",
        "Mera number hai nau aath saat chhe paanch, chaar teen do ek shunya.",
        "Haan, sahi hai.",
        "Hum chhe log hain.",
        "Bas dosto ke saath masti ke liye.",
        "Intermediate package de dijiye.",
        "Agle Monday ko.",
        "Shaam saat baje.",
    ],
}


@dataclass
class Turn:
    said: str
    heard: str = ""
    reply: str = ""
    tools: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ttfa_ms: int | None = None


# --- audio -----------------------------------------------------------------------------------------------


async def tts(settings: Settings, text: str, cache: Path) -> bytes:
    """24 kHz PCM16 mono speech for `text` (cached so every provider hears identical audio)."""
    path = cache / (str(abs(hash(text)) % 10**12) + ".pcm")
    if path.exists():
        return path.read_bytes()
    assert settings.openai_api_key is not None
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
            json={
                "model": "gpt-4o-mini-tts",
                "voice": "coral",
                "input": text,
                "response_format": "pcm",
                "instructions": "Speak like a young customer in Delhi with a natural Indian accent.",
            },
        )
        r.raise_for_status()
    path.write_bytes(r.content)
    return r.content


def resample(pcm: bytes, src: int, dst: int) -> bytes:
    if src == dst:
        return pcm
    s = array("h", pcm)
    n = int(len(s) * dst / src)
    out = array("h", [0]) * n
    for i in range(n):
        pos = i * src / dst
        j = int(pos)
        frac = pos - j
        a = s[j] if j < len(s) else 0
        b = s[j + 1] if j + 1 < len(s) else a
        out[i] = int(a + (b - a) * frac)
    return out.tobytes()


# --- run -------------------------------------------------------------------------------------------------


def make_provider(name: str, settings: Settings) -> VoiceProvider:
    if name == "openai":
        from app.voice.providers.openai_realtime import OpenAIRealtimeProvider

        return OpenAIRealtimeProvider(settings)
    from app.voice.providers.gemini_live import GeminiLiveProvider

    return GeminiLiveProvider(settings)


async def run_provider(name: str, script: list[str], settings: Settings, cache: Path, workdir: Path) -> dict[str, Any]:
    db = workdir / f"bakeoff-{name}.db"
    db.unlink(missing_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        await seed_reference(s)
        await seed_initial_catalogue(s)
        device, code = await kiosk_device_service.create(s, "bakeoff", Actor.system())
        await kiosk_device_service.register(s, code, None)
        device_id = str(device.id)

    flow = KioskFlow(maker, settings, InMemoryKioskStateStore())
    await flow.handle(device_id, "start", {})
    state = await flow.current(device_id)
    provider = make_provider(name, settings)
    executor = ToolExecutor(flow, maker, device_id)
    turns: list[Turn] = [Turn(said="(session start)")]
    last_event = time.monotonic()
    speech_end: float | None = None
    audio_out_s = 0.0

    t0 = time.monotonic()
    await provider.connect(build_instructions("Zara", summarize(state)), TOOLS, "en")
    connect_ms = int((time.monotonic() - t0) * 1000)
    await provider.send_text(screen_note("session started", summarize(state)))
    await provider.request_response()

    async def consume() -> None:
        nonlocal last_event, audio_out_s
        async for ev in provider.events():
            last_event = time.monotonic()
            turn = turns[-1]
            if isinstance(ev, AudioChunk):
                audio_out_s += len(ev.pcm16) / 2 / provider.output_rate
                if turn.ttfa_ms is None and speech_end is not None:
                    turn.ttfa_ms = int((time.monotonic() - speech_end) * 1000)
            elif isinstance(ev, Transcript):
                if ev.role == "user":
                    turn.heard += ev.text if not ev.final else (" " if turn.heard else "") + ev.text
                else:
                    turn.reply = ev.text if ev.final else turn.reply + ev.text
            elif isinstance(ev, ToolCall):
                result = await executor.execute(ev.name, ev.arguments)
                turn.tools.append(f"{ev.name}({json.dumps(ev.arguments, ensure_ascii=False)}) -> {'ok' if result.get('ok') else 'ERR ' + str(result.get('error'))}")
                await provider.send_tool_result(ev, result)
                await provider.request_response()
            elif isinstance(ev, ProviderError):
                turn.errors.append(ev.message[:200])
            elif isinstance(ev, (SpeechStarted, TurnDone)):
                pass

    consumer = asyncio.create_task(consume())

    async def settle(quiet: float = 2.5, timeout: float = 25) -> None:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            await asyncio.sleep(0.2)
            if time.monotonic() - last_event > quiet and time.monotonic() - start > quiet:
                return

    await settle()
    frame_s = 0.04
    for utterance in script:
        pcm = resample(await tts(settings, utterance, cache), 24_000, provider.input_rate)
        turns.append(Turn(said=utterance))
        step = int(provider.input_rate * frame_s) * 2
        silence = bytes(step)
        for i in range(0, len(pcm), step):
            await provider.send_audio(pcm[i : i + step])
            await asyncio.sleep(frame_s)
        speech_end = time.monotonic()
        for _ in range(int(1.2 / frame_s)):  # trailing silence so VAD ends the turn
            await provider.send_audio(silence)
            await asyncio.sleep(frame_s)
        await settle()
        if consumer.done():
            break

    final = await flow.current(device_id)
    consumer.cancel()
    await provider.close()
    await engine.dispose()
    usage = provider.usage()
    ttfas = [t.ttfa_ms for t in turns[1:] if t.ttfa_ms is not None]
    return {
        "provider": name,
        "model": settings.openai_realtime_model if name == "openai" else settings.gemini_live_model,
        "connect_ms": connect_ms,
        "final_step": final.state,
        "quote_total": str(final.quote.total) if final.quote else None,
        "start_time": final.start_time,
        "customer": {"name": final.customer_name, "phone": final.phone_e164, "guests": final.guest_count},
        "ttfa_ms": {"p50": sorted(ttfas)[len(ttfas) // 2] if ttfas else None, "max": max(ttfas) if ttfas else None},
        "assistant_audio_s": round(audio_out_s, 1),
        "usage": usage.__dict__,
        "turns": [t.__dict__ for t in turns],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="openai,gemini")
    ap.add_argument("--script", default="en", choices=sorted(SCRIPTS))
    ap.add_argument("--out", default="bakeoff-results")
    args = ap.parse_args()
    settings = get_settings()
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    cache = out / "tts-cache"
    cache.mkdir(exist_ok=True)
    os.environ.setdefault("APP_ENV", "dev")
    for name in args.providers.split(","):
        try:
            result = await run_provider(name.strip(), SCRIPTS[args.script], settings, cache, out)
        except Exception as exc:  # report and continue with the next provider
            result = {"provider": name, "error": f"{type(exc).__name__}: {exc}"[:500]}
        path = out / f"{name}-{args.script}-{int(time.time())}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "turns"}, ensure_ascii=False, default=str))
        for t in result.get("turns", []):
            print(f"  SAID : {t['said']}\n  HEARD: {t['heard']}\n  REPLY: {t['reply']}\n  TOOLS: {t['tools']}  ttfa={t['ttfa_ms']}ms {t['errors'] or ''}")
        print(f"  -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
