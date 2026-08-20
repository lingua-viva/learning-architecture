"""F2 (SPEC_LV_DEMO_EVE_FIX_2026-08-19 §2): Ask must refuse, not invent,
on zero data.

Demo-blocking Finding 2: with observations 0, evidence 0, all CEFR
dimensions null, Ask said the child "has been making good progress" — and
read it aloud. The hedge ("weak source") was a lie of framing: the truth
is "you have no data on this student".

The gate is CODE in Pipeline.run, before any model call, covering every
caller (ask, voice, /api/query, /api/query/stream) — the model cannot
route around it. These tests lock the class:
- zero-data student + progress question → fixed refusal, ZERO model calls,
  no progress/ability claims, route stays local;
- a student with ANY recorded data (one observation) → normal path;
- non-student questions → normal path;
- unreadable store → fail-open to the normal path (a broken roster must
  not silence every answer).
"""
from __future__ import annotations

import asyncio

import pytest

from src.pipeline import (
    Pipeline,
    ReasoningEngine,
    ReasonResult,
    _student_zero_data_refusal,
)

STUDENT_NAME = "Nora Vento"
PROGRESS_QUESTION = f"How is {STUDENT_NAME} doing with her Italian reading?"

# Claim phrases the refusal must never contain — the invented-progress
# vocabulary from Finding 2 ("has been making good progress", "is currently
# working on understanding basic sentences").
INVENTION_MARKERS = (
    "making progress",
    "making good progress",
    "is improving",
    "has improved",
    "working on",
    "is able to",
    "doing well",
    "good progress",
)


@pytest.fixture
def student_store(tmp_path, monkeypatch):
    """A real StudentLensStore with one zero-data student."""
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "student_lenses.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))
    with StudentLensStore(db_path=db_path) as store:
        student_id = store.create_lens(display_name=STUDENT_NAME)
    return {"db_path": db_path, "student_id": student_id}


@pytest.fixture
def captured_calls(monkeypatch):
    """Capture would-be model calls without any network."""
    calls: list[dict] = []

    async def fake_call_model(self, query, system_prompt, model, max_tokens=2000):
        calls.append({"model": model, "query": query})
        return ReasonResult(
            content=f"{STUDENT_NAME} has been making good progress with basic sentences.",
            confidence=0.8,
            model_used=model,
        )

    monkeypatch.setattr(ReasoningEngine, "_call_model", fake_call_model)
    return calls


def _add_observation(db_path, student_id):
    from src.education.student_lens import Observation, StudentLensStore

    with StudentLensStore(db_path=db_path) as store:
        store.append_observation(
            Observation(
                student_id=student_id,
                teacher_id="teacher:test",
                template_type="general",
                raw_transcript="Read a familiar paragraph aloud with support.",
            )
        )


# --- the helper, in isolation -------------------------------------------------


def test_refusal_fires_only_on_zero_data(student_store):
    refusal = _student_zero_data_refusal(PROGRESS_QUESTION)
    assert refusal is not None
    assert STUDENT_NAME in refusal
    assert "no observations recorded" in refusal
    lowered = refusal.lower()
    assert not any(marker in lowered for marker in INVENTION_MARKERS), refusal

    _add_observation(student_store["db_path"], student_store["student_id"])
    assert _student_zero_data_refusal(PROGRESS_QUESTION) is None


def test_refusal_ignores_non_student_questions(student_store):
    assert _student_zero_data_refusal(
        "What are good warm up activities for a beginner Italian class?"
    ) is None


def test_refusal_fails_open_when_store_unreadable(monkeypatch, tmp_path):
    corrupt = tmp_path / "student_lenses.db"
    corrupt.write_bytes(b"this is not a sqlite database")
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(corrupt))
    assert _student_zero_data_refusal(PROGRESS_QUESTION) is None


def test_refusal_fails_open_when_no_store_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "missing.db"))
    assert _student_zero_data_refusal(PROGRESS_QUESTION) is None


# --- the gate, through the full pipeline ---------------------------------------


def test_zero_data_progress_question_is_refused_with_zero_model_calls(
    student_store, captured_calls
):
    result = asyncio.run(Pipeline().run(query=PROGRESS_QUESTION, eval_mode=True))

    assert captured_calls == [], "the model must never be called on zero data"
    content = result.synthesis.content
    assert "no observations recorded" in content
    assert STUDENT_NAME in content
    lowered = content.lower()
    assert not any(marker in lowered for marker in INVENTION_MARKERS), content
    # route stays local and the trace says why
    assert result.external_called is False
    assert result.synthesis.model_used == "none:no_student_data"
    assert result.path_record.model_used == "none:no_student_data"
    assert "refused:no_student_data" in result.gap_signals
    assert "REFUSE(no_student_data)" in result.steps_executed
    # no hedge machinery: the refusal is literally true by construction
    assert result.path_record.voice_tone == "plain"
    assert result.path_record.gir_score == 1.0


def test_student_with_one_observation_takes_the_normal_path(
    student_store, captured_calls
):
    _add_observation(student_store["db_path"], student_store["student_id"])

    result = asyncio.run(Pipeline().run(query=PROGRESS_QUESTION, eval_mode=True))

    assert "refused:no_student_data" not in result.gap_signals
    assert result.synthesis.model_used != "none:no_student_data"
