from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.web import app


def test_student_lens_pdf_export_is_share_scoped_and_recorded(monkeypatch, tmp_path):
    db = tmp_path / "students.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    with StudentLensStore(db_path=db) as store:
        sid = store.create_lens(display_name="Marco Bianchi")
        store.add_support_entry(
            sid,
            "communication_and_language",
            "needs",
            "Needs sentence starters for oral rehearsal.",
            "teacher-a",
            source_observation_id="obs-public",
        )
        store.add_support_entry(
            sid,
            "personal_context",
            "needs",
            "Sensitive family context for HR only.",
            "teacher-a",
            source_observation_id="obs-private",
        )

    with TestClient(app) as client:
        teacher = client.post(f"/api/students/{sid}/lens/pdf", json={"audience": "teacher"})
        hr = client.post(f"/api/students/{sid}/lens/pdf", json={"audience": "hr"})

    assert teacher.status_code == 200
    assert hr.status_code == 200
    teacher_body = teacher.json()
    hr_body = hr.json()
    teacher_path = Path(teacher_body["file_path"])
    hr_path = Path(hr_body["file_path"])
    assert teacher_path.read_bytes().startswith(b"%PDF")
    assert hr_path.read_bytes().startswith(b"%PDF")
    assert teacher_body["share_scope"]["personal_context_included"] is False
    assert hr_body["share_scope"]["personal_context_included"] is True
    assert teacher_body["deliverable"]["type"] == "student_lens"
    assert teacher_body["deliverable"]["location"]["path"] == str(teacher_path)
    assert teacher_body["deliverable"]["deliverable_id"] in teacher_body["audit_receipt"]["deliverable_ids"]
    assert teacher_body["audit_receipt"]["export"]["format"] == "pdf"

    with TestClient(app) as client:
        repeated = client.post(f"/api/students/{sid}/lens/pdf", json={"audience": "teacher"})
    assert repeated.status_code == 200
    assert repeated.json()["file_path"] == teacher_body["file_path"]
