import asyncio
import json

from src.lingua_viva import config
from src.lingua_viva.reasoning import ReasonResult, ReasoningEngine


def run(coro):
    return asyncio.run(coro)


def reset_breaker():
    ReasoningEngine._ollama_failures = 0
    ReasoningEngine._ollama_breaker_open_until = 0.0


def test_reasoning_uses_model_response(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    engine = ReasoningEngine()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "Ciao, maestra."}}],
                "usage": {"total_tokens": 7},
            }).encode()

    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout, json.loads(req.data.decode())))
        return Response()

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", fake_urlopen)

    result = run(engine.reason("Help", {}, model="ollama/qwen2.5:7b", system_prompt="Local teacher help."))

    assert result.content == "Ciao, maestra."
    assert result.model_used == "ollama/qwen2.5:7b"
    assert result.tokens_used == 7
    assert calls[0][0] == "http://localhost:11434/v1/chat/completions"
    assert calls[0][2]["model"] == "qwen2.5:7b"


def test_reasoning_falls_back_without_model(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config, "detect_model", lambda: "ollama/qwen2.5:3b")

    def fail_urlopen(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", fail_urlopen)

    result = run(ReasoningEngine().reason("Help", {"riu_id": "lv-test"}, system_prompt="Prompt"))

    assert result.model_used == "ollama/qwen2.5:3b"
    assert result.error == "model_unreachable"
    # HF2 (2026-08-04): a configured local model that cannot be reached is
    # not the same as a missing installation. Say what failed.
    assert not result.content.startswith("[")
    assert "I tried to reach ollama/qwen2.5:3b" in result.content
    assert "install Ollama" not in result.content


def test_reasoning_provider_config_precedes_default_model(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "providers": {"ollama": {"model": "qwen3:8b"}},
        "default_provider": "ollama",
    }))

    used = {}

    async def fake_call(query, system_prompt, model, max_tokens=2000):
        used["model"] = model
        return None

    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_call_model", fake_call)

    run(engine.reason("Help", {}, default_model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert used["model"] == "ollama/qwen3:8b"


def test_endpoint_uses_saved_provider_key(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "providers": {"openai": {"model": "gpt-4o-mini", "api_key": "sk-test", "verified": True}},
        "default_provider": "openai",
    }))

    url, headers = ReasoningEngine._resolve_endpoint("openai/gpt-4o-mini")

    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"


def test_ollama_circuit_breaker_opens_after_three_timeouts(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config, "ollama_reachable", lambda: False)
    calls = {"count": 0}

    def timeout(*args, **kwargs):
        calls["count"] += 1
        raise TimeoutError("slow")

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", timeout)
    engine = ReasoningEngine()

    for _ in range(3):
        result = run(engine.reason("Help", {}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))
        assert result.error == "timeout"

    result = run(engine.reason("Help", {}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert "I tried to reach ollama/qwen2.5:7b" in result.content
    assert result.error == "ollama_unreachable"
    assert calls["count"] == 3
    reset_breaker()


def test_fresh_reasoning_engine_does_not_inherit_stale_ollama_breaker(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    ReasoningEngine._ollama_failures = 3
    ReasoningEngine._ollama_breaker_open_until = 9999999999.0

    async def ok_call(self, query, system_prompt, model, max_tokens=2000):
        return ReasonResult(content="Use a counting game.", confidence=0.75, model_used=model, tokens_used=3)

    monkeypatch.setattr(ReasoningEngine, "_call_model", ok_call)

    result = run(ReasoningEngine().reason("What are three Italian number games?", {}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert result.content == "Use a counting game."
    assert result.model_used == "ollama/qwen2.5:7b"


def test_open_breaker_rechecks_ollama_before_refusing(monkeypatch, tmp_path):
    reset_breaker()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config, "ollama_reachable", lambda: True)
    engine = ReasoningEngine()
    engine._ollama_failures = 3
    engine._ollama_breaker_open_until = 9999999999.0

    async def ok_call(query, system_prompt, model, max_tokens=2000):
        return ReasonResult(content="Ollama recovered.", confidence=0.75, model_used=model, tokens_used=3)

    monkeypatch.setattr(engine, "_call_model", ok_call)

    result = run(engine.reason("What are three Italian number games?", {}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert result.content == "Ollama recovered."
    assert engine._ollama_failures == 0
    assert engine._ollama_breaker_open_until == 0.0
