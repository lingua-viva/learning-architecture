"""Lesson plan revision loop — P2-TEST-003.

Spec: dev/SPEC_LV_IMPROVEMENT_CHECKLIST_2026-08-22.md.

The revision path in src/lingua_viva/lesson_materials.py has two layers:

- `_apply_deterministic_revision(plan, revision_text)` — pure, no LLM.
  Three keyword branches (song+warmup, visuals, harder extension) make a
  targeted edit; anything else preserves the plan and records the request
  in teacher_notes. This is the fallback a teacher actually gets when no
  model is running, so it is tested exhaustively here.
- `revise_lesson_plan_artifact(...)` — the full async pipeline: prompt an
  engine, parse its JSON, fall back to the deterministic path on any
  engine error, then normalize + render. Tested with stub engines (no
  model needed) plus one live-model test that skips without Ollama.

These tests treat lesson_materials.py as read-only: they pin current
behavior, including the fact that "make the warmup shorter" is NOT a
targeted branch (it lands in teacher_notes).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.education.content_differentiator import LessonInput
from src.lingua_viva.config import ollama_reachable
from src.lingua_viva.lesson_materials import (
    CurriculumKnowledgeEntry,
    _apply_deterministic_revision,
    _deterministic_lesson_plan,
    _validate_lesson_plan_safety,
    revise_lesson_plan_artifact,
)
from src.lingua_viva.reasoning import ReasonResult

ROSTER_NAMES = ["Marco", "Nora", "Luca"]  # fictional, per repo privacy rule


def _lesson(**overrides) -> LessonInput:
    data = {
        "ib_programme": "PYP",
        "subject": "language",
        "unit_title": "How we express ourselves",
        "topic": "Describing daily routines in Italian",
        "atl_skills": ["communication"],
        "cefr_target": "A2",
        "duration_minutes": 45,
    }
    data.update(overrides)
    return LessonInput(**data)


def _entries() -> list[CurriculumKnowledgeEntry]:
    return [
        CurriculumKnowledgeEntry(
            id="LV-KL-001",
            title="IB PYP Central Idea Requirement",
            content="Every PYP unit is organized around a central idea.",
            citations=["IB PYP: From Principles into Practice"],
            source_path="knowledge/education/curriculum_ib.yaml",
        )
    ]


def _base_plan() -> dict:
    return _deterministic_lesson_plan(_lesson(), _entries(), None)


class StubEngine:
    """Returns a canned ReasonResult; error='...' forces the fallback."""

    def __init__(self, content: str = "", model_used: str = "mock", error: str = ""):
        self.content = content
        self.model_used = model_used
        self.error = error
        self.calls: list[dict] = []

    async def reason(self, query, context=None, model=None, default_model=None, system_prompt=None, local_only=False, max_tokens=2000):
        self.calls.append({"query": query, "system_prompt": system_prompt})
        return ReasonResult(
            content=self.content,
            confidence=0.0 if self.error else 0.8,
            model_used=self.model_used,
            error=self.error,
        )


# --- targeted deterministic branches ----------------------------------------


def test_song_revision_rewrites_the_warmup():
    plan = _base_plan()
    revised = _apply_deterministic_revision(plan, "Can you add a song to the warmup?")
    warmup = revised["lesson_structure"]["warmup"]
    assert warmup["activity"] == "Song and movement vocabulary hook"
    assert "song" in warmup["instructions"].lower()


def test_song_revision_preserves_every_other_section():
    plan = _base_plan()
    revised = _apply_deterministic_revision(plan, "add a song to the hook")
    for phase in ("main_activity", "guided_practice", "independent_work", "wrapup"):
        assert revised["lesson_structure"][phase] == plan["lesson_structure"][phase]
    # duration of the revised phase itself is also untouched
    assert revised["lesson_structure"]["warmup"]["duration"] == plan["lesson_structure"]["warmup"]["duration"]
    for key in ("learning_objectives", "materials", "differentiation", "assessment"):
        assert revised[key] == plan[key]


def test_visual_revision_adds_cue_cards_and_foundation_support():
    plan = _base_plan()
    revised = _apply_deterministic_revision(plan, "Add more visual supports please")
    assert "visual cue cards" in revised["materials"]
    assert "visual" in revised["differentiation"]["foundation"]["modifications"].lower()


def test_visual_revision_does_not_duplicate_cue_cards():
    plan = _base_plan()
    once = _apply_deterministic_revision(plan, "more visual scaffolds")
    twice = _apply_deterministic_revision(once, "even more visual scaffolds")
    assert twice["materials"].count("visual cue cards") == 1


def test_harder_extension_revision_targets_only_the_extension_tier():
    plan = _base_plan()
    revised = _apply_deterministic_revision(plan, "Make the extension tier harder")
    assert revised["differentiation"]["extension"]["challenges"] != plan["differentiation"]["extension"].get("challenges")
    assert revised["differentiation"]["foundation"] == plan["differentiation"]["foundation"]
    assert revised["differentiation"]["core"] == plan["differentiation"]["core"]
    assert revised["lesson_structure"] == plan["lesson_structure"]


# --- unknown revisions preserve the plan ------------------------------------


def test_unrecognized_revision_preserves_plan_and_records_the_request():
    """'Make the warmup shorter' has no targeted branch (only song+warmup
    does) — current behavior is: change nothing, log the request in
    teacher_notes so the teacher sees it was heard, not silently dropped."""
    plan = _base_plan()
    request = "Make the warmup shorter"
    revised = _apply_deterministic_revision(plan, request)
    assert revised["lesson_structure"] == plan["lesson_structure"]
    assert revised["materials"] == plan["materials"]
    assert revised["differentiation"] == plan["differentiation"]
    assert f"Revision request to consider: {request}" in revised["teacher_notes"]


def test_revision_never_mutates_the_input_plan():
    plan = _base_plan()
    snapshot = json.loads(json.dumps(plan))
    _apply_deterministic_revision(plan, "add a song to the warmup")
    _apply_deterministic_revision(plan, "more visuals")
    _apply_deterministic_revision(plan, "something unrecognized entirely")
    assert plan == snapshot


# --- multi-revision compounding ---------------------------------------------


def test_two_sequential_revisions_compound():
    plan = _base_plan()
    step1 = _apply_deterministic_revision(plan, "add a song to the warmup")
    step2 = _apply_deterministic_revision(step1, "add visual supports")
    assert step2["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    assert "visual cue cards" in step2["materials"]


def test_three_sequential_revisions_compound_and_preserve_the_rest():
    plan = _base_plan()
    step1 = _apply_deterministic_revision(plan, "add a song to the warmup")
    step2 = _apply_deterministic_revision(step1, "add visual supports")
    # NB: the branch matches the substring "challenge" — "challenging"
    # would NOT match (no trailing 'e'); "harder" matches via "hard".
    step3 = _apply_deterministic_revision(step2, "make the extension harder")
    assert step3["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    assert "visual cue cards" in step3["materials"]
    assert "follow-up question" in step3["differentiation"]["extension"]["challenges"]
    # everything no revision touched is still the original
    for phase in ("main_activity", "guided_practice", "independent_work", "wrapup"):
        assert step3["lesson_structure"][phase] == plan["lesson_structure"][phase]
    assert step3["learning_objectives"] == plan["learning_objectives"]
    assert step3["assessment"] == plan["assessment"]


# --- privacy invariant ------------------------------------------------------


def test_deterministic_revision_branches_introduce_no_student_names():
    plan = _base_plan()
    for request in (
        "add a song to the warmup",
        "more visual supports",
        "make the extension harder",
        "make the warmup shorter",
    ):
        revised = _apply_deterministic_revision(plan, request)
        # must not raise: no roster name anywhere in the revised plan
        _validate_lesson_plan_safety(revised, ROSTER_NAMES)


def test_revision_text_naming_a_student_is_caught_by_the_safety_validator():
    """A revision request that names a student falls into the teacher_notes
    branch, which copies the request verbatim into the plan. The safety
    validator is the layer that must catch that before the plan is shared —
    this pins that it does when given the roster."""
    plan = _base_plan()
    revised = _apply_deterministic_revision(plan, "Give Marco an easier version of this task")
    with pytest.raises(ValueError, match="student_name_in_lesson_plan"):
        _validate_lesson_plan_safety(revised, ROSTER_NAMES)


# --- full artifact path, no model needed ------------------------------------


def test_artifact_revision_falls_back_deterministically_without_a_model():
    result = asyncio.run(
        revise_lesson_plan_artifact(
            _lesson(),
            _base_plan(),
            "add a song to the warmup",
            engine=StubEngine(error="connection_refused"),
            curriculum_entries=_entries(),
        )
    )
    assert result.generation_status == "template_fallback"
    assert result.plan["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    assert result.html and result.print_html and result.markdown


def test_artifact_revision_uses_engine_output_when_it_is_a_valid_plan():
    revised_plan = _apply_deterministic_revision(_base_plan(), "add a song to the warmup")
    engine = StubEngine(content=json.dumps(revised_plan))
    result = asyncio.run(
        revise_lesson_plan_artifact(
            _lesson(),
            _base_plan(),
            "add a song to the warmup",
            engine=engine,
            curriculum_entries=_entries(),
        )
    )
    assert result.generation_status == "revised"
    assert result.plan["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    # the engine was actually consulted, with the revision system prompt
    assert engine.calls and "revise" in (engine.calls[0]["system_prompt"] or "").lower()


def test_artifact_revision_requires_revision_text():
    with pytest.raises(ValueError, match="revision_text_required"):
        asyncio.run(
            revise_lesson_plan_artifact(
                _lesson(), _base_plan(), "   ", engine=StubEngine(), curriculum_entries=_entries()
            )
        )


def test_artifact_revision_requires_curriculum_knowledge():
    with pytest.raises(LookupError, match="missing_curriculum_knowledge"):
        asyncio.run(
            revise_lesson_plan_artifact(
                _lesson(), _base_plan(), "add a song", engine=StubEngine(), curriculum_entries=[]
            )
        )


# --- live model (optional) --------------------------------------------------


@pytest.mark.skipif(not ollama_reachable(), reason="local Ollama not reachable")
def test_live_model_revision_returns_a_complete_rendered_plan():
    """End-to-end wiring with a real local model. Output content varies, so
    this asserts structure + honesty of generation_status, not wording."""
    result = asyncio.run(
        revise_lesson_plan_artifact(
            _lesson(),
            _base_plan(),
            "add a song to the warmup",
            curriculum_entries=_entries(),
        )
    )
    assert result.generation_status in ("revised", "template_fallback")
    for key in ("lesson_structure", "differentiation", "materials", "teacher_notes"):
        assert key in result.plan
    assert result.html and result.markdown
