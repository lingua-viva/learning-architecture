"""Action Queue / Activity feed — Slice 3.

Spec: dev/SPEC_NATIVE_WORKSTATION_SURFACES_2026-07-28.md §Lingua Viva item 1.

The LV-specific constraint in that spec is the sharp one: these surfaces get
projected in classrooms and screen-shared in meetings, so no student name may
appear. The feed is built from the trace log (already hash-only) and the
privacy log (event types only), and anything student-linked renders as the
same anonymous reference the governance packs use.

The other thing worth guarding: an empty pending list means "you are caught
up", which is a claim. When the student record cannot be read the feed must
say so instead of rendering that claim.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import activity
from src.web import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.setenv("LV_EXPORT_SIGNING_KEY_PATH", str(tmp_path / "key"))
    yield


def test_empty_feed_explains_itself_rather_than_showing_nothing():
    feed = activity.activity_feed()
    assert feed["entries"] == []
    assert feed["empty_reason"], "an empty feed must say why it is empty"


def test_recorded_questions_appear_with_their_real_route():
    from dataclasses import asdict
    import json
    from pathlib import Path

    from src.lingua_viva.traces import new_trace, trace_path

    local = new_trace("q1", domain="education", model_used="qwen2.5:3b")
    remote = new_trace(
        "q2", domain="education", model_used="openai/gpt-4o", external_calls=1, route="external"
    )
    Path(trace_path()).parent.mkdir(parents=True, exist_ok=True)
    Path(trace_path()).write_text(
        json.dumps(asdict(local)) + "\n" + json.dumps(asdict(remote)) + "\n", encoding="utf-8"
    )

    entries = activity.activity_feed()["entries"]
    routes = {entry["route"] for entry in entries if entry["kind"] == "question"}
    assert routes == {"local", "external"}


def test_privacy_events_become_teacher_readable_actions():
    from src.lingua_viva.privacy_log import log_event

    log_event("observation_saved_locally")
    entries = activity.activity_feed()["entries"]
    labels = {entry["label"] for entry in entries}
    assert "Observation saved" in labels


def test_internal_bookkeeping_events_are_not_dressed_up_as_actions():
    """query_processed_locally is bookkeeping — the trace already covers it,
    and listing it too would double-count every question."""
    from src.lingua_viva.privacy_log import log_event

    log_event("query_processed_locally")
    entries = activity.activity_feed()["entries"]
    assert entries == []


def test_feed_is_newest_first():
    from src.lingua_viva.privacy_log import log_event

    log_event("observation_saved_locally")
    log_event("drive_files_imported")
    entries = activity.activity_feed()["entries"]
    timestamps = [entry["at"] for entry in entries]
    assert timestamps == sorted(timestamps, reverse=True)


def test_limit_is_respected():
    from src.lingua_viva.privacy_log import log_event

    for _ in range(10):
        log_event("observation_saved_locally")
    assert len(activity.activity_feed(limit=3)["entries"]) == 3


# --- the projection constraint ---------------------------------------------


def test_no_student_name_can_reach_the_feed(monkeypatch):
    """The LV constraint: this view gets projected in a classroom."""
    monkeypatch.setattr(
        activity,
        "pending_items",
        lambda: [{
            "reference": "S-ABCDEF123456",
            "label": "Suggestions awaiting your confirmation",
            "count": 2,
            "detail": "Kept out of parent reports until you confirm them.",
        }],
    )
    import json

    blob = json.dumps(activity.activity_feed())
    assert "S-ABCDEF123456" in blob
    assert "marco" not in blob.lower()


def test_pending_uses_an_anonymous_reference_not_a_display_name():
    """Drives the real store rather than a stub, so a future change that
    starts putting display_name in pending_items() fails here."""
    roster = client.get("/api/students").json()["students"]
    names = [(s.get("display_name") or "").lower() for s in roster if s.get("display_name")]

    import json

    blob = json.dumps(activity.pending_items()).lower()
    for name in names:
        if len(name) >= 3:
            assert name not in blob, f"student name {name!r} leaked into the pending list"


def test_unreadable_student_record_does_not_read_as_caught_up(monkeypatch):
    """An empty pending list is a claim. When the record cannot be read the
    feed must say unknown instead of making it."""
    import src.education.student_lens as lens_module

    def boom(*args, **kwargs):
        raise OSError("database is locked")

    monkeypatch.setattr(lens_module, "StudentLensStore", boom)
    monkeypatch.setenv("LV_STUDENT_DB_PATH", __file__)  # exists, but not a db

    pending = activity.pending_items()
    assert pending and pending[0].get("unknown") is True
    assert activity.activity_feed()["pending_total"] is None


# --- route + UI ------------------------------------------------------------


def test_history_route_returns_a_feed():
    response = client.get("/api/actions/history")
    assert response.status_code == 200
    payload = response.json()
    assert "entries" in payload and "pending" in payload
    assert payload["privacy_note"]


def test_history_route_bounds_the_limit():
    assert client.get("/api/actions/history?limit=99999").status_code == 200
    assert client.get("/api/actions/history?limit=0").status_code == 200


def test_activity_view_is_reachable_and_wired():
    body = client.get("/").text
    assert '["actions", "Activity"' in body, "no Activity entry in the nav"
    assert "actions: renderActions," in body, "view not registered"
    assert 'api("/api/actions/history")' in body
