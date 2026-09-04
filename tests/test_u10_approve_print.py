"""U10 — Summaries: approve and print, behind a minimum-evidence gate (readiness day 7).

Before this file the approve / print half of the parent report (parent_report.approve,
ParentArtifact.to_print_html / to_printable_text) was on no route; the UI printed the raw
textarea after a client-side checklist; and a note with nothing behind it ("We are still
collecting classroom observations...") could be printed like any other. BUG-6 (29 August)
was a fabricated recommendation reaching a parent draft.

What this locks:
  1. The draft reports `minimum_evidence` {met, count, threshold, reason}: count = the
     strength / growth sentences that resolve to an observation trend or a lens entry.
  2. POST /api/parents/approve refuses a note below the threshold (409, named), a body
     that reintroduces a trauma label (400, named), and a body that still carries the
     child's name after stripping (409, publication safety). Otherwise it returns the
     parent artifact: signed from_label, print_html, printable_text, and the evidence
     ids behind it - and logs a content-free `parent_report_approved` event.
  3. The UI approves through the route and prints the returned artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

STUDENT = "student-amina"
NAME = "Amina Rossi"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    from src.web import app

    return TestClient(app)


def _with_store(fn):
    from src import web

    return web._with_student_store(fn)


@pytest.fixture()
def empty_lens(client):
    _with_store(lambda store: store.create_lens(student_id=STUDENT, display_name=NAME, grade_level="G3"))
    return STUDENT


@pytest.fixture()
def evidenced_lens(client):
    def make(store):
        store.create_lens(student_id=STUDENT, display_name=NAME, grade_level="G3")
        store.add_support_entry(
            STUDENT, "learning_and_cognition", "strengths",
            "explains her thinking to a partner before writing", "local-teacher",
            confidence="teacher_confirmed",
        )
    _with_store(make)
    return STUDENT


def _privacy_events():
    import json
    import os

    path = Path(os.environ["LV_PRIVACY_LOG_PATH"])
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- 1. the draft says how much stands behind it ------------------------------------------

def test_draft_with_nothing_behind_it_says_so(client, empty_lens):
    r = client.post("/api/parents/recommendation", json={"student_id": STUDENT})
    assert r.status_code == 200, r.text
    body = r.json()
    gate = body["minimum_evidence"]
    assert gate["met"] is False and gate["count"] == 0 and gate["threshold"] >= 1, gate
    assert "observation" in gate["reason"].lower() or "evidence" in gate["reason"].lower()


def test_draft_with_a_confirmed_strength_meets_the_gate(client, evidenced_lens):
    body = client.post("/api/parents/recommendation", json={"student_id": STUDENT}).json()
    gate = body["minimum_evidence"]
    assert gate["met"] is True and gate["count"] >= 1, gate
    assert body["source_entry_ids"], body


# --- 2. approve -----------------------------------------------------------------------------

def test_approve_refuses_a_note_with_nothing_behind_it(client, empty_lens):
    r = client.post("/api/parents/approve", json={"student_id": STUDENT, "teacher_display_name": "Claudia"})
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "not_enough_evidence" and err["minimum_evidence"]["met"] is False
    assert "observation" in err["message"].lower() or "report card" in err["message"].lower()
    assert not [e for e in _privacy_events() if e.get("event_type") == "parent_report_approved"]


def test_approve_returns_a_signed_printable_artifact_with_its_evidence(client, evidenced_lens):
    draft = client.post("/api/parents/recommendation", json={"student_id": STUDENT}).json()
    edited = draft["body"] + " We are proud of her effort this term."
    r = client.post("/api/parents/approve", json={
        "student_id": STUDENT, "teacher_display_name": "Claudia", "body": edited,
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["approved"] is True
    art = out["artifact"]
    assert art["from_label"] == "Claudia (Class Teacher)"
    assert "proud of her effort" in art["body"]
    assert art["subject_line"]
    assert out["evidence"]["count"] >= 1 and out["evidence"]["source_entry_ids"] == draft["source_entry_ids"]
    html = out["print_html"]
    assert "proud of her effort" in html and "Claudia (Class Teacher)" in html
    for forbidden in (STUDENT, "AI", "confidence", "observation_id"):
        assert forbidden not in html, f"print html carries {forbidden!r}"
    assert NAME not in html and "Amina" not in html, "the child's name reached the parent artifact"
    assert out["printable_text"].startswith(art["subject_line"])
    assert "Claudia (Class Teacher)" in out["printable_text"]
    events = [e for e in _privacy_events() if e.get("event_type") == "parent_report_approved"]
    assert len(events) == 1
    assert "proud" not in str(events[0]) and NAME not in str(events[0]), "the log must stay content-free"


def test_approve_refuses_a_teacher_edit_that_reintroduces_a_trauma_label(client, evidenced_lens):
    r = client.post("/api/parents/approve", json={
        "student_id": STUDENT, "teacher_display_name": "Claudia",
        "body": "As a refugee student she has done well.",
    })
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "unsafe_label" and "refugee student" in r.json()["message"]


def test_approve_refuses_when_the_childs_name_survives_stripping(client, evidenced_lens):
    r = client.post("/api/parents/approve", json={
        "student_id": STUDENT, "teacher_display_name": "Claudia",
        "body": "amina's reading is growing and AMINA loves stories.",
    })
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "publication_safety" and err["violations"], err


def test_approve_unknown_student_and_missing_id_are_named(client):
    assert client.post("/api/parents/approve", json={}).status_code == 400
    assert client.post("/api/parents/approve", json={"student_id": "student-ghost"}).status_code == 404


# --- 3. the UI ----------------------------------------------------------------------------------

def test_ui_approves_through_the_route_and_prints_the_artifact():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "/api/parents/approve" in html, "no UI call site for approve"
    assert "minimum_evidence" in html, "the UI ignores the evidence gate"
    assert 'id="parent-approve"' in html
    view = html[html.index("async function draftParent()"): html.index("function healthBadgeClass(")]
    assert "print_html" in view and "printable_text" in view, "print still uses the raw textarea"
    assert "Not enough evidence" in view
