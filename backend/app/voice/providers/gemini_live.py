"""Google Gemini Live adapter (server-to-server WebSocket, BidiGenerateContent v1beta).

Protocol notes (aistudio.google.com/docs/live-api, checked 2026-11-10): input PCM16 16 kHz, output PCM16
24 kHz; client messages `setup`, `realtimeInput.audio`, `clientContent`, `toolResponse.functionResponses`;
server messages `setupComplete`, `serverContent` (modelTurn.parts[].inlineData, inputTranscription,
outputTranscription, interrupted, turnComplete), `toolCall.functionCalls`, `usageMetadata`, `goAway`.
Barge-in is handled by the service (serverContent.interrupted). The API key is sent as a header, not in
the URL, so it can't leak into proxy logs.
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

URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
IN_RATE, OUT_RATE = 16_000, 24_000


@dataclass
class ParseState:
    usage: UsageRecord = field(default_factory=UsageRecord)
    setup_complete: bool = False


def _schema(params: dict[str, Any]) -> dict[str, Any]:
    """Gemini function parameters accept an OpenAPI-style subset: drop keywords it doesn't support."""
    out = {k: v for k, v in params.items() if k not in ("additionalProperties", "pattern")}
    if "properties" in out:
        out["properties"] = {k: _schema(v) for k, v in out["properties"].items()}
    return out


def setup_payload(settings: Settings, instructions: str, tools: list[ToolSpec]) -> dict[str, Any]:
    return {
        "setup": {
            "model": f"models/{settings.gemini_live_model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": settings.gemini_voice}}
                },
            },
            "systemInstruction": {"parts": [{"text": instructions}]},
            "tools": [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": _schema(t.parameters)}
                        for t in tools
                    ]
                }
            ],
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            # A noisy reception: start a turn only on clear speech, and don't cut the customer off mid-pause.
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "startOfSpeechSensitivity": "START_SENSITIVITY_LOW",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                    "prefixPaddingMs": 200,
                    "silenceDurationMs": 700,
                }
            },
        }
    }


def _usage(u: dict[str, Any]) -> UsageRecord:
    """Field names vary between model versions (responseTokensDetails / candidatesTokensDetails)."""
    rec = UsageRecord()
    for d in u.get("promptTokensDetails") or []:
        if d.get("modality") == "AUDIO":
            rec.audio_in_tokens += int(d.get("tokenCount", 0))
        else:
            rec.text_in_tokens += int(d.get("tokenCount", 0))
    out_details = u.get("responseTokensDetails") or u.get("candidatesTokensDetails") or []
    for d in out_details:
        if d.get("modality") == "AUDIO":
            rec.audio_out_tokens += int(d.get("tokenCount", 0))
        else:
            rec.text_out_tokens += int(d.get("tokenCount", 0))
    if not out_details:  # only a total is reported: attribute it to audio (responses are audio-only)
        rec.audio_out_tokens = int(u.get("responseTokenCount", 0) or u.get("candidatesTokenCount", 0))
    rec.text_cached_tokens = int(u.get("cachedContentTokenCount", 0))
    return rec


def parse_message(msg: dict[str, Any], st: ParseState) -> list[ProviderEvent]:
    events: list[ProviderEvent] = []
    if "setupComplete" in msg:
        st.setup_complete = True
    sc = msg.get("serverContent")
    if sc:
        if sc.get("interrupted"):
            events.append(SpeechStarted())
        for part in (sc.get("modelTurn") or {}).get("parts") or []:
            data = (part.get("inlineData") or {}).get("data")
            if data:
                events.append(AudioChunk(base64.b64decode(data)))
        if (sc.get("inputTranscription") or {}).get("text"):
            events.append(Transcript("user", sc["inputTranscription"]["text"], final=False))
        if (sc.get("outputTranscription") or {}).get("text"):
            events.append(Transcript("assistant", sc["outputTranscription"]["text"], final=False))
        if sc.get("turnComplete"):
            events.append(TurnDone())
    for fc in (msg.get("toolCall") or {}).get("functionCalls") or []:
        events.append(
            ToolCall(
                call_id=str(fc.get("id", "")), name=str(fc.get("name", "")), arguments=fc.get("args") or {}
            )
        )
    if msg.get("usageMetadata"):
        # Observed live (2026-11-11): usageMetadata is reported per model turn (promptTokenCount covers the
        # whole context re-read for that turn), so turns are summed. Verify against Google's billing console.
        turn = _usage(msg["usageMetadata"])
        st.usage.add(turn)
        st.usage.extra.setdefault("turns", 0)
        st.usage.extra["turns"] += 1
    if "goAway" in msg:
        events.append(ProviderError("Live session ending soon (goAway)", fatal=False))
    if "error" in msg:
        events.append(ProviderError(str(msg["error"]), fatal=True))
    return events


class GeminiLiveProvider:
    name = "gemini"
    speech_gate = "transcript"
    input_rate = IN_RATE
    output_rate = OUT_RATE

    def __init__(self, settings: Settings) -> None:
        if settings.gemini_api_key is None:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.settings = settings
        self.ws: ClientConnection | None = None
        self.st = ParseState()
        self._names: dict[str, str] = {}
        self._send_lock = asyncio.Lock()

    async def _send(self, obj: dict[str, Any]) -> None:
        assert self.ws is not None
        async with self._send_lock:
            await self.ws.send(json.dumps(obj))

    async def connect(self, instructions: str, tools: list[ToolSpec], language_hint: str) -> None:
        assert self.settings.gemini_api_key is not None
        self.ws = await connect(
            URL,
            additional_headers={"x-goog-api-key": self.settings.gemini_api_key.get_secret_value()},
            max_size=None,
            open_timeout=10,
        )
        await self._send(setup_payload(self.settings, instructions, tools))
        # Wait for setupComplete before streaming audio.
        raw = await asyncio.wait_for(self.ws.recv(), timeout=10)
        msg = json.loads(raw)
        parse_message(msg, self.st)
        if not self.st.setup_complete:
            raise RuntimeError(f"Gemini Live setup failed: {str(msg)[:300]}")

    async def send_audio(self, pcm16: bytes) -> None:
        await self._send(
            {
                "realtimeInput": {
                    "audio": {
                        "data": base64.b64encode(pcm16).decode(),
                        "mimeType": f"audio/pcm;rate={IN_RATE}",
                    }
                }
            }
        )

    async def send_text(self, text: str) -> None:
        await self._send(
            {"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}
        )

    async def send_tool_result(self, call: ToolCall, result: dict[str, Any]) -> None:
        await self._send(
            {
                "toolResponse": {
                    "functionResponses": [{"id": call.call_id, "name": call.name, "response": result}]
                }
            }
        )

    async def request_response(self) -> None:
        return None  # Gemini continues on its own after a tool response or a completed client turn

    async def interrupt(self) -> None:
        return None  # the service detects barge-in itself and reports serverContent.interrupted

    async def events(self) -> AsyncIterator[ProviderEvent]:
        assert self.ws is not None
        async for raw in self.ws:
            msg = json.loads(raw if isinstance(raw, str) else raw.decode())
            for e in parse_message(msg, self.st):
                yield e

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()

    def usage(self) -> UsageRecord:
        return self.st.usage
