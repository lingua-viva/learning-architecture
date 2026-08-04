from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_query_missing_query_returns_400():
    response = client.post("/api/query", json={})

    assert response.status_code == 400
    assert response.json()["error"] == "query is required"


def test_prepare_invalid_duration_returns_400():
    response = client.post("/api/prepare/activity", json={"duration_minutes": "not-a-number"})

    assert response.status_code == 400
    assert "duration_minutes" in response.json()["error"]


def test_observe_unknown_student_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))

    response = client.post("/api/observe/capture", json={
        "student_id": "missing",
        "transcript": "test",
        "template_type": "sel_positive",
    })

    assert response.status_code == 404


def test_archive_student_soft_deletes_and_hides_from_roster(monkeypatch, tmp_path):
    """BUG-8: teachers need a way to remove a student (moved schools, typo).
    Archive is a soft delete — roster hides them, observations are retained."""
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))

    created = client.post("/api/students", json={"display_name": "Archive Test Student", "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]

    response = client.delete(f"/api/students/{student_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "archived"
    assert body["observations_retained"] is True

    roster = client.get("/api/students").json()["students"]
    assert student_id not in {s["student_id"] for s in roster}


def test_archive_unknown_student_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))

    response = client.delete("/api/students/does-not-exist")
    assert response.status_code == 404


def test_observe_without_type_defaults_to_general_not_invented_cefr(monkeypatch, tmp_path):
    """A4 (2026-08-04): a save without an observation type is never forced or
    rejected — it stores as template_type='general' (unclassified), not an
    invented cefr/speaking/A1 guess (that was BUG-5, QA 2026-08-02) and not a
    400 either (that was the interim BUG-5 fix, since replaced by A4)."""
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))

    created = client.post("/api/students", json={"display_name": "A4 Test Student", "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]

    response = client.post("/api/observe/capture", json={
        "student_id": student_id,
        "transcript": "test note",
    })
    assert response.status_code == 200
    assert response.json()["observation"]["template_type"] == "general"

    # cefr explicitly chosen without skill+level is still rejected, not defaulted —
    # that guard is unrelated to A4 and still protects against invented CEFR data.
    response = client.post("/api/observe/capture", json={
        "student_id": student_id,
        "transcript": "test note",
        "template_type": "cefr",
    })
    assert response.status_code == 400
    assert "skill" in response.json()["error"].lower()
