"""Voice Intent Router tests (MVP sprint Spec 4).

Unit tests for the signal-based classifier (no LLM, no DB, no network) plus
endpoint tests for POST /api/voice/act observation flows. Question-intent
endpoint behavior is not exercised here — it routes through the full
run_teacher_query pipeline, which is covered by its own suites.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import json

from src.lingua_viva.voice_intent import (
    classify_intent,
    context_takes_precedence,
    detect_student,
    detect_student_detailed,
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
    student_id, display_name, match_quality = detect_student("nora participated actively", ROSTER)
    assert student_id == "student-nora"
    assert display_name == "Nora Rossi"
    assert match_quality == "exact"


def test_student_detection_full_name():
    student_id, _, match_quality = detect_student("Observation for Marco Bianchi in math", ROSTER)
    assert student_id == "student-marco"
    assert match_quality == "exact"


def test_student_detection_no_match():
    student_id, display_name, match_quality = detect_student("Giulia read a whole page", ROSTER)
    assert student_id is None
    assert display_name is None
    assert match_quality is None


# ---------------------------------------------------------------------------
# Student detection v2 — fuzzy matching + context precedence (unit)
# ---------------------------------------------------------------------------

def test_fuzzy_detection_garbled_name():
    student_id, display_name, match_quality = detect_student("Marko helped today", ROSTER)
    assert student_id == "student-marco"
    assert display_name == "Marco Bianchi"
    assert match_quality == "fuzzy"


def test_fuzzy_detection_garbled_possessive():
    # Possessive stripping in the fuzzy pass: "Marko's" -> "marko" -> Marco.
    student_id, _, match_quality = detect_student("Marko's essay improved", ROSTER)
    assert student_id == "student-marco"
    assert match_quality == "fuzzy"


def test_fuzzy_detection_accent_dropped_by_stt():
    # Whisper routinely drops accents on international rosters: "José" heard
    # as "Jose" must fuzzy-resolve (difflib alone treats é != e — the fuzzy
    # pass accent-folds both sides; 2026-08-01 review finding).
    roster = [{"student_id": "student-jose", "display_name": "José García"}]
    student_id, display_name, match_quality = detect_student(
        "Jose helped today", roster
    )
    assert student_id == "student-jose"
    assert display_name == "José García"
    assert match_quality == "fuzzy"


def test_fuzzy_detection_accent_garbled():
    # Garbling + accent at once: "Josee" against roster "José".
    roster = [{"student_id": "student-jose", "display_name": "José García"}]
    student_id, _, match_quality = detect_student("Josee helped today", roster)
    assert student_id == "student-jose"
    assert match_quality == "fuzzy"


def test_exact_accented_name_still_exact():
    # The accented spelling itself stays on the exact path — folding is
    # confined to the fuzzy pass.
    roster = [{"student_id": "student-jose", "display_name": "José García"}]
    student_id, _, match_quality = detect_student("José helped today", roster)
    assert student_id == "student-jose"
    assert match_quality == "exact"


def test_exact_possessive_still_exact():
    # "Marco's" already exact-matches on the word boundary — the fuzzy pass
    # must not run (exact paths byte-identical to v1).
    student_id, _, match_quality = detect_student("Marco's essay improved", ROSTER)
    assert student_id == "student-marco"
    assert match_quality == "exact"


def test_fuzzy_ambiguous_two_candidates_no_match():
    roster = [
        {"student_id": "student-marco", "display_name": "Marco Bianchi"},
        {"student_id": "student-marko", "display_name": "Marko Rossi"},
    ]
    detection = detect_student_detailed("Marcko helped today", roster)
    assert detection.student_id is None
    assert detection.match_quality == "ambiguous"
    candidate_ids = {c["student_id"] for c in detection.candidates}
    assert candidate_ids == {"student-marco", "student-marko"}


def test_fuzzy_ambiguous_shared_first_name():
    roster = [
        {"student_id": "student-1", "display_name": "Marco Bianchi"},
        {"student_id": "student-2", "display_name": "Marco Rossi"},
    ]
    detection = detect_student_detailed("Marko struggled today", roster)
    assert detection.student_id is None
    assert detection.match_quality == "ambiguous"
    assert len(detection.candidates) == 2


def test_short_first_names_are_exact_only():
    roster = [{"student_id": "student-al", "display_name": "Al Verdi"}]
    student_id, display_name, match_quality = detect_student(
        "All done with the group work", roster)
    assert student_id is None
    assert display_name is None
    assert match_quality is None


def test_context_precedence_pronoun_subject_beats_named_object():
    # "he" is the subject; Nora as object must not steal attribution.
    assert context_takes_precedence("he also helped Nora", "nora") is True


def test_context_precedence_named_no_pronoun():
    assert context_takes_precedence("Nora struggled today", "nora") is False


def test_context_precedence_name_before_pronoun():
    # The name is the subject; a later pronoun refers to it, not to context.
    assert context_takes_precedence("Nora said she finished the exercise", "nora") is False


def test_context_precedence_pronoun_no_name():
    assert context_takes_precedence("he also asked for help", None) is True


def test_context_precedence_no_pronoun_no_name():
    # A nameless, pronounless observation never attaches to context.
    assert context_takes_precedence("the student struggled with reading", None) is False


def test_classify_ambiguous_fuzzy_is_observation_needing_clarification():
    roster = [
        {"student_id": "student-marco", "display_name": "Marco Bianchi"},
        {"student_id": "student-marko", "display_name": "Marko Rossi"},
    ]
    result = classify_intent("Marcko helped a classmate during group reading", roster)
    assert result.intent == "observation"
    assert result.needs_clarification is True
    assert result.match_quality == "ambiguous"
    assert len(result.candidates) == 2


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

def _isolate(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    routing_memory = tmp_path / "routing_memory.ndjson"
    monkeypatch.setenv("LV_ROUTING_MEMORY_PATH", str(routing_memory))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    return routing_memory


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


def test_endpoint_fuzzy_saved_echoes_resolved_name(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        student_id = _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Marko helped a classmate find the right page during group reading",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "saved"
        assert body["match_quality"] == "fuzzy"
        assert body["result"]["observation"]["student_id"] == student_id
        assert body["resolved_student"]["student_id"] == student_id
        # Non-exact resolutions must speak the resolved name (first name only).
        assert body["spoken_confirmation"] == "Got it — Marco. Saved."
        assert "Bianchi" not in body["spoken_confirmation"]


def test_endpoint_ambiguous_fuzzy_asks_with_both_candidates(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _create_observed_student(client, "Marco Bianchi")
        _create_observed_student(client, "Marko Rossi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Marcko helped a classmate during group reading",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "needs_clarification"
        assert body["match_quality"] == "ambiguous"
        spoken = body["spoken_confirmation"]
        assert "Marco" in spoken and "Marko" in spoken
        # First names only in speech; full data rides in candidates.
        assert "Bianchi" not in spoken and "Rossi" not in spoken
        candidate_names = {c["display_name"] for c in body["candidates"]}
        assert candidate_names == {"Marco Bianchi", "Marko Rossi"}


def test_endpoint_context_pronoun_subject_keeps_context_student(monkeypatch, tmp_path):
    # "he also helped Nora …" — pronoun is the subject; the context student
    # (Marco) keeps attribution, Nora as object must not steal it.
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        marco_id = _create_observed_student(client, "Marco Bianchi")
        _create_observed_student(client, "Nora Rossi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "he also helped Nora today in class",
                "context_student_id": marco_id,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "saved"
        assert body["match_quality"] == "context"
        assert body["result"]["observation"]["student_id"] == marco_id
        # Context resolution always names the student aloud.
        assert body["spoken_confirmation"] == "Still Marco — noted."
        assert "Bianchi" not in body["spoken_confirmation"]


def test_endpoint_named_student_ignores_context_without_pronoun(monkeypatch, tmp_path):
    # The reverse direction: a plain named observation must win over context.
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        marco_id = _create_observed_student(client, "Marco Bianchi")
        nora_id = _create_observed_student(client, "Nora Rossi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Nora struggled with the writing exercise today",
                "context_student_id": marco_id,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "saved"
        assert body["match_quality"] == "exact"
        assert body["result"]["observation"]["student_id"] == nora_id
        # Exact path spoken string unchanged from v1.
        assert body["spoken_confirmation"] == "Got it. Observation saved for Nora."


def test_endpoint_context_resolves_pronoun_only_followup(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        marco_id = _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "he also asked for help in class",
                "context_student_id": marco_id,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "saved"
        assert body["match_quality"] == "context"
        assert body["result"]["observation"]["student_id"] == marco_id


def test_endpoint_no_pronoun_no_name_clarifies_despite_context(monkeypatch, tmp_path):
    # A nameless, pronounless observation never silently attaches to context.
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        marco_id = _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "The student struggled with the reading exercise today",
                "context_student_id": marco_id,
            },
        )
        assert response.status_code == 200
        assert response.json()["action_taken"] == "needs_clarification"


def test_endpoint_unknown_context_id_is_ignored(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "he also asked for help in class",
                "context_student_id": "student-does-not-exist",
            },
        )
        assert response.status_code == 200
        assert response.json()["action_taken"] == "needs_clarification"


def test_detection_log_outcomes_and_content_free(monkeypatch, tmp_path):
    # Routing-memory rows per detection outcome — and never a transcript or
    # a name (key-set assertion + raw-file scan, per spec).
    memory_path = _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        marco_id = _create_observed_student(client, "Marco Bianchi")
        cases = [
            ("Marco helped a classmate find the right page during group reading", None),
            ("Marko helped a classmate find the right page during group reading", None),
            ("he also asked for help in class", marco_id),
        ]
        for transcript, context_id in cases:
            payload = {"teacher_id": "teacher-a", "transcript": transcript}
            if context_id:
                payload["context_student_id"] = context_id
            assert client.post("/api/voice/act", json=payload).status_code == 200

    rows = [
        json.loads(line)
        for line in memory_path.read_text().splitlines()
        if line.strip()
    ]
    detect_outcomes = [
        r["outcome"] for r in rows if r.get("decision") == "student_detect"]
    assert detect_outcomes == ["exact", "fuzzy", "context"]
    for row in rows:
        assert "transcript" not in row
        assert "display_name" not in row
    raw = memory_path.read_text()
    assert "Marco" not in raw and "Marko" not in raw and "Bianchi" not in raw


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
