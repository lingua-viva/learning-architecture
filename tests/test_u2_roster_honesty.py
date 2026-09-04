"""U2 — roster honesty (plan #4, dev/PLAN_PC23_LV_UX_LANE_2026-09-04.md).

Measured 2026-09-04 on demo-data/classe-3B.csv before this change: a CSV roster
was read as ONE text span, names were found by the bigram fallback (so every one
of six correct names was flagged "low confidence" at 0.99 and the teacher saw
"Check these names"), the Classe column was dropped, preview_classes was empty,
and every lens landed with grade_level "".

The honest roster: a CSV is a table. Header roles (Nome / Classe) are read the
way xlsx sheets already are, names carry student_column evidence, the class
travels to the lens as grade_level, and nothing is invented when the column is
absent.
"""
from __future__ import annotations

import time
from pathlib import Path

from tests.test_students_ingest import (  # noqa: F401  (fixtures re-exported)
    client,
    isolated_state,
    _upload_bytes,
    _wait_for_job,
)

REPO = Path(__file__).resolve().parents[1]
DEMO_CSV = REPO / "demo-data" / "classe-3B.csv"


def _roster_in_store():
    from src import web

    def read(store):
        return {
            str(l.get("display_name")): {"grade_level": l.get("grade_level"), "id": l.get("student_id")}
            for l in store.list_lenses()
        }

    return web._with_student_store(read)


def _approve(job_id: str) -> dict:
    response = client.post("/api/students/ingest/approve", json={"job_id": job_id})
    assert response.status_code == 200, response.text
    return _wait_for_job(job_id)


def test_demo_roster_names_are_column_evidence_not_guesses(isolated_state):
    started = _upload_bytes("classe-3B.csv", DEMO_CSV.read_bytes(), "text/csv")
    preview = _wait_for_job(started["job_id"])
    assert preview["status"] == "preview", preview
    names = sorted(s["display_name"] for s in preview["preview_students"])
    assert names == sorted([
        "Lucà Rossi", "Noëmi Villa", "Chang Abigail", "Chang Marco", "Bianchi Sofia", "Giuseppe Esposito",
    ]), names
    flagged = [s["display_name"] for s in preview["preview_students"] if s.get("low_confidence")]
    assert flagged == [], f"names read from a Nome column must not be flagged low confidence: {flagged}"
    assert preview["preview_classes"] == ["3B"], preview["preview_classes"]


def test_demo_roster_approve_creates_six_lenses_with_their_class_as_grade(isolated_state):
    started = _upload_bytes("classe-3B.csv", DEMO_CSV.read_bytes(), "text/csv")
    _wait_for_job(started["job_id"])
    job = _approve(started["job_id"])
    assert job["status"] == "done", job
    assert len(job["students_created"]) == 6, job["students_created"]
    assert job["needs_confirmation"] == []
    assert not any("low confidence" in w for w in job["warnings"]), job["warnings"]

    roster = _roster_in_store()
    assert set(roster) == {
        "Lucà Rossi", "Noëmi Villa", "Chang Abigail", "Chang Marco", "Bianchi Sofia", "Giuseppe Esposito",
    }
    for name, row in roster.items():
        assert row["grade_level"] == "3B", f"{name}: grade_level={row['grade_level']!r} — the Classe column was dropped"


def test_semicolon_csv_from_italian_excel_is_still_a_table(isolated_state):
    csv = "Nome;Classe;Note\r\nGiulia Ferrari;4A;\r\nOmar Haddad;4A;arrivato a gennaio\r\nAnna Conti;4B;\r\n"
    started = _upload_bytes("classe-4.csv", csv.encode("utf-8"), "text/csv")
    preview = _wait_for_job(started["job_id"])
    assert preview["status"] == "preview", preview
    assert sorted(s["display_name"] for s in preview["preview_students"]) == ["Anna Conti", "Giulia Ferrari", "Omar Haddad"]
    assert not any(s.get("low_confidence") for s in preview["preview_students"])
    assert preview["preview_classes"] == ["4A", "4B"]
    job = _approve(started["job_id"])
    assert job["status"] == "done", job
    roster = _roster_in_store()
    assert roster["Giulia Ferrari"]["grade_level"] == "4A"
    assert roster["Anna Conti"]["grade_level"] == "4B"


def test_csv_without_a_class_column_invents_no_grade(isolated_state):
    csv = "Nome,Note\nGiulia Ferrari,\nOmar Haddad,\nAnna Conti,\n"
    started = _upload_bytes("names-only.csv", csv.encode("utf-8"), "text/csv")
    preview = _wait_for_job(started["job_id"])
    assert preview["status"] == "preview", preview
    assert preview["preview_classes"] == []
    assert not any(s.get("low_confidence") for s in preview["preview_students"])
    job = _approve(started["job_id"])
    assert job["status"] == "done", job
    roster = _roster_in_store()
    assert {r["grade_level"] for r in roster.values()} == {""}, roster


def test_reimporting_the_roster_keeps_a_grade_the_teacher_already_set(isolated_state):
    started = _upload_bytes("classe-3B.csv", DEMO_CSV.read_bytes(), "text/csv")
    _wait_for_job(started["job_id"])
    job = _approve(started["job_id"])
    assert job["status"] == "done", job
    luca = _roster_in_store()["Lucà Rossi"]
    from src import web

    web._with_student_store(lambda store: store.update_profile(luca["id"], {"grade_level": "G3 (moved)"}))
    again = _upload_bytes("classe-3B.csv", DEMO_CSV.read_bytes(), "text/csv")
    _wait_for_job(again["job_id"])
    job2 = _approve(again["job_id"])
    assert job2["status"] == "done", job2
    assert _roster_in_store()["Lucà Rossi"]["grade_level"] == "G3 (moved)", "re-import overwrote the teacher's edit"


def test_free_text_csv_that_is_not_a_roster_still_extracts_as_text(isolated_state):
    """A CSV with no name column is not a table of students — the text path stays."""
    csv = "week,topic\n1,Le stagioni\n2,Gli animali della fattoria\n"
    started = _upload_bytes("plan.csv", csv.encode("utf-8"), "text/csv")
    job = _wait_for_job(started["job_id"])
    assert job["status"] in ("done", "preview"), job
    assert not job.get("students_created"), job
    assert not [s for s in (job.get("preview_students") or []) if s.get("display_name") in ("Le stagioni",)]
