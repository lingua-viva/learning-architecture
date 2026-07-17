"""
ReasoningEngine model-resolution-order tests — Gap 5a, SPEC_ONE_CLICK_LOCAL_APP
_2026-07-14.md point 1.

The spec's own changelog notes this order was corrected twice in review: a
single conflated `model` param used to let the ontology's default_model
always win, which meant a user's connected provider could never actually
take effect. This suite locks in the fixed 5-tier order directly against
ReasoningEngine.reason() (via _resolve_provider_model + the priority chain),
without going through the network — _call_model is monkeypatched to just
record what model string it was asked to use.

Uses SIR_CONFIG_HOME (same mechanism as test_provider_config.py) so this
suite never touches a real ~/.still-i-rise directory.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json

import pytest

from src.pipeline import ReasoningEngine, ReasonResult


@pytest.fixture(autouse=True)
def isolated_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIR_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("LV_REASON_MODEL", raising=False)
    yield tmp_path


def _write_provider_config(tmp_path, provider, model):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(json.dumps({
        "providers": {provider: {"model": model}},
        "default_provider": provider,
    }))


async def _recording_reason(engine, monkeypatch, **kwargs):
    seen = {}

    async def fake_call_model(query, system_prompt, model):
        seen["model"] = model
        return ReasonResult(content="ok", confidence=1.0, model_used=model)

    monkeypatch.setattr(engine, "_call_model", fake_call_model)
    await engine.reason(query="q", context={}, system_prompt="sys", **kwargs)
    return seen["model"]


def test_explicit_model_beats_everything(monkeypatch, isolated_config_home):
    _write_provider_config(isolated_config_home, "openai", "gpt-4o-mini")
    monkeypatch.setenv("LV_REASON_MODEL", "ollama/env-model")
    engine = ReasoningEngine()

    used = _run(_recording_reason(engine, monkeypatch, model="explicit/override", default_model="ollama/ontology-default"))

    assert used == "explicit/override"


def test_provider_config_beats_default_model_and_env(monkeypatch, isolated_config_home):
    _write_provider_config(isolated_config_home, "groq", "llama-3.1-8b-instant")
    monkeypatch.setenv("LV_REASON_MODEL", "ollama/env-model")
    engine = ReasoningEngine()

    used = _run(_recording_reason(engine, monkeypatch, default_model="ollama/ontology-default"))

    assert used == "groq/llama-3.1-8b-instant"


def test_default_model_beats_env_var_when_no_provider_connected(monkeypatch, isolated_config_home):
    monkeypatch.setenv("LV_REASON_MODEL", "ollama/env-model")
    engine = ReasoningEngine()

    used = _run(_recording_reason(engine, monkeypatch, default_model="ollama/ontology-default"))

    assert used == "ollama/ontology-default"


def test_env_var_used_when_no_provider_and_no_default_model(monkeypatch, isolated_config_home):
    monkeypatch.setenv("LV_REASON_MODEL", "ollama/env-model")
    engine = ReasoningEngine()

    used = _run(_recording_reason(engine, monkeypatch))

    assert used == "ollama/env-model"


def test_auto_detect_used_as_last_resort(monkeypatch, isolated_config_home):
    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_resolve_best_model", lambda: "ollama/auto-detected")

    used = _run(_recording_reason(engine, monkeypatch))

    assert used == "ollama/auto-detected"


def test_resolve_provider_model_honors_ollama_entry_as_tier_2(isolated_config_home):
    """The 'ollama' entry install.sh writes during setup is the auto-detected
    default, not a user 'connection' — but _resolve_provider_model still
    honors it as tier 2 if present, since it IS a legitimate saved model
    choice (just not one that counts as 'connected' for UI purposes, see
    provider_status()'s ollama-not-connected test in test_provider_config.py)."""
    _write_provider_config(isolated_config_home, "ollama", "qwen2.5:14b")
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() == "ollama/qwen2.5:14b"


def test_resolve_provider_model_returns_none_for_unrecognized_provider(monkeypatch, isolated_config_home):
    _write_provider_config(isolated_config_home, "anthropic", "claude-3")
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() is None


def test_resolve_provider_model_returns_none_when_no_config(isolated_config_home):
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() is None


# ---------------------------------------------------------------------
# 15-iteration hardening sweep, 2026-07-14 — see BUILD_JOURNAL.md Turn 32.
# Real bug: this method is called on EVERY REASON step, so a corrupted
# (valid-JSON-but-non-object) providers.json used to crash every single
# query in the app with an unhandled AttributeError, not just the
# provider-status onboarding screen. Full repro/fix details in
# tests/test_provider_config.py's matching sweep section.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("bad_content", ["[1,2,3]", '"just a string"', "42", "true"])
def test_resolve_provider_model_survives_non_object_top_level_json(isolated_config_home, bad_content):
    config_dir = isolated_config_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(bad_content)
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() is None


def test_resolve_provider_model_survives_non_dict_providers_key(isolated_config_home):
    config_dir = isolated_config_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(json.dumps({
        "providers": [1, 2, 3], "default_provider": "openai",
    }))
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() is None


def test_resolve_provider_model_ignores_non_string_saved_model(isolated_config_home):
    """A non-string `model` should never have been written by
    connect_provider() (rejected at that boundary now — see
    test_provider_config.py), but a hand-edited or pre-fix config file
    could still contain one. Must degrade to 'use default_model', not
    return a garbage-typed value that later gets baked into an f-string
    and sent to a real API."""
    config_dir = isolated_config_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(json.dumps({
        "providers": {"openai": {"model": 123}}, "default_provider": "openai",
    }))
    engine = ReasoningEngine()
    assert engine._resolve_provider_model() is None


def test_reason_end_to_end_survives_corrupted_provider_config(monkeypatch, isolated_config_home):
    """The full REASON call path, not just the resolver in isolation —
    proves a corrupted config degrades to default_model instead of
    crashing the whole pipeline turn."""
    config_dir = isolated_config_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text("[1,2,3]")

    engine = ReasoningEngine()
    used = _run(_recording_reason(engine, monkeypatch, default_model="ollama/qwen3:8b"))
    assert used == "ollama/qwen3:8b"


import asyncio


def _run(coro):
    return asyncio.run(coro)
