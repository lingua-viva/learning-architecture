from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    LESSON_PLAN_SYSTEM_PROMPT,
    CurriculumKnowledgeEntry,
    LessonPlanArtifactResult,
    generate_lesson_plan_artifact,
    load_generated_lesson_plan,
    parse_lesson_plan_json,
    render_lesson_plan_bundle,
    revise_lesson_plan_artifact,
    store_generated_lesson_plan,
)
from src.lingua_viva.reasoning import ReasonResult
from src.web import app


def _lesson() -> LessonInput:
    return LessonInput(
        ib_programme="PYP",
        subject="Italian",
        unit_title="Grade 3",
        topic="family vocabulary",
        atl_skills=["communication"],
        cefr_target="A2",
        duration_minutes=45,
        language_of_instruction="en",
    )


def _entry() -> CurriculumKnowledgeEntry:
    return CurriculumKnowledgeEntry(
        id="LV-KL-031",
        title="IB PYP Italian Vocabulary Lesson Design",
        content="Vocabulary instruction connects oral rehearsal, visuals, and meaningful exchanges.",
        citations=["IBO (2018). Primary Years Programme: From Principles into Practice."],
        source_path="knowledge/education/curriculum_ib.yaml",
    )


def _plan_json(**overrides) -> dict:
    data = {
        "subject": "Italian",
        "grade": "Grade 3",
        "date": "2026-08-22",
        "duration_minutes": 45,
        "teacher_name": "Claudia",
        "topic": "family vocabulary",
        "curriculum_standard": "LV-KL-031: IB PYP Italian Vocabulary Lesson Design",
        "curriculum_citations": ["LV-KL-031"],
        "learning_objectives": [
            "Use family words in a short oral exchange.",
            "Match family words to visual examples.",
            "Show understanding with an exit response.",
        ],
        "materials": ["family picture cards", "word bank"],
        "lesson_structure": {
            "warmup": {"duration": "5 min", "activity": "Picture hook", "instructions": "Name family members with gestures."},
            "main_activity": {"duration": "20 min", "activity": "Pair exchange", "instructions": "Ask and answer using family words."},
            "guided_practice": {"duration": "10 min", "activity": "Teacher check", "instructions": "Rehearse sentence frames."},
            "independent_work": {"duration": "5 min", "activity": "Mini card", "instructions": "Draw and label one family member."},
            "wrapup": {"duration": "5 min", "activity": "Exit phrase", "instructions": "Say one accurate phrase."},
        },
        "differentiation": {
            "foundation": {"description": "Use visuals and word bank.", "modifications": "Point, repeat, then say one phrase."},
            "core": {"description": "Use sentence frames.", "activities": "Complete a partner exchange."},
            "extension": {"description": "Add detail.", "challenges": "Create a new question."},
        },
        "assessment": "Listen for accurate vocabulary during exit phrases.",
        "teacher_notes": "Note which words need reteaching.",
    }
    data.update(overrides)
    return data


class FakeEngine:
    def __init__(self, responses: list[str] | None = None, model_used: str = "mock"):
        self.responses = list(responses or [json.dumps(_plan_json())])
        self.model_used = model_used
        self.calls: list[dict] = []

    async def reason(self, query, context=None, model=None, default_model=None, system_prompt=None, local_only=False, max_tokens=2000):
        self.calls.append({"query": query, "system_prompt": system_prompt, "max_tokens": max_tokens})
        return ReasonResult(content=self.responses.pop(0), confidence=0.8, model_used=self.model_used)


def test_parse_lesson_plan_json_accepts_fenced_json():
    assert parse_lesson_plan_json("```json\n{\"topic\":\"family\"}\n```") == {"topic": "family"}


def test_generate_lesson_plan_artifact_renders_structured_html_without_student_names():
    engine = FakeEngine()
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            teacher_id="teacher-a",
            teacher_name="Claudia",
            engine=engine,
            curriculum_entries=[_entry()],
            tier_groups={"foundational": ["student-a"], "on_track": ["student-b"], "extended": []},
            roster_names=["Student A", "Student B"],
            individual_support=[],
        )
    )

    assert engine.calls[0]["system_prompt"] == LESSON_PLAN_SYSTEM_PROMPT
    assert "Student A" not in engine.calls[0]["query"]
    assert result.plan["topic"] == "family vocabulary"
    assert result.generation_status == "generated"
    assert "Learning Objectives" in result.html
    assert "Foundation" in result.print_html
    assert "Student A" not in result.markdown


