"""Absence escalation worked example (W2, 2026-08-09). Synthetic fixtures."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lingua_viva import absence_escalation as ae


@pytest.fixture()
def state_home(monkeypatch, tmp_path):
    home = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(home))
    return home


# 2026-08 reference dates: 2026-08-03 is a Monday.
MON = date(2026, 8, 3)
TUE = date(2026, 8, 4)
WED = date(2026, 8, 5)
THU = date(2026, 8, 6)
FRI = date(2026, 8, 7)
NEXT_MON = date(2026, 8, 10)
NEXT_TUE = date(2026, 8, 11)


def test_record_absence_writes_ledger_and_dedupes(state_home):
    first = ae.record_absence("s-nora", MON)
    assert first["duplicate"] is False
    again = ae.record_absence("s-nora", "2026-08-03")
    assert again["duplicate"] is True
    entries = [
        json.loads(line)
        for line in ae.absences_path().read_text().splitlines()
        if line.strip()
    ]
    assert len(entries) == 1


def test_record_absence_rejects_missing_student(state_home):
    with pytest.raises(ValueError):
        ae.record_absence("", MON)


def test_three_consecutive_school_days_escalates(state_home):
    for day in (MON, TUE, WED):
        ae.record_absence("s-nora", day)
    pending = ae.check_escalations(today=THU)
    reasons = {(e["student_id"], e["reason"]) for e in pending}
    assert ("s-nora", "consecutive") in reasons


def test_two_consecutive_days_does_not_escalate(state_home):
    ae.record_absence("s-nora", MON)
    ae.record_absence("s-nora", TUE)
    assert ae.check_escalations(today=WED) == []


def test_weekend_gap_still_counts_as_consecutive(state_home):
    """Thu + Fri + Mon are three consecutive SCHOOL days."""
    for day in (THU, FRI, NEXT_MON):
        ae.record_absence("s-marco", day)
    pending = ae.check_escalations(today=NEXT_TUE)
    assert any(
        e["student_id"] == "s-marco" and e["reason"] == "consecutive" for e in pending
    )


def test_absent_holiday_calendar_preserves_weekday_behavior(state_home):
    assert ae.load_holiday_calendar()["configured"] is False
    for day in (MON, TUE, WED):
        ae.record_absence("s-nora", day)
    pending = ae.check_escalations(today=THU)
    assert any(e["student_id"] == "s-nora" and e["reason"] == "consecutive" for e in pending)


def test_holiday_break_skips_school_days_and_prevents_false_consecutive(state_home):
    calendar = state_home / "calendar" / "holidays.yaml"
    calendar.parent.mkdir(parents=True)
    calendar.write_text(
        "holidays:\n"
        "  - start: 2026-08-04\n"
        "    end: 2026-08-06\n"
        "    label: Midweek break\n",
        encoding="utf-8",
    )
    for day in (MON, TUE, WED):
        ae.record_absence("s-nora", day)

    loaded = ae.load_holiday_calendar()
    assert loaded["configured"] is True
    assert "2026-08-05" in loaded["holiday_dates"]
    pending = ae.check_escalations(today=FRI)
    assert not any(e["student_id"] == "s-nora" and e["reason"] == "consecutive" for e in pending)


def test_nonconsecutive_gap_resets_run(state_home):
    for day in (MON, WED, FRI):  # gaps on Tue/Thu
        ae.record_absence("s-marco", day)
    pending = ae.check_escalations(today=NEXT_MON)
    assert not any(e["reason"] == "consecutive" for e in pending)


def test_five_in_twenty_school_days_escalates(state_home):
    for day in (MON, WED, FRI, NEXT_MON, NEXT_TUE):  # 5 non-consecutive
        ae.record_absence("s-nora", day)
    pending = ae.check_escalations(today=NEXT_TUE)
    windows = [e for e in pending if e["reason"] == "window"]
    assert len(windows) == 1
    assert windows[0]["count"] == 5
    assert windows[0]["escalate_to"] == "coordinator"


def test_configurable_thresholds(state_home):
    ae.record_absence("s-nora", MON)
    ae.record_absence("s-nora", TUE)
    pending = ae.check_escalations(today=WED, consecutive_threshold=2)
    assert any(e["reason"] == "consecutive" for e in pending)


def test_recheck_does_not_duplicate_pending_escalations(state_home):
    for day in (MON, TUE, WED):
        ae.record_absence("s-nora", day)
    first = ae.check_escalations(today=THU)
    second = ae.check_escalations(today=THU)
    assert len(first) == len(second) == 1


def test_escalation_enqueues_content_free_notification(state_home):
    for day in (MON, TUE, WED):
        ae.record_absence("s-nora", day)
    pending = ae.check_escalations(today=THU)
    assert pending[0]["notification_id"].startswith("sgn-")
    queue = state_home / "safeguarding" / "notifications.ndjson"
    entries = [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["kind"] == "absence_escalation"
    assert entries[0]["status"] == "pending_config"  # channel unset by default
    assert "s-nora" not in json.dumps(entries[0])  # id-only, no student ref


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src.web import app

    return TestClient(app)


def _headers(role):
    return {"X-LV-User-Id": "u1", "X-LV-Role": role, "X-LV-Teacher-Id": "t1"}


def test_post_absence_and_get_escalations_local_mode(client, state_home):
    # Default LV_AUTH_MODE=off: local single-user machine.
    for day in ("2026-08-03", "2026-08-04", "2026-08-05"):
        response = client.post(
            "/api/absences", json={"student_id": "s-nora", "date": day}
        )
        assert response.status_code == 200
        assert response.json()["recorded"] is True
    listing = client.get("/api/absences")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1


def test_post_absence_validates_body(client, state_home):
    response = client.post("/api/absences", json={"student_id": "s-nora"})
    assert response.status_code == 400
    response = client.post(
        "/api/absences", json={"student_id": "s-nora", "date": "not-a-date"}
    )
    assert response.status_code == 400


def test_get_escalations_denied_to_teacher_in_auth_mode(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    response = client.get("/api/absences", headers=_headers("teacher"))
    assert response.status_code == 403
    ok = client.get("/api/absences", headers=_headers("coordinator"))
    assert ok.status_code == 200


def test_post_absence_allowed_for_teacher_in_auth_mode(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    response = client.post(
        "/api/absences",
        json={"student_id": "s-nora", "date": "2026-08-03"},
        headers=_headers("teacher"),
    )
    assert response.status_code == 200


def test_absence_calendar_route_reports_configured_holidays(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    calendar = state_home / "calendar" / "holidays.json"
    calendar.parent.mkdir(parents=True)
    calendar.write_text(
        json.dumps({"holidays": [{"date": "2026-08-04", "label": "Campus closure"}]}),
        encoding="utf-8",
    )
    denied = client.get("/api/absences/calendar", headers=_headers("teacher"))
    assert denied.status_code == 403
    response = client.get("/api/absences/calendar", headers=_headers("coordinator"))
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["holiday_dates"] == ["2026-08-04"]
