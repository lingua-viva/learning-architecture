"""In-app Google sign-in tests (SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A7).

Hermetic: the loopback flow runs against 127.0.0.1 with a fake transport —
no network beyond the test's own GET to the one-shot listener, no browser
(explicit `opener`), stored auth confined to tmp_path via the conftest
LV_GOOGLE_DRIVE_AUTH_PATH override.
"""

import base64
import io
import json
import time
from urllib import error, parse, request

import pytest

from src.lingua_viva import google_drive_integration as drive
from src.lingua_viva import google_drive_oauth as oauth
from src.lingua_viva.google_drive_integration import (
    TOKEN_URL,
    DriveAuthError,
    DriveConfigError,
)


def _id_token(email="teacher@example.org"):
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


class FakeTokenTransport:
    def __init__(self, *, refresh_token="refresh-token-secret", email="teacher@example.org"):
        self.posted = []
        self.refresh_token = refresh_token
        self.email = email

    def post_form(self, url, data):
        self.posted.append((url, dict(data)))
        if url == oauth.REVOKE_URL:
            return {}
        response = {"access_token": "at", "id_token": _id_token(self.email)}
        if self.refresh_token is not None:
            response["refresh_token"] = self.refresh_token
        return response


class FailingTransport:
    def __init__(self):
        self.posted = []

    def post_form(self, url, data):
        self.posted.append((url, dict(data)))
        raise OSError("network down")


@pytest.fixture
def client_env(monkeypatch):
    monkeypatch.setenv("LV_GOOGLE_OAUTH_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("LV_GOOGLE_OAUTH_CLIENT_SECRET", "app-client-secret")


def _start(transport, **kwargs):
    opened = []
    result = oauth.start_signin(transport=transport, opener=opened.append, **kwargs)
    return result, opened


def _redirect_params(result):
    query = parse.parse_qs(parse.urlparse(result["auth_url"]).query)
    return {key: value[0] for key, value in query.items()}


def _get(port, query):
    return request.urlopen(f"http://127.0.0.1:{port}/?{parse.urlencode(query)}", timeout=5)


def _wait_flow_done(deadline=5.0):
    end = time.monotonic() + deadline
    while oauth.flow_pending() and time.monotonic() < end:
        time.sleep(0.02)
    assert not oauth.flow_pending()


@pytest.fixture(autouse=True)
def _reset_flow():
    yield
    oauth.cancel_active_flow()


def test_signin_flow_end_to_end(client_env):
    transport = FakeTokenTransport()
    result, opened = _start(transport)
    assert result["flow_pending"] is True
    assert opened == [result["auth_url"]]

    params = _redirect_params(result)
    assert params["code_challenge_method"] == "S256"
    assert params["access_type"] == "offline"
    assert params["prompt"] == "consent"
    assert params["scope"] == oauth.SCOPES
    assert params["redirect_uri"] == f"http://127.0.0.1:{result['listen_port']}"

    with _get(result["listen_port"], {"state": params["state"], "code": "auth-code-1"}) as resp:
        assert resp.status == 200
        assert b"signed in" in resp.read().lower()
    _wait_flow_done()

    # Token exchange used PKCE + our code against the transport seam.
    token_calls = [call for call in transport.posted if call[0] == TOKEN_URL]
    assert len(token_calls) == 1
    form = token_calls[0][1]
    assert form["code"] == "auth-code-1"
    assert form["grant_type"] == "authorization_code"
    assert form["redirect_uri"] == params["redirect_uri"]
    assert form["code_verifier"]  # PKCE verifier travels only server-side

    stored = oauth.load_stored_auth()
    assert stored["refresh_token"] == "refresh-token-secret"
    assert stored["account_email"] == "teacher@example.org"
    assert stored["needs_signin"] is False
    assert (oauth.auth_config_path().stat().st_mode & 0o777) == 0o600

    status = oauth.auth_status()
    assert status["signed_in"] is True
    assert status["account_email"] == "teacher@example.org"
    assert status["flow_pending"] is False


def test_signin_records_privacy_event(client_env, monkeypatch, tmp_path):
    log_path = tmp_path / "privacy_events.ndjson"
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(log_path))
    transport = FakeTokenTransport()
    result, _ = _start(transport)
    params = _redirect_params(result)
    _get(result["listen_port"], {"state": params["state"], "code": "c"}).close()
    _wait_flow_done()

    events = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert any(event["event_type"] == "drive_account_connected" for event in events)
    text = log_path.read_text()
    assert "refresh-token-secret" not in text
    assert "teacher@example.org" not in text  # query_text is hashed


