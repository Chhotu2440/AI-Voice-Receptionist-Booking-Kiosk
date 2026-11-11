"""Deterministic test double (dev/test only; config refuses it in staging/prod).

It "hears" nothing: every N audio frames it emits the next scripted event (a tool call, a transcript,
a barge-in, or a short tone as assistant audio). Tool results are recorded for assertions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.voice.provider import (
    AudioChunk,
    ProviderEvent,
    SpeechStarted,
    ToolCall,
    ToolSpec,
    Transcript,
    TurnDone,
    UsageRecord,
)

TONE = bytes(480 * 2)  # 20 ms of silence at 24 kHz, enough to exercise the audio path


class ScriptedProvider:
    name = "scripted"
    speech_gate = "off"
    input_rate = 16_000
    output_rate = 24_000

    def __init__(self, script: list[ProviderEvent] | None = None, frames_per_step: int = 2) -> None:
        self.script = list(script or [])
        self.frames_per_step = frames_per_step
        self.queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self.tool_results: list[tuple[str, dict[str, Any]]] = []
        self.texts: list[str] = []
        self.frames = 0
        self.instructions = ""
        self.tools: list[ToolSpec] = []
        self.interrupted = 0
        self.closed = False

    async def connect(self, instructions: str, tools: list[ToolSpec], language_hint: str) -> None:
        self.instructions, self.tools = instructions, tools

    async def send_audio(self, pcm16: bytes) -> None:
        self.frames += 1
        if self.frames % self.frames_per_step == 0 and self.script:
            await self.queue.put(self.script.pop(0))

    async def send_text(self, text: str) -> None:
        self.texts.append(text)

    async def send_tool_result(self, call: ToolCall, result: dict[str, Any]) -> None:
        self.tool_results.append((call.name, result))

    async def request_response(self) -> None:
        await self.queue.put(AudioChunk(TONE))
        await self.queue.put(Transcript("assistant", "ok", final=True))
        await self.queue.put(TurnDone())

    async def interrupt(self) -> None:
        self.interrupted += 1

    async def events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            ev = await self.queue.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(None)

    def usage(self) -> UsageRecord:
        return UsageRecord(audio_in_tokens=self.frames)


__all__ = ["ScriptedProvider", "SpeechStarted", "ToolCall", "Transcript"]
