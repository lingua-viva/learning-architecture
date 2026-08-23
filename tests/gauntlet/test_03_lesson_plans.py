"""Gauntlet phase 3 — lesson plan generation, grounding, rendering, revision.

No LLM: the fallback path is forced with an erroring stub engine, and the
"model produced a plan" path is exercised with a stub returning valid JSON.
Roster names come from the labeled corpus — the safety validator must keep
every one of them out of every rendered artifact.
"""

from __future__ import annotations

import json

import pytest

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    IB_LEARNER_PROFILE_ATTRIBUTES,
    _apply_deterministic_revision,
    _deterministic_lesson_plan,
    generate_lesson_plan_artifact,
    load_curriculum_knowledge,
    revise_lesson_plan_artifact,
)
from src.lingua_viva.reasoning import ReasonResult

from .conftest import EXPECTED_STUDENTS, run

ATL_SKILLS = ["communication", "self-management"]


def _lesson(**overrides) -> LessonInput:
    data = {
        "ib_programme": "PYP",
        "subject": "language",
        "unit_title": "How we express ourselves",
        "topic": "Describing daily routines in Italian",
        "atl_skills": list(ATL_SKILLS),
        "cefr_target": "A2",
        "duration_minutes": 45,
    }
    data.update(overrides)
    return LessonInput(**data)


class StubEngine:
    def __init__(self, content: str = "", model_used: str = "mock", error: str = ""):
        self.content = content
        self.model_used = model_used
        self.error = error

    async def reason(self, query, context=None, model=None, default_model=None,
                     system_prompt=None, local_only=False, max_tokens=2000):
        return ReasonResult(
            content=self.content,
            confidence=0.0 if self.error else 0.8,
            model_used=self.model_used,
            error=self.error,
        )


def _entries():
    entries = load_curriculum_knowledge("language", "Describing daily routines in Italian")
    assert entries, "curriculum knowledge loader returned nothing"
    return entries


def _tier_groups(gauntlet_env):
    ids = list(gauntlet_env["student_ids"].values())
    return {"foundational": ids[:6], "on_track": ids[6:13], "extended": ids[13:]}


def _generate(gauntlet_env, engine, **overrides):
    kwargs = dict(
        teacher_id=gauntlet_env["teacher_id"],
        teacher_name="Ms. Rossi",
        engine=engine,
        tier_groups=_tier_groups(gauntlet_env),
        roster_names=list(EXPECTED_STUDENTS),
        curriculum_entries=_entries(),
    )
    kwargs.update(overrides)
    return run(generate_lesson_plan_artifact(_lesson(), **kwargs))


# --- generation without a model ----------------------------------------------


def test_no_model_yields_honest_template_fallback(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="connection_refused"))
    assert result.generation_status == "template_fallback"


def test_plan_has_all_five_lesson_phases(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="down"))
    structure = result.plan["lesson_structure"]
    for phase in ("warmup", "main_activity", "guided_practice", "independent_work", "wrapup"):
        assert structure[phase]["activity"].strip(), phase
        assert structure[phase]["instructions"].strip(), phase
        assert structure[phase]["duration"].strip(), phase


def test_plan_has_all_three_differentiation_tiers(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="down"))
    diff = result.plan["differentiation"]
    assert set(diff.keys()) == {"foundation", "core", "extension"}
    assert diff["foundation"]["modifications"].strip()
    assert diff["core"]["activities"].strip()
    assert diff["extension"]["challenges"].strip()


# --- curriculum grounding -----------------------------------------------------


def test_plan_cites_a_real_knowledge_entry(gauntlet_env):
    entries = _entries()
    result = _generate(gauntlet_env, StubEngine(error="down"), curriculum_entries=entries)
    entry_ids = {e.id for e in entries}
    standard_id = result.plan["curriculum_standard"].split(":")[0].strip()
    assert standard_id in entry_ids
    assert set(result.plan["curriculum_citations"]) & entry_ids


def test_result_reports_exactly_the_consulted_sources(gauntlet_env):
    entries = _entries()
    result = _generate(gauntlet_env, StubEngine(error="down"), curriculum_entries=entries)
    assert [s["id"] for s in result.curriculum_sources] == [e.id for e in entries]


def test_generation_without_curriculum_knowledge_refuses(gauntlet_env):
    with pytest.raises(LookupError, match="missing_curriculum_knowledge"):
        _generate(gauntlet_env, StubEngine(error="down"), curriculum_entries=[])


# --- ATL + learner profile grounding -----------------------------------------


