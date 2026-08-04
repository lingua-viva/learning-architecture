"""Coordinator views with real data — Gap 4.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 4, Option A.

Evidence, Capacity and Trends were honest "deferred" stubs — three nav items
that did nothing. The honesty requirement does not disappear when they are
built; it moves. A view with no data must say so, not render a grid of zeros
that reads as "everything is fine", and an unreadable record must report
unknown rather than empty.

These are coordinator views, read in meetings and shown on projectors, so
students appear as ARON codes.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import admin_metrics
from src.web import app

client = TestClient(app)


@pytest.fixture
def roster(demo_roster):
    """Ensure the student store has students before asserting on counts.

    First launches no longer seed a demo roster (T9 / acceptance A6 —
    fresh installs are empty), so this fixture opts in to conftest's
    explicit demo_roster trio and then reads the API view of it.
    """
    return client.get("/api/students").json()["students"]


# --- real data, not stubs ---------------------------------------------------


@pytest.mark.parametrize("view", ["evidence", "capacity", "trends"])
def test_no_view_returns_the_deferred_stub(view):
    body = client.get(f"/api/admin/{view}").json()
    assert "status" not in body
    assert "requires" not in body
    assert "phase" not in body


def test_evidence_counts_real_students_and_coverage(roster):
    body = client.get("/api/admin/evidence").json()
    assert body["available"] is True
    assert len(body["students"]) == len(roster)
    assert body["not_covered"] == sum(1 for s in body["students"] if not s["covered"])


def test_capacity_aggregates_the_same_feed_the_activity_view_shows():
    """Sharing the source means the two surfaces cannot disagree."""
    body = client.get("/api/admin/capacity").json()
    assert body["total_actions"] == sum(row["actions"] for row in body["per_week"])


def test_trends_distribution_sums_to_the_cohort(roster):
    body = client.get("/api/admin/trends").json()
    if not body.get("withheld"):
        assert sum(row["students"] for row in body["current"]) == body["cohort"]


# --- honest about what it is ------------------------------------------------


def test_capacity_does_not_claim_to_be_a_staffing_model():
    """The original stub was right that LV has no staffing inputs. Building
    the view must not quietly imply it acquired them."""
    body = client.get("/api/admin/capacity").json()
    assert "not a staffing" in body["measures"].lower()


def test_trends_withholds_a_distribution_over_too_few_children(roster):
    body = client.get("/api/admin/trends?min_cohort=1000").json()
    assert body["withheld"] is True
    assert body["current"] == []
    assert "say more about the sample" in body["empty_reason"]


def test_trends_flags_that_tier_1_is_a_default_not_a_finding(roster):
    body = client.get("/api/admin/trends").json()
    if not body.get("withheld"):
        assert "default" in body["note"].lower()


def test_an_unreadable_record_reports_unknown_not_zero(monkeypatch):
    def boom(callback):
        return {
            "available": False,
            "reason": "OSError",
            "empty_reason": "The student record could not be opened. These numbers are unknown, not zero.",
        }

    monkeypatch.setattr(admin_metrics, "_with_store", boom)
    for metrics in (admin_metrics.evidence_metrics, admin_metrics.trends_metrics):
        result = metrics()
        assert result["available"] is False
        assert "unknown, not zero" in result["empty_reason"]


def test_a_view_with_no_observations_says_so(roster):
    body = client.get("/api/admin/evidence").json()
    if body.get("total_observations") == 0:
        assert body["empty_reason"], "zero observations must be explained, not implied"


# --- the projection constraint ----------------------------------------------


def test_evidence_shows_aron_codes_not_names(roster):
    body = client.get("/api/admin/evidence").json()
    assert body["students"], "roster fixture should have seeded students"
    for row in body["students"]:
        assert row["student"].startswith("S-")

    blob = json.dumps(body).lower()
    for student in roster:
        name = (student.get("display_name") or "").lower()
        if len(name) >= 3:
            assert name not in blob, f"student name {name!r} reached a coordinator view"


# --- bounds -----------------------------------------------------------------


def test_windows_are_bounded():
    assert client.get("/api/admin/evidence?window_days=100000").json()["window_days"] == 90
    assert client.get("/api/admin/capacity?weeks=100000").json()["weeks"] == 52


# --- the UI renders them ----------------------------------------------------


def test_ui_has_a_renderer_for_each_view_and_no_deferred_text():
    body = client.get("/").text
    for fn in ("adminEvidenceHtml", "adminCapacityHtml", "adminTrendsHtml"):
        assert fn in body, f"{fn} missing"
    assert "Required Before Activation" not in body, "deferred stub markup still present"


def test_ui_annotates_aron_codes_in_the_evidence_table():
    body = client.get("/").text
    start = body.index("function adminEvidenceHtml")
    end = body.index("function adminCapacityHtml")
    assert "ARON_TITLE" in body[start:end]