def test_state_mismatch_is_rejected_and_flow_survives(client_env):
    transport = FakeTokenTransport()
    result, _ = _start(transport)
    params = _redirect_params(result)

    with pytest.raises(error.HTTPError) as excinfo:
        _get(result["listen_port"], {"state": "attacker-guess", "code": "stolen"})
    assert excinfo.value.code == 400
    assert transport.posted == []  # no token exchange attempted
    assert oauth.load_stored_auth() is None
    assert oauth.flow_pending() is True  # stale link doesn't kill the real flow

    # The genuine redirect still completes afterwards.
    _get(result["listen_port"], {"state": params["state"], "code": "real-code"}).close()
    _wait_flow_done()
    assert oauth.auth_status()["signed_in"] is True


def test_denied_consent_reports_failure(client_env):
    transport = FakeTokenTransport()
    result, _ = _start(transport)
    params = _redirect_params(result)

    with pytest.raises(error.HTTPError) as excinfo:
        _get(result["listen_port"], {"state": params["state"], "error": "access_denied"})
    assert excinfo.value.code == 400
    _wait_flow_done()
    assert oauth.load_stored_auth() is None


def test_missing_refresh_token_fails_without_saving(client_env):
    transport = FakeTokenTransport(refresh_token=None)
    result, _ = _start(transport)
    params = _redirect_params(result)

    with pytest.raises(error.HTTPError) as excinfo:
        _get(result["listen_port"], {"state": params["state"], "code": "c"})
    assert excinfo.value.code == 400
    _wait_flow_done()
    assert oauth.load_stored_auth() is None
    assert oauth.auth_status()["signed_in"] is False


def test_token_exchange_failure_fails_closed(client_env):
    transport = FailingTransport()
    result, _ = _start(transport)
    params = _redirect_params(result)

    with pytest.raises(error.HTTPError) as excinfo:
        _get(result["listen_port"], {"state": params["state"], "code": "c"})
    assert excinfo.value.code == 400
    _wait_flow_done()
    assert oauth.load_stored_auth() is None


def test_double_start_replaces_pending_flow(client_env):
    first, _ = _start(FakeTokenTransport())
    transport = FakeTokenTransport()
    second, _ = _start(transport)
    assert second["listen_port"] != first["listen_port"]
    assert oauth.flow_pending() is True

    params = _redirect_params(second)
    _get(second["listen_port"], {"state": params["state"], "code": "c"}).close()
    _wait_flow_done()
    assert oauth.auth_status()["signed_in"] is True


def test_flow_times_out(client_env):
    result, _ = _start(FakeTokenTransport(), timeout_seconds=0)
    _wait_flow_done()
    assert oauth.load_stored_auth() is None
    assert result["flow_pending"] is True  # was pending at return time


def test_start_signin_without_client_config_raises(monkeypatch, tmp_path):
    # Isolate lv_home(): on a machine with a real connected OAuth client,
    # ~/.lingua-viva/config/oauth_client.json exists and load_client_config()
    # would find it (hermeticity gap found 2026-08-01).
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    with pytest.raises(DriveConfigError):
        oauth.start_signin(transport=FakeTokenTransport(), opener=lambda url: None)


def test_client_config_env_beats_files(client_env):
    assert oauth.load_client_config() == {
        "client_id": "app-client-id",
        "client_secret": "app-client-secret",
    }


def test_client_config_accepts_spec_secret_alias(monkeypatch):
    monkeypatch.setenv("LV_GOOGLE_OAUTH_CLIENT_ID", "app-client-id")
    monkeypatch.delenv("LV_GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("LV_GOOGLE_OAUTH_SECRET", "app-client-secret")
    assert oauth.load_client_config() == {
        "client_id": "app-client-id",
        "client_secret": "app-client-secret",
    }


def test_client_config_falls_back_to_lv_home_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    config_dir = tmp_path / "lv-home" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "oauth_client.json").write_text(
        json.dumps({"client_id": "file-id", "client_secret": "file-secret"})
    )
    assert oauth.load_client_config() == {
        "client_id": "file-id",
        "client_secret": "file-secret",
    }


