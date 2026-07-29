"""Slack credential setup — Slice 5.

Spec: dev/SPEC_CONNECTION_CREDENTIAL_SETUP_2026-07-28.md §Lingua Viva
Application. The four LV_SLACK_* values used to be terminal-only environment
variables, which meant a teacher could not set up the ops assistant at all.

What these tests hold down, in order of how badly each would hurt:
  1. A secret never leaves the process (status routes, error messages).
  2. env > stored > unset, per variable, with the source reported honestly —
     the Settings panel disables fields it cannot actually change.
  3. Saved credentials really do configure the assistant (require_ops_config
     resolves through the store, not just the environment).
  4. Saving reconnects, so setup takes effect without an app restart.
  5. The file is 0600 and written atomically.

No test here touches the network: the reconnect is spied on, and auth.test
gets an injected urlopen.
"""

from __future__ import annotations

import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva import slack_credentials as sc
from src.lingua_viva.slack_socket import (
    SlackOpsConfigurationError,
    auth_test,
    ops_status,
    require_ops_config,
)

client = TestClient(web.app)

BOT = "xoxb-real-looking-token"
APP = "xapp-real-looking-token"
CHANNEL = "C0OPSCHANNEL"
TEACHERS = json.dumps({"U01": {"teacher_id": "claudia", "display_name": "Claudia"}})

