from app.voice.speech_gate import SpeechGate


def test_transcript_gate_blocks_changes_without_customer_words() -> None:
    g = SpeechGate("transcript")
    assert g.allows("get_current_step") and g.allows("continue_from_greeting")
    assert not g.allows("set_guest_count")
    g.on_speech_started()  # noise tripping VAD is not enough
    assert not g.allows("set_guest_count")
    g.on_user_transcript("  . ")  # punctuation / breath is not speech
    assert not g.allows("set_guest_count")
    g.on_user_transcript("हम छह लोग हैं")
    assert g.allows("set_guest_count") and g.allows("set_occasion")  # several tools from one utterance
    g.on_turn_done()
    assert not g.allows("select_package")


def test_vad_and_off_modes() -> None:
    v = SpeechGate("vad")
    v.on_speech_started()
    assert v.allows("set_customer_name")
    assert SpeechGate("off").allows("set_customer_name")
