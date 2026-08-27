"""In-app Google sign-in for Drive (SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A).

Installed-app OAuth 2.0: PKCE (S256) + one-shot loopback listener on
127.0.0.1. The refresh token is stored locally (0600, atomic) and consumed by
google_drive_integration.load_settings() with env-var precedence. The bundled
client id/secret are app configuration for Google's installed-app flow — not a
confidential server secret — and are NEVER committed (build-time injection or
local uncommitted file; see spec §A3).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse

from src.lingua_viva.config import lv_home
from src.lingua_viva.google_drive_integration import (
    DriveConfigError,
    DriveTransport,
    TOKEN_URL,
    _atomic_write_private_json,
    default_transport,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# openid + email make account_email reliable via the ID token (spec §A4).
# drive.file (2026-08-19, no-admin ruling): per-file access — the app only
# sees files/folders it created. Non-sensitive scope, so the app can be
# published to production with NO Google verification, NO test-user lists,
# NO school-admin setup: any teacher with a Google account can sign in.
# NEVER widen back to the restricted ".../auth/drive" scope — that requires
# CASA verification or per-user test registration, both ruled non-starters.
SCOPES = "openid email https://www.googleapis.com/auth/drive.file"
FLOW_TIMEOUT_SECONDS = 120


def auth_config_path() -> Path:
    override = os.environ.get("LV_GOOGLE_DRIVE_AUTH_PATH")
    if override:
        return Path(override).expanduser()
    return lv_home() / "config" / "google_drive.json"


def _client_config_candidates() -> list[Path]:
    """Uncommitted locations for the installed-app client config (spec §A3)."""
    candidates = [lv_home() / "config" / "oauth_client.json"]
    if getattr(sys, "frozen", False):  # packaged desktop build (CI-injected)
        candidates.append(Path(sys.executable).resolve().parent / "oauth_client.json")
    candidates.append(Path(__file__).resolve().parents[2] / "oauth_client.json")
    return candidates


def load_client_config() -> dict[str, str] | None:
    client_id = (os.environ.get("LV_GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (
        os.environ.get("LV_GOOGLE_OAUTH_CLIENT_SECRET")
        or os.environ.get("LV_GOOGLE_OAUTH_SECRET")
        or ""
    ).strip()
    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret}
    for path in _client_config_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data.get("client_id") and data.get("client_secret"):
            return {
                "client_id": str(data["client_id"]),
                "client_secret": str(data["client_secret"]),
            }
    return None


def load_stored_auth() -> dict[str, Any] | None:
    try:
        data = json.loads(auth_config_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _save_stored_auth(data: dict[str, Any]) -> None:
    _atomic_write_private_json(auth_config_path(), data)


def mark_needs_signin() -> None:
    """Called when a stored refresh token dies (invalid_grant) — spec §A6."""
    stored = load_stored_auth()
    if stored is None:
        return
    stored["needs_signin"] = True
    _save_stored_auth(stored)


def auth_status() -> dict[str, Any]:
    stored = load_stored_auth() or {}
    signed_in = bool(stored.get("refresh_token")) and not stored.get("needs_signin")
    return {
        "signed_in": signed_in,
        "account_email": stored.get("account_email") or None,
        "needs_signin": bool(stored.get("needs_signin")),
        "can_signin": load_client_config() is not None,
        "flow_pending": flow_pending(),
    }


def _decode_id_token_email(id_token: str) -> str | None:
    """Best-effort email from the ID token payload.

    No signature verification: the token arrives directly from Google's token
    endpoint over TLS in exchange for our PKCE-bound code (standard for
    installed apps consuming their own token response).
    """
    try:
        payload_segment = id_token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        email = payload.get("email")
        return str(email) if email else None
    except Exception:
        return None


_FLOW_LOCK = threading.Lock()
_ACTIVE_FLOW: dict[str, Any] | None = None


def flow_pending() -> bool:
    with _FLOW_LOCK:
        return bool(_ACTIVE_FLOW and not _ACTIVE_FLOW["done"])


def cancel_active_flow() -> None:
    """Invalidate any pending flow (double-start replaces it — spec §A1)."""
    global _ACTIVE_FLOW
    with _FLOW_LOCK:
        flow = _ACTIVE_FLOW
        _ACTIVE_FLOW = None
    if flow is not None:
        flow["done"] = True


_SUCCESS_PAGE = (
    "<html><body style='font-family:sans-serif;margin:3em;'>"
    "<h2>You're signed in.</h2><p>You can close this tab and go back to "
    "Lingua Viva.</p></body></html>"
)
_FAILURE_PAGE = (
    "<html><body style='font-family:sans-serif;margin:3em;'>"
    "<h2>Sign-in didn't finish.</h2><p>{message}</p>"
    "<p>Go back to Lingua Viva and try again.</p></body></html>"
)


def _log_connected_event(email: str | None) -> None:
    try:
        from src.lingua_viva.privacy_log import log_event

        log_event("drive_account_connected", query_text=email or "")
    except Exception:
        pass


def start_signin(
    *,
    transport: DriveTransport | None = None,
    opener: Callable[[str], Any] | None = None,
    timeout_seconds: int = FLOW_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Begin the loopback sign-in flow; returns the auth URL immediately.

    The UI polls /api/google-drive/status until `configured` flips (spec §A1).
    """
    global _ACTIVE_FLOW
    client = load_client_config()
    if client is None:
        raise DriveConfigError(
            "Google sign-in is not available on this build: the app's Google "
            "client configuration is missing."
        )
    cancel_active_flow()

    transport = transport or default_transport()
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    state = secrets.token_urlsafe(32)

    flow: dict[str, Any] = {"done": False, "error": None, "state": state}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # no request logging
            return

        def _respond(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            params = parse.parse_qs(parse.urlparse(self.path).query)
            returned_state = (params.get("state") or [""])[0]
            code = (params.get("code") or [""])[0]
            if flow["done"] or returned_state != state:
                self._respond(400, _FAILURE_PAGE.format(message="This sign-in link is stale."))
                return
            if not code:
                flow["error"] = "Google did not grant access."
                flow["done"] = True
                self._respond(400, _FAILURE_PAGE.format(message="Google did not grant access."))
                return
            try:
                tokens = transport.post_form(
                    TOKEN_URL,
                    {
                        "client_id": client["client_id"],
                        "client_secret": client["client_secret"],
                        "code": code,
                        "code_verifier": verifier,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                refresh_token = tokens.get("refresh_token")
                if not isinstance(refresh_token, str) or not refresh_token:
                    raise ValueError("no refresh token in response")
            except Exception:
                flow["error"] = "Sign-in could not be completed."
                flow["done"] = True
                self._respond(
                    400, _FAILURE_PAGE.format(message="Sign-in could not be completed.")
                )
                return
            email = _decode_id_token_email(str(tokens.get("id_token") or ""))
            _save_stored_auth(
                {
                    "version": 1,
                    "client_id": client["client_id"],
                    "client_secret": client["client_secret"],
                    "refresh_token": refresh_token,
                    "account_email": email,
                    "needs_signin": False,
                    "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            _log_connected_event(email)
            flow["done"] = True
            self._respond(200, _SUCCESS_PAGE)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.timeout = 1
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"

    def _serve() -> None:
        deadline = time.monotonic() + timeout_seconds
        try:
            while not flow["done"] and time.monotonic() < deadline:
                server.handle_request()
        finally:
            flow["done"] = True
            server.server_close()

    thread = threading.Thread(target=_serve, name="lv-drive-signin", daemon=True)
    flow["server"] = server
    flow["thread"] = thread
    flow["port"] = port
    with _FLOW_LOCK:
        _ACTIVE_FLOW = flow
    thread.start()

    auth_url = AUTH_URL + "?" + parse.urlencode(
        {
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    if opener is None:
        # Backend-side open works identically in browser and desktop modes and
        # sidesteps the Electron openExternal allowlist (spec §A1).
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
    else:
        opener(auth_url)
    return {"auth_url": auth_url, "flow_pending": True, "listen_port": port}


def disconnect(*, transport: DriveTransport | None = None) -> bool:
    """Delete the stored token; best-effort revoke at Google first."""
    cancel_active_flow()
    stored = load_stored_auth()
    if stored is None:
        return False
    refresh_token = stored.get("refresh_token")
    if refresh_token:
        transport = transport or default_transport()
        try:
            transport.post_form(REVOKE_URL, {"token": str(refresh_token)})
        except Exception:
            pass  # revocation is best-effort; local deletion is the guarantee
    try:
        auth_config_path().unlink()
    except FileNotFoundError:
        pass
    return True
