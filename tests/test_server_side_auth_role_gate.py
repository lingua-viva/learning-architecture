"""
Tests for the server-side auth role gate.

Spec: dev/SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.web import app

client = TestClient(app)

TEACHER_HEADERS = {
    "X-LV-User-Id": "user-ana",
    "X-LV-Role": "teacher",
    "X-LV-Teacher-Id": "t-ana",
    "X-LV-Campus": "Nairobi",
}
COORDINATOR_HEADERS = {
    "X-LV-User-Id": "user-clara",
    "X-LV-Role": "coordinator",
    "X-LV-Teacher-Id": "t-clara",
    "X-LV-Campus": "Nairobi",
}
ADMIN_HEADERS = {
    "X-LV-User-Id": "user-admin",
    "X-LV-Role": "admin",
    "X-LV-Teacher-Id": "t-admin",
}


# --- 1. Default mode preserves local behavior ---

def test_auth_off_preserves_existing_route(monkeypatch):
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    resp = client.get("/api/students")
    # Should not return 401 or 403
    assert resp.status_code != 401
    assert resp.status_code != 403


# --- 2. Missing identity returns 401 ---

def test_local_header_returns_401_without_identity(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/students")
    assert resp.status_code == 401
    assert resp.json()["error"] == "authentication_required"


# --- 3. Unknown role returns 403 ---

def test_unknown_role_returns_403(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/students", headers={
        "X-LV-User-Id": "user-x",
        "X-LV-Role": "janitor",
    })
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


def test_unknown_role_cannot_access_ops_records_with_matching_teacher_id(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/records?teacher_id=t-ana", headers={
        "X-LV-User-Id": "user-x",
        "X-LV-Role": "janitor",
        "X-LV-Teacher-Id": "t-ana",
    })
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


# --- 4. Teacher can call teacher route ---

def test_teacher_can_access_students(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/students", headers=TEACHER_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


# --- 5. Teacher cannot call admin route ---

def test_teacher_cannot_access_admin_route(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/slack/credentials", headers=TEACHER_HEADERS)
    assert resp.status_code == 403


def test_teacher_cannot_access_ops_setup(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/setup/catalog", headers=TEACHER_HEADERS)
    assert resp.status_code == 403


# --- 6. Coordinator can call coordinator route ---

def test_coordinator_can_access_ops_summary(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/staffing-summary", headers=COORDINATOR_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_coordinator_can_access_admin_evidence(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/admin/evidence", headers=COORDINATOR_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


# --- 7. Teacher cannot fetch all ops records ---

def test_teacher_cannot_fetch_all_ops_records(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/records", headers=TEACHER_HEADERS)
    assert resp.status_code == 403


# --- 8. Teacher can fetch own ops records ---

def test_teacher_can_fetch_own_ops_records(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/records?teacher_id=t-ana", headers=TEACHER_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_teacher_can_access_own_daily_file(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/daily?teacher_id=t-ana", headers=TEACHER_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


# --- 9. Teacher cannot impersonate another teacher ---

def test_teacher_cannot_fetch_other_teacher_ops(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/records?teacher_id=t-ben", headers=TEACHER_HEADERS)
    assert resp.status_code == 403


def test_teacher_cannot_fetch_all_daily_files(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/ops/daily", headers=TEACHER_HEADERS)
    assert resp.status_code == 403


def test_observe_capture_forces_header_teacher_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))

    roster = client.get("/api/students", headers=TEACHER_HEADERS)
    assert roster.status_code == 200
    student_id = roster.json()["students"][0]["student_id"]
    transcript = "auth gate impersonation regression note"

    resp = client.post("/api/observe/capture", headers=TEACHER_HEADERS, json={
        "student_id": student_id,
        "teacher_id": "t-ben",
        "transcript": transcript,
    })
    assert resp.status_code == 200

    lens = client.get(f"/api/students/{student_id}/lens", headers=TEACHER_HEADERS).json()
    matching = [
        obs for obs in lens["observations"]
        if obs.get("raw_transcript") == transcript
    ]
    assert matching
    assert {obs["teacher_id"] for obs in matching} == {"t-ana"}


def test_parent_recommendation_forces_header_teacher_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    seen: dict[str, str] = {}

    def fake_generate(self, student_id, teacher_id):
        seen["teacher_id"] = teacher_id
        return SimpleNamespace(
            subject_line="Progress update",
            body="We noticed your child trying a new strategy.",
            home_activities=["Read together for ten minutes."],
        )

    monkeypatch.setattr(
        "src.education.parent_report.ParentReportGenerator.generate_draft",
        fake_generate,
    )

    student_id = client.get("/api/students", headers=TEACHER_HEADERS).json()["students"][0]["student_id"]
    resp = client.post("/api/parents/recommendation", headers=TEACHER_HEADERS, json={
        "student_id": student_id,
        "teacher_id": "t-ben",
    })
    assert resp.status_code == 200
    assert seen["teacher_id"] == "t-ana"


# --- 10. Admin can call admin routes ---

def test_admin_can_access_slack_credentials(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/slack/credentials", headers=ADMIN_HEADERS)
    # Should pass the role gate (may get a non-auth error if no creds configured)
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_admin_can_access_provider_routes(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.post("/api/provider/disconnect", headers=ADMIN_HEADERS)
    assert resp.status_code != 401
    assert resp.status_code != 403


# --- 11. Access roles module tests ---

def test_role_hierarchy():
    from src.lingua_viva.access_roles import role_allows
    assert role_allows("admin", {"teacher"})
    assert role_allows("coordinator", {"teacher"})
    assert role_allows("teacher", {"teacher"})
    assert not role_allows("teacher", {"admin"})
    assert not role_allows("co_teacher", {"coordinator"})
    assert role_allows("admin", {"coordinator", "admin"})


def test_effective_teacher_id_for_teacher(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    from src.lingua_viva.access_roles import effective_teacher_id

    class FakeReq:
        headers = {"X-LV-User-Id": "u1", "X-LV-Role": "teacher", "X-LV-Teacher-Id": "t-ana"}

    # Teacher cannot use a different teacher_id
    assert effective_teacher_id(FakeReq(), "t-ben") == "t-ana"


def test_effective_teacher_id_for_teacher_without_header_does_not_use_payload(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    from src.lingua_viva.access_roles import effective_teacher_id

    class FakeReq:
        headers = {"X-LV-User-Id": "u1", "X-LV-Role": "teacher"}

    assert effective_teacher_id(FakeReq(), "t-ben") == ""


def test_effective_teacher_id_for_coordinator(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    from src.lingua_viva.access_roles import effective_teacher_id

    class FakeReq:
        headers = {"X-LV-User-Id": "u2", "X-LV-Role": "coordinator", "X-LV-Teacher-Id": "t-clara"}

    # Coordinator can query another teacher
    assert effective_teacher_id(FakeReq(), "t-ben") == "t-ben"


# --- 12. Unprotected routes still work ---

def test_health_endpoint_unprotected(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/")
    assert resp.status_code == 200


def test_extraction_routes_are_protected(monkeypatch):
    monkeypatch.setenv("LV_AUTH_MODE", "local_header")
    resp = client.get("/api/extraction/sources")
    assert resp.status_code == 401
