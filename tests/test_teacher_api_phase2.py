from pathlib import Path
import asyncio

from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def _isolate_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "lv_revision_log.ndjson"))


def test_teacher_curriculum_and_prepare_endpoints(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)

    overview = client.get("/api/curriculum/overview")
    assert overview.status_code == 200
    assert overview.json()["source_status"]["badge"] == "Authoritative source: Manuale v1"

    grade = client.get("/api/curriculum/grade/G3")
    assert grade.status_code == 200
    unit_id = grade.json()["units"][0]["unit_id"]

    activity = client.post("/api/prepare/activity", json={"grade": "G3", "unit_id": unit_id})
    assert activity.status_code == 200
    body = activity.json()
    assert set(body["tiers"]) == {"foundational", "on_track", "extended"}
    assert body["source_citation"].startswith("Generated from Manuale")
    assert "achieve" not in body["cefr_rule"].lower()


def test_observe_students_parents_and_reflect_endpoints(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)

    roster = client.get("/api/students")
    assert roster.status_code == 200
    students = roster.json()["students"]
    assert students

    student_id = students[0]["student_id"]
    obs = client.post("/api/observe/capture", json={
        "student_id": student_id,
        "transcript": "Self-corrected passato prossimo in context",
    })
    assert obs.status_code == 200
    assert obs.json()["local_only"] is True

    lens = client.get(f"/api/students/{student_id}/lens")
    assert lens.status_code == 200
    assert lens.json()["observations"]
    assert lens.json()["rti_proposals"][0]["message"].startswith("System suggests")

    parent = client.post("/api/parents/recommendation", json={
        "student_id": student_id,
        "focus": "creative quiet workspace",
    })
    assert parent.status_code == 200
    parent_payload = parent.json()
    parent_body = parent_payload["body"].lower()
    assert "student_id" not in parent_payload
    assert "ai" not in parent_body
    assert students[0]["display_name"].lower() not in parent_body
    assert "we noticed your child" in parent_body
    assert "what your child chooses to try first" in parent_body

    reflect = client.post("/api/reflect/note", json={"note": "Checklist worked today."})
    assert reflect.status_code == 200
    assert (tmp_path / "lv_revision_log.ndjson").exists()


def test_assess_and_publication_status(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)

    unit_id = client.get("/api/curriculum/grade/G3").json()["units"][0]["unit_id"]
    rubric = client.get(f"/api/assess/rubric/{unit_id}")
    assert rubric.status_code == 200
    body = rubric.json()
    assert body["assessment"]["cefr_language"].startswith("Designed to target")
    assert "achieve" not in body["assessment"]["cefr_language"].lower()
    descriptors = " ".join(body["assessment"]["band_descriptors"].values()).lower()
    assert "does not yet reach" not in descriptors
    assert "limited:" not in descriptors

    publication = client.get("/api/publication/status")
    assert publication.status_code == 200
    assert publication.json()["claim_count"] >= 1


def test_query_endpoint_times_out_cleanly(monkeypatch):
    async def slow_query(*_args, **_kwargs):
        await asyncio.sleep(1)

    import src.lingua_viva.app as lv_app

    monkeypatch.setattr(lv_app, "run_teacher_query", slow_query)
    response = client.post("/api/query", json={
        "query": "How do I scaffold listening?",
        "timeout_seconds": 0.01,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "error"
    assert body["timeout"] is True
