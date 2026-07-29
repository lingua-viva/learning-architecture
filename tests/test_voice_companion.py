from pathlib import Path

from fastapi.testclient import TestClient

from src.web import app


REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
ELECTRON_MAIN = (REPO / "desktop" / "electron" / "main.ts").read_text(encoding="utf-8")
client = TestClient(app)


def test_voice_companion_is_single_mic_surface():
    assert 'id="voice-companion"' in HTML
    assert 'id="vc-mic"' in HTML
    assert 'src="/assets/mc-avatar.png"' in HTML
    assert "toggleVoiceCompanion" in HTML
    assert 'statusId: "vc-state"' in HTML
    assert 'id="ask-mic"' not in HTML
    assert 'id="mic"' not in HTML


def test_voice_companion_routes_ask_and_observe():
    assert 'state.view === "observe"' in HTML
    assert 'await switchView("ask")' in HTML
    assert 'inputId: "obs-text"' in HTML
    assert 'inputId: "ask-input"' in HTML
    assert "submitAskText(text, true)" in HTML
    assert 'updateVoiceCompanion("speaking", "Speaking")' in HTML


def test_voice_companion_avatar_is_served():
    response = client.get("/assets/mc-avatar.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content


def test_electron_csp_allows_blob_audio_for_tts():
    assert "\"media-src 'self' blob:\"," in ELECTRON_MAIN
