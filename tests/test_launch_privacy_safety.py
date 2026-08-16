"""Rung 3 — Privacy & Safety: student data never leaves, GIR gates delivery, no fabrication.

SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md §3

These tests determine whether the product is safe to use with real
children's data. If any fail, the launch doesn't happen.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("LV_AUTH_MODE", "off")


# ─── 3.1 Student data never leaves the machine ───────────────────────────────


def test_student_pii_never_sent_to_external_model(monkeypatch):
    """Any query containing student name/ID routes local. Never external.

    The model_gate + exit_gates + privacy module form a layered defense.
    """
    from src.lingua_viva.exit_gates import ExitGate, ExitRequest

    gate = ExitGate()

    # A request carrying student IDs must be blocked for external reasoning
    request = ExitRequest(
        surface="reasoning",
        destination="openai/gpt-4",
        payload_text="Tell me about Marco's reading level",
        student_ids=("student-marco",),
        student_names=("Marco",),
    )
    decision = gate.check(request)
    assert not decision.allowed, (
        "EXIT GATE FAILED: student data was allowed to leave the machine"
    )
    assert "student_data" in decision.blocked_reason


def test_observation_content_local_only():
    """Observation text is never sent to cloud models.

    The exit gate must block any attempt to send observation content externally.
    """
    from src.lingua_viva.exit_gates import ExitGate, ExitRequest

    gate = ExitGate()

    # An observation transcript containing student details
    request = ExitRequest(
        surface="reasoning",
        destination="groq/llama-3.1-70b",
        payload_text="Marco showed strong engagement with peer reading activity today. His confidence has improved since last week.",
        student_ids=("student-marco",),
        student_names=("Marco",),
    )
    decision = gate.check(request)
    assert not decision.allowed, (
        "EXIT GATE FAILED: observation content was allowed to reach external model"
    )


def test_parent_report_local_only():
    """Parent report generation is entirely local.

    The exit gate must block any attempt to send parent report content externally.
    """
    from src.lingua_viva.exit_gates import ExitGate, ExitRequest

    gate = ExitGate()

    request = ExitRequest(
        surface="reasoning",
        destination="openai/gpt-4",
        payload_text="Generate a parent-friendly summary of Marco's progress in reading this term.",
        student_ids=("student-marco",),
        student_names=("Marco",),
        metadata={"local_only": True},
    )
    decision = gate.check(request)
    assert not decision.allowed


def test_exit_gate_blocks_student_data_in_tts():
    """Exit gate refuses to transmit content with student identifiers to TTS."""
    from src.lingua_viva.exit_gates import ExitGate, ExitRequest

    gate = ExitGate()

    # TTS should not speak text containing student names
    request = ExitRequest(
        surface="tts",
        destination="rime",
        payload_text="Marco is making good progress in reading comprehension.",
        student_names=("Marco",),
    )
    decision = gate.check(request)
    assert not decision.allowed, (
        "EXIT GATE FAILED: student name would have been sent to TTS"
    )


def test_exit_gate_allows_clean_external_reasoning():
    """Curriculum-only questions (no student data) ARE allowed to go external."""
    from src.lingua_viva.exit_gates import ExitGate, ExitRequest

    gate = ExitGate()

    request = ExitRequest(
        surface="reasoning",
        destination="openai/gpt-4",
        payload_text="What are best practices for teaching reading comprehension to grade 3 students?",
        student_ids=(),
        student_names=(),
    )
    decision = gate.check(request)
    assert decision.allowed, (
        "Clean curriculum question should be allowed externally"
    )


def test_model_gate_fail_closed_no_allowlist(monkeypatch):
    """When no local models are available and allowlist is empty,
    is_provably_local_model must return False for unknown models — fail closed.
    
    Note: models that are actually installed in Ollama will still return True
    (that's correct — they ARE provably local). We test with a model name
    that definitely doesn't exist.
    """
    from src.lingua_viva.model_gate import clear_model_gate_cache, is_provably_local_model

    monkeypatch.delenv("LV_LOCAL_MODEL_ALLOWLIST", raising=False)
    clear_model_gate_cache()

    # A made-up model name should NOT be provably local
    assert not is_provably_local_model("nonexistent-model-xyz-99")
    assert not is_provably_local_model("fake/model:latest")

    # External models must never be provably local, regardless of allowlist
    assert not is_provably_local_model("openai/gpt-4")
    assert not is_provably_local_model("groq/llama-3.1-70b")
    assert not is_provably_local_model("mistral/mistral-large")

    # Restore for other tests
    monkeypatch.setenv("LV_LOCAL_MODEL_ALLOWLIST", "test-model")
    clear_model_gate_cache()


# ─── 3.2 No fabricated content presented as fact ──────────────────────────────


def test_no_fabricated_observations(tmp_path):
    """Student lens only contains teacher-submitted observations, never model-generated.

    The store must not invent observations — only store what teachers submit.
    """
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "test_no_fab.db"
    store = StudentLensStore(db_path=db_path)
    try:
        student_id = store.create_lens(display_name="Fabrication Test")

        # Record exactly one observation
        pipeline = ObservationCapturePipeline(store=store)
        pipeline.capture(
            student_id=student_id,
            teacher_id="teacher-1",
            raw_transcript="Student read aloud fluently today.",
            template_type="general",
        )

        lens = store.export_lens(student_id)
        observations = lens.get("observations") or []

        # Exactly one observation should exist — the one we submitted
        assert len(observations) == 1
        assert observations[0]["raw_transcript"] == "Student read aloud fluently today."
        # Must have been marked as teacher-submitted
        assert observations[0]["teacher_id"] == "teacher-1"
    finally:
        store.close()


# ─── 3.3 Access control & demo fallback ──────────────────────────────────────


def test_demo_student_fallback_removed():
    """POST /api/parents/recommendation with unknown student_id returns 404,
    not demo data."""
    from httpx import ASGITransport, AsyncClient

    from src.web import app

    async def _check():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/parents/recommendation",
                json={"student_id": "nonexistent-student-xyz"},
            )
            # Must be 404 (student not found), NOT 200 with demo content
            assert resp.status_code == 404, (
                f"Expected 404 for unknown student, got {resp.status_code}: {resp.text[:200]}"
            )
            body = resp.json()
            assert "error" in body

    import asyncio
    asyncio.run(_check())


def test_observe_capture_rejects_empty_student_id():
    """POST /api/observe/capture with empty student_id returns 400."""
    from httpx import ASGITransport, AsyncClient

    from src.web import app

    async def _check():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/observe/capture",
                json={
                    "student_id": "",
                    "transcript": "Test observation",
                },
            )
            assert resp.status_code == 400, (
                f"Expected 400 for empty student_id, got {resp.status_code}"
            )

    import asyncio
    asyncio.run(_check())


def test_no_cross_student_data_leak(tmp_path):
    """Query about student A never returns data from student B."""
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "test_isolation.db"
    store = StudentLensStore(db_path=db_path)
    try:
        id_a = store.create_lens(display_name="Student A")
        id_b = store.create_lens(display_name="Student B")

        pipeline = ObservationCapturePipeline(store=store)
        pipeline.capture(
            student_id=id_a,
            teacher_id="teacher-1",
            raw_transcript="Student A loves mathematics",
            template_type="general",
        )
        pipeline.capture(
            student_id=id_b,
            teacher_id="teacher-1",
            raw_transcript="Student B struggles with reading",
            template_type="general",
        )

        lens_a = store.export_lens(id_a)
        lens_b = store.export_lens(id_b)

        # A's observations must not contain B's data
        for obs in lens_a.get("observations", []):
            assert "Student B" not in obs["raw_transcript"]
            assert obs["student_id"] == id_a

        # B's observations must not contain A's data
        for obs in lens_b.get("observations", []):
            assert "Student A" not in obs["raw_transcript"]
            assert obs["student_id"] == id_b
    finally:
        store.close()


# ─── 3.4 PDF scoping rules ───────────────────────────────────────────────────


def test_student_lens_pdf_family_scope_excludes_personal_context(tmp_path):
    """Family-scoped PDF excludes Personal Context."""
    from src.education.student_lens import StudentLensStore, support_profile_for_audience

    db_path = tmp_path / "test_scope.db"
    store = StudentLensStore(db_path=db_path)
    try:
        student_id = store.create_lens(display_name="Scope Test")

        # Simulate a support profile with personal_context
        profile = {
            "schema_version": 2,
            "categories": {
                "academic_support": {
                    "needs": [{"text": "Needs help with reading fluency"}],
                    "strengths": [],
                    "strategies_worked": [],
                    "strategies_not_worked": [],
                    "evidence": [],
                    "open_questions": [],
                },
                "personal_context": {
                    "needs": [{"text": "Family going through separation"}],
                    "strengths": [],
                    "strategies_worked": [],
                    "strategies_not_worked": [],
                    "evidence": [],
                    "open_questions": [],
                },
            },
        }

        # Family view must exclude personal_context
        family_view = support_profile_for_audience(profile, "family")
        assert "personal_context" not in family_view.get("categories", {}), (
            "PRIVACY FAILURE: personal_context leaked to family view"
        )

        # Teacher view must also exclude personal_context
        teacher_view = support_profile_for_audience(profile, "teacher")
        assert "personal_context" not in teacher_view.get("categories", {}), (
            "PRIVACY FAILURE: personal_context leaked to teacher view"
        )

        # HR view SHOULD include personal_context
        hr_view = support_profile_for_audience(profile, "hr")
        assert "personal_context" in hr_view.get("categories", {}), (
            "HR view should include personal_context"
        )
    finally:
        store.close()
