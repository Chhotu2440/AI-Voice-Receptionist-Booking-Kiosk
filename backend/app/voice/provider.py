"""Provider-neutral voice interface (ADR-007, docs/06 §4). Booking logic never imports a provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (object)


@dataclass(frozen=True)
class AudioChunk:
    pcm16: bytes  # mono little-endian, at the provider's output rate


@dataclass(frozen=True)
class Transcript:
    role: str  # "user" | "assistant"
    text: str
    final: bool


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class SpeechStarted:
    """The customer started talking: stop playback now (barge-in)."""


@dataclass(frozen=True)
class TurnDone:
    pass


@dataclass(frozen=True)
class ProviderError:
    message: str
    fatal: bool = False


ProviderEvent = AudioChunk | Transcript | ToolCall | SpeechStarted | TurnDone | ProviderError


@dataclass
class UsageRecord:
    audio_in_tokens: int = 0
    audio_out_tokens: int = 0
    text_in_tokens: int = 0
    text_cached_tokens: int = 0
    text_out_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def add(self, other: UsageRecord) -> None:
        self.audio_in_tokens += other.audio_in_tokens
        self.audio_out_tokens += other.audio_out_tokens
        self.text_in_tokens += other.text_in_tokens
        self.text_cached_tokens += other.text_cached_tokens
        self.text_out_tokens += other.text_out_tokens


class VoiceProvider(Protocol):
    name: str
    input_rate: int  # PCM16 sample rate the provider expects from the kiosk
    output_rate: int  # PCM16 sample rate of the audio it returns

    async def connect(self, instructions: str, tools: list[ToolSpec], language_hint: str) -> None: ...
    async def send_audio(self, pcm16: bytes) -> None: ...
    async def send_text(self, text: str) -> None: ...
    async def send_tool_result(self, call: ToolCall, result: dict[str, Any]) -> None: ...
    async def request_response(self) -> None: ...
    async def interrupt(self) -> None: ...
    def events(self) -> AsyncIterator[ProviderEvent]: ...
    async def close(self) -> None: ...
    def usage(self) -> UsageRecord: ...