def test_client_config_missing_returns_none_and_status_reflects_it(monkeypatch, tmp_path):
    # Same lv_home() isolation as test_start_signin_without_client_config_raises.
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    assert oauth.load_client_config() is None
    status = oauth.auth_status()
    assert status["can_signin"] is False
    assert status["signed_in"] is False


def test_mark_needs_signin_flips_status():
    oauth._save_stored_auth(
        {
            "version": 1,
            "client_id": "cid",
            "client_secret": "csecret",
            "refresh_token": "rt",
            "account_email": "teacher@example.org",
            "needs_signin": False,
        }
    )
    assert oauth.auth_status()["signed_in"] is True
    oauth.mark_needs_signin()
    status = oauth.auth_status()
    assert status["signed_in"] is False
    assert status["needs_signin"] is True
    assert status["account_email"] == "teacher@example.org"


def test_mark_needs_signin_noop_when_never_signed_in():
    oauth.mark_needs_signin()
    assert oauth.load_stored_auth() is None


def test_auth_status_is_secret_free(client_env):
    oauth._save_stored_auth(
        {
            "version": 1,
            "client_id": "cid",
            "client_secret": "stored-client-secret",
            "refresh_token": "stored-refresh-secret",
            "account_email": "teacher@example.org",
            "needs_signin": False,
        }
    )
    text = json.dumps(oauth.auth_status())
    assert "stored-client-secret" not in text
    assert "stored-refresh-secret" not in text


def test_disconnect_revokes_and_deletes():
    oauth._save_stored_auth({"version": 1, "refresh_token": "rt-to-revoke"})
    transport = FakeTokenTransport()
    assert oauth.disconnect(transport=transport) is True
    assert transport.posted == [(oauth.REVOKE_URL, {"token": "rt-to-revoke"})]
    assert oauth.load_stored_auth() is None
    assert not oauth.auth_config_path().exists()


def test_disconnect_deletes_even_when_revoke_fails():
    oauth._save_stored_auth({"version": 1, "refresh_token": "rt"})
    assert oauth.disconnect(transport=FailingTransport()) is True
    assert oauth.load_stored_auth() is None


def test_disconnect_without_stored_auth_returns_false():
    assert oauth.disconnect(transport=FakeTokenTransport()) is False


def test_decode_id_token_email():
    assert oauth._decode_id_token_email(_id_token("x@y.z")) == "x@y.z"
    assert oauth._decode_id_token_email("garbage") is None
    assert oauth._decode_id_token_email("") is None
    no_email = base64.urlsafe_b64encode(b'{"sub": "123"}').decode().rstrip("=")
    assert oauth._decode_id_token_email(f"h.{no_email}.s") is None


# --- load_settings precedence + status fields (spec §A2/§A5/§A6) ---------


def _store_signin(email="teacher@example.org", *, needs_signin=False):
    oauth._save_stored_auth(
        {
            "version": 1,
            "client_id": "stored-cid",
            "client_secret": "stored-csecret",
            "refresh_token": "stored-rt",
            "account_email": email,
            "needs_signin": needs_signin,
        }
    )


def _env_creds(monkeypatch):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "env-cid")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "env-csecret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "env-rt")


def test_load_settings_env_shadows_stored_signin(monkeypatch):
    _store_signin()
    _env_creds(monkeypatch)
    settings = drive.load_settings()
    assert settings.auth_source == "env"
    assert settings.refresh_token == "env-rt"


def test_load_settings_falls_back_to_stored_signin(monkeypatch):
    _store_signin()
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ROOT_ID", "env-root")
    settings = drive.load_settings()
    assert settings.configured is True
    assert settings.auth_source == "stored"
    assert settings.refresh_token == "stored-rt"
    assert settings.root_id == "env-root"  # root id still honored from env


def test_load_settings_ignores_dead_stored_signin():
    _store_signin(needs_signin=True)
    settings = drive.load_settings()
    assert settings.configured is False
    assert settings.auth_source == "env"


def test_status_env_shadowing_hides_account_email(monkeypatch):
    _store_signin()
    _env_creds(monkeypatch)
    status = drive.status()
    assert status["configured"] is True
    assert status["auth_source"] == "env"
    assert status["account_email"] is None


