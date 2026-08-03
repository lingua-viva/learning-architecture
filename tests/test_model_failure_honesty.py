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

    async def fake_call_model(self, query, system_prompt, model, max_tokens=2000):
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
