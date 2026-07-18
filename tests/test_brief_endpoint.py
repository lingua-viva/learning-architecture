import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import Observation, StudentLensStore
from src.web import app


client = TestClient(app)


def _seed(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "students.db"
    log_path = tmp_path / "revision.ndjson"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(log_path))
    store = StudentLensStore(db_path=db_path)
    observed = store.create_lens(student_id="student-observed", display_name="Observed", grade_level="G3")
    unobserved = store.create_lens(student_id="student-unobserved", display_name="Unobserved", grade_level="G3", rti_current_tier=2)
    store.append_observation(Observation(
        student_id=observed,
        teacher_id="t1",
        template_type="literacy",
        raw_transcript="Recent note",
        recorded_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    ))
    store.close()
    log_path.write_text(json.dumps({"timestamp": "2026-07-15T21:00:00+00:00", "note": "private"}) + "\n")
    return observed, unobserved


def test_brief_returns_today_when_schedule_configured(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    schedule = {"monday": {"grade": "G3", "unit_id": "g3-unit-1"}}

    response = client.get("/api/brief", params={"day": "Monday", "schedule": json.dumps(schedule)})

    assert response.status_code == 200
    today = response.json()["today"]
    assert today["configured"] is True
    assert today["unit_id"] == "g3-unit-1"
    assert today["source"].startswith("Manuale")


def test_brief_returns_unobserved_students(monkeypatch, tmp_path):
    _observed, unobserved = _seed(monkeypatch, tmp_path)

    response = client.get("/api/brief?days=14")

    attention = response.json()["attention"]
    assert attention["unobserved_count"] >= 1
    assert "Unobserved" in attention["unobserved_students"]
    assert attention["rti_pending"] >= 1


def test_brief_returns_recent_observation_count(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)

    response = client.get("/api/brief")

    recent = response.json()["recent"]
    assert recent["observations_this_week"] == 1
    assert recent["last_observation"] is not None
    assert recent["last_reflection"] == "2026-07-15T21:00:00+00:00"


def test_brief_returns_health_status(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)

    response = client.get("/api/brief")

    assert response.status_code == 200
    assert response.json()["health"]["status"] in {"OK", "WARN", "FIXABLE", "BLOCKED", "PRIVATE_RISK"}


def test_brief_returns_unconfigured_today_when_no_schedule(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)

    response = client.get("/api/brief", params={"day": "Monday"})

    assert response.json()["today"] == {"day": "Monday", "configured": False}
