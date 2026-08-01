"""Voice Intent Router tests (MVP sprint Spec 4).

Unit tests for the signal-based classifier (no LLM, no DB, no network) plus
endpoint tests for POST /api/voice/act observation flows. Question-intent
endpoint behavior is not exercised here — it routes through the full
run_teacher_query pipeline, which is covered by its own suites.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva.voice_intent import (
    classify_intent,
    detect_student,
    parse_generation_context,
    parse_observation_context,
)
from src.web import app

ROSTER = [
    {"student_id": "student-marco", "display_name": "Marco Bianchi"},
    {"student_id": "student-nora", "display_name": "Nora Rossi"},
]


# ---------------------------------------------------------------------------
# Classifier unit tests
# ---------------------------------------------------------------------------

def test_observation_detected():
    result = classify_intent(
        "Marco helped a classmate find the right page during group reading", ROSTER
    )
    assert result.intent == "observation"
    assert result.student_id == "student-marco"
    assert result.student_name == "Marco Bianchi"
    assert result.needs_clarification is False


def test_generation_detected():
    result = classify_intent("Create a worksheet about daily routines", ROSTER)
    assert result.intent == "generate"
    assert result.generation_context.get("material_type") == "worksheet"
    assert result.generation_context.get("topic") == "daily routines"


def test_question_default():
    result = classify_intent("What level is Nora at?", ROSTER)
    assert result.intent == "question"


def test_question_wins_over_observation_verbs():
    # Question-shaped input asking ABOUT behavior must not become a write.
    result = classify_intent("What did Marco read today?", ROSTER)
    assert result.intent == "question"


def test_ambiguous_defaults_to_question():
    result = classify_intent("Marco reading", ROSTER)
    assert result.intent == "question"


def test_empty_transcript_defaults_to_question():
    result = classify_intent("", ROSTER)
    assert result.intent == "question"


def test_observation_no_student_needs_clarification():
    result = classify_intent(
        "The student struggled with the reading exercise today", ROSTER
    )
    assert result.intent == "observation"
    assert result.student_id is None
    assert result.needs_clarification is True


def test_observation_verbs_without_any_student_falls_to_question():
    # Behavior verbs but no roster match and no generic reference.
    result = classify_intent("Everyone participated during the morning circle", ROSTER)
    assert result.intent == "question"


def test_student_detection_first_name():
    student_id, display_name = detect_student("nora participated actively", ROSTER)
    assert student_id == "student-nora"
    assert display_name == "Nora Rossi"


def test_student_detection_full_name():
    student_id, _ = detect_student("Observation for Marco Bianchi in math", ROSTER)
    assert student_id == "student-marco"


def test_student_detection_no_match():
    student_id, display_name = detect_student("Giulia read a whole page", ROSTER)
    assert student_id is None
    assert display_name is None


def test_observation_context_parsing():
    context = parse_observation_context("She read aloud with clear pronunciation")
    assert context["cefr_dimension"] == "reading"


def test_observation_context_explicit_cefr_level():
    context = parse_observation_context("Marco used A2-level Italian in conversation")
    assert context["cefr_level_hint"] == "A2"


def test_observation_context_direction():
    struggling = parse_observation_context("He struggled with the writing task")
    assert struggling["direction"] == "emerging"
    confident = parse_observation_context("She spoke fluently and independently")
    assert confident["direction"] == "secure"


def test_generation_context_parsing():
    context = parse_generation_context("worksheet for daily routines")
    assert context.get("material_type") == "worksheet"
    assert context.get("topic") == "daily routines"


def test_generation_context_class_target_is_not_topic():
    context = parse_generation_context("Make a worksheet for my class")
    assert context.get("material_type") == "worksheet"
    assert "topic" not in context


# ---------------------------------------------------------------------------
# Endpoint tests — POST /api/voice/act
# ---------------------------------------------------------------------------

def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _create_observed_student(client: TestClient, name: str, teacher_id: str = "teacher-a"):
    created = client.post("/api/students", json={"display_name": name, "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]
    obs = client.post(
        "/api/observe/capture",
        json={
            "student_id": student_id,
            "teacher_id": teacher_id,
            "transcript": "Private raw transcript phrase.",
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": "A2",
            "cefr_direction": "progressing",
        },
    )
    assert obs.status_code == 200
    return student_id


def test_endpoint_requires_transcript(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/voice/act", json={})
        assert response.status_code == 400


def test_endpoint_observation_saved_first_name_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        student_id = _create_observed_student(client, "Marco Bianchi")

        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Marco helped a classmate find the right page during group reading",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "observation"
        assert body["action_taken"] == "saved"
        assert body["result"]["observation"]["student_id"] == student_id
        # Privacy: spoken text carries first name only, never the full name.
        assert "Marco" in body["spoken_confirmation"]
        assert "Bianchi" not in body["spoken_confirmation"]


def test_endpoint_observation_needs_clarification(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _create_observed_student(client, "Marco Bianchi")

        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "The student struggled with the reading exercise today",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "observation"
        assert body["action_taken"] == "needs_clarification"
        assert body["needs_clarification"] is True


def test_endpoint_generate_returns_context_without_generating(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Create a worksheet about daily routines",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "generate"
        assert body["action_taken"] == "ready_to_generate"
        assert body["needs_confirmation"] is True
        assert body["generation_context"].get("topic") == "daily routines"