def test_atl_skills_are_the_teachers_selection_verbatim(gauntlet_env):
    """ATL skills come from the lesson input (the teacher), never the model."""
    result = _generate(gauntlet_env, StubEngine(error="down"))
    assert result.plan["atl_skills"] == ATL_SKILLS


def test_learner_profile_attributes_are_official_ib_only(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="down"))
    attributes = result.plan["learner_profile_attributes"]
    assert attributes, "plan must carry at least one learner profile attribute"
    for item in attributes:
        assert item["attribute"] in IB_LEARNER_PROFILE_ATTRIBUTES, item


def test_hallucinated_learner_profile_attribute_is_stripped(gauntlet_env):
    """A model inventing 'Resilient' (not one of the official 10) must not
    print on a plan — normalization drops it, keeping only official ones."""
    fabricated = _deterministic_lesson_plan(_lesson(), _entries(), None)
    fabricated["learner_profile_attributes"] = [
        {"attribute": "Resilient", "connection": "made up"},
        {"attribute": "Caring", "connection": "supports peers in Italian"},
    ]
    result = _generate(gauntlet_env, StubEngine(content=json.dumps(fabricated)))
    assert result.generation_status == "generated"
    names = [a["attribute"] for a in result.plan["learner_profile_attributes"]]
    assert "Resilient" not in names
    assert "Caring" in names


# --- model-JSON path ----------------------------------------------------------


def test_valid_model_json_is_used_and_marked_generated(gauntlet_env):
    plan = _deterministic_lesson_plan(_lesson(), _entries(), None)
    result = _generate(gauntlet_env, StubEngine(content=json.dumps(plan)))
    assert result.generation_status == "generated"


def test_model_plan_naming_a_student_is_rejected_before_rendering(gauntlet_env):
    """If the model leaks a roster name into the plan, generation must fail
    loudly rather than render the name into a shareable artifact."""
    plan = _deterministic_lesson_plan(_lesson(), _entries(), None)
    plan["teacher_notes"] = "Give Marco Bianchi extra practice with routines."
    with pytest.raises(ValueError, match="student_name_in_lesson_plan"):
        _generate(gauntlet_env, StubEngine(content=json.dumps(plan)))


def test_model_plan_with_clinical_language_is_rejected(gauntlet_env):
    plan = _deterministic_lesson_plan(_lesson(), _entries(), None)
    plan["teacher_notes"] = "Informed by the diagnosis shared by the specialist."
    with pytest.raises(ValueError, match="unsafe_lesson_plan"):
        _generate(gauntlet_env, StubEngine(content=json.dumps(plan)))


# --- rendering ----------------------------------------------------------------


def test_all_three_renderings_are_produced(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="down"))
    assert result.html.strip()
    assert result.print_html.strip()
    assert result.markdown.strip()
    assert result.plan["topic"] in result.markdown


def test_no_roster_name_in_any_rendered_artifact(gauntlet_env):
    result = _generate(gauntlet_env, StubEngine(error="down"))
    for artifact in (result.html, result.print_html, result.markdown, json.dumps(result.plan)):
        for name in EXPECTED_STUDENTS:
            assert name not in artifact, name


# --- revision through the artifact path --------------------------------------


def test_revision_round_trip_keeps_grounding_and_stays_print_safe(gauntlet_env):
    base = _generate(gauntlet_env, StubEngine(error="down"))
    revised = run(
        revise_lesson_plan_artifact(
            _lesson(),
            base.plan,
            "add a song to the warmup",
            engine=StubEngine(error="down"),
            curriculum_entries=_entries(),
        )
    )
    assert revised.generation_status == "template_fallback"
    assert revised.plan["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    # grounding survives the revision
    assert revised.plan["curriculum_standard"] == base.plan["curriculum_standard"]
    # and the revised artifacts are still name-free
    for artifact in (revised.html, revised.print_html, revised.markdown):
        for name in EXPECTED_STUDENTS:
            assert name not in artifact, name


def test_sequential_deterministic_revisions_compound(gauntlet_env):
    plan = _generate(gauntlet_env, StubEngine(error="down")).plan
    step1 = _apply_deterministic_revision(plan, "add a song to the warmup")
    step2 = _apply_deterministic_revision(step1, "add more visual supports")
    assert step2["lesson_structure"]["warmup"]["activity"] == "Song and movement vocabulary hook"
    assert "visual cue cards" in step2["materials"]
    assert step2["learning_objectives"] == plan["learning_objectives"]