def test_status_stored_signin_fields_and_folder_destination():
    _store_signin()
    status = drive.status()
    assert status["configured"] is True
    assert status["auth_source"] == "stored"
    assert status["account_email"] == "teacher@example.org"
    assert status["needs_signin"] is False
    assert status["can_upload"] is False  # no root_id, no connected folders

    drive._save_connected_folders(
        [{"id": "folder-1", "name": "Class", "purpose": "curriculum_unit_source"}]
    )
    assert drive.status()["can_upload"] is True  # connected folder = destination


def test_status_needs_signin_surfaces_reauth_message():
    _store_signin(needs_signin=True)
    status = drive.status()
    assert status["configured"] is False
    assert status["needs_signin"] is True
    assert status["account_email"] == "teacher@example.org"
    assert "sign in" in status["setup_message"].lower()


def test_status_is_secret_free_with_stored_signin():
    _store_signin()
    text = json.dumps(drive.status())
    assert "stored-csecret" not in text
    assert "stored-rt" not in text


class InvalidGrantTransport:
    def post_form(self, url, data):
        raise error.HTTPError(
            url, 400, "Bad Request", None, io.BytesIO(b'{"error": "invalid_grant"}')
        )


def test_invalid_grant_on_stored_signin_marks_needs_signin():
    _store_signin()
    settings = drive.load_settings()
    assert settings.auth_source == "stored"
    with pytest.raises(DriveAuthError, match="sign in to Google again"):
        drive._access_token(settings, InvalidGrantTransport())
    assert oauth.load_stored_auth()["needs_signin"] is True
    assert drive.load_settings().configured is False


def test_invalid_grant_on_env_settings_stays_generic(monkeypatch):
    _env_creds(monkeypatch)
    settings = drive.load_settings()
    with pytest.raises(DriveAuthError, match="authorization failed"):
        drive._access_token(settings, InvalidGrantTransport())
    assert oauth.load_stored_auth() is None  # nothing flagged


def test_loopback_listener_closed_after_flow_completes(client_env):
    """H5 (SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27): the one-shot loopback
    listener must release its port once the flow finishes — a lingering
    listener on 127.0.0.1 would be a local attack surface."""
    transport = FakeTokenTransport()
    result, _opened = _start(transport)
    params = _redirect_params(result)
    port = result["listen_port"]

    with _get(port, {"state": params["state"], "code": "auth-code-1"}) as resp:
        assert resp.status == 200
    _wait_flow_done()

    # server_close() runs in the serve thread's finally block, so poll
    # briefly rather than asserting an instant refusal.
    end = time.monotonic() + 2.0
    while time.monotonic() < end:
        try:
            with request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                pass
        except (error.URLError, OSError):
            return  # port refused / reset — listener is gone
        time.sleep(0.05)
    pytest.fail("loopback listener still accepting connections after flow completed")


# --- Scope class-lock (no-admin ruling, 2026-08-19) -------------------------
# The app must request ONLY per-file Drive access (drive.file). The restricted
# full-Drive scope requires Google CASA verification or per-user test-user
# registration — both ruled non-starters (schools will not maintain staff
# email lists; teachers must sign in with zero special access). This lock
# fails if anyone widens the scope back.


def test_scope_is_per_file_never_restricted_full_drive():
    scopes = oauth.SCOPES.split()
    assert "https://www.googleapis.com/auth/drive.file" in scopes
    assert "https://www.googleapis.com/auth/drive" not in scopes
    assert "https://www.googleapis.com/auth/drive.readonly" not in scopes


def test_access_denied_surfaces_per_file_hint():
    """A 403/404 on a pasted link is EXPECTED under drive.file — the message
    must direct the teacher to direct upload, never to a sharing fix."""

    class Denied:
        def get_json(self, url, token):
            raise error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))

        def get_bytes(self, url, token):
            raise error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))

        def post_form(self, url, data):
            return {"access_token": "at"}

    settings = drive.DriveSettings(
        enabled=True,
        client_id="cid",
        client_secret="csecret",
        refresh_token="rt",
        root_id=None,
    )
    with pytest.raises(DriveAuthError) as excinfo:
        drive.connect_folder(
            "https://drive.google.com/drive/folders/abc123DEF456ghi789",
            settings=settings,
            transport=Denied(),
        )
    assert "per-file" in str(excinfo.value)
    assert "upload" in str(excinfo.value)

    with pytest.raises(DriveAuthError) as excinfo:
        drive.download_file_text(
            "abc123DEF456ghi789", settings=settings, transport=Denied()
        )
    assert "per-file" in str(excinfo.value)
