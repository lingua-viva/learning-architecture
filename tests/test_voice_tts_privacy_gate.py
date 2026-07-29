"""Rime TTS with the student-data privacy gate — Gap 5.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 5.

Rime is an external service, so /api/voice/tts is an egress path and gets the
same treatment as every other: check_publication_safety() runs BEFORE the API
key is even read, and a student name means the request never leaves this
machine.

The ordering is the thing worth pinning. A gate that runs after the key check
would pass on a machine with no key configured and start leaking the day
someone sets RIME_API_KEY — the failure would appear at configuration time,
far from the code that caused it.

Every non-200 tells the caller to use the browser's own voice. That fallback
is the private path, not a degraded one: the local voice speaks Italian
(contract v52).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.web import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def roster_and_no_key(monkeypatch):
    monkeypatch.delenv("RIME_API_KEY", raising=False)
    client.get("/api/students")  # seed the demo roster so names exist to match
    yield


def _tts(text: str, **extra):
    return client.post("/api/voice/tts", json={"text": text, **extra})


# --- the gate runs first ----------------------------------------------------


def test_student_data_is_refused_even_with_no_api_key_configured():
    """Proves ordering: the safety check precedes the key check. If it did
    not, this would return 503 (not configured) instead of 403."""
    response = _tts("Marco is doing well today")
    assert response.status_code == 403
    body = response.json()
    assert body["fallback"] == "local"
    assert body["violations"]


def test_student_data_is_still_refused_when_a_key_is_present(monkeypatch):
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")
    sent = []
    monkeypatch.setattr(web, "_request_rime_audio", lambda *a, **k: sent.append(a) or b"RIFF")

    response = _tts("Marco is doing well today")
    assert response.status_code == 403
    assert sent == [], "a request carrying a student name reached Rime"


def test_the_refusal_explains_itself_in_teacher_language():
    body = _tts("Marco is doing well today").json()
    assert "mentions a student" in body["error"]
    assert "this computer" in body["error"]


def test_refusing_is_recorded_as_a_privacy_event():
    from src.lingua_viva.privacy_log import read_privacy_events

    _tts("Marco is doing well today")
    kinds = {event.event_type for event in read_privacy_events(limit=200)}
    assert "voice_kept_local_student_data" in kinds


def test_an_unreadable_roster_fails_closed(monkeypatch):
    """Without the roster we cannot prove the text names no child, so the
    text stays local rather than being sent on the assumption it is fine."""
    def boom():
        raise OSError("database is locked")

    monkeypatch.setattr(web, "_active_student_names", boom)
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")

    response = _tts("Buongiorno a tutti")
    assert response.status_code == 403
    assert response.json()["fallback"] == "local"


# --- the happy path ---------------------------------------------------------


def test_clean_text_reaches_rime_and_returns_audio(monkeypatch):
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")
    captured = {}

    def fake_audio(text, speaker, model_id, key):
        captured.update(text=text, speaker=speaker, model_id=model_id, key=key)
        return b"RIFF....WAVEfmt "

    monkeypatch.setattr(web, "_request_rime_audio", fake_audio)

    response = _tts("Buongiorno, oggi lavoriamo sui suoni.")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
    assert captured["key"] == "rime-test-key"
    assert "Marco" not in captured["text"]


def test_sending_to_rime_is_recorded_as_a_privacy_event(monkeypatch):
    from src.lingua_viva.privacy_log import read_privacy_events

    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")
    monkeypatch.setattr(web, "_request_rime_audio", lambda *a, **k: b"RIFF")

    _tts("Buongiorno a tutti")
    kinds = {event.event_type for event in read_privacy_events(limit=200)}
    assert "voice_sent_to_external_tts" in kinds, (
        "an external call must be visible to the governance view"
    )


# --- graceful degradation ---------------------------------------------------


def test_no_key_reports_not_configured_and_asks_for_the_local_voice():
    response = _tts("Buongiorno a tutti")
    assert response.status_code == 503
    assert response.json()["fallback"] == "local"


def test_a_rime_failure_falls_back_rather_than_erroring_out(monkeypatch):
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")

    def boom(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(web, "_request_rime_audio", boom)
    response = _tts("Buongiorno a tutti")
    assert response.status_code == 502
    assert response.json()["fallback"] == "local"


@pytest.mark.parametrize("text,status", [("", 400), ("x" * 20_000, 400)])
def test_bad_input_is_rejected(text, status):
    assert _tts(text).status_code == status


# --- the UI actually falls back ---------------------------------------------


def test_ui_tries_the_endpoint_then_the_local_voice():
    body = client.get("/").text
    assert '"/api/voice/tts"' in body, "voice handler never calls the endpoint"
    assert "this.speakLocally(text)" in body, "no fallback to the local voice"


def test_local_fallback_still_speaks_italian():
    """The fallback must not undo the v52 Italian TTS fix."""
    body = client.get("/").text
    start = body.index("speakLocally(text)")
    end = body.index("toggleAsk()")
    assert 'utterance.lang = "it-IT"' in body[start:end]


def test_stopping_speech_also_stops_rime_playback():
    """Otherwise the browser voice and the Rime audio talk over each other."""
    body = client.get("/").text
    start = body.index("stopSpeaking() {")
    end = body.index("speak(text)")
    assert "this.remoteAudio.pause()" in body[start:end]
