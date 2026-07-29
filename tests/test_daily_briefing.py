"""Daily view augmentation — Slice 6.

Spec: dev/SPEC_NATIVE_WORKSTATION_SURFACES_2026-07-28.md §Lingua Viva item 2.
Daily showed only the Slack ops schedule. These widgets make it the teacher's
morning briefing: who has not been observed, which support decisions are
waiting, what is still unconfirmed.

Built on BriefService._unobserved and ._rti_pending, which already existed —
this surfaces them rather than reimplementing the rules.

The constraint that matters: Daily is read in staff rooms and projected in
meetings, so every student appears as an anonymous reference, exactly as in
the Activity view.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.web import app

client = TestClient(app)


def test_briefing_returns_the_three_widgets():
    payload = client.get("/api/daily/briefing").json()
    assert payload["readable"] is True
    ids = [widget["id"] for widget in payload["widgets"]]
    assert ids == ["unobserved", "rti_pending", "confirmations"]


def test_every_widget_has_a_count_and_a_readable_detail():
    payload = client.get("/api/daily/briefing").json()
    for widget in payload["widgets"]:
        assert isinstance(widget["count"], int)
        assert widget["detail"]
        assert widget["status"] in {"ok", "attention"}


def test_widgets_with_nothing_waiting_say_so_rather_than_going_blank():
    payload = client.get("/api/daily/briefing").json()
    for widget in payload["widgets"]:
        if widget["count"] == 0:
            assert widget["status"] == "ok"
            assert widget["detail"], "an empty widget must still explain itself"


def test_needs_attention_counts_only_widgets_that_do():
    payload = client.get("/api/daily/briefing").json()
    expected = sum(1 for w in payload["widgets"] if w["status"] == "attention")
    assert payload["needs_attention"] == expected


# --- the projection constraint ---------------------------------------------


def test_no_student_name_appears_in_the_briefing():
    """Daily is read in staff rooms. Names must never reach it."""
    roster = client.get("/api/students").json()["students"]
    blob = json.dumps(client.get("/api/daily/briefing").json()).lower()

    for student in roster:
        name = (student.get("display_name") or "").lower()
        if len(name) >= 3:
            assert name not in blob, f"student name {name!r} leaked into the daily briefing"


def test_students_are_listed_by_anonymous_reference():
    payload = client.get("/api/daily/briefing").json()
    for widget in payload["widgets"]:
        for reference in widget["students"]:
            assert reference.startswith("S-"), f"{reference!r} is not an anonymous reference"


def test_the_note_tells_the_teacher_it_is_safe_to_show():
    payload = client.get("/api/daily/briefing").json()
    assert "anonymous" in payload["note"].lower()


# --- honest failure --------------------------------------------------------


def test_unreadable_student_record_is_reported_not_hidden(monkeypatch):
    """An empty widget set would read as "nothing waiting" — a claim the code
    cannot make when it could not open the record."""
    def boom():
        raise OSError("database is locked")

    monkeypatch.setattr(web, "_student_store_for_brief", boom)

    payload = client.get("/api/daily/briefing").json()
    assert payload["readable"] is False
    assert payload["widgets"] == []
    assert "not the same as having nothing waiting" in payload["note"]


def test_window_is_bounded():
    assert client.get("/api/daily/briefing?days=100000").json()["window_days"] == 90
    # days=0 is a meaningless window, so it falls back to the 7-day default
    # rather than clamping to a 1-day one the caller did not ask for.
    assert client.get("/api/daily/briefing?days=0").json()["window_days"] == 7
    assert client.get("/api/daily/briefing?days=-5").json()["window_days"] == 1


def test_window_is_reflected_in_the_label():
    payload = client.get("/api/daily/briefing?days=21").json()
    unobserved = next(w for w in payload["widgets"] if w["id"] == "unobserved")
    assert "21" in unobserved["label"]


# --- the UI actually calls it ----------------------------------------------


def test_daily_view_renders_the_briefing():
    body = client.get("/").text
    assert "renderDailyBriefing()" in body, "briefing never called from renderDaily"
    assert 'id="daily-briefing"' in body
    assert 'api("/api/daily/briefing")' in body
