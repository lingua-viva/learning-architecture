"""ARON — Anonymized Reference for Observation Notes (Gap 3).

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 3.

The mechanism already existed and worked; the gap was that it had no name in
runtime code and no explanation anywhere a teacher would look. Someone seeing
`S-8D2F6FD74015` in the Daily briefing had no way to learn what it was or why
it was there instead of a child's name.

So the substance here is naming and disclosure — but the rename must not
break the thing it renames, which is what most of these tests check.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.lingua_viva import governance
from src.web import app

client = TestClient(app)


# --- the rename does not break the mechanism --------------------------------


def test_aron_ref_produces_a_stable_code():
    first = governance.aron_ref("student-marco")
    assert first.startswith("S-")
    assert governance.aron_ref("student-marco") == first


def test_different_students_get_different_codes():
    assert governance.aron_ref("student-marco") != governance.aron_ref("student-ana")


def test_the_code_does_not_contain_the_student_id():
    assert "marco" not in governance.aron_ref("student-marco").lower()


def test_the_old_name_still_works():
    """Kept so any external caller or older branch keeps working."""
    assert governance.anonymous_student_ref is governance.aron_ref
    assert governance.anonymous_student_ref("student-marco") == governance.aron_ref("student-marco")


# --- it is explained ---------------------------------------------------------


def test_aron_ref_documents_what_aron_stands_for():
    doc = governance.aron_ref.__doc__ or ""
    assert "Anonymized Reference for Observation Notes" in doc
    assert "non-reversible" in doc


def test_aron_status_reports_active_and_where_it_applies():
    status = governance.aron_status()
    assert status["name"] == "ARON"
    assert status["expanded"] == "Anonymized Reference for Observation Notes"
    assert status["active"] is True
    assert status["explanation"]
    assert {"Activity view", "Daily briefing", "Observation exports"} <= set(status["applies_to"])


def test_aron_status_does_not_leak_the_signing_key():
    status = governance.aron_status()
    key = governance._load_or_create_signing_key().decode("ascii")
    assert key not in str(status)
    # a short fingerprint is fine and useful; the key itself is not
    assert len(status["key_fingerprint"]) == 16


# --- surfaced to the teacher -------------------------------------------------


def test_privacy_route_reports_aron():
    payload = client.get("/api/privacy").json()
    assert "aron" in payload
    assert payload["aron"]["active"] is True


def test_privacy_view_explains_aron():
    body = client.get("/").text
    assert "privacy.aron" in body, "Privacy view never reads the ARON status"
    assert "privacy.aron.explanation" in body


def test_every_place_a_code_appears_carries_an_explanation():
    """A bare S-XXXX with no way to find out what it means is the gap."""
    body = client.get("/").text
    assert "ARON_TITLE" in body
    assert "Anonymized Reference for Observation Notes" in body
    # Activity pending items, Daily briefing badges, and the export pack.
    assert "aronBadge(ref)" in body, "Daily briefing codes have no tooltip"
    assert body.count("ARON_TITLE") >= 5, "not every code display site is annotated"


def test_the_explanation_says_it_cannot_be_reversed():
    """The property a teacher actually needs to trust when projecting."""
    body = client.get("/").text
    assert "cannot be turned back into a name" in body
