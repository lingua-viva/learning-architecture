"""Safeguarding severity tier + restricted routing (W2, 2026-08-09).

All names are synthetic per publication-policy.md ("Nora Rossi",
"Marco Bianchi", "Rafael" are established synthetic fixtures).
Runtime state is hermetic: tests set LV_STATE_HOME under tmp_path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lingua_viva import safeguarding as sg


@pytest.fixture()
def state_home(monkeypatch, tmp_path):
    home = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(home))
    return home


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

def test_clear_disclosure_phrase_is_red():
    result = sg.classify_severity(
        "Nora Rossi told me that someone at home hurts her and asked me not to tell anyone."
    )
    assert result.tier == sg.RED
    assert any(m["category"] == "disclosure" for m in result.matched)


def test_explicit_abuse_vocabulary_is_red():
    result = sg.classify_severity(
        "Possible neglect at home — raising a child protection concern for Marco Bianchi."
    )
    assert result.tier == sg.RED


def test_ambiguous_indicator_rounds_up_to_red():
    """Bruising with no explanation could be innocent — fail closed says
    the coordinator decides, not the classifier."""
    result = sg.classify_severity(
        "Marco Bianchi had unexplained bruises on his arm during PE today."
    )
    assert result.tier == sg.RED
    assert result.rounded_up is True


def test_wellbeing_concern_is_amber():
    result = sg.classify_severity(
        "Nora Rossi was tearful this morning and seemed withdrawn during group work."
    )
    assert result.tier == sg.AMBER


def test_normal_teaching_observation_is_green():
    result = sg.classify_severity(
        "Rafael read the passage fluently and self-corrected twice — strong B1 reading sample."
    )
    assert result.tier == sg.GREEN


def test_empty_transcript_rounds_up_to_amber():
    result = sg.classify_severity("")
    assert result.tier == sg.AMBER
    assert result.rounded_up is True


def test_secondary_personal_context_signal_raises_green_to_amber():
    # No RED/AMBIGUOUS/AMBER pattern of ours, but the existing
    # personal_context category classifier fires (>= threshold).
    result = sg.classify_severity(
        "Rafael mentioned his family situation and their housing changed this month."
    )
    assert result.tier in (sg.AMBER, sg.RED)  # never lowered below AMBER
    assert result.tier != sg.GREEN


# ---------------------------------------------------------------------------
# filter_for_role chokepoint
# ---------------------------------------------------------------------------

ITEMS = [{"entry_id": "sg-1"}, {"entry_id": "sg-2"}]


@pytest.mark.parametrize("role", ["teacher", "co_teacher", "parent", "", None, "unknown_role"])
def test_filter_for_role_denies_below_coordinator(role):
    assert sg.filter_for_role(ITEMS, role) == []


@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_filter_for_role_allows_coordinator_and_admin(role):
    assert sg.filter_for_role(ITEMS, role) == ITEMS


# ---------------------------------------------------------------------------
# Capture wrapper — RED containment
# ---------------------------------------------------------------------------

def _make_pipeline(tmp_path):
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    store = StudentLensStore(db_path=tmp_path / "lens.db")
    store.create_lens(student_id="s-nora", display_name="Nora Rossi")
    return store, ObservationCapturePipeline(store=store)


def _observation_count(store, student_id):
    row = store._conn.execute(
        "SELECT COUNT(*) AS c FROM observations WHERE student_id = ?", (student_id,)
    ).fetchone()
    return row["c"]


def test_red_capture_never_lands_in_normal_observation_store(state_home, tmp_path):
    store, pipeline = _make_pipeline(tmp_path)
    result = sg.capture_with_safeguarding(
        pipeline,
        student_id="s-nora",
        teacher_id="teacher_1",
        raw_transcript=(
            "Nora Rossi told me someone hurts her at home and begged me not to tell."
        ),
        template_type="general",
    )
    assert result["restricted"] is True
    assert result["observation_stored"] is False
    # RED item is NOT in the SQLite store the daily brief reads.
    assert _observation_count(store, "s-nora") == 0
    # It IS in the restricted ledger.
    ledger = state_home / "safeguarding" / "restricted.ndjson"
    assert ledger.exists()
    entries = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["entry_id"] == result["entry_id"]
    assert entries[0]["severity"]["tier"] == sg.RED


def test_red_capture_queues_pending_config_notification(state_home, tmp_path):
    _, pipeline = _make_pipeline(tmp_path)
    result = sg.capture_with_safeguarding(
        pipeline,
        student_id="s-nora",
        teacher_id="teacher_1",
        raw_transcript="She said someone hurt her and asked me not to tell anyone.",
        template_type="general",
    )
    # No safeguarding_channel configured -> stays queued locally.
    assert result["notification"]["status"] == "pending_config"
    queue = state_home / "safeguarding" / "notifications.ndjson"
    entries = [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    # Content discipline: the notification never carries observation text
    # or the student's name.
    serialized = json.dumps(entries[0]).lower()
    assert "nora" not in serialized
    assert "hurt" not in serialized


def test_notification_queued_when_channel_configured(state_home):
    config_dir = state_home / "safeguarding"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps({"safeguarding_channel": "C-SAFEGUARDING"})
    )
    entry = sg.enqueue_notification(kind="safeguarding_red", ref_id="sg-test")
    assert entry["status"] == "queued"
    assert entry["channel"] == "C-SAFEGUARDING"


def test_green_capture_delegates_to_normal_pipeline(state_home, tmp_path):
    store, pipeline = _make_pipeline(tmp_path)
    result = sg.capture_with_safeguarding(
        pipeline,
        student_id="s-nora",
        teacher_id="teacher_1",
        raw_transcript="I noticed Nora read the passage fluently at B1 level.",
        template_type="cefr",
        cefr_dimension="reading",
        cefr_level_observed="B1",
        cefr_direction="progressing",
    )
    assert result["restricted"] is False
    assert result["safeguarding"]["tier"] == sg.GREEN
    assert _observation_count(store, "s-nora") == 1
    assert not (state_home / "safeguarding" / "restricted.ndjson").exists()


def test_read_restricted_goes_through_chokepoint(state_home):
    sg.record_red_observation(
        student_id="s-nora",
        teacher_id="teacher_1",
        raw_transcript="disclosure text",
    )
    assert sg.read_restricted("teacher") == []
    assert sg.read_restricted("parent") == []
    assert len(sg.read_restricted("coordinator")) == 1
    assert len(sg.read_restricted("admin")) == 1


def test_restricted_status_lifecycle_preserves_original_content(state_home):
    entry = sg.record_red_observation(
        student_id="s-nora",
        teacher_id="teacher_1",
        raw_transcript="Nora said someone hurt her.",
        teacher_edited_transcript="Nora said someone hurt her at home.",
    )
    acknowledged = sg.update_restricted_status(
        entry_id=entry["entry_id"],
        status="acknowledged",
        reviewed_by="coordinator-1",
    )
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["raw_transcript"] == "Nora said someone hurt her."
    assert acknowledged["teacher_edited_transcript"] == "Nora said someone hurt her at home."
    assert acknowledged["review_audit"][0]["from"] == "open"
    assert acknowledged["review_audit"][0]["to"] == "acknowledged"

    closed = sg.update_restricted_status(
        entry_id=entry["entry_id"],
        status="closed",
        reviewed_by="coordinator-1",
        closed_reason="Transferred to the school's designated safeguarding lead.",
    )
    assert closed["status"] == "closed"
    assert closed["closed_reason"].startswith("Transferred")
    assert len(closed["review_audit"]) == 2
    assert closed["review_audit"][1]["to"] == "closed"
    reread = sg.read_restricted("coordinator")[0]
    assert reread["raw_transcript"] == entry["raw_transcript"]
    assert reread["severity"] == entry["severity"]


def test_restricted_status_rewrite_accepts_legacy_open_status(state_home):
    legacy = {
        "entry_id": "sg-legacy",
        "student_id": "s-nora",
        "teacher_id": "teacher_1",
        "raw_transcript": "restricted narrative",
        "status": "awaiting_coordinator_review",
    }
    ledger = state_home / "safeguarding" / "restricted.ndjson"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    updated = sg.update_restricted_status(
        entry_id="sg-legacy",
        status="acknowledged",
        reviewed_by="coordinator-1",
    )
    assert updated["status"] == "acknowledged"
    assert updated["review_audit"][0]["from"] == "open"


def test_restricted_status_requires_close_reason(state_home):
    entry = sg.record_red_observation(
        student_id="s-nora", teacher_id="teacher_1", raw_transcript="disclosure"
    )
    with pytest.raises(ValueError, match="closed_reason"):
        sg.update_restricted_status(
            entry_id=entry["entry_id"],
            status="closed",
            reviewed_by="coordinator-1",
        )


# ---------------------------------------------------------------------------
# Route: /api/safeguarding/restricted
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src.web import app

    return TestClient(app)


def _headers(role, user="u1"):
    return {"X-LV-User-Id": user, "X-LV-Role": role, "X-LV-Teacher-Id": "t1"}


def test_restricted_route_forbidden_for_teacher(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    response = client.get("/api/safeguarding/restricted", headers=_headers("teacher"))
    assert response.status_code == 403


def test_restricted_route_unauthenticated_is_401(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    response = client.get("/api/safeguarding/restricted")
    assert response.status_code == 401


def test_restricted_route_unknown_role_fails_closed(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    response = client.get(
        "/api/safeguarding/restricted", headers=_headers("superuser")
    )
    assert response.status_code == 403


def test_restricted_route_coordinator_sees_items(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    sg.record_red_observation(
        student_id="s-nora", teacher_id="teacher_1", raw_transcript="disclosure"
    )
    response = client.get(
        "/api/safeguarding/restricted", headers=_headers("coordinator")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["student_id"] == "s-nora"


def test_restricted_status_route_forbidden_for_teacher(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    entry = sg.record_red_observation(
        student_id="s-nora", teacher_id="teacher_1", raw_transcript="disclosure"
    )
    response = client.post(
        f"/api/safeguarding/restricted/{entry['entry_id']}/status",
        headers=_headers("teacher"),
        json={"status": "acknowledged"},
    )
    assert response.status_code == 403


def test_restricted_status_route_coordinator_updates_entry(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    entry = sg.record_red_observation(
        student_id="s-nora", teacher_id="teacher_1", raw_transcript="disclosure"
    )
    response = client.post(
        f"/api/safeguarding/restricted/{entry['entry_id']}/status",
        headers=_headers("coordinator", user="coord-1"),
        json={"status": "acknowledged"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] is True
    assert body["entry"]["status"] == "acknowledged"
    assert body["entry"]["reviewed_by"] == "coord-1"
    assert body["entry"]["review_audit"][0]["reviewed_by"] == "coord-1"


def test_household_adult_violence_disclosure_is_red():
    """Class lock (integration fix 2026-08-09): direct disclosures of an adult
    at home hitting the child classified GREEN because the physical_abuse
    pattern lacked present-tense verb forms and required the verb to sit
    immediately before "at home". Any household-adult + violence-verb phrasing
    must be RED."""
    phrases = [
        "The student disclosed that an adult at home hits them.",
        "He told me his dad hits him at home.",
        "She says her stepdad smacks her when she gets things wrong.",
        "Rafael said he was beaten by his uncle last weekend.",
        "Marco mentioned his mother punches him.",
    ]
    for phrase in phrases:
        result = sg.classify_severity(phrase)
        assert result.tier == sg.RED, phrase
        assert any(
            m["category"] in ("physical_abuse", "disclosure") for m in result.matched
        ), phrase


def test_peer_conflict_without_adult_is_not_red():
    """Playground peer conflict stays out of the restricted ledger — it is a
    behavior observation, not a safeguarding disclosure."""
    result = sg.classify_severity(
        "During recess Marco hit another student and both were separated."
    )
    assert result.tier != sg.RED


# ---------------------------------------------------------------------------
# Live-wire tests (integration 2026-08-09): the three production capture
# sites must route through capture_with_safeguarding — a RED transcript
# never reaches the lens store, from any entry point.
# ---------------------------------------------------------------------------

RED_TRANSCRIPT = "He told me his dad hits him at home."


def test_observe_capture_endpoint_diverts_red(client, state_home):
    response = client.post(
        "/api/observe/capture",
        json={
            "student_id": "student-marco",
            "transcript": RED_TRANSCRIPT,
            "template_type": "general",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["restricted"] is True
    assert body["observation_stored"] is False
    assert "safeguarding" in body
    # It landed in the restricted ledger, and only there.
    ledger = sg.read_restricted("coordinator")
    assert len(ledger) == 1
    assert ledger[0]["student_id"] == "student-marco"


def test_slack_bot_diverts_red_and_acks_content_free(tmp_path, state_home):
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.slack_bot import ACK_RESTRICTED, SlackObservationBot
    from src.education.student_lens import StudentLensStore

    store = StudentLensStore(db_path=tmp_path / "test.db")
    store.create_lens(student_id="s1", display_name="Test Student")
    log = []
    bot = SlackObservationBot(
        capture_pipeline=ObservationCapturePipeline(store=store),
        teacher_channel_map={"C123": "teacher_1"},
        signing_secret="test-signing-secret",
        post_message=lambda channel, text: log.append((channel, text)),
    )
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "EvRed1",
        "event": {
            "type": "message",
            "channel": "C123",
            "text": f"[student:s1] {RED_TRANSCRIPT}",
        },
    })
    assert result["ok"] is True
    assert result["restricted"] is True
    assert log == [("C123", ACK_RESTRICTED)]
    # Nothing entered the normal lens store; the restricted ledger has it.
    assert store.export_lens("s1")["observations"] == []
    assert len(sg.read_restricted("coordinator")) == 1
