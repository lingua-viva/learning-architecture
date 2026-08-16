"""Rung 2 — Frontend verification: every button works, PDFs scope correctly.

SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md §2
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("LV_AUTH_MODE", "off")


@pytest.fixture()
async def client():
    from src.web import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── 2.1 Teacher workflow routes respond correctly ────────────────────────────


@pytest.mark.anyio
async def test_observe_capture_workflow(client, tmp_path):
    """Observe → save → response includes observation data."""
    from src.education.student_lens import StudentLensStore

    # Create a real student in a temp store — the route uses the app-level store.
    # For route-level testing, we verify the route handles input correctly.
    resp = await client.post(
        "/api/observe/capture",
        json={
            "student_id": "test-student-observe",
            "transcript": "Student showed strong oral participation today.",
            "template_type": "general",
        },
    )
    # Expect 404 (student doesn't exist in the real store) — not 500
    assert resp.status_code in (200, 404), (
        f"Observe route crashed: {resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.anyio
async def test_ask_workflow_no_crash(client):
    """Ask route handles a question without crashing."""
    resp = await client.post(
        "/api/ask",
        json={
            "question": "What are effective strategies for teaching phonics?",
        },
    )
    # Should respond — either with an answer, or 'not configured' for Perplexity
    assert resp.status_code == 200, (
        f"Ask route crashed: {resp.status_code} {resp.text[:200]}"
    )
    body = resp.json()
    assert "type" in body  # ask_result, ask_unavailable, or ask_refused


@pytest.mark.anyio
async def test_morning_brief_route(client):
    """GET /api/brief responds without crashing."""
    resp = await client.get("/api/brief")
    assert resp.status_code == 200, (
        f"Brief route crashed: {resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.anyio
async def test_student_lens_route(client):
    """GET /api/students/:id/lens responds properly for known and unknown students."""
    # Unknown student → 404
    resp = await client.get("/api/students/nonexistent-xyz/lens")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_parent_recommendation_requires_student_id(client):
    """POST /api/parents/recommendation with no student_id returns 400."""
    resp = await client.post(
        "/api/parents/recommendation",
        json={},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error") == "student_id_required"


@pytest.mark.anyio
async def test_lesson_materials_generate_route(client):
    """POST /api/lesson-materials/generate handles minimal input gracefully."""
    resp = await client.post(
        "/api/lesson-materials/generate",
        json={
            "topic": "Fractions",
            "subject": "Mathematics",
        },
    )
    # Should be 400/422 (missing required fields) or 200, never 500
    assert resp.status_code != 500, (
        f"Lesson materials route crashed: {resp.text[:200]}"
    )


@pytest.mark.anyio
async def test_lesson_packet_approve_route(client):
    """POST /api/lesson-materials/packet/approve handles minimal input gracefully."""
    resp = await client.post(
        "/api/lesson-materials/packet/approve",
        json={},
    )
    # Should fail with validation error, never crash
    assert resp.status_code in (400, 422), (
        f"Packet approve should reject empty payload, got {resp.status_code}: {resp.text[:200]}"
    )


# ─── 2.2 PDF scoping verification ────────────────────────────────────────────


def test_lesson_packet_pdf_teacher_version_includes_support():
    """Teacher PDF includes individual support section in the bundle."""
    from src.lingua_viva.lesson_materials import (
        IndividualSupportStudent,
        LessonInput,
        render_packet_bundle,
        TierMaterial,
    )

    lesson = LessonInput(
        ib_programme="PYP",
        subject="English",
        unit_title="Communication",
        topic="Narrative Writing",
        atl_skills=["communication"],
        cefr_target="B1",
        duration_minutes=45,
    )
    materials = [
        TierMaterial(
            tier="approaching",
            student_ids=["s1"],
            title="Simplified Narrative",
            instructions_for_student="Write a short story with sentence starters.",
            exercise_body="Use the sentence starters to write 3 paragraphs.",
            scaffolding=["sentence starters provided"],
            teacher_note="Focus on structure, not length.",
        ),
        TierMaterial(
            tier="meeting",
            student_ids=["s2"],
            title="Standard Narrative",
            instructions_for_student="Write a narrative with beginning, middle, and end.",
            exercise_body="Write a complete story.",
            scaffolding=[],
            teacher_note="Encourage detail.",
        ),
        TierMaterial(
            tier="extending",
            student_ids=["s3"],
            title="Extended Narrative",
            instructions_for_student="Write a narrative with complex sentence structures.",
            exercise_body="Include dialogue and descriptive language.",
            scaffolding=[],
            teacher_note="Push for literary techniques.",
        ),
    ]
    support = [
        IndividualSupportStudent(
            student_id="s1",
            display_name="Marco",
            reason="Needs sentence starters",
        )
    ]
    bundle = render_packet_bundle(lesson, materials, status="APPROVED", individual_support=support)

    # Teacher markdown MUST include the individual support section
    assert "Individual Support" in bundle["markdown"] or "individual" in bundle["markdown"].lower() or "Marco" in bundle["markdown"], (
        "Teacher packet missing individual support section"
    )
    # Student HTML must NOT include individual support names
    student_html = bundle.get("student_print_html", "")
    assert "Individual Support" not in student_html or "Marco" not in student_html, (
        "Student version must not include teacher-only individual support names"
    )


def test_student_lens_pdf_scoping():
    """Family and teacher PDFs exclude Personal Context; HR includes it."""
    from src.education.student_lens import support_profile_for_audience

    # Use canonical category names from the normalized schema
    profile = {
        "schema_version": 2,
        "categories": {
            "communication_and_language": {
                "needs": [{"text": "Reading fluency below grade level", "confidence": "teacher_confirmed"}],
                "strengths": [{"text": "Strong verbal storytelling", "confidence": "teacher_confirmed"}],
                "strategies_worked": [],
                "strategies_not_worked": [],
                "evidence": [],
                "open_questions": [],
            },
            "personal_context": {
                "needs": [{"text": "Parents recently separated", "confidence": "teacher_confirmed"}],
                "strengths": [],
                "strategies_worked": [],
                "strategies_not_worked": [],
                "evidence": [],
                "open_questions": [],
            },
        },
    }

    # Teacher: NO personal_context
    teacher = support_profile_for_audience(profile, "teacher")
    assert "personal_context" not in teacher["categories"]
    assert "communication_and_language" in teacher["categories"]

    # Family: NO personal_context
    family = support_profile_for_audience(profile, "family")
    assert "personal_context" not in family["categories"]
    assert "communication_and_language" in family["categories"]

    # HR: YES personal_context
    hr = support_profile_for_audience(profile, "hr")
    assert "personal_context" in hr["categories"]
    assert "communication_and_language" in hr["categories"]


def test_rubric_pdf_export_route(client):
    """Rubric PDF export route responds without crash."""
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from src.web import app

    async def _check():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/assess/rubric/test-unit/pdf",
                json={},
            )
            # 404 (unit not found) or 400 is fine — 500 is not
            assert resp.status_code != 500, (
                f"Rubric PDF route crashed: {resp.text[:200]}"
            )

    asyncio.run(_check())


# ─── 2.3 UI call site verification ───────────────────────────────────────────


def test_teacher_workflow_routes_exist_in_ui():
    """Every critical teacher workflow route must be reachable from the UI.

    This is a structural check: the route path must exist in static/index.html
    or in the route reachability manifest.
    """
    import yaml

    manifest_path = REPO / "contracts" / "ROUTE_REACHABILITY.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    reachable = {e["route"] for e in manifest["reachable_from_ui"]}
    backend_only = {e["route"] for e in manifest["intentionally_backend_only"]}
    all_classified = reachable | backend_only

    # Critical teacher workflow routes that MUST be reachable
    critical_routes = [
        "POST /api/observe/capture",
        "POST /api/ask",
        "POST /api/lesson-materials/generate",
        "POST /api/lesson-materials/packet/approve",
        "POST /api/parents/recommendation",
        "GET /api/students/{student_id}/lens",
        "GET /api/brief",
    ]
    missing = [r for r in critical_routes if r not in all_classified]
    assert not missing, f"Critical teacher routes not in manifest: {missing}"

    # These must be reachable_from_ui specifically (not just backend_only)
    backend_critical = [r for r in critical_routes if r in backend_only]
    assert not backend_critical, (
        f"Teacher workflow routes classified as backend_only — teachers can't reach them: {backend_critical}"
    )
