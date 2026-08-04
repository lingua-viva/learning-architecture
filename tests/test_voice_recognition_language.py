"""Voice input must use local STT, not Electron-broken Web Speech.

Electron does not provide Chrome's cloud SpeechRecognition service. The
voice-first contract is now getUserMedia -> MediaRecorder -> local
/api/voice/stt, while playback remains Italian.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.web import app

client = TestClient(app)


def _served_index() -> str:
    response = client.get("/")
    assert response.status_code == 200, response.status_code
    return response.text


def test_both_voice_handlers_use_local_stt():
    body = _served_index()
    assert "navigator.mediaDevices.getUserMedia({audio: true})" in body
    assert "new MediaRecorder(this.mediaStream" in body
    assert 'fetch("/api/voice/stt"' in body
    for handler, next_handler_marker in (
        ("toggleAsk()", "toggleObserve()"),
        ("toggleObserve()", None),
    ):
        start = body.index(handler)
        end = body.index(next_handler_marker) if next_handler_marker else len(body)
        assert "captureLocalStt({" in body[start:end], f"{handler} does not use local STT capture"


def test_no_english_recogniser_survives_anywhere_in_the_bundle():
    assert 'recognition.lang = "en-US"' not in _served_index()
    assert "window.webkitSpeechRecognition" not in _served_index()


def test_playback_speaks_italian_not_english():
    """Speech synthesis uses language detection: Italian content → Italian voice,
    English content (refusals) → English voice. B2 fix ensures locale matches text.
    """
    body = _served_index()
    start = body.index("speakLocally(text)")
    end = body.index("window.speechSynthesis.speak(utterance)", start)
    speak_body = body[start:end]

    # Language detection present
    assert 'textLang' in speak_body, "utterance.lang must be set dynamically from textLang"
    assert 'looksEnglish' in speak_body, "English detection regex must be present"
    # Italian path still exists
    assert "/^it([-_]|$)/i.test(voice.lang)" in speak_body, (
        "Italian voice filter must still be present for Italian content"
    )
    # English path exists for refusal messages
    assert "/^en([-_]|$)/i.test(voice.lang)" in speak_body, (
        "English voice filter must exist for English refusal messages"
    )


def test_playback_sets_language_before_reading_the_voice_list():
    """getVoices() is empty until the browser loads voices asynchronously.

    Language must be set before the voice lookup so the first-call-empty
    case falls back to the correct language default.
    """
    body = _served_index()
    start = body.index("speakLocally(text)")
    end = body.index("window.speechSynthesis.speak(utterance)", start)
    speak_body = body[start:end]
    assert speak_body.index("utterance.lang = textLang") < speak_body.index(
        "window.speechSynthesis.getVoices()"
    ), "utterance.lang must be set before the voice list is consulted"


def test_local_stt_capture_is_inside_both_named_handlers():
    body = _served_index()
    for handler, next_handler_marker in (
        ("toggleAsk()", "toggleObserve()"),
        ("toggleObserve()", None),
    ):
        start = body.index(handler)
        end = body.index(next_handler_marker) if next_handler_marker else len(body)
        assert "captureLocalStt({" in body[start:end], f"{handler} does not call local STT capture"
