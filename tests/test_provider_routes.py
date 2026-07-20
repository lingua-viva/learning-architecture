"""
Provider route tests — Gap 5a, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Route-level contract for GET /api/provider, POST /api/provider/connect,
POST /api/provider/disconnect. Monkeypatches src.provider_config's public
functions directly (same pattern as test_provider_config.py uses for
verify_key) so this suite never hits a real provider API or a real
~/.lingua-viva directory.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import src.provider_config as provider_config
import src.web as web

client = TestClient(web.app)


def test_get_provider_returns_status_shape(monkeypatch):
    monkeypatch.setattr(provider_config, "provider_status", lambda: {
        "connected": False, "provider": "local", "model": None, "ollama_reachable": True,
    })
    response = client.get("/api/provider")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False, "provider": "local", "model": None, "ollama_reachable": True,
    }


def test_connect_rejects_unsupported_provider(monkeypatch):
    response = client.post("/api/provider/connect", json={"provider": "anthropic", "api_key": "x"})
    assert response.status_code == 400
    assert "Unsupported provider" in response.json()["error"]


def test_connect_rejects_blank_key():
    response = client.post("/api/provider/connect", json={"provider": "openai", "api_key": "   "})
    assert response.status_code == 400
    assert "didn't work" in response.json()["error"]


def test_connect_bad_key_returns_400_with_spec_message(monkeypatch):
    monkeypatch.setattr(provider_config, "connect_provider", lambda provider, api_key, model: {
        "status": "rejected", "message": "This key didn't work — check it and try again.",
    })
    response = client.post("/api/provider/connect", json={"provider": "openai", "api_key": "sk-bad"})
    assert response.status_code == 400
    assert response.json()["error"] == "This key didn't work — check it and try again."


def test_connect_success_returns_200_with_provider_echoed(monkeypatch):
    monkeypatch.setattr(provider_config, "connect_provider", lambda provider, api_key, model: {
        "status": "connected", "message": "Connected to groq.",
    })
    response = client.post("/api/provider/connect", json={"provider": "GROQ", "api_key": "gsk-x"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["provider"] == "groq"


def test_connect_network_unreachable_still_returns_200(monkeypatch):
    monkeypatch.setattr(provider_config, "connect_provider", lambda provider, api_key, model: {
        "status": "saved_unreachable", "message": "Saved — will use local mode until we can reach mistral.",
    })
    response = client.post("/api/provider/connect", json={"provider": "mistral", "api_key": "mk-x"})
    assert response.status_code == 200
    assert response.json()["status"] == "saved_unreachable"


def test_disconnect_calls_through_and_returns_disconnected(monkeypatch):
    calls = []
    monkeypatch.setattr(provider_config, "disconnect_provider", lambda: calls.append(True))
    response = client.post("/api/provider/disconnect")
    assert response.status_code == 200
    assert response.json() == {"status": "disconnected"}
    assert calls == [True]


# 15-iteration hardening sweep, 2026-07-14 — see BUILD_JOURNAL.md Turn 32.
def test_connect_rejects_non_string_model_before_calling_provider_config(monkeypatch):
    calls = []
    monkeypatch.setattr(provider_config, "connect_provider", lambda *a, **k: calls.append((a, k)))
    response = client.post(
        "/api/provider/connect",
        json={"provider": "openai", "api_key": "sk-x", "model": 123},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Unsupported model value."
    assert calls == []  # never reaches connect_provider()
