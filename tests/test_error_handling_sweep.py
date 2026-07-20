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

    response = client.post("/api/observe/capture", json={"student_id": "missing", "transcript": "test"})

    assert response.status_code == 404
