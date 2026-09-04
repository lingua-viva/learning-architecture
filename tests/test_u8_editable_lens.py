"""U8 — edit a lens by hand: correct an automatic write in two seconds (plan #5).

The readiness path's property 3: automatic routing (U3 report cards, U4 Observe)
is acceptable only because a teacher can see what a note did and undo it at
once. Before this file: confirm existed for support entries, dismiss existed
for strengths only, the Observe result showed nothing about the lens write,
and nothing in the UI could remove a routed support entry.

What this locks:
  1. POST /api/students/{id}/support-entry/dismiss deactivates one entry and
     every reader (family view, markdown, admin query) stops showing it.
  2. Unknown ids are named 400s; unknown students 404.
  3. A teacher note routed to the lens returns `written_entries` with the ids
     the UI needs to undo exactly that write.
  4. The UI reads lens_update in the Observe result and carries a remove
     control on every support entry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

STUDENT = "student-u8"
NAME = "Amina Test"
TEXT = "Sentence starters on the desk helped her start writing"


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv-state"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    return tmp_path


@pytest.fixture()
def client(sandbox):
    from fastapi.testclient import TestClient

    from src.web import app

    return TestClient(app)


def _with_store(fn):
    from src import web

    return web._with_student_store(fn)


@pytest.fixture()
def suggested_entry(client):
    """A model-suggested entry on Amina's lens, as Observe routing would leave it."""
    def make(store):
        try:
            store.get_lens(STUDENT)
        except Exception:
            store.create_lens(student_id=STUDENT, display_name=NAME)
        # teacher_confirmed so it renders in the markdown/family views (unconfirmed
        # entries are held back there already) — dismiss must work on both.
        sp = store.add_support_entry(
            STUDENT, "learning_and_cognition", "strategies_worked", TEXT,
            "local-teacher", confidence="teacher_confirmed",
        )
        return sp["categories"]["learning_and_cognition"]["strategies_worked"][-1]["id"]

    return _with_store(make)


def _entry(store, entry_id):
    sp = store.export_lens(STUDENT)["support_profile"]
    for entry in sp["categories"]["learning_and_cognition"]["strategies_worked"]:
        if entry["id"] == entry_id:
            return entry
    return None


# --- 1. dismiss removes it from every reader ------------------------------------------

def test_dismiss_deactivates_the_entry_and_every_reader_drops_it(client, suggested_entry):
    from src.education.student_lens import support_profile_for_audience
    from src.lingua_viva.lens_query import run_question

    assert "starters" in client.get(f"/api/students/{STUDENT}/lens/markdown").text.lower()
    response = client.post(
        f"/api/students/{STUDENT}/support-entry/dismiss",
        json={"category_id": "learning_and_cognition", "bucket": "strategies_worked", "entry_id": suggested_entry},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dismissed"] is True and body["entry_id"] == suggested_entry
    assert "starters" not in str(body).lower(), "the response repeats the entry text — counts and ids only"

    entry = _with_store(lambda store: _entry(store, suggested_entry))
    assert entry is not None, "dismiss must deactivate, never delete — the record stays auditable"
    assert entry["active"] is False and entry.get("dismissed_by") == "local-teacher" and entry.get("dismissed_at")

    family = _with_store(lambda store: support_profile_for_audience(store.export_lens(STUDENT)["support_profile"], "family"))
    assert "starters" not in str(family).lower()
    assert "starters" not in client.get(f"/api/students/{STUDENT}/lens/markdown").text.lower()
    hits = _with_store(lambda store: run_question(store, "L11", term="starters"))
    assert not hits.get("rows"), hits


def test_dismiss_is_idempotent_and_reversible_by_confirm_never(client, suggested_entry):
    for _ in range(2):
        r = client.post(
            f"/api/students/{STUDENT}/support-entry/dismiss",
            json={"category_id": "learning_and_cognition", "bucket": "strategies_worked", "entry_id": suggested_entry},
        )
        assert r.status_code == 200, r.text
    entry = _with_store(lambda store: _entry(store, suggested_entry))
    assert entry["active"] is False


# --- 2. named refusals -------------------------------------------------------------------

def test_unknown_entry_bucket_or_student_are_named(client, suggested_entry):
    r = client.post(
        f"/api/students/{STUDENT}/support-entry/dismiss",
        json={"category_id": "learning_and_cognition", "bucket": "strategies_worked", "entry_id": "nope"},
    )
    assert r.status_code == 400 and "nope" in r.json()["error"], r.text
    r = client.post(
        f"/api/students/{STUDENT}/support-entry/dismiss",
        json={"category_id": "learning_and_cognition", "bucket": "not_a_bucket", "entry_id": suggested_entry},
    )
    assert r.status_code == 400 and "not_a_bucket" in r.json()["error"], r.text
    r = client.post(
        "/api/students/student-ghost/support-entry/dismiss",
        json={"category_id": "learning_and_cognition", "bucket": "strategies_worked", "entry_id": suggested_entry},
    )
    assert r.status_code == 404, r.text
    r = client.post(f"/api/students/{STUDENT}/support-entry/dismiss", json={})
    assert r.status_code == 400 and "entry_id" in r.json()["error"]


# --- 3. the Observe write hands back the ids the undo needs -------------------------------

def test_teacher_note_routed_to_the_lens_returns_written_entries_with_ids(client):
    from src.lingua_viva.observe_to_lens import observe_comment_to_lens_sync

    def make(store):
        store.create_lens(student_id=STUDENT, display_name=NAME)
        return observe_comment_to_lens_sync(
            "Amina finished early again and could benefit from extension activities.",
            student_id=STUDENT, display_name=NAME, teacher_id="local-teacher", store=store,
        )

    result = _with_store(make)
    assert result["written_fields"], result
    entries = result.get("written_entries")
    assert entries, "the write returns no entry ids — the UI cannot undo exactly this"
    for item in entries:
        assert set(item) >= {"path", "category_id", "bucket", "entry_id", "text"}, item
        present = _with_store(lambda store, it=item: any(
            e["id"] == it["entry_id"]
            for e in store.export_lens(STUDENT)["support_profile"]["categories"][it["category_id"]][it["bucket"]]
        ))
        assert present, item
    # and the two-second undo through the endpoint works on exactly that id
    first = entries[0]
    r = client.post(
        f"/api/students/{STUDENT}/support-entry/dismiss",
        json={"category_id": first["category_id"], "bucket": first["bucket"], "entry_id": first["entry_id"]},
    )
    assert r.status_code == 200, r.text


# --- 4. the UI can see it and undo it ----------------------------------------------------

def test_ui_shows_what_a_note_did_and_can_remove_an_entry():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "/support-entry/dismiss" in html, "no UI call site for dismiss"
    assert "data-dismiss-entry" in html, "support entries carry no remove control"
    assert "data-undo-entry" in html, "the Observe result has no undo for what it just wrote"
    start = html.index("<h3>Saved</h3>")
    window = html[start - 4000: start + 2000]
    assert "lens_update" in window, "the Observe result does not show what the note did to the lens"
    assert "written_entries" in window
    # dismissed entries disappear from the lens view
    fn = html[html.index("function categoryEntryList("): html.index("function renderCategorySection(")]
    assert "active !== false" in fn, "the lens view still renders dismissed entries"
