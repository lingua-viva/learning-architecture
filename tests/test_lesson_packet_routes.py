from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.web import app


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
        "materials": [
            {
                "tier": "foundational",
                "student_ids": ["student-nora"],
                "title": "Routine Match",
                "instructions_for_student": "Match each routine word to a picture.",
                "exercise_body": "1. wake up\n2. eat breakfast\n3. go to school",
                "scaffolding": ["word bank", "sentence starters"],
                "teacher_note": "Use the model first.",
            },
            {
                "tier": "on_track",
                "student_ids": ["student-marco"],
                "title": "Routine Sentences",
                "instructions_for_student": "Write three sentences about a morning routine.",
                "exercise_body": "Use prima, poi, and dopo in your answers.",
                "scaffolding": ["model example"],
                "teacher_note": "Independent practice after one example.",
            },
            {
                "tier": "extended",
                "student_ids": ["student-luca"],
                "title": "Routine Interview",
                "instructions_for_student": "Interview a partner and report the routine.",
                "exercise_body": "Ask two follow-up questions and write a short report.",
                "scaffolding": [],
                "teacher_note": "Invite transfer to a new context.",
            },
        ],
    }


def test_lesson_packet_approval_writes_deliverable_and_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_LESSON_PACKET_DIR", str(tmp_path / "packets"))

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/approve", json=_payload())

    assert response.status_code == 200
    body = response.json()
    packet_path = Path(body["packet"]["file_path"])
    assert packet_path.exists()
    assert packet_path.suffix == ".md"
    assert body["deliverable"]["type"] == "lesson_material_packet"
    assert body["deliverable"]["deliverable_id"] in body["audit_receipt"]["deliverable_ids"]
    assert body["audit_receipt"]["is_complete"] is True
    assert body["sync_status"] == "not_requested"
    assert "# Student Handout -" in body["packet"]["markdown"]
    assert "student-nora" not in body["packet"]["markdown"]
