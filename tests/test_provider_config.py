"""
Provider config tests — Gap 5a, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Exercises src/provider_config.py's write side (connect/disconnect,
verify-then-save) in isolation, without the FastAPI layer. Network calls
are monkeypatched — verify_key() itself is exercised directly against
HTTPError/URLError branches by faking urlopen, not by hitting real
provider APIs (that was done once manually against the real network
during development; this suite must be safe to run offline/in CI).

Uses LV_CONFIG_HOME to point _provider_config_path() at a tmp_path for
every test, so nothing here ever touches a real user's
~/.lingua-viva/config/providers.json.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from urllib import error

import pytest

from src import provider_config


@pytest.fixture(autouse=True)
def isolated_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    yield tmp_path


def test_provider_status_defaults_to_local_when_no_config(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "ollama_reachable", lambda: True)
    status = provider_config.provider_status()
    assert status == {
        "connected": False,
        "provider": "local",
        "model": None,
        "ollama_reachable": True,
    }


def test_provider_status_ollama_entry_is_not_treated_as_connected(isolated_config_home, monkeypatch):
    """The 'ollama' entry install.sh writes during setup is the auto-detected
    default state, not something a user 'connects' via this UI — spec point 2
    frames the choice as OpenAI/Groq/Mistral/Local, so 'local' must be
    reported even when providers.json already has an ollama default."""
    config_path = provider_config._provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "providers": {"ollama": {"model": "llama3.2"}},
        "default_provider": "ollama",
    }))
    monkeypatch.setattr(provider_config, "ollama_reachable", lambda: True)

    status = provider_config.provider_status()
    assert status["connected"] is False
    assert status["provider"] == "local"


def test_provider_status_reports_connected_external_provider(isolated_config_home, monkeypatch):
    config_path = provider_config._provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "providers": {"openai": {"model": "gpt-4o-mini", "api_key": "sk-x", "verified": True}},
        "default_provider": "openai",
    }))
    monkeypatch.setattr(provider_config, "ollama_reachable", lambda: False)

    status = provider_config.provider_status()
    assert status["connected"] is True
    assert status["provider"] == "openai"
    assert status["model"] == "gpt-4o-mini"
    assert status["ollama_reachable"] is False


def test_connect_provider_rejects_unsupported_provider(isolated_config_home):
    result = provider_config.connect_provider("anthropic", "sk-x")
    assert result["status"] == "rejected"
    assert not provider_config._provider_config_path().exists()


def test_connect_provider_rejects_blank_key(isolated_config_home):
    result = provider_config.connect_provider("openai", "   ")
    assert result["status"] == "rejected"
    assert not provider_config._provider_config_path().exists()


def test_connect_provider_bad_key_never_written_to_disk(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (False, "bad_key"))

    result = provider_config.connect_provider("openai", "sk-bad")

    assert result["status"] == "rejected"
    assert result["message"] == "This key didn't work — check it and try again."
    assert not provider_config._provider_config_path().exists()


def test_connect_provider_network_failure_still_saves_with_honest_message(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (False, "network"))

    result = provider_config.connect_provider("groq", "gsk-x")

    assert result["status"] == "saved_unreachable"
    assert "local mode" in result["message"]
    config_path = provider_config._provider_config_path()
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved["providers"]["groq"]["api_key"] == "gsk-x"
    assert saved["providers"]["groq"]["verified"] is False
    assert saved["default_provider"] == "groq"


def test_connect_provider_success_saves_verified_and_permissions_restricted(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (True, "ok"))

    result = provider_config.connect_provider("mistral", "mk-x", model="mistral-small-latest")

    assert result["status"] == "connected"
    config_path = provider_config._provider_config_path()
    saved = json.loads(config_path.read_text())
    assert saved["providers"]["mistral"] == {
        "model": "mistral-small-latest",
        "api_key": "mk-x",
        "verified": True,
    }
    assert saved["default_provider"] == "mistral"
    assert (config_path.stat().st_mode & 0o777) == 0o600


def test_connect_provider_defaults_model_when_omitted(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (True, "ok"))
    provider_config.connect_provider("openai", "sk-x")
    saved = json.loads(provider_config._provider_config_path().read_text())
    assert saved["providers"]["openai"]["model"] == "gpt-4o-mini"


def test_disconnect_provider_deletes_config_file(isolated_config_home, monkeypatch):
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (True, "ok"))
    provider_config.connect_provider("openai", "sk-x")
    config_path = provider_config._provider_config_path()
    assert config_path.exists()

    provider_config.disconnect_provider()

    assert not config_path.exists()


def test_disconnect_provider_is_a_noop_when_nothing_connected(isolated_config_home):
    provider_config.disconnect_provider()  # must not raise


def test_verify_key_distinguishes_bad_key_from_network_failure(monkeypatch):
    class FakeHTTPError(error.HTTPError):
        def __init__(self, code):
            super().__init__("http://x", code, "err", {}, None)

    def raise_401(req, timeout=None):
        raise FakeHTTPError(401)

    def raise_urlerror(req, timeout=None):
        raise error.URLError("connection refused")

    monkeypatch.setattr(provider_config.request, "urlopen", raise_401)
    ok, reason = provider_config.verify_key("openai", "sk-bad", "gpt-4o-mini")
    assert (ok, reason) == (False, "bad_key")

    monkeypatch.setattr(provider_config.request, "urlopen", raise_urlerror)
    ok, reason = provider_config.verify_key("openai", "sk-x", "gpt-4o-mini")
    assert (ok, reason) == (False, "network")


def test_verify_key_rejects_unsupported_provider_without_network_call():
    ok, reason = provider_config.verify_key("anthropic", "key", "claude")
    assert (ok, reason) == (False, "unsupported")


# ---------------------------------------------------------------------
# 15-iteration hardening sweep, 2026-07-14 — see BUILD_JOURNAL.md Turn 32.
#
# Real bug found: valid-but-non-object JSON on disk (a truncated write,
# a hand-edit, or two racing writers interleaving) used to crash every
# `.get()` call built on `_read_provider_config()` — including
# `ReasoningEngine._resolve_provider_model()`, called on *every* REASON
# step — with an unhandled AttributeError. `provider_status()` is
# exercised here since it shares the exact same read path; the REASON-step
# call site itself is covered in tests/test_reasoning_model_resolution.py.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("bad_content", ["[1,2,3]", '"just a string"', "42", "true"])
def test_provider_status_survives_non_object_top_level_json(isolated_config_home, monkeypatch, bad_content):
    config_path = provider_config._provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(bad_content)
    monkeypatch.setattr(provider_config, "ollama_reachable", lambda: True)

    status = provider_config.provider_status()
    assert status == {
        "connected": False,
        "provider": "local",
        "model": None,
        "ollama_reachable": True,
    }


def test_provider_status_survives_non_dict_providers_key(isolated_config_home, monkeypatch):
    """Top-level JSON is a valid dict (passes the outer guard) but the
    nested `providers` value is malformed — the same corruption class one
    level down. Must fall back to local, not crash."""
    config_path = provider_config._provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"providers": [1, 2, 3], "default_provider": "openai"}))
    monkeypatch.setattr(provider_config, "ollama_reachable", lambda: True)

    status = provider_config.provider_status()
    assert status["connected"] is False
    assert status["provider"] == "local"


def test_connect_provider_rejects_non_string_model(isolated_config_home, monkeypatch):
    """A malformed JSON body (int/list/dict for `model`) must never be
    persisted — it doesn't crash anything downstream, but it silently
    degrades every future REASON call to the placeholder until the
    teacher manually disconnects, with no visible cause."""
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (True, "ok"))

    for bad_model in (123, ["a", "b"], {"x": 1}, True):
        result = provider_config.connect_provider("openai", "sk-x", model=bad_model)
        assert result["status"] == "rejected"
        assert result["message"] == "Unsupported model value."
    assert not provider_config._provider_config_path().exists()


def test_connect_provider_writes_config_atomically(isolated_config_home, monkeypatch):
    """No `.json.tmp` sidecar should survive a successful connect — the
    write-then-rename must leave only the final file behind."""
    monkeypatch.setattr(provider_config, "verify_key", lambda provider, api_key, model: (True, "ok"))
    provider_config.connect_provider("openai", "sk-x")

    config_path = provider_config._provider_config_path()
    tmp_path = config_path.with_suffix(".json.tmp")
    assert config_path.exists()
    assert not tmp_path.exists()
    # And the final file must still be valid, complete JSON.
    json.loads(config_path.read_text())