FULL = {
    "LV_SLACK_BOT_TOKEN": BOT,
    "LV_SLACK_APP_TOKEN": APP,
    "LV_SLACK_OPS_CHANNEL": CHANNEL,
    "LV_SLACK_TEACHER_MAP": TEACHERS,
}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Point the store at a temp file and clear any real LV_SLACK_* env.

    Without the delenv sweep a developer machine that genuinely exports these
    would silently turn every "unset" assertion green for the wrong reason.
    """
    monkeypatch.setenv("LV_SLACK_CREDENTIALS_PATH", str(tmp_path / "slack.json"))
    for name in sc.SLACK_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture(autouse=True)
def no_reconnect(monkeypatch):
    """Spy on the reconnect instead of opening a real Slack socket."""
    calls: list[int] = []

    async def fake_restart():
        calls.append(1)

    monkeypatch.setattr(web, "_restart_slack_ops", fake_restart)
    return calls


# --- storage + precedence --------------------------------------------------


def test_saved_credentials_configure_the_assistant():
    """The whole point: no env vars, yet the ops config resolves."""
    with pytest.raises(SlackOpsConfigurationError):
        require_ops_config()

    sc.save_stored(FULL)

    config = require_ops_config()
    assert config.bot_token == BOT
    assert config.app_token == APP
    assert config.ops_channel == CHANNEL
    assert list(config.teacher_map) == ["U01"]
    assert ops_status()["configured"] is True


def test_environment_shadows_the_store_per_variable(monkeypatch):
    sc.save_stored(FULL)
    monkeypatch.setenv("LV_SLACK_OPS_CHANNEL", "C0ADMIN")

    assert require_ops_config().ops_channel == "C0ADMIN"
    assert sc.field_source("LV_SLACK_OPS_CHANNEL") == "env"
    # the others still come from the store — precedence is per variable
    assert sc.field_source("LV_SLACK_BOT_TOKEN") == "stored"
    assert require_ops_config().bot_token == BOT


def test_env_managed_fields_are_not_editable_in_app(monkeypatch):
    monkeypatch.setenv("LV_SLACK_BOT_TOKEN", "xoxb-from-admin")
    fields = sc.credential_status()["fields"]
    assert fields["LV_SLACK_BOT_TOKEN"]["source"] == "env"
    assert fields["LV_SLACK_BOT_TOKEN"]["editable_in_app"] is False
    # a field the app CAN change stays editable
    assert fields["LV_SLACK_OPS_CHANNEL"]["editable_in_app"] is True


def test_credentials_file_is_private_and_survives_partial_updates():
    sc.save_stored(FULL)
    path = sc.credentials_path()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    sc.save_stored({"LV_SLACK_OPS_CHANNEL": "C0NEW"})
    stored = sc.load_stored()
    assert stored["LV_SLACK_OPS_CHANNEL"] == "C0NEW"
    assert stored["LV_SLACK_BOT_TOKEN"] == BOT  # untouched field preserved


def test_explicit_blank_clears_a_field():
    sc.save_stored(FULL)
    sc.save_stored({"LV_SLACK_OPS_CHANNEL": ""})
    assert "LV_SLACK_OPS_CHANNEL" not in sc.load_stored()


def test_unknown_keys_are_never_written():
    sc.save_stored({**FULL, "EVIL": "x", "LV_SLACK_SIGNING_SECRET": "y"})
    assert set(sc.load_stored()) <= set(sc.SLACK_ENV_VARS)


def test_clear_removes_everything():
    sc.save_stored(FULL)
    sc.clear_stored()
    assert sc.load_stored() == {}
    with pytest.raises(SlackOpsConfigurationError):
        require_ops_config()


def test_unreadable_store_does_not_break_startup():
    sc.credentials_path().parent.mkdir(parents=True, exist_ok=True)
    sc.credentials_path().write_text("{ this is not json", encoding="utf-8")
    assert sc.load_stored() == {}
    with pytest.raises(SlackOpsConfigurationError):
        require_ops_config()  # unconfigured, not a crash


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("LV_SLACK_BOT_TOKEN", "xapp-wrong-kind"),
        ("LV_SLACK_APP_TOKEN", "xoxb-wrong-kind"),
        ("LV_SLACK_TEACHER_MAP", "not json at all"),
        ("LV_SLACK_TEACHER_MAP", "[]"),
        ("LV_SLACK_TEACHER_MAP", "{}"),
    ],
)
def test_malformed_values_are_rejected_without_echoing_them(field, value):
    with pytest.raises(sc.SlackCredentialError) as excinfo:
        sc.save_stored({field: value})
    assert value not in str(excinfo.value)
    assert sc.load_stored() == {}  # nothing partially written


# --- secret containment ----------------------------------------------------


def test_status_never_contains_a_secret():
    sc.save_stored(FULL)
    blob = json.dumps(sc.credential_status())
    assert BOT not in blob
    assert APP not in blob
    # non-secrets are echoed so the form can be pre-filled
    assert CHANNEL in blob


def test_status_route_never_contains_a_secret():
    sc.save_stored(FULL)
    body = client.get("/api/slack/credentials").text
    assert BOT not in body
    assert APP not in body


def test_secret_fields_report_set_without_revealing_value():
    sc.save_stored(FULL)
    fields = client.get("/api/slack/credentials").json()["fields"]
    assert fields["LV_SLACK_BOT_TOKEN"]["set"] is True
    assert fields["LV_SLACK_BOT_TOKEN"]["secret"] is True
    assert "value" not in fields["LV_SLACK_BOT_TOKEN"]
    assert fields["LV_SLACK_OPS_CHANNEL"]["value"] == CHANNEL


# --- routes ----------------------------------------------------------------


def test_put_saves_reconnects_and_reports_configured(no_reconnect):
    response = client.put("/api/slack/credentials", json=FULL)
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["teacher_count"] == 1
    assert len(no_reconnect) == 1, "saving must reconnect, not wait for a restart"


def test_delete_forgets_and_reconnects(no_reconnect):
    client.put("/api/slack/credentials", json=FULL)
    response = client.delete("/api/slack/credentials")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert sc.load_stored() == {}
    assert len(no_reconnect) == 2  # once for the save, once for the delete


def test_put_rejects_malformed_value_with_a_readable_error():
    response = client.put("/api/slack/credentials", json={"LV_SLACK_BOT_TOKEN": "nope"})
    assert response.status_code == 400
    # `error`, not `detail` — static/index.html's api() helper reads .error and
    # would otherwise drop this message for a generic "Request failed: 400".
    assert "xoxb-" in response.json()["error"]
    assert "detail" not in response.json()


def test_put_rejects_a_body_with_no_known_settings():
    response = client.put("/api/slack/credentials", json={"nonsense": "x"})
    assert response.status_code == 400
    assert "error" in response.json()


def test_put_rejects_a_non_object_body():
    response = client.put("/api/slack/credentials", json=["a", "list"])
    assert response.status_code == 400


def test_blank_secret_keeps_the_saved_one(no_reconnect):
    """The panel sends no token when the box is left blank; a saved token
    must survive an edit to a different field."""
    client.put("/api/slack/credentials", json=FULL)
    client.put("/api/slack/credentials", json={"LV_SLACK_OPS_CHANNEL": "C0OTHER"})
    assert sc.load_stored()["LV_SLACK_BOT_TOKEN"] == BOT
    assert require_ops_config().ops_channel == "C0OTHER"


# --- test-connection -------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, _size):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_auth_test_reports_success_without_echoing_the_token():
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["auth"] = req.get_header("Authorization")
        return _FakeResponse({"ok": True, "team": "Scuola", "user": "lv_bot"})

    result = auth_test(BOT, urlopen=fake_urlopen)
    assert result == {"ok": True, "team": "Scuola", "bot_user": "lv_bot"}
    assert seen["auth"] == f"Bearer {BOT}"
    assert BOT not in json.dumps(result)


def test_auth_test_translates_slack_errors_for_a_teacher():
    def fake_urlopen(req, timeout=None):
        return _FakeResponse({"ok": False, "error": "invalid_auth"})

    result = auth_test(BOT, urlopen=fake_urlopen)
    assert result["ok"] is False
    assert result["error"] == "invalid_auth"
    assert "OAuth & Permissions" in result["message"]


def test_auth_test_handles_no_network():
    def boom(req, timeout=None):
        raise TimeoutError()

    result = auth_test(BOT, urlopen=boom)
    assert result["ok"] is False
    assert "Slack did not answer" in result["message"]


def test_auth_test_route_without_a_token_asks_for_one():
    response = client.post("/api/slack/credentials/test", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "Add a bot token first" in payload["message"]


def test_auth_test_route_uses_the_typed_token(monkeypatch):
    captured = {}

    def fake_auth_test(token, urlopen=None):
        captured["token"] = token
        return {"ok": True, "team": "Scuola", "bot_user": "lv_bot"}

    monkeypatch.setattr("src.lingua_viva.slack_socket.auth_test", fake_auth_test)
    response = client.post(
        "/api/slack/credentials/test", json={"LV_SLACK_BOT_TOKEN": "xoxb-typed"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["token"] == "xoxb-typed"
    # testing must not persist — that is a separate, explicit Save
    assert sc.load_stored() == {}


def test_auth_test_route_falls_back_to_the_saved_token(monkeypatch):
    captured = {}

    def fake_auth_test(token, urlopen=None):
        captured["token"] = token
        return {"ok": True, "team": "Scuola", "bot_user": "lv_bot"}

    monkeypatch.setattr("src.lingua_viva.slack_socket.auth_test", fake_auth_test)
    sc.save_stored(FULL)
    client.post("/api/slack/credentials/test", json={})
    assert captured["token"] == BOT


# --- the UI actually calls all of this -------------------------------------


def test_settings_view_renders_the_slack_setup_panel():
    """Guards the built-not-mounted failure mode: the panel must be reachable
    from the real Settings view, not merely defined."""
    body = client.get("/").text
    assert "renderIntegrationsControls()" in body, "panel never called from renderSettings"
    assert 'id="integrations-slack"' in body
    assert 'api("/api/slack/credentials")' in body
    assert 'api("/api/slack/credentials/test", {' in body
    for name in sc.SLACK_ENV_VARS:
        assert name in body, f"{name} has no field in the Settings panel"
