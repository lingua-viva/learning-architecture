from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    IndividualSupportStudent,
    TierMaterial,
    render_packet_bundle,
)
from src.web import app


REPO = Path(__file__).resolve().parents[1]


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


def test_packet_preview_route_returns_both_print_variants(monkeypatch, tmp_path):
    # F3: preview renders the STORED artifact from the last generation — no
    # generation machinery involved. Seed the store the way generate does.
    from src.lingua_viva.lesson_materials import (
        LessonMaterialsResult,
        store_generated_materials,
    )

    monkeypatch.setenv("LV_GENERATED_MATERIALS_DIR", str(tmp_path / "generated"))
    store_generated_materials(
        _lesson(),
        LessonMaterialsResult(
            materials=_materials(),
            lesson_summary="fake summary",
            sync_status="not_requested",
            individual_support=_support(),
        ),
        teacher_id="teacher-a",
    )

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/preview", json=_payload())

    assert response.status_code == 200
    packet = response.json()["packet"]
    assert packet["print_html"].startswith("<!doctype html>")
    assert packet["student_print_html"].startswith("<!doctype html>")
    assert "Teacher-Only Individual Support" in packet["print_html"]
    assert "Teacher-Only Individual Support" not in packet["student_print_html"]
    assert "Zoe Rivera" not in packet["student_print_html"]


def test_packet_preview_without_generation_is_refused(monkeypatch, tmp_path):
    # F3: never invent a packet the teacher hasn't reviewed.
    monkeypatch.setenv("LV_GENERATED_MATERIALS_DIR", str(tmp_path / "empty"))

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/preview", json=_payload())

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "no_generated_materials"
    assert "reviewed" in body["detail"]


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


def test_packet_print_surface_uses_iframe_chokepoint():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")

    assert "function printPacketHtml(printHtml, label)" in html
    assert "packet.print_html" in html
    assert "packet.student_print_html" in html
    assert "Print teacher packet" in html
    assert "Print student handouts" in html
    assert "Student handouts exclude the teacher-only individual support section." in html
    assert "document.createElement(\"iframe\")" in html
    assert "srcdoc = printHtml" in html
    assert "window.print" not in html
    assert html.count(".print()") == 1
