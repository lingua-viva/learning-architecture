"""App-facing contracts for the Slack observation integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva.slack_integration import (
    SlackConfigurationError,
    post_slack_message,
    slack_status,
    teacher_channel_map,
)
import src.lingua_viva.slack_integration as slack_integration


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(web.app)


def _signature(secret: str, timestamp: str, body: str) -> str:
    digest = hmac.new(
        secret.encode(),
        f"v0:{timestamp}:{body}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"v0={digest}"


def test_status_is_secret_free():
    env = {
        "LV_SLACK_SIGNING_SECRET": "super-secret",
        "LV_SLACK_BOT_TOKEN": "xoxb-secret",
        "LV_SLACK_TEACHER_CHANNEL_MAP": '{"C123":"teacher-1"}',
    }
    result = slack_status(env)
    assert result["configured"] is True
    assert result["registered_channel_count"] == 1
    assert "super-secret" not in json.dumps(result)
    assert "xoxb-secret" not in json.dumps(result)
    assert "C123" not in json.dumps(result)


def test_empty_injected_environment_does_not_fall_back_to_machine_environment(monkeypatch):
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", "machine-secret")
    assert slack_status({})["signing_secret_set"] is False
    assert teacher_channel_map({}) == {}


def test_channel_map_rejects_non_mapping():
    try:
        teacher_channel_map({"LV_SLACK_TEACHER_CHANNEL_MAP": '["C123"]'})
    except SlackConfigurationError:
        pass
    else:
        raise AssertionError("non-mapping channel configuration was accepted")


def test_outbound_ack_uses_bearer_token_and_expected_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return b'{"ok":true,"ts":"1"}'

    def fake_urlopen(outgoing, timeout):
        captured["authorization"] = outgoing.get_header("Authorization")
        captured["body"] = json.loads(outgoing.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(slack_integration.request, "urlopen", fake_urlopen)
    post_slack_message("xoxb-secret", "C123", "fixed acknowledgement")
    assert captured == {
        "authorization": "Bearer xoxb-secret",
        "body": {"channel": "C123", "text": "fixed acknowledgement"},
        "timeout": 10,
    }


def test_outbound_ack_rejects_non_object_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return b"[]"

    monkeypatch.setattr(
        slack_integration.request, "urlopen", lambda *_args, **_kwargs: FakeResponse()
    )
    try:
        post_slack_message("xoxb-secret", "C123", "fixed acknowledgement")
    except RuntimeError as exc:
        assert "invalid response" in str(exc)
    else:
        raise AssertionError("non-object Slack API response was accepted")


def test_status_route_reports_unconfigured(monkeypatch):
    for name in (
        "LV_SLACK_SIGNING_SECRET",
        "LV_SLACK_BOT_TOKEN",
        "LV_SLACK_TEACHER_CHANNEL_MAP",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.get("/api/slack/status")
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_events_route_rejects_missing_configuration(monkeypatch):
    web._slack_runtime.clear()
    for name in (
        "LV_SLACK_SIGNING_SECRET",
        "LV_SLACK_BOT_TOKEN",
        "LV_SLACK_TEACHER_CHANNEL_MAP",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.post("/api/slack/events", content="{}")
    assert response.status_code == 503


def test_events_route_handles_signed_url_verification(monkeypatch, tmp_path):
    secret = "signing-secret"
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", secret)
    monkeypatch.setenv("LV_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("LV_SLACK_TEACHER_CHANNEL_MAP", '{"C123":"teacher-1"}')
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    web._slack_runtime.clear()

    body = json.dumps(
        {"type": "url_verification", "challenge": "challenge-value"},
        separators=(",", ":"),
    )
    timestamp = str(time.time())
    response = client.post(
        "/api/slack/events",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": _signature(secret, timestamp, body),
        },
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-value"}


def test_url_verification_only_requires_signing_secret(monkeypatch):
    secret = "signing-secret"
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", secret)
    monkeypatch.delenv("LV_SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LV_SLACK_TEACHER_CHANNEL_MAP", raising=False)
    web._slack_runtime.clear()
    body = '{"type":"url_verification","challenge":"setup-first"}'
    timestamp = str(time.time())
    response = client.post(
        "/api/slack/events",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": _signature(secret, timestamp, body),
        },
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "setup-first"}


def test_events_route_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("LV_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("LV_SLACK_TEACHER_CHANNEL_MAP", '{"C123":"teacher-1"}')
    web._slack_runtime.clear()
    response = client.post(
        "/api/slack/events",
        content="{}",
        headers={
            "x-slack-request-timestamp": str(time.time()),
            "x-slack-signature": "v0=bad",
        },
    )
    assert response.status_code == 401


def test_events_route_rejects_oversized_body_before_parsing(monkeypatch):
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", "signing-secret")
    response = client.post("/api/slack/events", content=b"x" * 1_000_001)
    assert response.status_code == 413


def test_events_route_rejects_signed_invalid_json(monkeypatch):
    secret = "signing-secret"
    monkeypatch.setenv("LV_SLACK_SIGNING_SECRET", secret)
    body = "{bad json"
    timestamp = str(time.time())
    response = client.post(
        "/api/slack/events",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": _signature(secret, timestamp, body),
        },
    )
    assert response.status_code == 400


def test_slack_button_and_view_are_present():
    html = (ROOT / "static" / "index.html").read_text()
    assert '["slack", "Slack"' in html
    assert "Slack observation bot" in html
    assert "/api/slack/status" in html
    assert "LV_SLACK_SIGNING_SECRET" in html
