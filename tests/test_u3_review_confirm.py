"""U3 — the report-card fields held for confirmation can be confirmed from the app.

Witnessed by Claudia on PC-23, 2026-09-05 03:08Z (desktop-v0.2.91): she uploaded
the demo pagella and clicked "Update all lenses". The apply wrote one verified
field, held six for her confirmation — and the app showed her "student-chang-abigail
— 1 field(s) updated" and nothing else. The wire carried review_required since
2026-09-03 (baseline B5); no control let her confirm, and the route could not
take a per-field confirmation at all.

What this locks:
  1. POST /api/students/apply-extractions accepts confirmed_fields
     {student_id: [field_path, ...]} and writes exactly those held fields.
  2. Each updated entry carries the student's display_name and the counts a
     teacher reads: written, waiting for confirmation, refused.
  3. The import preview offers a tick box per held field, plain labels instead
     of raw paths, and the apply sends what was ticked; the result names the
     student, never the id.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PAGELLA = REPO / "demo-data" / "pagella_abigail_chang.txt"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    from src import web
    from src.web import app

    c = TestClient(app)
    web._with_student_store(lambda s: s.create_lens(student_id="student-chang-abigail", display_name="Chang Abigail", grade_level="3B"))
    return c


def _import(client):
    r = client.post("/api/students/import-document", files={"file": (PAGELLA.name, PAGELLA.read_bytes(), "text/plain")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [s["student_id"] for s in data["matched_students"]] == ["student-chang-abigail"], data["matched_students"]
    return data


def test_apply_without_confirmation_holds_the_unverified_fields_and_names_the_student(client):
    data = _import(client)
    r = client.post("/api/students/apply-extractions", json={
        "extraction_log_path": data["extraction_log_path"], "confirmed_students": ["student-chang-abigail"],
    })
    assert r.status_code == 200, r.text
    u = r.json()["updated_students"][0]
    assert u["display_name"] == "Chang Abigail", u
    assert u["written_count"] >= 4, u  # the four CEFR levels at least (Italian labels, cycle 7)
    assert u["review_count"] == len(u["review_required"]) >= 1, u
    assert "refused_count" in u
    held = [f["field_path"] if isinstance(f, dict) else f for f in u["review_required"]]
    assert any(p.startswith("support_profile.") or p.endswith("_strengths") for p in held), held


def test_confirmed_fields_are_written_on_the_second_apply(client):
    data = _import(client)
    first = client.post("/api/students/apply-extractions", json={
        "extraction_log_path": data["extraction_log_path"], "confirmed_students": ["student-chang-abigail"],
    }).json()["updated_students"][0]
    held = [f["field_path"] if isinstance(f, dict) else f for f in first["review_required"]]
    pick = [p for p in held if p.endswith("_strengths")][:1] or held[:1]
    r = client.post("/api/students/apply-extractions", json={
        "extraction_log_path": data["extraction_log_path"],
        "confirmed_students": ["student-chang-abigail"],
        "confirmed_fields": {"student-chang-abigail": pick},
    })
    assert r.status_code == 200, r.text
    second = r.json()["updated_students"][0]
    assert pick[0] in second["fields_written"], second
    still_held = [f["field_path"] if isinstance(f, dict) else f for f in second["review_required"]]
    assert pick[0] not in still_held

    from src import web

    lens = web._with_student_store(lambda s: s.export_lens("student-chang-abigail"))
    if pick[0].endswith("_strengths"):
        kind = pick[0]
        assert lens["strengths_profile"].get(kind), lens["strengths_profile"]
    else:
        assert lens["cefr_snapshot"]["reading"] == "A2"


def test_malformed_confirmed_fields_is_a_named_400(client):
    data = _import(client)
    r = client.post("/api/students/apply-extractions", json={
        "extraction_log_path": data["extraction_log_path"], "confirmed_fields": ["not", "a", "map"],
    })
    assert r.status_code == 400 and "confirmed_fields" in r.json()["error"], r.text


def test_ui_offers_confirmation_and_names_the_student():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "data-confirm-field" in html, "no tick box for a held field"
    assert "confirmed_fields" in html, "the apply never sends what was ticked"
    assert "function fieldLabel(" in html, "raw field paths shown to a teacher"
    block = html[html.index('$("doc-import-apply").addEventListener'): html.index('$("doc-import-cancel").addEventListener')]
    assert "u.display_name" in block and "u.student_id}" not in block.replace("u.student_id]", ""), "the result shows the id, not the name"
    assert "waiting for your confirmation" in block
    assert "refused" in block
