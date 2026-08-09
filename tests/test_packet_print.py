from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    IndividualSupportStudent,
    TierMaterial,
    render_packet_bundle,
)
from src.web import app


def _lesson() -> LessonInput:
    return LessonInput(
        ib_programme="PYP",
        subject="language",
        unit_title="How we express ourselves",
        topic="Describing daily routines in Italian",
        atl_skills=["communication"],
        cefr_target="A2",
        duration_minutes=45,
    )


def _materials() -> list[TierMaterial]:
    return [
        TierMaterial(
            tier="foundational",
            student_ids=["student-a"],
            title="Routine Match",
            instructions_for_student="Match each routine word to a picture.",
            exercise_body="1. wake up\n2. eat breakfast\n3. go to school",
            scaffolding=["word bank"],
            teacher_note="Use the model first.",
        ),
        TierMaterial(
            tier="on_track",
            student_ids=["student-b"],
            title="Routine Sentences",
            instructions_for_student="Write three sentences about a morning routine.",
            exercise_body="Use prima, poi, and dopo.",
            scaffolding=["model example"],
            teacher_note="Independent practice after one example.",
        ),
        TierMaterial(
            tier="extended",
            student_ids=["student-c"],
            title="Routine Interview",
            instructions_for_student="Interview a partner and report the routine.",
            exercise_body="Ask two follow-up questions and write a short report.",
            scaffolding=[],
            teacher_note="Invite transfer to a new context.",
        ),
    ]


def _support() -> list[IndividualSupportStudent]:
    return [
        IndividualSupportStudent(
            student_id="student-zoe",
            display_name="Zoe Rivera",
            reason="rti_current_tier_3",
        )
    ]


def _payload() -> dict:
    return {
        "teacher_id": "teacher-a",
        "lesson": {
            "ib_programme": "PYP",
            "subject": "language",
            "unit_title": "How we express ourselves",
            "topic": "Describing daily routines in Italian",
            "atl_skills": ["communication"],
            "cefr_target": "A2",
            "duration_minutes": 45,
        },
    }


def test_render_packet_bundle_has_teacher_and_student_safe_print_docs():
    bundle = render_packet_bundle(
        _lesson(),
        _materials(),
        status="DRAFT",
        individual_support=_support(),
    )

    assert bundle["print_html"].startswith("<!doctype html>")
    assert bundle["student_print_html"].startswith("<!doctype html>")
    assert "page-break" in bundle["print_html"]
    assert "page-break" in bundle["student_print_html"]
    assert "Teacher-Only Individual Support" in bundle["print_html"]
    assert "Teacher-Only Individual Support" not in bundle["student_print_html"]
    assert "Zoe Rivera" not in bundle["student_print_html"]


def test_render_packet_bundle_student_variant_prints_without_support_litter():
    bundle = render_packet_bundle(
        _lesson(),
        _materials(),
        status="APPROVED",
        individual_support=[],
    )

    assert bundle["print_html"].startswith("<!doctype html>")
    assert bundle["student_print_html"].startswith("<!doctype html>")
    assert "Teacher-Only Individual Support" not in bundle["print_html"]
    assert "Teacher-Only Individual Support" not in bundle["student_print_html"]
    assert bundle["student_print_html"].count("Student Handout") == 3


def test_packet_preview_route_returns_both_print_variants(monkeypatch):
    from src.lingua_viva import lesson_materials

    monkeypatch.setattr(
        lesson_materials,
        "assign_roster_split",
        lambda *args, **kwargs: SimpleNamespace(
            tier_groups={m.tier: m.student_ids for m in _materials()},
            roster_names={},
            individual_support=_support(),
        ),
    )

    async def fake_generate_lesson_materials(**kwargs):
        return SimpleNamespace(
            materials=_materials(),
            individual_support=_support(),
            lesson_summary="fake summary",
            sync_status="not_requested",
        )

    monkeypatch.setattr(lesson_materials, "generate_lesson_materials", fake_generate_lesson_materials)

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/preview", json=_payload())

    assert response.status_code == 200
    packet = response.json()["packet"]
    assert packet["print_html"].startswith("<!doctype html>")
    assert packet["student_print_html"].startswith("<!doctype html>")
    assert "Teacher-Only Individual Support" in packet["print_html"]
    assert "Teacher-Only Individual Support" not in packet["student_print_html"]
    assert "Zoe Rivera" not in packet["student_print_html"]


def test_packet_approve_route_returns_both_print_variants(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_LESSON_PACKET_DIR", str(tmp_path / "packets"))
    payload = {
        **_payload(),
        "materials": [material.__dict__ for material in _materials()],
        "individual_support": [student.__dict__ for student in _support()],
    }

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/approve", json=payload)

    assert response.status_code == 200
    packet = response.json()["packet"]
    assert packet["print_html"].startswith("<!doctype html>")
    assert packet["student_print_html"].startswith("<!doctype html>")
    assert "Teacher-Only Individual Support" in packet["print_html"]
    assert "Teacher-Only Individual Support" not in packet["student_print_html"]
    assert "Zoe Rivera" not in packet["student_print_html"]
