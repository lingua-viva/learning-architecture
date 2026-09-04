from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import Observation, StudentLensStore
from src.web import app


REPO = Path(__file__).resolve().parents[1]


def _isolate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def test_parent_summary_missing_student_id_fails_closed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/parents/recommendation", json={"focus": "reading"})

    assert response.status_code == 400
    body = response.json()
    assert body == {"error": "student_id_required"}
    assert "body" not in body
    assert "subject_line" not in body
    assert "home_activities" not in body


def test_parent_summary_unknown_student_fails_closed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/parents/recommendation",
            json={"student_id": "student-missing"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body == {"error": "unknown_student"}
    assert "body" not in body
    assert "subject_line" not in body
    assert "home_activities" not in body


def test_parent_summary_route_has_no_demo_student_fallback():
    web_source = (REPO / "src" / "web.py").read_text(encoding="utf-8")
    assert "student-nora" not in web_source


def test_parent_summary_source_observation_ids_are_student_owned(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    teacher_id = "teacher-a"
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        target_id = store.create_lens(display_name="Mira Patel")
        other_id = store.create_lens(display_name="Leo Costa")
        target_obs = store.append_observation(
            Observation(
                student_id=target_id,
                teacher_id=teacher_id,
                template_type="cefr",
                raw_transcript="Mira read a familiar paragraph with more confidence.",
                cefr_dimension="reading",
                cefr_level_observed="A2",
            )
        )["observation"]["observation_id"]
        other_obs = store.append_observation(
            Observation(
                student_id=other_id,
                teacher_id=teacher_id,
                template_type="general",
                raw_transcript="Leo asked for a sentence starter.",
            )
        )["observation"]["observation_id"]

    with TestClient(app) as client:
        response = client.post(
            "/api/parents/recommendation",
            json={"student_id": target_id, "teacher_id": teacher_id},
        )

    assert response.status_code == 200
    source_ids = response.json()["source_observation_ids"]
    assert source_ids
    assert target_obs in source_ids
    assert other_obs not in source_ids
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        exported = store.export_lens(target_id)
    owned_ids = {obs["observation_id"] for obs in exported["observations"]}
    assert set(source_ids).issubset(owned_ids)


def test_parent_summary_exit_surface_stays_mounted():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "Copy final text" in html
    assert "parentSummaryFinalText" in html
    assert 'querySelector("textarea")' in html
    assert "navigator.clipboard.writeText(text)" in html
    assert "printParentSummaryFinalText" in html
    assert "printPacketHtml" in html
    # U10 (2026-09-04): Print now hands the APPROVED artifact's print_html to the same
    # exit surface — the server-rendered page, not a client-built doc.
    assert "printPacketHtml(state.parentApproved.print_html, \"Student summary\")" in html
    assert "textarea.value" in html
    assert "Select who this note is about before drafting." in html
    assert "window.print" not in html
    assert html.count(".print()") == 1
