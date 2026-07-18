from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import Observation, StudentLensStore
from src.web import app


client = TestClient(app)


def _seed(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "students.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))
    store = StudentLensStore(db_path=db_path)
    no_obs = store.create_lens(student_id="student-no-obs", display_name="Student No Obs", grade_level="G3")
    old = store.create_lens(student_id="student-old", display_name="Student Old", grade_level="G3")
    recent = store.create_lens(student_id="student-recent", display_name="Student Recent", grade_level="G3")
    store.append_observation(Observation(
        student_id=old,
        teacher_id="t1",
        template_type="literacy",
        raw_transcript="Old note",
        recorded_at=(datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
    ))
    store.append_observation(Observation(
        student_id=recent,
        teacher_id="t1",
        template_type="literacy",
        raw_transcript="Recent note",
        recorded_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    ))
    store.close()
    return no_obs, old, recent


def test_unobserved_returns_students_without_recent_observations(monkeypatch, tmp_path):
    no_obs, old, _recent = _seed(monkeypatch, tmp_path)

    response = client.get("/api/students/unobserved?days=14")

    assert response.status_code == 200
    ids = {student["student_id"] for student in response.json()["students"]}
    assert {no_obs, old} <= ids


def test_unobserved_respects_days_parameter(monkeypatch, tmp_path):
    _no_obs, old, recent = _seed(monkeypatch, tmp_path)

    response = client.get("/api/students/unobserved?days=1")

    ids = {student["student_id"] for student in response.json()["students"]}
    assert old in ids
    assert recent in ids


def test_unobserved_excludes_recently_observed(monkeypatch, tmp_path):
    _no_obs, _old, recent = _seed(monkeypatch, tmp_path)

    response = client.get("/api/students/unobserved?days=14")

    ids = {student["student_id"] for student in response.json()["students"]}
    assert recent not in ids
