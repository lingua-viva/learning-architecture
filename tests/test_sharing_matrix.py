"""Stakeholder sharing matrix (W2, 2026-08-09). Synthetic fixtures only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lingua_viva import sharing_matrix as sm


# ---------------------------------------------------------------------------
# allowed_view
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["teacher", "co_teacher", "parent"])
def test_safeguarding_denied_below_coordinator_and_to_parents(role):
    assert sm.allowed_view("safeguarding", role) == sm.NONE


@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_safeguarding_full_for_coordinator_and_admin(role):
    assert sm.allowed_view("safeguarding", role) == sm.FULL


def test_safeguarding_code_floor_survives_matrix_misedit(monkeypatch):
    """Even if the data row were edited to allow parents, the code-level
    floor in allowed_view keeps it closed."""
    corrupted = {**sm.SHARING_MATRIX, "safeguarding": {r: sm.FULL for r in sm.ROLES}}
    monkeypatch.setattr(sm, "SHARING_MATRIX", corrupted)
    assert sm.allowed_view("safeguarding", "parent") == sm.NONE
    assert sm.allowed_view("safeguarding", "teacher") == sm.NONE
    assert sm.allowed_view("safeguarding", "coordinator") == sm.FULL


def test_unknown_info_type_fails_closed():
    assert sm.allowed_view("salary_data", "admin") == sm.NONE


def test_unknown_role_fails_closed():
    assert sm.allowed_view("academic_progress", "visitor") == sm.NONE
    assert sm.allowed_view("academic_progress", "") == sm.NONE


def test_parent_gets_summary_of_academic_progress():
    assert sm.allowed_view("academic_progress", "parent") == sm.SUMMARY


def test_wellbeing_never_reaches_parents_via_system():
    assert sm.allowed_view("wellbeing", "parent") == sm.NONE


def test_every_matrix_cell_is_a_valid_view():
    for info_type, row in sm.SHARING_MATRIX.items():
        assert set(row) == set(sm.ROLES), f"{info_type} row missing roles"
        for role, view in row.items():
            assert view in sm.VALID_VIEWS, f"{info_type}/{role} = {view!r}"


# ---------------------------------------------------------------------------
# filter_payload
# ---------------------------------------------------------------------------

PAYLOAD = {
    "academic_progress": {"summary": "Reading moved from A2 to B1.", "notes": "raw detail"},
    "safeguarding": {"summary": "restricted", "notes": "restricted detail"},
    "behavior": "Full behavior narrative about Marco Bianchi's group work.",
    "mystery_field": "unclassified content",
}


def test_filter_payload_teacher_drops_safeguarding_and_unknown_keys():
    filtered = sm.filter_payload(PAYLOAD, "teacher")
    assert "safeguarding" not in filtered
    assert "mystery_field" not in filtered
    assert filtered["academic_progress"] == PAYLOAD["academic_progress"]
    assert filtered["behavior"] == PAYLOAD["behavior"]


def test_filter_payload_parent_gets_summaries_not_raw_notes():
    filtered = sm.filter_payload(PAYLOAD, "parent")
    assert "safeguarding" not in filtered
    progress = filtered["academic_progress"]
    assert progress["view"] == sm.SUMMARY
    assert progress["summary"] == "Reading moved from A2 to B1."
    assert "raw detail" not in str(progress)


def test_filter_payload_summary_without_prepared_summary_withholds():
    filtered = sm.filter_payload({"behavior": "raw narrative"}, "parent")
    assert filtered["behavior"]["summary"] is None
    assert "raw narrative" not in str(filtered)


def test_filter_payload_coordinator_gets_safeguarding_full():
    filtered = sm.filter_payload(PAYLOAD, "coordinator")
    assert filtered["safeguarding"] == PAYLOAD["safeguarding"]


def test_filter_payload_unknown_role_gets_nothing():
    assert sm.filter_payload(PAYLOAD, "visitor") == {}


def test_parent_recommendation_route_uses_sharing_matrix():
    from pathlib import Path

    html_or_py = (Path(__file__).resolve().parents[1] / "src" / "web.py").read_text(
        encoding="utf-8"
    )
    route_block = html_or_py.split('@app.post("/api/parents/recommendation")', 1)[1].split(
        '@app.post("/api/reflect/note")', 1
    )[0]
    assert "filter_payload(matrix_payload, \"parent\")" in route_block
    assert '"safeguarding": result.get("safeguarding")' in route_block


# ---------------------------------------------------------------------------
# Route: /api/sharing/check
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src.web import app

    return TestClient(app)


def test_sharing_check_route(client):
    response = client.get(
        "/api/sharing/check", params={"info_type": "safeguarding", "role": "teacher"}
    )
    assert response.status_code == 200
    assert response.json()["allowed"] == sm.NONE


def test_sharing_check_route_requires_params(client):
    response = client.get("/api/sharing/check")
    assert response.status_code == 400
