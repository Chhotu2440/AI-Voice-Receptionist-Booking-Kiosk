"""OpenAI Realtime adapter (server-to-server WebSocket, GA event names).

Protocol notes (developers.openai.com Realtime guides, checked 2026-11-10):
- URL wss://api.openai.com/v1/realtime?model=<model>, header Authorization: Bearer <key>
- session.update {session: {type: "realtime", instructions, audio.input/output.format {type: audio/pcm,
  rate: 24000}, audio.input.turn_detection, audio.output.voice, tools [{type: function,...}], tool_choice}}
- client: input_audio_buffer.append {audio: b64}, conversation.item.create (function_call_output),
  response.create, response.cancel, conversation.item.truncate {item_id, content_index, audio_end_ms}
- server: response.output_audio.delta, response.output_audio_transcript.delta/.done,
  conversation.item.input_audio_transcription.completed, input_audio_buffer.speech_started,
  response.function_call_arguments.done, response.created, response.done (+usage), error
Anything not listed explicitly in those guides is handled defensively (unknown events are ignored).
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from app.core.config import Settings
from app.voice.provider import (
    AudioChunk,
    ProviderError,
    ProviderEvent,
    SpeechStarted,
    ToolCall,
    ToolSpec,
    Transcript,
    TurnDone,
    UsageRecord,
)

URL = "wss://api.openai.com/v1/realtime?model={model}"
RATE = 24_000


@dataclass
class ParseState:
    seen_calls: set[str] = field(default_factory=set)
    current_item: str | None = None
    current_item_bytes: int = 0
    response_active: bool = False
    usage: UsageRecord = field(default_factory=UsageRecord)


def session_payload(settings: Settings, instructions: str, tools: list[ToolSpec]) -> dict[str, Any]:
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": RATE},
                    "transcription": {"model": settings.openai_transcribe_model},
                    "noise_reduction": {"type": "far_field"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.6,  # reception is noisy: a little less eager than default
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 600,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },
                "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": settings.openai_voice},
            },
            "tools": [
                {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters}
                for t in tools
            ],
            "tool_choice": "auto",
        },
    }


def _usage(u: dict[str, Any]) -> UsageRecord:
    inp = u.get("input_token_details") or {}
    out = u.get("output_token_details") or {}
    return UsageRecord(
        audio_in_tokens=int(inp.get("audio_tokens", 0)),
        text_in_tokens=int(inp.get("text_tokens", 0)),
        text_cached_tokens=int(inp.get("cached_tokens", 0)),
        audio_out_tokens=int(out.get("audio_tokens", 0)),
        text_out_tokens=int(out.get("text_tokens", 0)),
    )


def _tool_call(call_id: str, name: str, arguments: str | None, st: ParseState) -> list[ProviderEvent]:
    if not call_id or call_id in st.seen_calls:
        return []
    st.seen_calls.add(call_id)
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    return [ToolCall(call_id=call_id, name=name, arguments=args if isinstance(args, dict) else {})]


def parse_event(evt: dict[str, Any], st: ParseState) -> list[ProviderEvent]:
    """Map one server event to provider-neutral events (pure; unit-tested with canned events)."""
    t = evt.get("type", "")
    if t == "response.output_audio.delta":
        audio = base64.b64decode(evt.get("delta", ""))
        if evt.get("item_id") != st.current_item:
            st.current_item, st.current_item_bytes = evt.get("item_id"), 0
        st.current_item_bytes += len(audio)
        return [AudioChunk(audio)]
    if t == "response.output_audio_transcript.delta":
        return [Transcript("assistant", evt.get("delta", ""), final=False)]
    if t == "response.output_audio_transcript.done":
        return [Transcript("assistant", evt.get("transcript", ""), final=True)]
    if t == "conversation.item.input_audio_transcription.completed":
        return [Transcript("user", evt.get("transcript", ""), final=True)]
    if t == "input_audio_buffer.speech_started":
        return [SpeechStarted()]
    if t == "response.function_call_arguments.done":
        return _tool_call(evt.get("call_id", ""), evt.get("name", ""), evt.get("arguments"), st)
    if t == "response.created":
        st.response_active = True
        return []
    if t == "response.done":
        st.response_active = False
        resp = evt.get("response") or {}
        events: list[ProviderEvent] = []
        for item in resp.get("output") or []:  # some events may only arrive here
            if item.get("type") == "function_call":
                events += _tool_call(item.get("call_id", ""), item.get("name", ""), item.get("arguments"), st)
        if resp.get("usage"):
            st.usage.add(_usage(resp["usage"]))
        return [*events, TurnDone()]
    if t == "error":
        err = evt.get("error") or {}
        code = str(err.get("code", ""))
        if code in ("response_cancel_not_active", "conversation_already_has_active_response"):
            return []  # benign races around barge-in
        fatal = code in ("invalid_api_key", "session_expired", "insufficient_quota")
        return [ProviderError(err.get("message", "provider error"), fatal=fatal)]
    return []


class OpenAIRealtimeProvider:
    name = "openai"
    speech_gate = "vad"  # input transcription is asynchronous and may land after tool calls
    input_rate = RATE
    output_rate = RATE

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.settings = settings
        self.ws: ClientConnection | None = None
        self.st = ParseState()
        self._queued_response = False
        self._send_lock = asyncio.Lock()

    async def _send(self, obj: dict[str, Any]) -> None:
        assert self.ws is not None
        async with self._send_lock:
            await self.ws.send(json.dumps(obj))

    async def connect(self, instructions: str, tools: list[ToolSpec], language_hint: str) -> None:
        assert self.settings.openai_api_key is not None
        self.ws = await connect(
            URL.format(model=self.settings.openai_realtime_model),
            additional_headers={"Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"},
            max_size=None,
            open_timeout=10,
        )
        await self._send(session_payload(self.settings, instructions, tools))

    async def send_audio(self, pcm16: bytes) -> None:
        await self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm16).decode()})

    async def send_text(self, text: str) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )

    async def send_tool_result(self, call: ToolCall, result: dict[str, Any]) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, default=str),
                },
            }
        )

    async def request_response(self) -> None:
        # Only one response may be active; queue and send when the current one finishes.
        if self.st.response_active:
            self._queued_response = True
        else:
            self.st.response_active = True
            await self._send({"type": "response.create"})

    async def interrupt(self) -> None:
        # Server VAD already cancels the response (interrupt_response=true); truncate so the model's memory
        # matches what the customer actually heard (approximation: audio sent so far for that item).
        if self.st.current_item:
            ms = int(self.st.current_item_bytes / 2 / RATE * 1000)
            await self._send(
                {
                    "type": "conversation.item.truncate",
                    "item_id": self.st.current_item,
                    "content_index": 0,
                    "audio_end_ms": ms,
                }
            )
            self.st.current_item = None

    async def events(self) -> AsyncIterator[ProviderEvent]:
        assert self.ws is not None
        async for raw in self.ws:
            evt = json.loads(raw)
            for e in parse_event(evt, self.st):
                yield e
            if evt.get("type") == "response.done" and self._queued_response:
                self._queued_response = False
                self.st.response_active = True
                await self._send({"type": "response.create"})

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()

    def usage(self) -> UsageRecord:
        return self.st.usage
