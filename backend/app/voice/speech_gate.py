"""Server-side guard against "phantom" answers.

Noise, other people or the assistant's own echo can make a speech model believe the customer answered and
call a tool. The gate allows tools that CHANGE the booking only if the customer actually said something
since the assistant last finished speaking. Read-only tools are always allowed.

Evidence of customer speech depends on the provider:
- "transcript": a user transcript with real words (Gemini streams input transcription before tool calls).
- "vad":        the provider's speech-start event (OpenAI transcribes asynchronously, often after tools).
- "off":        test double.
"""

from __future__ import annotations

import re
from typing import Literal

GateMode = Literal["transcript", "vad", "off"]

ALWAYS_ALLOWED = {"get_current_step", "get_business_information", "continue_from_greeting"}
_WORDISH = re.compile(r"[0-9A-Za-zऀ-ॿ]")  # digits, Latin, Devanagari

BLOCKED_RESULT = {
    "ok": False,
    "error": "Not applied: the customer has not said this yet. Ask them and wait for their answer.",
}


class SpeechGate:
    def __init__(self, mode: GateMode) -> None:
        self.mode = mode
        self.heard_user = False

    def on_user_transcript(self, text: str) -> None:
        if len(_WORDISH.findall(text)) >= 2:
            self.heard_user = True

    def on_speech_started(self) -> None:
        if self.mode == "vad":
            self.heard_user = True

    def on_turn_done(self) -> None:
        self.heard_user = False

    def allows(self, tool_name: str) -> bool:
        return self.mode == "off" or tool_name in ALWAYS_ALLOWED or self.heard_user
