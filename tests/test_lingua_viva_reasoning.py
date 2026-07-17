import asyncio
import json

from src.lingua_viva import config
from src.lingua_viva.reasoning import ReasoningEngine


def run(coro):
    return asyncio.run(coro)


def test_reasoning_uses_model_response(monkeypatch, tmp_path):
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
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config, "detect_model", lambda: "ollama/qwen2.5:3b")

    def fail_urlopen(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", fail_urlopen)

    result = run(ReasoningEngine().reason("Help", {"riu_id": "lv-test"}, system_prompt="Prompt"))

    assert result.model_used == "none"
    assert "lv-test" in result.content


def test_reasoning_provider_config_precedes_default_model(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "providers": {"ollama": {"model": "qwen3:8b"}},
        "default_provider": "ollama",
    }))

    used = {}

    async def fake_call(query, system_prompt, model):
        used["model"] = model
        return None

    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_call_model", fake_call)

    run(engine.reason("Help", {}, default_model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert used["model"] == "ollama/qwen3:8b"


def test_endpoint_uses_saved_provider_key(monkeypatch, tmp_path):
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
