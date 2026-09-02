"""P1-2 (Claudia QA 2026-08-03): when no local model exists, the teacher
must get an actionable, speakable setup message — never a bracketed
developer placeholder. Both reasoning engines share one message source
(src/lingua_viva/messages.py); these tests lock the class shut.
"""

from __future__ import annotations

import pytest

from src.lingua_viva.messages import (
    DEFAULT_LOCAL_MODEL,
    local_only_no_model_message,
    model_unreachable_message,
    no_model_message,
)
from src.lingua_viva.reasoning import ReasoningEngine


def test_messages_are_speakable_and_actionable():
    for message in (no_model_message(), local_only_no_model_message()):
        # Spoken by TTS as-is: no developer bracket syntax or markdown.
        assert "[" not in message and "]" not in message
        assert "#" not in message and "*" not in message
        # Actionable: name the tool and the exact command.
        assert "Ollama" in message
        assert f"ollama pull {DEFAULT_LOCAL_MODEL}" in message


def test_local_only_message_explains_why_external_is_closed():
    assert "student or family information" in local_only_no_model_message()


def test_model_unreachable_message_does_not_claim_install_missing():
    message = model_unreachable_message("ollama/qwen2.5:7b", "connection refused")

    assert "I tried to reach ollama/qwen2.5:7b" in message
    assert "connection refused" in message
    assert "install Ollama" not in message
    assert "[" not in message and "]" not in message


@pytest.mark.asyncio
async def test_engine_no_model_fallback_uses_shared_message(monkeypatch):
    async def no_result(self, query, prompt, model, max_tokens=None, **kwargs):
        return None

    monkeypatch.setattr(ReasoningEngine, "_call_model", no_result)
    monkeypatch.setattr(ReasoningEngine, "_ollama_breaker_open", lambda self, model: False)

    result = await ReasoningEngine().reason(
        "come stai?",
        model=DEFAULT_LOCAL_MODEL,
        system_prompt="Answer briefly.",
    )

    assert result.model_used == "none"
    assert result.confidence == 0.0
    assert result.content == no_model_message()
    assert not result.content.startswith("[")


@pytest.mark.asyncio
async def test_pipeline_engine_no_model_fallback_uses_shared_message(monkeypatch):
    from src.pipeline import ReasoningEngine as PipelineEngine

    async def no_result(self, query, prompt, model, max_tokens=None, **kwargs):
        return None

    monkeypatch.setattr(PipelineEngine, "_call_model", no_result)

    result = await PipelineEngine().reason(
        "come stai?",
        {},
        model=DEFAULT_LOCAL_MODEL,
        system_prompt="Answer briefly.",
    )

    assert result.model_used == "none"
    assert result.content == no_model_message()
    assert not result.content.startswith("[")