def test_invalid_model_json_falls_back_to_structured_plan():
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            engine=FakeEngine(["not json"]),
            curriculum_entries=[_entry()],
            tier_groups={"foundational": [], "on_track": [], "extended": []},
            roster_names=[],
            individual_support=[],
        )
    )

    assert result.generation_status == "template_fallback"
    assert result.plan["curriculum_standard"].startswith("LV-KL-031")
    assert result.plan["lesson_structure"]["warmup"]["activity"]


def test_missing_curriculum_knowledge_is_honest_refusal():
    try:
        asyncio.run(
            generate_lesson_plan_artifact(
                _lesson(),
                engine=FakeEngine(),
                curriculum_entries=[],
                tier_groups={"foundational": [], "on_track": [], "extended": []},
                roster_names=[],
                individual_support=[],
            )
        )
    except LookupError as exc:
        assert str(exc) == "missing_curriculum_knowledge"
    else:
        raise AssertionError("expected missing curriculum refusal")


def test_revision_preserves_existing_plan_and_updates_warmup():
    original = _plan_json()
    revised = _plan_json()
    revised["lesson_structure"] = dict(revised["lesson_structure"])
    revised["lesson_structure"]["warmup"] = {
        "duration": "7 min",
        "activity": "Song hook",
        "instructions": "Sing a short family vocabulary chant.",
    }
    result = asyncio.run(
        revise_lesson_plan_artifact(
            _lesson(),
            original,
            "Add a song activity to the warm-up",
            engine=FakeEngine([json.dumps(revised)]),
            curriculum_entries=[_entry()],
        )
    )

    assert result.plan["lesson_structure"]["warmup"]["activity"] == "Song hook"
    assert result.plan["lesson_structure"]["main_activity"] == original["lesson_structure"]["main_activity"]


