"""In-app Slack credential storage (Slice 5 — Credentials).

Spec: dev/SPEC_CONNECTION_CREDENTIAL_SETUP_2026-07-28.md §Lingua Viva
Application. Teachers starting Monday need the ops bot, and until now the
only way to configure it was to export four environment variables in a
terminal — impossible for a non-developer, and the #1 LV credential gap.

Precedence, per variable: **env > stored > unset**. This mirrors
``google_drive_integration.load_settings()`` ("A fully env-configured
machine (operator provisioning) always shadows the stored sign-in"), with
one deliberate difference: Drive resolves all-or-nothing, this resolves per
variable, so an administrator can pin the bot token in the environment while
a teacher still sets the ops channel in-app. That hybrid is only honest if
the user can see it, so :func:`credential_status` reports the source of every
field individually and the Settings panel renders it — an env-sourced field
is shown as administrator-managed and cannot be overwritten from the app.

Storage is a 0600 atomic JSON file under ``lv_home()/config/``, the same
posture this repo already uses for the Google Drive refresh token
(``google_drive_oauth.auth_config_path``).

**Encryption at rest is deliberately NOT implemented here** — see
:data:`STORAGE_REASON`. The spec asks for Electron ``safeStorage``, but
safeStorage ciphertext is only decryptable inside the Electron main process,
and the component that needs the bot token is the *Python* Socket Mode
client (``slack_socket.SlackSocketClient``) at runtime. Adopting safeStorage
therefore requires decrypting in Electron and injecting into the backend
process env at spawn (``desktop/electron/bootstrap.ts``, the ``env:`` block
where the Python child is created). That path is designed for and left as
the documented next step rather than written blind and claimed working.

Nothing in this module logs, returns, or reprs a secret value.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.lingua_viva.config import lv_home
from src.lingua_viva.google_drive_integration import _atomic_write_private_json

# The four variables the ops assistant needs. Order is the order the
# Settings panel renders them.
SLACK_ENV_VARS: tuple[str, ...] = (
    "LV_SLACK_BOT_TOKEN",
    "LV_SLACK_APP_TOKEN",
    "LV_SLACK_OPS_CHANNEL",
    "LV_SLACK_TEACHER_MAP",
)

# Which of those are secrets. Non-secrets may be echoed back to the UI so a
# teacher can see what they typed; secrets never leave this process.
SLACK_SECRET_VARS: frozenset[str] = frozenset(
    {"LV_SLACK_BOT_TOKEN", "LV_SLACK_APP_TOKEN"}
)

STORAGE_MODE = "file-0600"
STORAGE_REASON = (
    "Stored in a 0600 file in your home folder, readable only by your user "
    "account — the same protection Lingua Viva already uses for your Google "
    "Drive sign-in. OS-keychain encryption needs the desktop app to hand the "
    "token to the backend at startup; that is not wired up yet."
)


class SlackCredentialError(ValueError):
    """Raised when a submitted credential is malformed. Never carries a value."""


def credentials_path() -> Path:
    override = os.environ.get("LV_SLACK_CREDENTIALS_PATH")
    if override:
        return Path(override).expanduser()
    return lv_home() / "config" / "slack_credentials.json"


def load_stored() -> dict[str, str]:
    """Stored credentials, or {} when absent/unreadable. Secret-bearing."""
    try:
        data = json.loads(credentials_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        name: str(data[name]).strip()
        for name in SLACK_ENV_VARS
        if isinstance(data.get(name), str) and str(data[name]).strip()
    }


def _validate(name: str, value: str) -> str:
    """Reject malformed values at the door, naming the field but never its
    content. Mirrors the checks in ``slack_socket.require_ops_config`` so a
    teacher is told at save time, not at silent-startup-failure time."""
    value = value.strip()
    if not value:
        raise SlackCredentialError(f"{name} cannot be empty.")
    if name == "LV_SLACK_BOT_TOKEN" and not value.startswith("xoxb-"):
        raise SlackCredentialError(
            "Bot token must start with 'xoxb-'. Copy it from your Slack app's "
            "OAuth & Permissions page (Bot User OAuth Token)."
        )
    if name == "LV_SLACK_APP_TOKEN" and not value.startswith("xapp-"):
        raise SlackCredentialError(
            "App-level token must start with 'xapp-'. Create it under Basic "
            "Information -> App-Level Tokens with the connections:write scope."
        )
    if name == "LV_SLACK_TEACHER_MAP":
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SlackCredentialError(
                "Teacher map must be valid JSON."
            ) from exc
        if not isinstance(parsed, dict) or not parsed:
            raise SlackCredentialError(
                "Teacher map must be a JSON object with at least one teacher, "
                'like {"U123": {"teacher_id": "t1", "display_name": "Ada"}}.'
            )
    return value


def save_stored(values: Mapping[str, Any]) -> dict[str, str]:
    """Merge ``values`` into the stored credentials and persist 0600.

    Only the four known variables are accepted; anything else is ignored so a
    malformed request can never write arbitrary keys. Returns the updated
    stored mapping (secret-bearing — callers must not return it to a client).
    """
    stored = load_stored()
    for name in SLACK_ENV_VARS:
        if name not in values:
            continue
        raw = values[name]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            stored.pop(name, None)  # explicit blank clears that field
            continue
        if not isinstance(raw, str):
            raise SlackCredentialError(f"{name} must be a string.")
        stored[name] = _validate(name, raw)
    if stored:
        _atomic_write_private_json(credentials_path(), stored)
    else:
        clear_stored()
    return stored


def clear_stored() -> None:
    credentials_path().unlink(missing_ok=True)


def effective_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The mapping the ops assistant should actually be configured from.

    Per-variable env-over-stored. Returned as a plain dict so it can be passed
    straight to ``require_ops_config``/``ops_status``, which already accept an
    injectable mapping.
    """
    env = os.environ if environ is None else environ
    merged: dict[str, str] = {}
    stored = load_stored()
    for name in SLACK_ENV_VARS:
        from_env = str(env.get(name, "") or "").strip()
        if from_env:
            merged[name] = from_env
        elif stored.get(name):
            merged[name] = stored[name]
    return merged


def field_source(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Where a given variable's effective value comes from."""
    env = os.environ if environ is None else environ
    if str(env.get(name, "") or "").strip():
        return "env"
    if load_stored().get(name):
        return "stored"
    return "unset"


def credential_status(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Secret-free description of how Slack is configured.

    Safe to return over HTTP: reports only whether each field is set and where
    it came from. Non-secret fields (ops channel, teacher map) echo their
    value so the Settings form can be pre-filled; secrets never do.
    """
    env = os.environ if environ is None else environ
    stored = load_stored()
    merged = effective_env(env)

    fields: dict[str, dict[str, Any]] = {}
    for name in SLACK_ENV_VARS:
        source = "env" if str(env.get(name, "") or "").strip() else (
            "stored" if stored.get(name) else "unset"
        )
        entry: dict[str, Any] = {
            "set": name in merged,
            "source": source,
            "secret": name in SLACK_SECRET_VARS,
            # An env-sourced field is provisioned by an administrator; the app
            # must not offer to overwrite something it cannot actually change.
            "editable_in_app": source != "env",
        }
        if name not in SLACK_SECRET_VARS and name in merged:
            entry["value"] = merged[name]
        fields[name] = entry

    return {
        "fields": fields,
        "storage": {
            "mode": STORAGE_MODE,
            "encrypted_at_rest": False,
            "explanation": STORAGE_REASON,
            "path": str(credentials_path()),
        },
    }
