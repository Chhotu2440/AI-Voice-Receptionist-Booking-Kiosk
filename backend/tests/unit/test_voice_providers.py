"""Provider adapters translate wire events into provider-neutral events (tested on canned messages)."""

from __future__ import annotations

import base64

from app.voice.provider import AudioChunk, ProviderError, SpeechStarted, ToolCall, Transcript, TurnDone
from app.voice.providers import gemini_live, openai_realtime
from app.voice.tools import TOOLS
from tests.conftest import make_settings

PCM = b"\x01\x00\x02\x00"
B64 = base64.b64encode(PCM).decode()


# --- OpenAI Realtime --------------------------------------------------------------------------------


def test_openai_session_payload() -> None:
    s = make_settings(openai_api_key="sk-test-not-real")
    p = openai_realtime.session_payload(s, "be nice", TOOLS)
    sess = p["session"]
    assert p["type"] == "session.update" and sess["type"] == "realtime"
    assert sess["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert sess["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    assert {t["name"] for t in sess["tools"]} == {t.name for t in TOOLS}
    assert all(t["type"] == "function" for t in sess["tools"])
    assert "sk-test" not in str(p)  # the key never goes into payloads


def test_openai_event_mapping() -> None:
    st = openai_realtime.ParseState()
    parse = openai_realtime.parse_event
    assert parse({"type": "response.created"}, st) == [] and st.response_active
    assert parse({"type": "response.output_audio.delta", "item_id": "it1", "delta": B64}, st) == [
        AudioChunk(PCM)
    ]
    assert st.current_item == "it1" and st.current_item_bytes == 4
    assert parse({"type": "response.output_audio_transcript.delta", "delta": "Hi"}, st) == [
        Transcript("assistant", "Hi", final=False)
    ]
    assert parse(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "mera naam Riya"}, st
    ) == [Transcript("user", "mera naam Riya", final=True)]
    assert parse({"type": "input_audio_buffer.speech_started", "audio_start_ms": 10}, st) == [SpeechStarted()]


def test_openai_tool_calls_deduplicated_and_usage_summed() -> None:
    st = openai_realtime.ParseState()
    parse = openai_realtime.parse_event
    first = parse(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "c1",
            "name": "set_customer_name",
            "arguments": '{"name":"Riya"}',
        },
        st,
    )
    assert first == [ToolCall("c1", "set_customer_name", {"name": "Riya"})]
    done = parse(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "set_customer_name",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call",
                        "call_id": "c2",
                        "name": "set_guest_count",
                        "arguments": '{"count": 4}',
                    },
                ],
                "usage": {
                    "input_token_details": {"audio_tokens": 100, "text_tokens": 40, "cached_tokens": 30},
                    "output_token_details": {"audio_tokens": 200, "text_tokens": 10},
                },
            },
        },
        st,
    )
    assert done == [ToolCall("c2", "set_guest_count", {"count": 4}), TurnDone()]
    assert (st.usage.audio_in_tokens, st.usage.audio_out_tokens, st.usage.text_cached_tokens) == (
        100,
        200,
        30,
    )
    assert not st.response_active
    bad_json = parse(
        {"type": "response.function_call_arguments.done", "call_id": "c3", "name": "x", "arguments": "{"}, st
    )
    assert bad_json == [ToolCall("c3", "x", {})]


def test_openai_errors() -> None:
    st = openai_realtime.ParseState()
    parse = openai_realtime.parse_event
    assert parse({"type": "error", "error": {"code": "response_cancel_not_active"}}, st) == []
    assert parse({"type": "error", "error": {"code": "invalid_api_key", "message": "bad key"}}, st) == [
        ProviderError("bad key", fatal=True)
    ]
    assert parse({"type": "some.future.event"}, st) == []


# --- Gemini Live ------------------------------------------------------------------------------------


def test_gemini_setup_payload_strips_unsupported_schema_keywords() -> None:
    s = make_settings(gemini_api_key="AIza-test-not-real")
    p = gemini_live.setup_payload(s, "be nice", TOOLS)["setup"]
    assert p["model"] == "models/gemini-3.8-live"
    assert p["generationConfig"]["responseModalities"] == ["AUDIO"]
    decls = p["tools"][0]["functionDeclarations"]
    assert len(decls) == len(TOOLS)
    assert "additionalProperties" not in str(decls) and "pattern" not in str(decls)
    assert "AIza" not in str(p)


def test_gemini_message_mapping() -> None:
    st = gemini_live.ParseState()
    parse = gemini_live.parse_message
    assert parse({"setupComplete": {}}, st) == [] and st.setup_complete
    evs = parse(
        {
            "serverContent": {
                "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": B64}}]},
                "outputTranscription": {"text": "Namaste"},
                "inputTranscription": {"text": "hello"},
            }
        },
        st,
    )
    assert evs == [
        AudioChunk(PCM),
        Transcript("user", "hello", False),
        Transcript("assistant", "Namaste", False),
    ]
    assert parse({"serverContent": {"interrupted": True}}, st) == [SpeechStarted()]
    assert parse({"serverContent": {"turnComplete": True}}, st) == [TurnDone()]
    assert parse(
        {"toolCall": {"functionCalls": [{"id": "f1", "name": "set_guest_count", "args": {"count": 6}}]}}, st
    ) == [ToolCall("f1", "set_guest_count", {"count": 6})]
    parse(
        {
            "usageMetadata": {
                "promptTokensDetails": [
                    {"modality": "AUDIO", "tokenCount": 50},
                    {"modality": "TEXT", "tokenCount": 900},
                ],
                "responseTokensDetails": [{"modality": "AUDIO", "tokenCount": 70}],
            }
        },
        st,
    )
    assert (st.usage.audio_in_tokens, st.usage.text_in_tokens, st.usage.audio_out_tokens) == (50, 900, 70)
    assert parse({"goAway": {"timeLeft": "10s"}}, st)[0].fatal is False  # type: ignore[union-attr]
