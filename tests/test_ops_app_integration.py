"""
App-facing contracts for the Slack Daily Operations Assistant (Lane E).

Covers: the secret-free status route, the Daily view's render route
(/api/ops/daily) with and without configuration, the records audit route
(/api/ops/records), and the startup handler's clean-off behavior when
the ops assistant is unconfigured.

Hermetic: the suite-wide conftest fixture redirects LV_OPS_DB_PATH /
LV_OPS_DESKTOP_DIR / LV_OPS_STATE_PATH / LV_PRIVACY_LOG_PATH into
tmp_path for every test; these tests additionally control the
LV_SLACK_* ops variables explicitly. No network is ever touched — the
read routes never build a transport, and the startup test runs
unconfigured (which returns before any client exists).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.education.ops_records import OpsRecordStore
from src.lingua_viva.slack_socket import ops_status, register_ops_client

client = TestClient(web.app)

OPS_ENV = {
    "LV_SLACK_BOT_TOKEN": "xoxb-test-token",
    "LV_SLACK_APP_TOKEN": "xapp-test-token",
    "LV_SLACK_OPS_CHANNEL": "C0TESTOPS",
    "LV_SLACK_TEACHER_MAP": json.dumps(
        {
            "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
            "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
        }
    ),
}

DAY = "2026-07-28"


@pytest.fixture
def ops_env(monkeypatch):
    for key, value in OPS_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def no_ops_env(monkeypatch):
    for key in OPS_ENV:
        monkeypatch.delenv(key, raising=False)


def _seed_records():
    with OpsRecordStore() as store:
        store.add_record(
            category="schedule_change",
            date_for=DAY,
            text_clean="Assembly moved to 10:30.",
        )
        store.add_record(
            category="absence",
            teacher_id="t-ana",
            actor_name="Ana Ruiz",
            date_for=DAY,
            text_clean="Out sick, coverage arranged.",
        )
        store.add_record(
            category="other",
            teacher_id="t-ben",
            actor_name="Ben Ali",
            date_for=DAY,
            text_clean="hello there",
            needs_review=True,
            review_reason="unclear",
        )


# ------------------------------------------------------------------ status


def test_ops_status_route_is_secret_free(ops_env):
    response = client.get("/api/slack/ops/status")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["mode"] == "socket_mode"
    assert data["teacher_count"] == 2
    body = json.dumps(data)
    assert "xoxb-test-token" not in body
    assert "xapp-test-token" not in body
    assert "C0TESTOPS" not in body


def test_ops_status_route_reports_missing_config(no_ops_env):
    data = client.get("/api/slack/ops/status").json()
    assert data["configured"] is False
    assert data["connected"] is False
    assert "LV_SLACK_BOT_TOKEN" in (data["config_error"] or "")


# ------------------------------------------------------------------ daily


def test_ops_daily_renders_every_mapped_teacher(ops_env):
    _seed_records()
    data = client.get(f"/api/ops/daily?date={DAY}").json()
    assert data["date"] == DAY
    assert data["configured"] is True
    assert data["needs_review"] == 1
    by_teacher = {t["teacher_id"]: t for t in data["teachers"]}
    assert set(by_teacher) == {"t-ana", "t-ben"}
    ana = by_teacher["t-ana"]["markdown"]
    assert "# Today - Ana Ruiz" in ana
    assert "Assembly moved to 10:30." in ana  # broadcast reaches everyone
    assert "Out sick" in ana
    assert "hello there" not in ana  # Ben's item stays out of Ana's file
    ben = by_teacher["t-ben"]["markdown"]
    assert "## To Review" in ben
    assert "hello there" in ben
    assert by_teacher["t-ana"]["file_path"].endswith("Today - Ana Ruiz.md")


def test_ops_daily_filters_by_teacher(ops_env):
    _seed_records()
    data = client.get(f"/api/ops/daily?date={DAY}&teacher_id=t-ana").json()
    assert [t["teacher_id"] for t in data["teachers"]] == ["t-ana"]


def test_ops_daily_unconfigured_derives_teachers_from_records(no_ops_env):
    _seed_records()
    data = client.get(f"/api/ops/daily?date={DAY}").json()
    assert data["configured"] is False
    by_teacher = {t["teacher_id"]: t for t in data["teachers"]}
    assert set(by_teacher) == {"t-ana", "t-ben"}
    assert by_teacher["t-ana"]["display_name"] == "Ana Ruiz"  # actor_name fallback


def test_ops_daily_empty_day(no_ops_env):
    data = client.get(f"/api/ops/daily?date={DAY}").json()
    assert data["teachers"] == []
    assert data["needs_review"] == 0


def test_ops_routes_tolerate_malformed_query_params(ops_env):
    # Hostile/typo'd params must come back 200-empty, never 500.
    for url in (
        "/api/ops/daily?date=definitely-not-a-date",
        "/api/ops/daily?date=%27%3B--&teacher_id=%3Cscript%3E",
        "/api/ops/records?date=9999-99-99&teacher_id=nobody",
    ):
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        # No day matches a nonsense date: records empty, renders empty.
        assert data.get("records", []) == []
        for teacher in data.get("teachers", []):
            assert "No coverage assigned" in teacher["markdown"]
            assert "<script>" not in teacher["markdown"]


# ------------------------------------------------------------------ records


def test_ops_records_returns_day_records(ops_env):
    _seed_records()
    data = client.get(f"/api/ops/records?date={DAY}").json()
    assert data["count"] == 3
    categories = {r["category"] for r in data["records"]}
    assert categories == {"schedule_change", "absence", "other"}
    body = json.dumps(data)
    assert "xoxb-test-token" not in body


def test_ops_records_filters_by_teacher(ops_env):
    _seed_records()
    data = client.get(f"/api/ops/records?date={DAY}&teacher_id=t-ana").json()
    # Ana's own record + the broadcast schedule change.
    assert data["count"] == 2
    assert {r["category"] for r in data["records"]} == {"schedule_change", "absence"}


# ------------------------------------------------------------------ startup


def test_startup_unconfigured_stays_cleanly_off(no_ops_env):
    register_ops_client(None)
    with TestClient(web.app) as started:
        data = started.get("/api/slack/ops/status").json()
        assert data["configured"] is False
        assert data["connected"] is False
    # Nothing was registered or left behind by the lifespan run.
    assert ops_status()["connected"] is False
    assert web._ops_runtime == {}
