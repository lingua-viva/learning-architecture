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
    """Speech synthesis must answer in Italian.

    Recognising Italian but replying in an English voice is the same bug
    half-fixed, so the playback path is pinned here alongside the
    recognisers.
    """
    body = _served_index()
    start = body.index("speak(text)")
    end = body.index("toggleAsk()")
    speak_body = body[start:end]

    assert 'utterance.lang = "it-IT"' in speak_body, "playback language is not Italian"
    assert "/^it([-_]|$)/i.test(voice.lang)" in speak_body, (
        "playback does not filter the voice list to Italian voices"
    )
    assert "samantha" not in speak_body.lower(), (
        "English voice preference still present in playback"
    )
    assert "/^en[-_]/i.test(voice.lang)" not in speak_body, (
        "English voice fallback still present in playback"
    )


def test_playback_sets_language_before_reading_the_voice_list():
    """getVoices() is empty until the browser loads voices asynchronously.

    If lang were set after the voice lookup, that first-call-empty case
    would fall back to an English default. Order matters, so pin it.
    """
    body = _served_index()
    start = body.index("speak(text)")
    speak_body = body[start:body.index("toggleAsk()")]
    # Match the qualified call, not the bare name — the explanatory comment
    # above the assignment also mentions getVoices().
    assert speak_body.index('utterance.lang = "it-IT"') < speak_body.index(
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
