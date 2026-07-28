"""
Tests for src/education/ops_records.py (Lane C, spec §3.3).

Covers: schema round-trip (incl. JSON fields), path resolution through
the lv_home() seam, the coverage status machine (valid AND invalid
transitions), the announcements-for-everyone teacher-filter rule,
needs_review counting, and the privacy-log audit trail (structural
metadata only — never message text).

The suite-wide conftest fixture already redirects LV_OPS_DB_PATH and
LV_PRIVACY_LOG_PATH into tmp_path; tests that assert on specific paths
set their own overrides, which win.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.education.ops_records import (
    CATEGORIES,
    OpsRecord,
    OpsRecordStore,
    default_db_path,
    source_reference,
)
from src.lingua_viva.privacy_log import privacy_log_path


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops" / "ops_records.db"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy_events.ndjson"))
    with OpsRecordStore() as s:
        yield s


def _add_full(store: OpsRecordStore, **overrides) -> OpsRecord:
    kwargs = dict(
        category="absence",
        teacher_id="t-ana",
        actor_slack_id="U111",
        actor_name="Ana",
        date_for="2026-07-28",
        time_window="08:00-15:30",
        periods=[2, 4],
        text_raw="I'm out tomorrow. Fever. Need coverage for 2nd and 4th period.",
        text_clean="Ana out 2026-07-28 (fever); coverage needed periods 2 and 4.",
        source_channel="C0PS",
        source_ts="1721990400.123456",
        thread_ts="1721990300.000100",
        needs_review=False,
        review_reason="",
        extra={"origin": "dm", "confidence": "high"},
    )
    kwargs.update(overrides)
    return store.add_record(**kwargs)


# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------

def test_default_path_resolves_through_lv_home(tmp_path, monkeypatch):
    monkeypatch.delenv("LV_OPS_DB_PATH", raising=False)
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    assert default_db_path() == tmp_path / "lv-home" / "ops" / "ops_records.db"


def test_env_override_wins_over_lv_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "elsewhere.db"))
    assert default_db_path() == tmp_path / "elsewhere.db"


def test_explicit_db_path_argument_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "env.db"))
    with OpsRecordStore(db_path=tmp_path / "arg" / "explicit.db") as s:
        assert s.db_path == tmp_path / "arg" / "explicit.db"
        assert s.db_path.parent.is_dir()  # parent dirs created


# ----------------------------------------------------------------------
# Schema round-trip + JSON fields
# ----------------------------------------------------------------------

def test_schema_round_trip(store):
    record = _add_full(store)
    loaded = store.get_record(record.id)
    assert loaded == record
    assert loaded.category == "absence"
    assert loaded.status == "logged"
    assert loaded.teacher_id == "t-ana"
    assert loaded.actor_slack_id == "U111"
    assert loaded.actor_name == "Ana"
    assert loaded.date_for == "2026-07-28"
    assert loaded.time_window == "08:00-15:30"
    assert loaded.source_channel == "C0PS"
    assert loaded.source_ts == "1721990400.123456"
    assert loaded.thread_ts == "1721990300.000100"
    assert loaded.needs_review is False
    assert loaded.claim_by == ""
    assert loaded.created_at.endswith("+00:00")  # UTC timestamps
    assert loaded.updated_at == loaded.created_at


def test_json_fields_round_trip_types(store):
    record = _add_full(
        store,
        periods=[1, "advisory", 6],
        extra={"nested": {"a": 1}, "flags": ["x", "y"]},
    )
    loaded = store.get_record(record.id)
    assert loaded.periods == [1, "advisory", 6]
    assert isinstance(loaded.periods, list)
    assert loaded.extra == {"nested": {"a": 1}, "flags": ["x", "y"]}
    assert isinstance(loaded.extra, dict)


def test_get_record_missing_returns_none(store):
    assert store.get_record("nope") is None


def test_add_record_rejects_unknown_category(store):
    with pytest.raises(ValueError):
        store.add_record(category="gossip")


def test_all_spec_categories_accepted(store):
    for category in CATEGORIES:
        record = store.add_record(category=category, teacher_id="t-x", date_for="2026-07-28")
        assert record.category == category


# ----------------------------------------------------------------------
# Status machine
# ----------------------------------------------------------------------

def test_coverage_request_defaults_to_open(store):
    record = _add_full(store, category="coverage_request")
    assert record.status == "open"


def test_coverage_open_claimed_confirmed(store):
    record = _add_full(store, category="coverage_request")
    claimed = store.update_status(record.id, "claimed", claim_by="t-ben")
    assert claimed.status == "claimed"
    assert claimed.claim_by == "t-ben"
    assert claimed.claim_at != ""
    assert claimed.updated_at >= record.updated_at
    confirmed = store.update_status(record.id, "confirmed")
    assert confirmed.status == "confirmed"
    assert confirmed.claim_by == "t-ben"  # preserved through confirm


def test_coverage_claim_auto_confirm_direct(store):
    # v1: claim => auto-confirmed, so open -> confirmed directly is legal.
    record = _add_full(store, category="coverage_request")
    confirmed = store.update_status(
        record.id, "confirmed", claim_by="t-ben", claim_at="2026-07-28T09:00:00+00:00"
    )
    assert confirmed.status == "confirmed"
    assert confirmed.claim_by == "t-ben"
    assert confirmed.claim_at == "2026-07-28T09:00:00+00:00"


def test_non_coverage_logged_to_resolved(store):
    record = _add_full(store, category="announcement")
    resolved = store.update_status(record.id, "resolved")
    assert resolved.status == "resolved"


def test_needs_review_to_resolved_and_logged(store):
    a = _add_full(store, category="facilities", needs_review=True, review_reason="ambiguous")
    assert a.status == "needs_review"
    assert a.needs_review is True
    resolved = store.update_status(a.id, "resolved")
    assert resolved.status == "resolved"
    assert resolved.needs_review is False  # leaving review clears the flag

    b = _add_full(store, category="reminder", needs_review=True)
    logged = store.update_status(b.id, "logged")
    assert logged.status == "logged"
    assert logged.needs_review is False


@pytest.mark.parametrize(
    "category,start_kwargs,bad_status",
    [
        ("announcement", {}, "claimed"),  # coverage-only status on non-coverage
        ("absence", {}, "open"),
        ("schedule_change", {}, "confirmed"),
        ("coverage_request", {}, "logged"),  # coverage never uses logged-machine
        ("announcement", {}, "sideways"),  # unknown status
    ],
)
def test_invalid_status_for_category_rejected(store, category, start_kwargs, bad_status):
    record = _add_full(store, category=category, **start_kwargs)
    with pytest.raises(ValueError):
        store.update_status(record.id, bad_status)


def test_coverage_withdrawal_open_to_resolved(store):
    """Cancel on the absence flow withdraws the coverage request."""
    cov = _add_full(store, category="coverage_request")
    withdrawn = store.update_status(cov.id, "resolved")
    assert withdrawn.status == "resolved"
    with pytest.raises(ValueError):
        store.update_status(cov.id, "claimed")  # withdrawn is terminal


def test_update_extra_merges(store):
    rec = _add_full(store, category="absence")
    store.update_extra(rec.id, lesson_notes="see shared drive folder")
    updated = store.update_extra(rec.id, emergency_plan=True)
    assert updated.extra["lesson_notes"] == "see shared drive folder"
    assert updated.extra["emergency_plan"] is True


def test_invalid_transitions_rejected(store):
    cov = _add_full(store, category="coverage_request")
    store.update_status(cov.id, "claimed", claim_by="t-ben")
    store.update_status(cov.id, "confirmed")
    with pytest.raises(ValueError):
        store.update_status(cov.id, "claimed")  # confirmed is terminal
    with pytest.raises(ValueError):
        store.update_status(cov.id, "open")  # no going back

    ann = _add_full(store, category="announcement")
    store.update_status(ann.id, "resolved")
    with pytest.raises(ValueError):
        store.update_status(ann.id, "logged")  # resolved is terminal


def test_update_status_unknown_record(store):
    with pytest.raises(ValueError):
        store.update_status("missing", "resolved")


def test_failed_update_does_not_mutate(store):
    record = _add_full(store, category="announcement")
    with pytest.raises(ValueError):
        store.update_status(record.id, "claimed")
    assert store.get_record(record.id).status == "logged"


def test_mark_reviewed(store):
    record = _add_full(store, category="student_logistics", needs_review=True)
    reviewed = store.mark_reviewed(record.id)
    assert reviewed.needs_review is False
    assert reviewed.status == "logged"  # parked needs_review status moves to logged

    # A flagged coverage_request keeps its machine status when reviewed.
    cov = _add_full(store, category="coverage_request", needs_review=True)
    assert cov.status == "open" and cov.needs_review is True
    reviewed_cov = store.mark_reviewed(cov.id)
    assert reviewed_cov.needs_review is False
    assert reviewed_cov.status == "open"


def test_mark_reviewed_unknown_record(store):
    with pytest.raises(ValueError):
        store.mark_reviewed("missing")


# ----------------------------------------------------------------------
# records_for_day + needs_review_count
# ----------------------------------------------------------------------

def test_records_for_day_teacher_filtering(store):
    day = "2026-07-28"
    mine = _add_full(store, category="absence", teacher_id="t-ana", date_for=day)
    announce = _add_full(store, category="announcement", teacher_id="t-admin", date_for=day)
    schedule = _add_full(store, category="schedule_change", teacher_id="t-admin", date_for=day)
    theirs = _add_full(store, category="facilities", teacher_id="t-ben", date_for=day)
    other_day = _add_full(store, category="absence", teacher_id="t-ana", date_for="2026-07-29")

    for_ana = {r.id for r in store.records_for_day(day, teacher_id="t-ana")}
    # Own record + broadcasts, NOT another teacher's facilities record.
    assert for_ana == {mine.id, announce.id, schedule.id}

    for_ben = {r.id for r in store.records_for_day(day, teacher_id="t-ben")}
    assert for_ben == {theirs.id, announce.id, schedule.id}

    everyone = {r.id for r in store.records_for_day(day)}
    assert everyone == {mine.id, announce.id, schedule.id, theirs.id}
    assert other_day.id not in everyone


def test_records_for_day_ordering_is_stable(store):
    day = "2026-07-28"
    first = _add_full(store, category="announcement", date_for=day)
    second = _add_full(store, category="announcement", date_for=day)
    ids = [r.id for r in store.records_for_day(day)]
    assert ids.index(first.id) < ids.index(second.id)


def test_needs_review_count(store):
    day = "2026-07-28"
    _add_full(store, category="facilities", teacher_id="t-ana", date_for=day, needs_review=True)
    _add_full(store, category="announcement", teacher_id="t-admin", date_for=day, needs_review=True)
    _add_full(store, category="absence", teacher_id="t-ben", date_for=day, needs_review=True)
    _add_full(store, category="absence", teacher_id="t-ana", date_for=day)  # not flagged

    assert store.needs_review_count(day) == 3
    # Ana sees her own flagged record + the flagged broadcast, not Ben's.
    assert store.needs_review_count(day, teacher_id="t-ana") == 2
    assert store.needs_review_count("2026-07-29") == 0


# ----------------------------------------------------------------------
# Privacy-log audit trail
# ----------------------------------------------------------------------

def test_audit_entries_written_for_add_and_update(store):
    record = _add_full(store, category="coverage_request")
    store.update_status(record.id, "claimed", claim_by="t-ben")
    store.mark_reviewed(record.id)

    log_text = privacy_log_path().read_text(encoding="utf-8")
    lines = [json.loads(line) for line in log_text.splitlines() if line.strip()]
    types = [entry["event_type"] for entry in lines]
    assert "ops_record_added" in types
    assert "ops_record_updated" in types
    assert "ops_record_reviewed" in types

    added = next(e for e in lines if e["event_type"] == "ops_record_added")
    assert f"record={record.id}" in added["detail"]
    assert "category=coverage_request" in added["detail"]
    assert "source=slack://C0PS/p1721990400123456" in added["detail"]


def test_audit_log_never_contains_message_text(store):
    secret = "Sofia's mother will pick her up early for a medical appointment"
    _add_full(
        store,
        category="student_logistics",
        text_raw=secret,
        text_clean="Early pickup logged for one student.",
    )
    log_text = privacy_log_path().read_text(encoding="utf-8")
    assert "Sofia" not in log_text
    assert "medical" not in log_text
    assert "Early pickup" not in log_text  # not even the cleaned text
    assert "ops_record_added" in log_text


def test_source_reference_shapes():
    assert source_reference("C0PS", "1721990400.123456") == "slack://C0PS/p1721990400123456"
    assert source_reference("", "") == "local"
    assert source_reference("C0PS", "") == "slack://C0PS/p0"
