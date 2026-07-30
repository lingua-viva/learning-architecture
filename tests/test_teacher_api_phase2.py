from pathlib import Path
import asyncio
from types import SimpleNamespace

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


def _mock_query_result():
    grounding = SimpleNamespace(
        as_dict=lambda: {
            "tier_used": "local",
            "gir": {"score": 0.91, "method": "claim_support_v1_heuristic"},
        }
    )
    return SimpleNamespace(
        synthesis=SimpleNamespace(
            content="Italian is taught through songs. Students also practice classroom phrases.",
            confidence=0.82,
            citations=["Manuale v1"],
            model_used="none",
        ),
        classification=SimpleNamespace(
            riu_id="LV-EDU-001",
            name="Curriculum support",
            domain="curriculum",
            confidence=0.88,
        ),
        path_record=SimpleNamespace(
            gir_score=0.91,
            gir_method="claim_support_v1_heuristic",
            voice_tone="plain",
        ),
        duration_ms=12,
        steps_executed=["SCAN", "CLASSIFY", "RETRIEVE", "REASON", "SYNTHESIZE", "STORE"],
        gap_signals=[],
        grounding=grounding,
    )


def test_query_stream_emits_sentence_events_and_final_result(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)

    async def fake_query(*_args, **_kwargs):
        return _mock_query_result()

    import src.lingua_viva.app as lv_app

    monkeypatch.setattr(lv_app, "run_teacher_query", fake_query)
    response = client.post("/api/query/stream", json={
        "query": "What languages does this school teach?",
        "intent": "TEACH",
    })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: query_received" in body
    assert "event: status" in body
    assert "event: answer_sentence" in body
    assert "Italian is taught through songs." in body
    assert "event: result" in body
    assert '"gir_score":0.91' in body


def test_query_stream_timeout_is_an_sse_error(monkeypatch):
    async def slow_query(*_args, **_kwargs):
        await asyncio.sleep(1)

    import src.lingua_viva.app as lv_app

    monkeypatch.setattr(lv_app, "run_teacher_query", slow_query)
    response = client.post("/api/query/stream", json={
        "query": "How do I scaffold listening?",
        "timeout_seconds": 0.01,
    })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: error" in body
    assert '"timeout":true' in body


def test_query_json_shape_survives_stream_helper_extraction(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)

    async def fake_query(*_args, **_kwargs):
        return _mock_query_result()

    import src.lingua_viva.app as lv_app

    monkeypatch.setattr(lv_app, "run_teacher_query", fake_query)
    response = client.post("/api/query", json={
        "query": "What languages does this school teach?",
        "intent": "TEACH",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "result"
    assert body["result"]["content"].startswith("Italian is taught")
    assert body["gir_score"] == 0.91
    assert body["gir_method"] == "claim_support_v1_heuristic"
    assert body["voice_tone"] == "plain"


def test_query_response_does_not_invent_default_citation(monkeypatch, tmp_path):
    _isolate_runtime(monkeypatch, tmp_path)
    result = _mock_query_result()
    result.synthesis.citations = []

    async def fake_query(*_args, **_kwargs):
        return result

    import src.lingua_viva.app as lv_app

    monkeypatch.setattr(lv_app, "run_teacher_query", fake_query)
    response = client.post("/api/query", json={
        "query": "What unsupported thing can you tell me?",
        "intent": "TEACH",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert body["source_citation"] == ""
