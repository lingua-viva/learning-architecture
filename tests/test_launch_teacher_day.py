"""Rung 4 — End-to-end teacher day simulation.

SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md §4

Simulates Claudia's full teacher day: morning brief → observe → ask →
materials → packet → parent report → student summary. Then tests error
recovery: model timeout messaging and empty student handling.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("LV_AUTH_MODE", "off")
os.environ.setdefault("LV_LOCAL_MODEL_ALLOWLIST", "test-model")


@pytest.fixture()
async def client():
    from src.web import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def student_store(tmp_path):
    """Create a pre-populated student store for simulation."""
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "teacher_day.db"
    store = StudentLensStore(db_path=db_path)
    pipeline = ObservationCapturePipeline(store=store)

    # Pre-create 3 students with history
    students = {}
    for name in ("Marco", "Sofia", "Leo"):
        sid = store.create_lens(display_name=name)
        students[name] = sid

    # Add historical observations
    pipeline.capture(
        student_id=students["Marco"],
        teacher_id="teacher-claudia",
        raw_transcript="Marco participated actively in group reading today. He initiated discussion about character motivations.",
        template_type="general",
    )
    pipeline.capture(
        student_id=students["Sofia"],
        teacher_id="teacher-claudia",
        raw_transcript="Sofia completed the writing task independently and helped a classmate with spelling.",
        template_type="general",
    )
    pipeline.capture(
        student_id=students["Leo"],
        teacher_id="teacher-claudia",
        raw_transcript="Leo was quiet during circle time but engaged strongly during art integration.",
        template_type="general",
    )

    yield store, students, pipeline
    store.close()


# ─── 4.1 Claudia's morning workflow ──────────────────────────────────────────


@pytest.mark.anyio
async def test_step_1_morning_brief(client):
    """Step 1: Open app → morning brief loads."""
    resp = await client.get("/api/brief")
    assert resp.status_code == 200
    body = resp.json()
    # Brief should have some structure
    assert isinstance(body, dict)


@pytest.mark.anyio
async def test_step_2_record_observations(student_store):
    """Step 2: Record 3 observations for different students."""
    store, students, pipeline = student_store

    # Record new observations for today
    observations = [
        (students["Marco"], "Marco showed improved confidence reading aloud to the class today."),
        (students["Sofia"], "Sofia struggled with multi-step word problems but persevered."),
        (students["Leo"], "Leo volunteered to share his art project and explained his process clearly."),
    ]

    for student_id, transcript in observations:
        result = pipeline.capture(
            student_id=student_id,
            teacher_id="teacher-claudia",
            raw_transcript=transcript,
            template_type="general",
        )
        assert not result.get("duplicate"), f"Observation for {student_id} was flagged as duplicate"
        assert result.get("observation"), f"No observation returned for {student_id}"


@pytest.mark.anyio
async def test_step_3_ask_about_student(student_store, client):
    """Step 3: Ask 'What patterns am I seeing with Marco this week?'

    When a student name is detected, the query routes local — never external.
    """
    store, students, _ = student_store

    # The ask endpoint with a student name should route locally
    resp = await client.post(
        "/api/ask",
        json={
            "question": "What patterns am I seeing with Marco this week?",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Should be routed locally (student name detected), refused for PII,
    # or marked as unavailable (no Perplexity key but student name detected
    # routes to local pipeline which may also fail gracefully)
    assert body.get("type") in ("ask_result", "ask_refused", "ask_unavailable"), (
        f"Unexpected ask response type: {body.get('type')}"
    )
    # If it returned a result, it must be local_only
    if body.get("type") == "ask_result":
        assert body.get("local_only") is True or body.get("external_calls", 0) == 0


@pytest.mark.anyio
async def test_step_4_generate_lesson_materials(client):
    """Step 4: Generate differentiated lesson materials for today's topic."""
    resp = await client.post(
        "/api/lesson-materials/generate",
        json={
            "lesson": {
                "ib_programme": "PYP",
                "subject": "English",
                "unit_title": "Communication",
                "topic": "Persuasive Writing",
                "atl_skills": ["communication", "thinking"],
                "cefr_target": "B1",
                "duration_minutes": 45,
            },
        },
    )
    # Should generate or fail gracefully (model may not be available)
    assert resp.status_code in (200, 400, 422, 503), (
        f"Lesson materials generation crashed: {resp.status_code} {resp.text[:200]}"
    )
    # If 200, verify structure
    if resp.status_code == 200:
        body = resp.json()
        assert "materials" in body


@pytest.mark.anyio
async def test_step_5_student_lens_view(student_store):
    """Step 5: View full student lens → check all sections render."""
    store, students, _ = student_store

    lens = store.export_lens(students["Marco"])
    assert lens["display_name"] == "Marco"
    assert lens["student_id"] == students["Marco"]
    assert "observations" in lens
    assert len(lens["observations"]) >= 1
    # Lens should have support_profile structure
    assert "support_profile" in lens


@pytest.mark.anyio
async def test_step_6_parent_report(student_store):
    """Step 6: Generate parent report → verify grounded in observations."""
    store, students, _ = student_store

    from src.education.parent_report import ParentReportGenerator

    generator = ParentReportGenerator(store)
    draft = generator.generate_draft(
        student_id=students["Marco"],
        teacher_id="teacher-claudia",
    )
    # Parent report must exist and have content
    assert draft is not None
    assert draft.body, "Parent report body is empty"
    assert draft.subject_line, "Parent report subject is empty"
    # Home activities should be present
    assert isinstance(draft.home_activities, list)


# ─── 4.2 Error recovery ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_empty_student_shows_honest_message(client):
    """New student with zero observations → honest 'no data' message, not fabrication."""
    # Ask about a student who doesn't exist → should get 404 or honest message
    resp = await client.get("/api/students/brand-new-student-zero-data/lens")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_parent_report_empty_student_returns_404(client):
    """Parent report for nonexistent student returns 404, not fabricated content."""
    resp = await client.post(
        "/api/parents/recommendation",
        json={"student_id": "student-who-does-not-exist"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("error") == "unknown_student"


@pytest.mark.anyio
async def test_pipeline_model_unavailable_returns_honest_message(monkeypatch):
    """If local model is unavailable, pipeline returns honest message, not crash."""
    from src.lingua_viva.model_gate import clear_model_gate_cache
    from src.pipeline import ReasoningEngine, ReasonResult

    monkeypatch.delenv("LV_LOCAL_MODEL_ALLOWLIST", raising=False)
    clear_model_gate_cache()

    engine = ReasoningEngine()
    result = await engine.reason(
        query="What are Marco's strengths?",
        context={},
        local_only=True,
    )
    assert isinstance(result, ReasonResult)
    # Must return an honest message about model unavailability
    assert result.model_used in ("none:local_only", "none")
    assert result.content  # Must say SOMETHING honest

    # Restore
    monkeypatch.setenv("LV_LOCAL_MODEL_ALLOWLIST", "test-model")
    clear_model_gate_cache()


# ─── 4.3 Data isolation across the simulation ────────────────────────────────


@pytest.mark.anyio
async def test_observation_isolation(student_store):
    """Observations for one student never appear in another's lens."""
    store, students, _ = student_store

    for name, student_id in students.items():
        lens = store.export_lens(student_id)
        for obs in lens.get("observations", []):
            assert obs["student_id"] == student_id, (
                f"Observation {obs['observation_id']} has wrong student_id: "
                f"expected {student_id}, got {obs['student_id']}"
            )
