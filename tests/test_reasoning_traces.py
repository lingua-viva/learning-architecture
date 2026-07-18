import asyncio
import json

from src.lingua_viva.reasoning import ReasonResult, ReasoningEngine
from src.lingua_viva.traces import ReasoningTrace, append_trace, get_trace, read_traces, trace_path


def run(coro):
    return asyncio.run(coro)


def _trace_store(monkeypatch, tmp_path):
    path = tmp_path / "traces.ndjson"
    monkeypatch.setenv("LV_TRACE_PATH", str(path))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    return path


def test_trace_appended_after_reasoning(monkeypatch, tmp_path):
    path = _trace_store(monkeypatch, tmp_path)

    async def fake_call(query, system_prompt, model):
        return ReasonResult(content="ok", confidence=0.8, model_used=model, tokens_used=5)

    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_call_model", fake_call)

    run(engine.reason("What CEFR targets for Grade 3?", {"domain": "curriculum"}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    traces = read_traces()
    assert len(traces) == 1
    assert traces[0].classification_domain == "curriculum"
    assert traces[0].external_calls == 0
    assert path.stat().st_mode & 0o777 == 0o600


def test_trace_never_contains_raw_query(monkeypatch, tmp_path):
    path = _trace_store(monkeypatch, tmp_path)
    raw = "What CEFR targets for Grade 3 La Famiglia?"

    async def fake_call(query, system_prompt, model):
        return ReasonResult(content="ok", confidence=0.8, model_used=model)

    engine = ReasoningEngine()
    monkeypatch.setattr(engine, "_call_model", fake_call)
    run(engine.reason(raw, {"domain": "curriculum"}, model="ollama/qwen2.5:7b", system_prompt="Prompt"))

    assert raw not in path.read_text(encoding="utf-8")
    assert "CEFR targets" not in path.read_text(encoding="utf-8")


def test_read_traces_returns_most_recent_first(monkeypatch, tmp_path):
    _trace_store(monkeypatch, tmp_path)
    append_trace(ReasoningTrace("old", "2026-07-18T01:00:00+00:00", "h1", "general", "none", 1, 0))
    append_trace(ReasoningTrace("new", "2026-07-18T02:00:00+00:00", "h2", "general", "none", 1, 0))

    assert [trace.trace_id for trace in read_traces()] == ["new", "old"]


def test_get_trace_by_id(monkeypatch, tmp_path):
    _trace_store(monkeypatch, tmp_path)
    append_trace(ReasoningTrace("trace-1", "2026-07-18T01:00:00+00:00", "h1", "general", "none", 1, 0))

    assert get_trace("trace-1").trace_id == "trace-1"
    assert get_trace("missing") is None
