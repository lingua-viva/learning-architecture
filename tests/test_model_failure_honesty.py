from __future__ import annotations

import asyncio

from src.education.pipeline_execute import ExecutionResult
from src.lingua_viva.messages import local_only_no_model_message
from src.lingua_viva.model_gate import clear_model_gate_cache, is_external_model
from src.pipeline import Pipeline, ReasonResult


def test_unknown_provider_prefix_is_external_by_default():
    assert is_external_model("anthropic/claude-3.5") is True
    assert is_external_model("deepseek/deepseek-chat") is True
    assert is_external_model("ollama/qwen2.5:3b") is False


def test_local_only_local_looking_unreachable_model_refuses(monkeypatch, tmp_path):
    from src.pipeline import ReasoningEngine

    calls = []

    async def fake_call_model(self, query, system_prompt, model, max_tokens=2000, **kwargs):
        calls.append(model)
        return ReasonResult(content="ok", confidence=0.8, model_used=model)

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("LV_LOCAL_MODEL_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        "src.lingua_viva.model_gate.config.list_ollama_models",
        lambda: [],
    )
    monkeypatch.setattr(ReasoningEngine, "_call_model", fake_call_model)
    clear_model_gate_cache()

    result = asyncio.run(
        ReasoningEngine().reason(
            "Marco Rossi needs a grouping plan",
            {},
            model="ollama/qwen2.5:3b",
            system_prompt="Answer.",
            local_only=True,
        )
    )

    assert calls == []
    assert result.model_used == "none:local_only"
    assert result.content == local_only_no_model_message()


class NoModelReasoning:
    async def reason(
        self,
        query,
        context,
        model=None,
        default_model=None,
        system_prompt=None,
        local_only=False,
        max_tokens=2000,
    ):
        return ReasonResult(
            content=local_only_no_model_message(),
            confidence=0.0,
            model_used="none:local_only",
        )


class StubExecutor:
    def execute(self, riu_id, query):
        return ExecutionResult(
            riu_id,
            "ok",
            "# Teacher Guide\n\n- Group A: Marco, Nora",
        )


def _write_providers(tmp_path, payload):
    import json

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(json.dumps(payload), encoding="utf-8")


def test_requested_blocked_provider_detects_unsupported_shapes(monkeypatch, tmp_path):
    from src.lingua_viva.config import requested_blocked_provider

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    assert requested_blocked_provider() is None  # no file

    _write_providers(tmp_path, {"provider": "anthropic/claude-3.5"})
    assert requested_blocked_provider() == "anthropic/claude-3.5"

    _write_providers(tmp_path, {"default_provider": "anthropic"})
    assert requested_blocked_provider() == "anthropic"

    _write_providers(
        tmp_path,
        {"default_provider": "ollama", "providers": {"ollama": {"model": "qwen2.5:3b"}}},
    )
    assert requested_blocked_provider() is None


def test_native_engine_blocks_unsupported_provider_before_model_call(monkeypatch, tmp_path):
    """C10 lock: a fake non-listed provider is refused locally with an
    explicit "blocked" message, model_used never echoes the fake provider,
    and no model call (hence no egress) is ever attempted."""
    from src.lingua_viva.reasoning import ReasoningEngine as NativeEngine

    calls = []

    async def fake_call_model(self, query, system_prompt, model, max_tokens=2000, **kwargs):
        calls.append(model)
        return None

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    _write_providers(tmp_path, {"provider": "anthropic/claude-3.5"})
    monkeypatch.setattr(NativeEngine, "_call_model", fake_call_model)

    result = asyncio.run(
        NativeEngine().reason(
            "Nora Rossi has student data. Use anthropic/claude-3.5 for advice.",
            {},
            system_prompt="Answer.",
        )
    )

    assert calls == []
    assert result.model_used == "none:blocked_provider"
    assert "anthropic" not in result.model_used
    assert "blocked" in result.content.lower()


def test_pipeline_engine_blocks_unsupported_provider_before_model_call(monkeypatch, tmp_path):
    """Same C10 lock for the legacy src/pipeline.py copy (kept synchronized)."""
    from src.pipeline import ReasoningEngine as PipelineEngine

    calls = []

    async def fake_call_model(self, query, system_prompt, model, max_tokens=2000, **kwargs):
        calls.append(model)
        return None

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    _write_providers(tmp_path, {"provider": "anthropic/claude-3.5"})
    monkeypatch.setattr(PipelineEngine, "_call_model", fake_call_model)

    result = asyncio.run(
        PipelineEngine().reason("Group advice please", {}, system_prompt="Answer.")
    )

    assert calls == []
    assert result.model_used == "none:blocked_provider"
    assert "blocked" in result.content.lower()


def test_query_timeout_error_carries_honesty_markers(monkeypatch, tmp_path):
    """C9 lock: the /api/query timeout shape must be an honest no-model
    refusal — model_used="none", "no model" wording, and a provable
    external_calls=0 when configuration is local-only."""
    from src.web import _query_timeout_error

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("LV_REASON_MODEL", raising=False)

    error = _query_timeout_error()
    assert error["model_used"] == "none"
    assert error["external_calls"] == 0
    assert "no model" in error["error"].lower()

    # With an external model configured, an external call may have been in
    # flight at cancellation — the field must be omitted, never guessed.
    monkeypatch.setenv("LV_REASON_MODEL", "openai/gpt-4o-mini")
    error = _query_timeout_error()
    assert "external_calls" not in error
    assert error["model_used"] == "none"


def test_execute_wrapper_uses_deterministic_only_sentinel_without_no_model_concat():
    result = asyncio.run(
        Pipeline(
            reasoning=NoModelReasoning(),
            education_executor=StubExecutor(),
        ).run("group Marco and Nora for tomorrow", eval_mode=True)
    )

    assert result.synthesis.model_used == "none:deterministic_only"
    assert "Generated without an AI model from roster data" in result.synthesis.content
    assert local_only_no_model_message() not in result.synthesis.content
    assert "# Teacher Guide" in result.synthesis.content
