from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva.privacy_log import log_event
from src.lingua_viva.traces import append_trace, new_trace
from src.web import app


client = TestClient(app)


def _stores(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_FILE_MAP_PATH", str(tmp_path / "file_map.yaml"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))


def test_why_returns_traces_without_raw_query(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    raw = "What CEFR targets for Grade 3 La Famiglia?"
    append_trace(new_trace(raw, domain="curriculum", model_used="ollama/qwen2.5:7b"))

    response = client.get("/api/why")

    assert response.status_code == 200
    assert response.json()["traces"]
    assert raw not in response.text
    assert "CEFR targets" not in response.text
    assert response.json()["external_calls"] == 0


def test_why_single_trace_by_id(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    trace = new_trace("private query", domain="assessment")
    append_trace(trace)

    response = client.get("/api/why", params={"trace_id": trace.trace_id})

    assert response.status_code == 200
    assert response.json()["trace_id"] == trace.trace_id
    assert response.json()["route"] == "local"
    assert response.json()["external_calls"] == 0


def test_privacy_returns_summary(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    log_event("query_processed_locally")

    response = client.get("/api/privacy")

    assert response.status_code == 200
    assert response.json()["total_queries_local"] == 1
    assert response.json()["external_calls"] == 0
    assert response.json()["docx_modifications"] == 0


def test_privacy_events_no_student_names(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    log_event("student_data_blocked", query_text="Marco needs support")

    response = client.get("/api/privacy")

    assert response.status_code == 200
    assert "Marco" not in response.text
    assert "student_data_blocked" in response.text


def test_profile_returns_aggregation(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    append_trace(new_trace("hello", domain="general"))

    response = client.get("/api/profile")

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "teacher"
    assert "reasoning_traces" in data
    assert data["local_only"] is True


def test_profile_clear_requires_confirmation(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)

    response = client.post("/api/profile/clear", json={})

    assert response.status_code == 400


def test_profile_clear_with_confirmation(monkeypatch, tmp_path):
    _stores(monkeypatch, tmp_path)
    trace = new_trace("hello", domain="general")
    append_trace(trace)
    log_event("query_processed_locally")

    response = client.post("/api/profile/clear", json={"confirm": "clear-all-data"})

    assert response.status_code == 200
    assert client.get("/api/why").json()["traces"] == []
    assert client.get("/api/privacy").json()["events"] == []
