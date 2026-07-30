from __future__ import annotations

from fastapi.testclient import TestClient

import src.education.help_artifacts as help_artifacts
from src.education.content_differentiator import ContentDifferentiator
from src.lingua_viva.deliverables.store import read_deliverables
from src.web import app


def _client():
    return TestClient(app)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))


def _seed_student_with_observation(client: TestClient, transcript: str = "Raw unique transcript phrase should stay private."):
    created = client.post("/api/students", json={"display_name": "Marco", "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]
    obs = client.post(
        "/api/observe/capture",
        json={
            "student_id": student_id,
            "teacher_id": "teacher-a",
            "transcript": transcript,
            "template_type": "cefr",
            "cefr_dimension": "writing",
            "cefr_level_observed": "A1",
            "cefr_direction": "progressing",
            "support_category": "executive_function",
            "evidence_summary": "Uses a checklist when writing.",
        },
    )
    assert obs.status_code == 200
    return student_id, transcript


def test_help_artifact_preview_uses_lens_evidence_and_requires_approval(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)

        response = client.post(
            f"/api/students/{student_id}/help-artifact/preview",
            json={"teacher_id": "teacher-a", "artifact_type": "practice"},
        )

        assert response.status_code == 200
        body = response.json()
        draft = body["draft"]
        assert body["requires_teacher_approval"] is True
        assert draft["source_observation_ids"]
        assert "writing" in draft["source_summary"]
        assert draft["status"] == "draft"


def test_preview_does_not_create_deliverable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)

        response = client.post(f"/api/students/{student_id}/help-artifact/preview", json={})

        assert response.status_code == 200
        assert read_deliverables(limit=20) == []
        assert help_artifacts.read_records() == []


def test_help_artifact_uses_content_differentiator_tier(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(ContentDifferentiator, "assign_tier_for_student", lambda self, lens: "extended")
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)

        draft = client.post(f"/api/students/{student_id}/help-artifact/preview", json={}).json()["draft"]

        assert draft["differentiation_tier"] == "extended"
        assert "challenge" in draft["student_prompt"].lower()


def test_raw_transcript_not_copied_into_student_facing_help_artifact(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    raw = "Student used the exact secret phrase purple moon ladder."
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client, raw)

        draft = client.post(f"/api/students/{student_id}/help-artifact/preview", json={}).json()["draft"]

        student_facing = f"{draft['instructions']} {draft['student_prompt']}"
        assert "purple moon ladder" not in student_facing
        assert raw not in student_facing


def test_help_artifact_approval_creates_deliverable_and_audit_receipt(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)
        draft = client.post(f"/api/students/{student_id}/help-artifact/preview", json={}).json()["draft"]

        response = client.post(f"/api/students/{student_id}/help-artifact/approve", json={"draft": draft})

        assert response.status_code == 200
        body = response.json()
        assert body["record"]["status"] == "approved"
        assert body["deliverable"]["type"] == "help_artifact"
        assert body["deliverable"]["deliverable_id"] in body["audit_receipt"]["deliverable_ids"]
        assert body["audit_receipt"]["is_complete"] is True
        assert body["audit_receipt"]["source_record_ids"]


def test_portfolio_preview_uses_latest_observations_and_avoids_labels(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)
        client.post(
            "/api/observe/capture",
            json={
                "student_id": student_id,
                "teacher_id": "teacher-a",
                "transcript": "Latest observation: explained one choice in writing.",
                "template_type": "cefr",
                "cefr_dimension": "writing",
                "cefr_level_observed": "A1",
                "cefr_direction": "progressing",
            },
        )

        draft = client.post(f"/api/students/{student_id}/portfolio-entry/preview", json={}).json()["draft"]

        assert draft["source_observation_ids"]
        text = f"{draft['title']} {draft['body']}".lower()
        for banned in ("rti", "tier", "diagnosis", "deficit", "disorder"):
            assert banned not in text


def test_portfolio_approval_creates_deliverable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)
        draft = client.post(f"/api/students/{student_id}/portfolio-entry/preview", json={}).json()["draft"]

        response = client.post(f"/api/students/{student_id}/portfolio-entry/approve", json={"draft": draft})

        assert response.status_code == 200
        body = response.json()
        assert body["record"]["status"] == "approved"
        assert body["deliverable"]["type"] == "portfolio_entry"
        assert body["deliverable"]["deliverable_id"] in body["audit_receipt"]["deliverable_ids"]
        assert body["audit_receipt"]["is_complete"] is True
        assert body["audit_receipt"]["source_record_ids"]


def test_teacher_edits_are_preserved_after_safety_checks(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)
        draft = client.post(f"/api/students/{student_id}/help-artifact/preview", json={}).json()["draft"]

        response = client.post(
            f"/api/students/{student_id}/help-artifact/approve",
            json={"draft": draft, "teacher_edits": {"student_prompt": "Try the frame, then underline one strong word."}},
        )

        assert response.status_code == 200
        assert response.json()["record"]["student_prompt"] == "Try the frame, then underline one strong word."


def test_unsafe_teacher_edits_are_rejected(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)
        draft = client.post(f"/api/students/{student_id}/help-artifact/preview", json={}).json()["draft"]

        response = client.post(
            f"/api/students/{student_id}/help-artifact/approve",
            json={"draft": draft, "teacher_edits": {"student_prompt": "Generated by AI for a tier 2 intervention."}},
        )

        assert response.status_code == 422
        assert response.json()["error"] == "unsafe_teacher_edit"


def test_teacher_id_impersonation_is_prevented_in_local_header_mode(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    headers = {
        "X-LV-User-Id": "u-teacher",
        "X-LV-Role": "teacher",
        "X-LV-Teacher-Id": "teacher-real",
    }
    with _client() as client:
        created = client.post("/api/students", json={"display_name": "Marco"}, headers=headers)
        assert created.status_code == 200
        student_id = created.json()["student_id"]

        response = client.post(
            f"/api/students/{student_id}/help-artifact/preview",
            json={"teacher_id": "teacher-impersonated"},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["draft"]["teacher_id"] == "teacher-real"


def test_existing_rti_decision_route_still_passes(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        student_id, _transcript = _seed_student_with_observation(client)

        response = client.post(f"/api/students/{student_id}/rti/decision", json={"decision": "defer"})

        assert response.status_code == 200
        assert response.json()["status"] == "recorded"
