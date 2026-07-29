"""Adaptive learning Phase 1 — assessment deltas — Gap 6.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 6, Phase 1 only.

The loop is observe -> assess -> compare -> adjust tier -> differentiate.
Everything but *compare* already existed. This is the comparison step and
nothing more.

The hard requirement, stated twice in the spec and once in its anti-patterns:
**no automatic tier changes**. The system recommends; the teacher decides. So
the most important tests here are the ones asserting nothing gets written.

The second requirement is not overclaiming. Two observations are a line, not
a trend, so a recommendation needs more evidence than a badge does, and
below that bar the module says "not enough yet" rather than inventing a
neutral recommendation the teacher learns to ignore.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import adaptive
from src.web import app

client = TestClient(app)


def _deltas(*directions: str) -> list[dict]:
    """Synthesise a delta run; only `direction` is read by the callers here."""
    return [{"dimension": "reading", "at": f"2026-07-{index + 1:02d}", "direction": d,
             "from": "A1", "to": "A2", "steps": 1}
            for index, d in enumerate(directions)]


# --- the scale --------------------------------------------------------------


def test_the_scale_is_ordered_so_movement_means_something():
    assert adaptive.CEFR_SCALE.index("A1") < adaptive.CEFR_SCALE.index("A2")
    assert adaptive.CEFR_SCALE.index("B1") < adaptive.CEFR_SCALE.index("C1")


def test_an_unknown_level_is_skipped_not_guessed():
    assert adaptive._level_index("not-a-level") is None
    assert adaptive._level_index(None) is None
    assert adaptive._level_index("A2") is not None


# --- the badge --------------------------------------------------------------


def test_no_deltas_reads_as_not_enough_yet():
    signal = adaptive.growth_signal([])
    assert signal["signal"] == adaptive.INSUFFICIENT
    assert signal["delta_count"] == 0
    assert signal["detail"]


@pytest.mark.parametrize("directions,expected", [
    (("growth", "growth"), adaptive.GROWTH),
    (("regression", "regression"), adaptive.REGRESSION),
    (("growth", "regression"), adaptive.STABLE),
    (("stable",), adaptive.STABLE),
    (("growth", "growth", "regression"), adaptive.GROWTH),
])
def test_the_badge_follows_the_balance_of_movement(directions, expected):
    assert adaptive.growth_signal(_deltas(*directions))["signal"] == expected


# --- the recommendation, and its restraint ----------------------------------


def test_no_recommendation_below_the_evidence_threshold():
    """Two moves are a line, not a trend."""
    assert adaptive.tier_recommendation(_deltas("growth", "growth"), 2) is None


def test_no_recommendation_when_movement_is_mixed():
    assert adaptive.tier_recommendation(
        _deltas("growth", "regression", "growth"), 2
    ) is None


def test_consistent_growth_suggests_a_lower_tier():
    rec = adaptive.tier_recommendation(_deltas("growth", "growth", "growth"), 2)
    assert rec["recommendation"] == "consider_lower_tier"
    assert rec["suggested_tier"] == 1
    assert rec["requires_teacher_confirmation"] is True


def test_consistent_regression_suggests_a_higher_tier():
    rec = adaptive.tier_recommendation(_deltas("regression", "regression", "regression"), 1)
    assert rec["recommendation"] == "consider_higher_tier"
    assert rec["suggested_tier"] == 2


def test_no_recommendation_past_the_ends_of_the_scale():
    assert adaptive.tier_recommendation(_deltas("growth", "growth", "growth"), 1) is None
    assert adaptive.tier_recommendation(
        _deltas("regression", "regression", "regression"), 3
    ) is None


def test_thin_evidence_yields_none_not_a_neutral_recommendation():
    """A recommendation a teacher is meant to ignore trains them to ignore
    all of them."""
    assert adaptive.tier_recommendation(_deltas("growth"), 2) is None


# --- nothing is applied automatically ---------------------------------------


def test_this_module_never_changes_a_tier():
    """Parsed, not grepped: the docstring names update_rti_tier() precisely to
    say it is NOT called, so a substring check would fail on its own
    documentation. This asserts on actual call nodes."""
    import ast

    with open(adaptive.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called.add(func.attr)
            elif isinstance(func, ast.Name):
                called.add(func.id)

    for forbidden in ("update_rti_tier", "append_observation", "save_map"):
        assert forbidden not in called, f"the recommender must not call {forbidden}()"


def test_the_route_changes_nothing(monkeypatch):
    client.get("/api/students")
    before = {s["student_id"]: s["rti_current_tier"]
              for s in client.get("/api/students").json()["students"]}

    client.get("/api/students/growth")

    after = {s["student_id"]: s["rti_current_tier"]
             for s in client.get("/api/students").json()["students"]}
    assert before == after, "reading growth changed a support tier"


def test_every_recommendation_demands_confirmation():
    for tier, directions in ((2, ("growth",) * 3), (1, ("regression",) * 3)):
        rec = adaptive.tier_recommendation(_deltas(*directions), tier)
        assert rec["requires_teacher_confirmation"] is True
        assert rec["because"]


# --- routes and surfaces ----------------------------------------------------


def test_growth_route_returns_a_row_per_student():
    client.get("/api/students")
    body = client.get("/api/students/growth").json()
    roster = client.get("/api/students").json()["students"]
    assert len(body["students"]) == len(roster)
    assert body["threshold"] == adaptive.RECOMMENDATION_THRESHOLD
    assert "you decide" in body["note"].lower()


def test_growth_rows_carry_an_aron_reference():
    client.get("/api/students")
    for row in client.get("/api/students/growth").json()["students"]:
        assert row["reference"].startswith("S-")


def test_recommendations_reach_the_daily_briefing():
    client.get("/api/students")
    widgets = {w["id"] for w in client.get("/api/daily/briefing").json()["widgets"]}
    assert "tier_recommendations" in widgets


def test_the_briefing_widget_says_the_teacher_decides():
    client.get("/api/students")
    widget = next(
        w for w in client.get("/api/daily/briefing").json()["widgets"]
        if w["id"] == "tier_recommendations"
    )
    assert "you decide" in widget["detail"].lower() or widget["count"] == 0


def test_students_view_renders_the_badge():
    body = client.get("/").text
    assert "growthBadge(s.student_id)" in body, "no badge in the roster"
    assert 'api("/api/students/growth")' in body
    assert "suggests tier" in body, "recommendation not surfaced in the roster"