def test_generated_lesson_plans_are_saved_as_immutable_snapshots(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GENERATED_LESSON_PLANS_DIR", str(tmp_path / "plans"))
    first_plan = _plan_json()
    second_plan = _plan_json()
    second_plan["lesson_structure"] = dict(second_plan["lesson_structure"])
    second_plan["lesson_structure"]["warmup"] = {
        "duration": "7 min",
        "activity": "Song hook",
        "instructions": "Sing a short family vocabulary chant.",
    }

    first_path = store_generated_lesson_plan(
        _lesson(),
        LessonPlanArtifactResult(
            plan=first_plan,
            html="",
            print_html="",
            markdown="",
            generation_status="generated",
            curriculum_sources=[],
            generated_at="2026-08-22T00:00:00Z",
        ),
        teacher_id="teacher-a",
    )
    second_path = store_generated_lesson_plan(
        _lesson(),
        LessonPlanArtifactResult(
            plan=second_plan,
            html="",
            print_html="",
            markdown="",
            generation_status="generated",
            curriculum_sources=[],
            generated_at="2026-08-22T00:01:00Z",
        ),
        teacher_id="teacher-a",
    )

    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()
    assert len(list((tmp_path / "plans").glob("*.json"))) == 2
    latest = load_generated_lesson_plan(_lesson(), "teacher-a")
    assert latest["plan"]["lesson_structure"]["warmup"]["activity"] == "Song hook"


def test_render_bundle_contains_printable_sections():
    bundle = render_lesson_plan_bundle(_plan_json())
    assert "Lesson Structure" in bundle["markdown"]
    assert "<!doctype html>" in bundle["print_html"]
    assert "Differentiation" in bundle["html"]


def test_lesson_plan_routes_generate_revise_preview_print_without_model_on_print(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_GENERATED_LESSON_PLANS_DIR", str(tmp_path / "plans"))

    calls = []

    class RouteEngine(FakeEngine):
        async def reason(self, *args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                content = json.dumps(_plan_json())
            else:
                revised = _plan_json()
                revised["lesson_structure"]["warmup"]["activity"] = "Song hook"
                content = json.dumps(revised)
            return ReasonResult(content=content, confidence=0.8, model_used="mock")

    monkeypatch.setattr("src.lingua_viva.reasoning.ReasoningEngine", RouteEngine)
    payload = {
        "teacher_id": "teacher-a",
        "teacher_name": "Claudia",
        "lesson": {
            "ib_programme": "PYP",
            "subject": "Italian",
            "unit_title": "Grade 3",
            "topic": "family vocabulary",
            "atl_skills": ["communication"],
            "cefr_target": "A2",
            "duration_minutes": 45,
        },
    }

    with TestClient(app) as client:
        generated = client.post("/api/lesson-plans/generate", json=payload)
        assert generated.status_code == 200
        assert generated.json()["plan"]["topic"] == "family vocabulary"

        revised = client.post("/api/lesson-plans/revise", json={**payload, "revision_text": "Add a song activity to the warm-up"})
        assert revised.status_code == 200
        assert revised.json()["plan"]["lesson_structure"]["warmup"]["activity"] == "Song hook"

        preview = client.post("/api/lesson-plans/preview", json=payload)
        assert preview.status_code == 200
        assert preview.json()["plan"]["lesson_structure"]["warmup"]["activity"] == "Song hook"

        before_print_calls = len(calls)
        printed = client.post("/api/lesson-plans/print", json=payload)
        assert printed.status_code == 200
        body = printed.json()

    assert len(calls) == before_print_calls
    assert Path(body["artifact"]["file_path"]).read_bytes().startswith(b"%PDF")
    assert body["deliverable"]["type"] == "cohort_lesson_plan"
    assert load_generated_lesson_plan(_lesson(), "teacher-a")["plan"]["lesson_structure"]["warmup"]["activity"] == "Song hook"


# --- P1-DOC-004 (SPEC_LV_IMPROVEMENT_CHECKLIST_2026-08-22): IB PYP framing ---


def test_ib_fields_default_honestly_when_model_omits_them():
    """Model returns the pre-enrichment schema → plan still carries the IB
    framing: ATL from the TEACHER'S lesson input (never invented), safe
    defaults elsewhere, empty cross-curricular stays empty."""
    engine = FakeEngine()  # _plan_json() has no IB fields
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            engine=engine,
            tier_groups={"foundational": [], "on_track": [], "extended": []},
            roster_names=[],
            curriculum_entries=[_entry()],
        )
    )
    plan = result.plan
    assert plan["atl_skills"] == ["communication"]
    assert plan["central_idea"]
    assert len(plan["lines_of_inquiry"]) == 3
    assert plan["learner_profile_attributes"][0]["attribute"] == "Communicators"
    assert plan["cross_curricular_connections"] == []
    assert plan["success_criteria"] == []


def test_hallucinated_learner_profile_attribute_never_prints():
    """Only the 10 official IB attributes survive normalization."""
    engine = FakeEngine([
        json.dumps(
            _plan_json(
                learner_profile_attributes=[
                    {"attribute": "Synergizers", "connection": "made up"},
                    {"attribute": "risk-takers", "connection": "Students try new phrases aloud."},
                ]
            )
        )
    ])
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            engine=engine,
            tier_groups={"foundational": [], "on_track": [], "extended": []},
            roster_names=[],
            curriculum_entries=[_entry()],
        )
    )
    attributes = [item["attribute"] for item in result.plan["learner_profile_attributes"]]
    assert attributes == ["Risk-takers"]
    assert "Synergizers" not in result.html


def test_model_ib_fields_pass_through_and_render():
    engine = FakeEngine([
        json.dumps(
            _plan_json(
                central_idea="Families shape how we express who we are.",
                lines_of_inquiry=["Words for the people close to us"],
                cross_curricular_connections=["Art: draw a family portrait and label it"],
                success_criteria=["Students can name four family members in Italian."],
            )
        )
    ])
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            engine=engine,
            tier_groups={"foundational": [], "on_track": [], "extended": []},
            roster_names=[],
            curriculum_entries=[_entry()],
        )
    )
    for surface in (result.html, result.markdown):
        assert "Families shape how we express who we are." in surface
        assert "Art: draw a family portrait and label it" in surface
        assert "Students can name four family members in Italian." in surface


def test_rendered_plan_has_all_enriched_sections():
    engine = FakeEngine()
    result = asyncio.run(
        generate_lesson_plan_artifact(
            _lesson(),
            engine=engine,
            tier_groups={"foundational": [], "on_track": [], "extended": []},
            roster_names=[],
            curriculum_entries=[_entry()],
        )
    )
    for surface in (result.html, result.markdown):
        assert "IB PYP Framing" in surface
        assert "Central idea" in surface
        assert "Lines of inquiry" in surface
        assert "Approaches to Learning" in surface
        assert "Learner Profile" in surface
        assert "Cross-Curricular Connections" in surface
        assert "Teacher Reflection (after the lesson)" in surface
    # materials render as a checklist
    assert "- [ ] family picture cards" in result.markdown
    assert 'class="checklist"' in result.html
    assert "Linked standard:" in result.html
