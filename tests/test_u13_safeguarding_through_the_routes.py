"""U13 — safeguarding P0, proven through the routes and at the surfaces.

Spec: dev/SPEC_SAFEGUARDING_P0_END_TO_END_2026-09-04.md §2 (contract), plan #2.
Before this file the sentence Claudia typed on 29 August was pinned at the
classifier only (tests/test_safeguarding_italian.py). Here the same corpus is
posted to the typed route on a sandboxed app and the RESPONSE is asserted;
then every normal surface a teacher looks at is read back and must be empty of
it; then the coordinator can SEE that something is waiting.

Fixture names are the audit's fictional ones. Both home variables are
sandboxed (LV_STATE_HOME here, LV_CONFIG_HOME by tests/conftest.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.lingua_viva import safeguarding as sg  # noqa: E402

# The retest's RED rows (1.1-1.3) — Claudia's sentence in both languages + the third.
RED_ROWS = [
    "Someone at home makes him feel scared.",
    "Qualcuno a casa gli fa paura.",
    "Ha detto che suo padre lo picchia",
]
# The retest's innocent rows (2.1-2.5) — a flag here teaches a teacher to distrust the flag.
GREEN_ROWS = [
    "Ha paura di parlare davanti alla classe",
    "Ha paura del buio durante la lettura",
    "Il lupo picchia alla porta nella storia",
    "Ha dimenticato i compiti a casa",
    "Boyce hit the ball really hard at recess and cheered",
]
STUDENT = "student-marco"
NAME = "Marco Bianchi"


@pytest.fixture()
def state_home(monkeypatch, tmp_path):
    home = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(home))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    return home


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src.web import app

    return TestClient(app)


@pytest.fixture()
def marco(state_home):
    from src import web

    def make(store):
        try:
            store.get_lens(STUDENT)
        except Exception:
            store.create_lens(student_id=STUDENT, display_name=NAME)
        return STUDENT

    return web._with_student_store(make)


def _capture(client, text: str) -> dict:
    response = client.post(
        "/api/observe/capture",
        json={"student_id": STUDENT, "transcript": text, "template_type": "general"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- §2.1 the corpus through the typed route ------------------------------------

@pytest.mark.parametrize("text", RED_ROWS)
def test_red_row_through_the_typed_route_is_restricted_and_content_free(client, state_home, marco, text):
    body = _capture(client, text)
    assert body["restricted"] is True, body
    assert body["observation_stored"] is False, body
    assert "observation" not in body, "a RED capture must not hand the observation back to the UI"
    # content-free response: no word of the transcript, no student name
    blob = str(body).lower()
    for word in ("scared", "paura", "picchia", "padre", "home makes"):
        assert word not in blob, f"the response leaks the transcript ({word!r}): {body}"
    assert NAME.lower() not in blob
    ledger = sg.read_restricted("coordinator")
    assert len(ledger) == 1 and ledger[0]["student_id"] == STUDENT


@pytest.mark.parametrize("text", GREEN_ROWS)
def test_innocent_row_through_the_typed_route_is_an_ordinary_note(client, state_home, marco, text):
    body = _capture(client, text)
    assert not body.get("restricted"), f"innocent note flagged: {text!r} -> {body}"
    assert body.get("observation_stored", True) is not False, body
    assert sg.read_restricted("coordinator") == [], "an innocent note reached the restricted ledger"


# --- §2.2 absent from every normal surface -----------------------------------------

def _red_then_surfaces(client):
    _capture(client, RED_ROWS[0])
    _capture(client, RED_ROWS[1])
    return ("scared", "paura", "qualcuno")


def test_red_capture_is_absent_from_the_lens_and_its_markdown(client, state_home, marco):
    words = _red_then_surfaces(client)
    lens = client.get(f"/api/students/{STUDENT}/lens")
    assert lens.status_code == 200, lens.text
    body = lens.json()
    assert body.get("observations", []) == [], body.get("observations")
    for word in words:
        assert word not in str(body).lower()
    md = client.get(f"/api/students/{STUDENT}/lens/markdown")
    assert md.status_code == 200, md.text
    for word in words:
        assert word not in md.text.lower(), f"lens markdown carries {word!r}"


def test_red_capture_is_absent_from_the_parent_note(client, state_home, marco):
    words = _red_then_surfaces(client)
    note = client.post("/api/parents/recommendation", json={"student_id": STUDENT})
    assert note.status_code == 200, note.text
    for word in words:
        assert word not in note.text.lower(), f"parent note carries {word!r}"


def test_red_capture_is_absent_from_the_admin_lens_query(client, state_home, marco):
    from src import web
    from src.lingua_viva.lens_query import run_question

    words = _red_then_surfaces(client)
    for word in words:
        result = web._with_student_store(lambda store, w=word: run_question(store, "L11", term=w))
        assert not result.get("rows"), f"lens-query L11 finds {word!r}: {result}"


def test_red_capture_through_the_voice_route_reaches_no_normal_surface(client, state_home, marco):
    response = client.post(
        "/api/voice/act",
        json={"transcript": f"{NAME}: {RED_ROWS[0]}", "teacher_id": "local-teacher"},
    )
    assert response.status_code == 200, response.text
    lens = client.get(f"/api/students/{STUDENT}/lens").json()
    assert lens.get("observations", []) == [], lens.get("observations")
    assert "scared" not in client.get(f"/api/students/{STUDENT}/lens/markdown").text.lower()


# --- §2.3 seen: the coordinator can tell something is waiting ------------------------

def test_pending_route_counts_and_stays_content_free(client, state_home, marco):
    fresh = client.get("/api/safeguarding/pending")
    assert fresh.status_code == 200, fresh.text
    assert fresh.json() == {"count": 0, "queued": 0, "pending_config": 0, "oldest_at": None, "restricted": True}

    _capture(client, RED_ROWS[0])
    body = client.get("/api/safeguarding/pending").json()
    assert body["count"] == 1 and body["pending_config"] == 1 and body["queued"] == 0, body
    assert body["oldest_at"], body
    assert set(body) == {"count", "queued", "pending_config", "oldest_at", "restricted"}, "counts and a timestamp only"
    assert "scared" not in str(body).lower() and NAME.lower() not in str(body).lower()


def test_pending_route_is_coordinator_gated_like_drain(client, state_home, monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    assert client.get("/api/safeguarding/pending").status_code == 401
    teacher = client.get("/api/safeguarding/pending", headers={"X-LV-User-Id": "t1", "X-LV-Role": "teacher"})
    assert teacher.status_code == 403, teacher.text
    coord = client.get("/api/safeguarding/pending", headers={"X-LV-User-Id": "c1", "X-LV-Role": "coordinator"})
    assert coord.status_code == 200, coord.text


def test_governance_view_shows_the_count_to_coordinators_only():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "/api/safeguarding/pending" in html, "nothing in the UI reads the pending count"
    assert "No notification channel is configured" in html, "the pending_config state has no plain-words sentence"
    assert "safeguarding-pending" in html, "no element carries the count"
    # the panel is role-gated: teachers see nothing (spec §2.3)
    start = html.index("async function renderGovernance()")
    end = html.index("async function renderGovernanceExportControls()")
    view = html[start:end]
    assert "/api/safeguarding/pending" in view
    assert 'state.role === "coordinator"' in view, "the pending panel is not gated to the coordinator role"
    # the drain stays a button a human presses (K5): wired in the view, never scheduled
    assert "/api/safeguarding/drain" in view and "wireSafeguardingDrain()" in view
    assert "setInterval" not in view
