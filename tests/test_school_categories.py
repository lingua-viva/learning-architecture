"""Base Lens — School Category Profile tests.

SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01: profile edit path
(background_notes + PATCH), deterministic category suggestion (threshold-
gated, never silent), strategies-trialed outcome parsing, tap-to-confirm,
and Tier 2 school display config.

Hermetic per tests/test_voice_intent.py's _isolate pattern — never reads
the machine's real ~/.lingua-viva.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.observation_capture import (
    CATEGORY_SUGGESTION_THRESHOLD,
    suggest_support_categories,
)
from src.education.student_lens import StudentLensStore
from src.lingua_viva.voice_intent import parse_strategy_outcome
from src.web import app


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _create_student(client: TestClient, name: str = "Marco Bianchi") -> str:
    created = client.post("/api/students", json={"display_name": name, "grade_level": "G3"})
    assert created.status_code == 200
    return created.json()["student_id"]


def _privacy_events(tmp_path: Path) -> list[dict]:
    path = tmp_path / "privacy.ndjson"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. update_profile store method
# ---------------------------------------------------------------------------

def test_update_profile_happy_path(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with StudentLensStore(db_path=tmp_path / "s.db") as store:
        sid = store.create_lens(display_name="Test Student")
        before = store.get_lens(sid)["profile_version"]
        lens = store.update_profile(
            sid,
            {
                "background_notes": "Moved from another school in September.",
                "grade_level": "G4",
                "campus": "north",
                "home_languages": ["it", "en"],
                "learning_differences": ["dyslexia (reported)"],
            },
        )
        assert lens["background_notes"] == "Moved from another school in September."
        assert lens["grade_level"] == "G4"
        assert lens["campus"] == "north"
        assert lens["home_languages"] == ["it", "en"]
        assert lens["learning_differences"] == ["dyslexia (reported)"]
        assert lens["profile_version"] == before + 1


def test_update_profile_rejects_rti_tier(monkeypatch, tmp_path):
    """rti_current_tier must NOT be PATCH-editable: tier changes go through
    update_rti_tier() so rti_tier_history stays reconstructable (2026-08-01
    review finding — the profile path silently bypassed the audit trail)."""
    _isolate(monkeypatch, tmp_path)
    with StudentLensStore(db_path=tmp_path / "s.db") as store:
        sid = store.create_lens(display_name="Test Student")
        try:
            store.update_profile(sid, {"rti_current_tier": 2})
            raise AssertionError("rti_current_tier via update_profile must raise")
        except ValueError as exc:
            assert "rti_current_tier" in str(exc)
        assert store.get_lens(sid)["profile_version"] == 1


def test_update_profile_rejects_unknown_field(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with StudentLensStore(db_path=tmp_path / "s.db") as store:
        sid = store.create_lens(display_name="Test Student")
        try:
            store.update_profile(sid, {"display_name": "New Name"})
            raise AssertionError("unknown field must raise ValueError")
        except ValueError as exc:
            assert "display_name" in str(exc)
        # Nothing changed, version untouched.
        assert store.get_lens(sid)["profile_version"] == 1


def test_update_profile_rejects_bad_types(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with StudentLensStore(db_path=tmp_path / "s.db") as store:
        sid = store.create_lens(display_name="Test Student")
        for bad in (
            {"home_languages": "it"},
            {"background_notes": 42},
        ):
            try:
                store.update_profile(sid, bad)
                raise AssertionError(f"{bad} must raise ValueError")
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# 2. PATCH /api/students/{student_id}
# ---------------------------------------------------------------------------

def test_patch_endpoint_updates_and_logs_privacy_event(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.patch(
            f"/api/students/{sid}",
            json={"background_notes": "New-school background info."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "updated"
        assert body["updated_fields"] == ["background_notes"]

        lens = client.get(f"/api/students/{sid}/lens").json()
        assert lens["background_notes"] == "New-school background info."

        events = _privacy_events(tmp_path)
        assert any(e["event_type"] == "profile_updated" for e in events)
        # Event carries no PII — generic detail plus a hash only. The free
        # -text note must never appear in the privacy log.
        for event in events:
            assert "New-school" not in json.dumps(event)


def test_patch_endpoint_unknown_field_400(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.patch(f"/api/students/{sid}", json={"trauma_flag": True})
        assert res.status_code == 400


def test_patch_endpoint_unknown_student_404(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        res = client.patch(
            "/api/students/no-such-student", json={"background_notes": "x"}
        )
        assert res.status_code == 404


def test_patch_endpoint_empty_payload_400(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.patch(f"/api/students/{sid}", json={})
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# 3. Category suggestion engine
# ---------------------------------------------------------------------------

def test_executive_functioning_suggested_above_threshold():
    suggestions = suggest_support_categories(
        "Marco struggled to stay on task during group reading"
    )
    by_id = {s["category_id"]: s for s in suggestions}
    assert "executive_functioning" in by_id
    assert by_id["executive_functioning"]["confidence"] >= CATEGORY_SUGGESTION_THRESHOLD
    assert by_id["executive_functioning"]["matched_signals"]
    assert "attendance_and_engagement" not in by_id


def test_vague_transcript_nothing_above_threshold():
    suggestions = suggest_support_categories("He read a book this morning")
    assert all(s["confidence"] < CATEGORY_SUGGESTION_THRESHOLD for s in suggestions)
    assert suggest_support_categories("") == []


def test_personal_context_suggested_only_from_explicit_context():
    suggestions = suggest_support_categories(
        "Teacher-confirmed safeguarding note: the family situation may affect attendance."
    )
    by_id = {s["category_id"]: s for s in suggestions}
    assert "personal_context" in by_id
    assert by_id["personal_context"]["confidence"] >= CATEGORY_SUGGESTION_THRESHOLD


def test_suggestions_sorted_by_confidence():
    suggestions = suggest_support_categories(
        "She was distracted and off-task, then got frustrated and cried"
    )
    confidences = [s["confidence"] for s in suggestions]
    assert confidences == sorted(confidences, reverse=True)


# ---------------------------------------------------------------------------
# 4. Strategy outcome parsing
# ---------------------------------------------------------------------------

def test_strategy_worked():
    parsed = parse_strategy_outcome(
        "We tried sentence starters and it really helped"
    )
    assert parsed["strategy_statement"] == "sentence starters"
    assert parsed["outcome"] == "worked"


def test_strategy_not_worked():
    parsed = parse_strategy_outcome("Tried peer pairing but he shut down")
    assert parsed["strategy_statement"] == "peer pairing"
    assert parsed["outcome"] == "not_worked"


def test_strategy_mentioned_without_outcome():
    parsed = parse_strategy_outcome("Marco tried the visual timer today")
    assert parsed["outcome"] is None


def test_no_strategy_clause():
    parsed = parse_strategy_outcome("He read a passage aloud")
    assert parsed == {"strategy_statement": None, "outcome": None}


# ---------------------------------------------------------------------------
# 5. Auto-file: threshold-gated, model_suggested, never silent promotion
# ---------------------------------------------------------------------------

def _capture(client: TestClient, sid: str, transcript: str) -> dict:
    res = client.post(
        "/api/observe/capture",
        json={
            "student_id": sid,
            "teacher_id": "teacher-a",
            "transcript": transcript,
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": "A2",
            "cefr_direction": "progressing",
        },
    )
    assert res.status_code == 200
    return res.json()


def test_strategy_above_threshold_files_model_suggested(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        result = _capture(
            client,
            sid,
            "Marco struggled to stay on task so we tried a visual timer and it worked",
        )
        parsed = result["strategy_outcome_parsed"]
        assert parsed["autofiled"] == {
            "category_id": "executive_functioning",
            "bucket": "strategies_worked",
        }
        lens = client.get(f"/api/students/{sid}/lens").json()
        entries = lens["support_profile"]["categories"]["executive_functioning"][
            "strategies_worked"
        ]
        assert len(entries) == 1
        # Never silently teacher_confirmed.
        assert entries[0]["confidence"] == "model_suggested"


def test_strategy_below_threshold_routes_to_open_questions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        result = _capture(
            client,
            sid,
            "We tried peer pairing with a classmate but he shut down",
        )
        parsed = result["strategy_outcome_parsed"]
        assert parsed["outcome"] == "not_worked"
        autofiled = parsed["autofiled"]
        assert autofiled is not None
        assert autofiled["bucket"] == "open_questions"
        lens = client.get(f"/api/students/{sid}/lens").json()
        cat = lens["support_profile"]["categories"][autofiled["category_id"]]
        # Landed in open_questions, never in a guessed category bucket.
        assert len(cat["open_questions"]) == 1
        assert cat["open_questions"][0]["confidence"] == "model_suggested"
        assert not cat["strategies_worked"]
        assert not cat["strategies_not_worked"]


def test_explicit_teacher_entries_suppress_autofile(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.post(
            "/api/observe/capture",
            json={
                "student_id": sid,
                "teacher_id": "teacher-a",
                "transcript": "We tried a visual timer to stay on task and it worked",
                "template_type": "cefr",
                "cefr_dimension": "speaking",
                "cefr_level_observed": "A2",
                "cefr_direction": "progressing",
                "support_entries": [
                    {
                        "support_category": "executive_functioning",
                        "strategy_statement": "visual timer",
                        "strategy_outcome": "worked",
                        "teacher_confirmed": True,
                    }
                ],
            },
        )
        assert res.status_code == 200
        assert res.json()["strategy_outcome_parsed"]["autofiled"] is None
        lens = client.get(f"/api/students/{sid}/lens").json()
        entries = lens["support_profile"]["categories"]["executive_functioning"][
            "strategies_worked"
        ]
        # Exactly the teacher's entry — no model duplicate.
        assert len(entries) == 1
        assert entries[0]["confidence"] == "teacher_confirmed"


# ---------------------------------------------------------------------------
# 6. Tap-to-confirm
# ---------------------------------------------------------------------------

def test_confirm_support_entry_flips_confidence(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        _capture(
            client,
            sid,
            "Marco struggled to stay on task so we tried a visual timer and it worked",
        )
        lens = client.get(f"/api/students/{sid}/lens").json()
        entry = lens["support_profile"]["categories"]["executive_functioning"][
            "strategies_worked"
        ][0]
        res = client.post(
            f"/api/students/{sid}/support-entry/confirm",
            json={
                "category_id": "executive_functioning",
                "bucket": "strategies_worked",
                "entry_id": entry["id"],
            },
        )
        assert res.status_code == 200
        lens = client.get(f"/api/students/{sid}/lens").json()
        assert (
            lens["support_profile"]["categories"]["executive_functioning"][
                "strategies_worked"
            ][0]["confidence"]
            == "teacher_confirmed"
        )
        events = _privacy_events(tmp_path)
        assert any(e["event_type"] == "support_entry_confirmed" for e in events)


def test_confirm_support_entry_missing_entry_400(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.post(
            f"/api/students/{sid}/support-entry/confirm",
            json={
                "category_id": "executive_functioning",
                "bucket": "needs",
                "entry_id": "no-such-entry",
            },
        )
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# 7. voice/act: additive category_suggestions, spoken stays first-name-only
# ---------------------------------------------------------------------------

def test_voice_act_response_additive_and_first_name_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        # Roster membership requires one prior observation by this teacher.
        _capture(client, sid, "Private raw transcript phrase.")

        res = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Marco struggled to stay on task during group reading",
            },
        )
        assert res.status_code == 200
        body = res.json()
        # Existing contract fields unchanged.
        assert body["intent"] == "observation"
        assert body["action_taken"] == "saved"
        assert body["result"]["observation"]["student_id"] == sid
        # Additive field present with the EF suggestion.
        ids = [s["category_id"] for s in body["category_suggestions"]]
        assert "executive_functioning" in ids
        # Privacy: spoken confirmation is first-name-only, unchanged.
        assert "Marco" in body["spoken_confirmation"]
        assert "Bianchi" not in body["spoken_confirmation"]


def test_observe_classify_includes_category_suggestions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.post(
            "/api/observe/classify",
            json={
                "student_id": sid,
                "raw_transcript": "She was distracted and off-task during the activity",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert "category_suggestions" in body
        ids = [s["category_id"] for s in body["category_suggestions"]]
        assert "executive_functioning" in ids
        # Deterministic suggestions ride along even when the LLM is degraded.
        assert body["teacher_confirmation_required"] is True
        assert body["writes_made"] == 0


# ---------------------------------------------------------------------------
# 8. Tier 2 school profile config
# ---------------------------------------------------------------------------

def test_read_school_profile_defaults_when_missing(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from src.lingua_viva.config import read_school_profile

    profile = read_school_profile()
    assert profile["category_labels"] == {}
    assert profile["hidden_categories"] == ["advanced_enrichment"]


def test_read_school_profile_custom_labels(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from src.lingua_viva.config import read_school_profile, school_profile_path

    path = school_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "category_labels": {
                    "learning_and_cognition": "Learning & Cognition (IB)"
                },
                "hidden_categories": [],
            }
        )
    )
    profile = read_school_profile()
    assert profile["category_labels"]["learning_and_cognition"] == "Learning & Cognition (IB)"
    assert profile["hidden_categories"] == []


def test_read_school_profile_corrupt_json_degrades(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from src.lingua_viva.config import read_school_profile, school_profile_path

    path = school_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    profile = read_school_profile()
    assert profile["hidden_categories"] == ["advanced_enrichment"]


def test_school_profile_endpoint(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        res = client.get("/api/school-profile")
        assert res.status_code == 200
        body = res.json()
        # IDs are immutable — the endpoint only ever ships labels/visibility
        # (+ teacher display names, SPEC_LV_MULTI_TEACHER_TRIANGULATION
        # 2026-08-01 operator ruling: names live in Tier 2 config only;
        # + own_teacher_id, teacher-identity P1 2026-08-02).
        assert set(body.keys()) == {
            "category_labels",
            "hidden_categories",
            "teacher_display_names",
            "own_teacher_id",
        }


# ---------------------------------------------------------------------------
# 9. Migration: background_notes lands on a pre-existing DB
# ---------------------------------------------------------------------------

def test_background_notes_migration_on_existing_db(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    db = tmp_path / "s.db"
    with StudentLensStore(db_path=db) as store:
        sid = store.create_lens(display_name="Test Student")
    # Simulate an older DB missing the column.
    import sqlite3

    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(students)")]
    assert "background_notes" in cols
    conn.close()
    # Re-open: migration guard must be idempotent.
    with StudentLensStore(db_path=db) as store:
        lens = store.get_lens(sid)
        assert lens["background_notes"] == ""
