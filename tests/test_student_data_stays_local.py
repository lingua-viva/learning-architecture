"""Student data must never reach an external model provider.

Slice 4 (SPEC_GOVERNANCE_CONTROL_PLANE_2026-07-28 §Lingua Viva) requires the
governance view to answer "Was any student-identifiable information sent
externally?" with an unconditional NO. It could not, and these tests are why.

The bug: ContextBuilder.build() is called with the RAW `query`, not the entry
gate's `sanitized_query`, so `user_message` carries the original text. That is
fine for a local model. But ReasoningEngine.reason()'s resolution order put
`_resolve_provider_model()` — the teacher's Settings -> Cloud Provider choice —
ABOVE `default_model`, the ontology's governed suggestion. So with a cloud
provider connected, a query naming a student and their IEP was sent verbatim to
OpenAI/Groq/Mistral, while the entry gate (which only guards the
research/gateway path) recorded the data as blocked and the Privacy view
displayed "No external calls".

The fix is `local_only`, set from `entry_gate_blocked_external`. It is not
advisory: every external candidate is discarded, including an explicit `model`
override, and it fails closed when no local model exists.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import src.pipeline as pipeline_module
from src.pipeline import Pipeline, ReasoningEngine, ReasonResult

STUDENT_QUERY = "Marco Rossi is struggling with reading, his IEP says he needs extra support"
NEUTRAL_QUERY = "What are good warm up activities for a beginner Italian class?"


@pytest.fixture
def cloud_provider(tmp_path, monkeypatch):
    """A teacher who connected a cloud provider in Settings."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "providers.json").write_text(
        json.dumps(
            {
                "default_provider": "openai",
                "providers": {"openai": {"model": "gpt-4o", "api_key": "sk-test"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.delenv("LV_REASON_MODEL", raising=False)
    return tmp_path


@pytest.fixture
def captured_calls(monkeypatch):
    """Capture what would have been sent, without making a network call."""
    calls: list[dict] = []

    async def fake_call_model(self, query, system_prompt, model):
        calls.append({"model": model, "query": query})
        return ReasonResult(content="ok", confidence=0.8, model_used=model)

    monkeypatch.setattr(ReasoningEngine, "_call_model", fake_call_model)
    return calls


# --- the invariant ---------------------------------------------------------


def test_student_query_never_reaches_an_external_model(cloud_provider, captured_calls, monkeypatch):
    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")  # a local model exists
    asyncio.run(Pipeline().run(query=STUDENT_QUERY, eval_mode=True))

    assert captured_calls, "expected the local model to answer"
    for call in captured_calls:
        assert not ReasoningEngine._is_external_model(call["model"]), (
            f"student data was routed to {call['model']}"
        )


def test_student_name_is_not_in_any_external_payload(cloud_provider, captured_calls, monkeypatch):
    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")
    asyncio.run(Pipeline().run(query=STUDENT_QUERY, eval_mode=True))

    external = [c for c in captured_calls if ReasoningEngine._is_external_model(c["model"])]
    assert external == [], "an external call carrying student data was made"


def test_local_model_still_sees_the_real_text(cloud_provider, captured_calls, monkeypatch):
    """Redacting for the local model would wreck answer quality for no gain —
    the data is already on the teacher's machine. Only egress is restricted."""
    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")
    asyncio.run(Pipeline().run(query=STUDENT_QUERY, eval_mode=True))

    assert any("Marco Rossi" in call["query"] for call in captured_calls)


def test_ordinary_queries_still_use_the_connected_provider(cloud_provider, captured_calls):
    """The fix must not quietly disable the feature a teacher paid for."""
    asyncio.run(Pipeline().run(query=NEUTRAL_QUERY, eval_mode=True))

    assert any(
        ReasoningEngine._is_external_model(call["model"]) for call in captured_calls
    ), "non-student queries should still reach the configured cloud provider"


# --- local_only is not advisory --------------------------------------------


def test_local_only_overrides_even_an_explicit_model_override(cloud_provider, captured_calls):
    """`model` is documented as "always wins". For student data it must not."""
    engine = ReasoningEngine()
    asyncio.run(
        engine.reason(
            query=STUDENT_QUERY,
            context={},
            model="openai/gpt-4o",
            default_model="qwen2.5:3b",
            system_prompt="prompt",
            local_only=True,
        )
    )
    assert captured_calls
    assert not ReasoningEngine._is_external_model(captured_calls[0]["model"])


def test_fails_closed_when_no_local_model_can_be_resolved(cloud_provider, captured_calls, monkeypatch):
    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_resolve_best_model", lambda: "openai/gpt-4o")

    result = asyncio.run(
        engine.reason(
            query=STUDENT_QUERY,
            context={},
            default_model="openai/gpt-4o",
            system_prompt="prompt",
            local_only=True,
        )
    )
    assert captured_calls == [], "nothing may be sent when no local model exists"
    assert result.model_used == "none:local_only"
    assert "on this computer" in result.content


def test_local_only_is_recorded_as_a_privacy_event(cloud_provider, captured_calls, monkeypatch):
    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")
    from src.lingua_viva.privacy_log import read_privacy_events

    asyncio.run(Pipeline().run(query=STUDENT_QUERY, eval_mode=True))

    kinds = {event.event_type for event in read_privacy_events(limit=100)}
    assert "student_data_kept_local_for_reasoning" in kinds


# --- what counts as external ----------------------------------------------


@pytest.mark.parametrize(
    "model,external",
    [
        ("openai/gpt-4o", True),
        ("groq/llama-3.1-70b", True),
        ("mistral/mistral-large", True),
        # Ollama ':cloud' tags go through the local daemon but execute on
        # Ollama's servers — localhost in _resolve_endpoint() does not make
        # them local.
        ("kimi:cloud", True),
        ("qwen2.5:3b", False),
        ("ollama/qwen2.5:3b", False),
        ("llama3.1:8b", False),
        ("", False),
        (None, False),
    ],
)
def test_external_model_detection(model, external):
    assert ReasoningEngine._is_external_model(model) is external


# --- the real teacher path -------------------------------------------------
# The tests above drive Pipeline() directly, which uses src/pipeline.py's own
# ReasoningEngine. The actual app does NOT: src/web.py's /api/query calls
# run_teacher_query() (src/lingua_viva/app.py), which injects
# src/lingua_viva/reasoning.py's engine into the Pipeline. Fixing only
# src/pipeline.py would have left the teacher-facing route leaking, so the
# route itself is covered here.


@pytest.fixture
def captured_native_calls(monkeypatch):
    import src.lingua_viva.reasoning as native

    calls: list[dict] = []

    async def fake_call_model(self, query, system_prompt, model):
        calls.append({"model": model, "query": query})
        return native.ReasonResult(content="ok", confidence=0.8, model_used=model)

    monkeypatch.setattr(native.ReasoningEngine, "_call_model", fake_call_model)
    # A previous failed Ollama probe would otherwise short-circuit REASON.
    monkeypatch.setattr(native.ReasoningEngine, "_ollama_breaker_open_until", 0)
    return calls


def test_api_query_route_never_sends_student_data_to_a_provider(
    cloud_provider, captured_native_calls, monkeypatch
):
    from fastapi.testclient import TestClient

    import src.lingua_viva.reasoning as native
    from src.web import app

    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")
    TestClient(app).post(
        "/api/query",
        json={
            "query": "What does the IEP for student Marco Rossi suggest about reading?",
            "eval_mode": True,
        },
    )

    external = [
        call for call in captured_native_calls
        if native.ReasoningEngine._is_external_model(call["model"])
    ]
    assert external == [], (
        f"POST /api/query sent student data to {[c['model'] for c in external]}"
    )


def test_entry_gate_still_flags_student_data(cloud_provider, captured_calls, monkeypatch):
    """Guards the signal local_only depends on. If the entry gate stops
    detecting student data, local_only silently becomes False everywhere."""
    monkeypatch.setenv("LV_REASON_MODEL", "qwen2.5:3b")
    result = asyncio.run(Pipeline().run(query=STUDENT_QUERY, eval_mode=True))
    assert any("entry_gate_blocked" in signal for signal in (result.gap_signals or []))


def test_neutral_query_does_not_trip_the_gate(cloud_provider, captured_calls):
    result = asyncio.run(Pipeline().run(query=NEUTRAL_QUERY, eval_mode=True))
    assert not any("entry_gate_blocked" in s for s in (result.gap_signals or []))
