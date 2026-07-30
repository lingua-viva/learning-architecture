from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import src.education.cohort_planning as cohort_planning
from src.education.content_differentiator import ContentDifferentiator
from src.education.student_lens import StudentLensStore
from src.lingua_viva.deliverables.store import read_deliverables
from src.web import app


def _client():
    return TestClient(app)


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _lesson_payload():
    return {
        "ib_programme": "PYP",
        "subject": "Italian",
        "unit_title": "Migration Stories",
        "topic": "describing journeys and reasons",
        "atl_skills": ["communication", "self-management"],
        "cefr_target": "A2",
        "duration_minutes": 45,
        "language_of_instruction": "it",
    }


def _create_observed_student(client: TestClient, name: str, teacher_id: str = "teacher-a", level: str = "A2", transcript: str = "Private raw transcript phrase."):
    created = client.post("/api/students", json={"display_name": name, "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]
    obs = client.post(
        "/api/observe/capture",
        json={
            "student_id": student_id,
            "teacher_id": teacher_id,
            "transcript": transcript,
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": level,
            "cefr_direction": "progressing",
            "support_category": "executive_functioning",
            "evidence_summary": "Uses a checklist during group work.",
        },
    )
    assert obs.status_code == 200
    return student_id


def _preview(client: TestClient, **overrides):
    payload = {"teacher_id": "teacher-a", "lesson": _lesson_payload(), "teacher_notes": ["Use table groups."]}
    payload.update(overrides)
    return client.post("/api/cohort-plans/preview", json=payload)


def test_preview_builds_plan_from_effective_teacher_roster(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco", level="A1")
        _create_observed_student(client, "Nora", level="B2")

        response = _preview(client)

        assert response.status_code == 200
        body = response.json()
        plan = body["plan"]
        assert body["requires_teacher_approval"] is True
        assert body["writes"] == {"deliverables": 0, "audit_receipts": 0}
        assert plan["teacher_id"] == "teacher-a"
        assert plan["cohort_summary"]["total_students"] == 2
        assert set(plan["content_pack"]["tiers"]) == {"foundational", "on_track", "extended"}
        assert "Teacher Guide" in plan["teacher_guide_markdown"]


def test_preview_does_not_create_deliverable_or_plan_record(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco")

        response = _preview(client)

        assert response.status_code == 200
        assert read_deliverables(limit=20) == []
        assert cohort_planning.read_cohort_plans(limit=20) == []


def test_tier_assignment_reuses_content_differentiator(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = []

    def fake_assign(self, lens):
        calls.append(lens["student_id"])
        return "extended"

    monkeypatch.setattr(ContentDifferentiator, "assign_tier_for_student", fake_assign)
    with _client() as client:
        _create_observed_student(client, "Marco")

        plan = _preview(client).json()["plan"]

        assert calls
        assert {item["assigned_tier"] for item in plan["student_assignments"]} == {"extended"}


def test_subset_planning_rejects_students_outside_teacher_roster(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco", teacher_id="teacher-a")
        outsider = _create_observed_student(client, "Luca", teacher_id="teacher-b")

        response = _preview(client, student_ids=[outsider])

        assert response.status_code == 422
        assert response.json()["error"] == "unauthorized_student_ids"


def test_empty_roster_returns_stable_empty_plan(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        response = _preview(client, teacher_id="teacher-empty")

        assert response.status_code == 200
        plan = response.json()["plan"]
        assert plan["cohort_summary"]["total_students"] == 0
        assert plan["student_assignments"] == []
        assert "No teacher-owned roster lenses" in plan["teacher_guide_markdown"]


def test_teacher_guide_includes_conflict_grouping_and_manual_review(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        f_id = _create_observed_student(client, "Fatima", level="A1")
        o_id = _create_observed_student(client, "Omar", level="A2")
        e_id = _create_observed_student(client, "Elena", level="B2")
        with StudentLensStore(db_path=tmp_path / "students.db") as store:
            store.set_avoid_pairing_with(f_id, [o_id, e_id])

        plan = _preview(client).json()["plan"]

        assert "Needs Manual Grouping" in plan["teacher_guide_markdown"]
        flagged = [item for item in plan["student_assignments"] if item["student_id"] == f_id]
        assert flagged and "grouping_review" in flagged[0]["grouping_notes"]


def test_student_facing_tier_content_has_no_student_names_or_raw_transcript(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    raw = "Secret exact classroom transcript emerald ladder."
    with _client() as client:
        _create_observed_student(client, "Marco", transcript=raw)

        plan = _preview(client).json()["plan"]

        tier_text = str(plan["content_pack"]["tiers"])
        full_text = str(plan)
        assert "Marco" not in tier_text
        assert "emerald ladder" not in full_text
        assert raw not in full_text


def test_approval_creates_cohort_deliverable_and_audit_receipt(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco")
        plan = _preview(client).json()["plan"]

        response = client.post("/api/cohort-plans/approve", json={"teacher_id": "teacher-a", "plan": plan})

        assert response.status_code == 200
        body = response.json()
        assert body["record"]["status"] == "approved"
        assert body["deliverable"]["type"] == "cohort_lesson_plan"
        assert body["deliverable"]["deliverable_id"] in body["audit_receipt"]["deliverable_ids"]
        assert "Marco" not in str(body["audit_receipt"])
        assert cohort_planning.read_cohort_plans("teacher-a", limit=5)


def test_safe_teacher_edits_are_preserved(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco")
        plan = _preview(client).json()["plan"]

        response = client.post(
            "/api/cohort-plans/approve",
            json={
                "teacher_id": "teacher-a",
                "plan": plan,
                "teacher_edits": {"teacher_notes": ["Use the picture cards first."]},
            },
        )

        assert response.status_code == 200
        assert response.json()["record"]["teacher_notes"] == ["Use the picture cards first."]


def test_unsafe_teacher_edits_are_rejected(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        _create_observed_student(client, "Marco")
        plan = _preview(client).json()["plan"]

        response = client.post(
            "/api/cohort-plans/approve",
            json={
                "teacher_id": "teacher-a",
                "plan": plan,
                "teacher_edits": {"teacher_notes": ["Generated by AI for a diagnosis review."]},
            },
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
        student_id = client.post("/api/students", json={"display_name": "Marco"}, headers=headers).json()["student_id"]
        obs = client.post(
            "/api/observe/capture",
            json={
                "student_id": student_id,
                "teacher_id": "teacher-impersonated",
                "transcript": "Observed a short speaking turn.",
                "template_type": "cefr",
                "cefr_dimension": "speaking",
                "cefr_level_observed": "A2",
                "cefr_direction": "progressing",
            },
            headers=headers,
        )
        assert obs.status_code == 200

        response = client.post(
            "/api/cohort-plans/preview",
            json={"teacher_id": "teacher-impersonated", "lesson": _lesson_payload()},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["plan"]["teacher_id"] == "teacher-real"


def test_existing_prepare_routes_still_pass(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with _client() as client:
        activity = client.post("/api/prepare/activity", json={"grade": "G3"})
        assignments = client.get("/api/prepare/tier-assignments")

        assert activity.status_code == 200
        assert set(activity.json()["tiers"]) == {"foundational", "on_track", "extended"}
        assert assignments.status_code == 200
        assert "assignments" in assignments.json()
