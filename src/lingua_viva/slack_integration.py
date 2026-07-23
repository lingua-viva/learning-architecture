"""Configuration and outbound transport for Lingua Viva's Slack observation bot.

Secrets stay in the local process environment.  The browser-facing status
shape intentionally reports only whether each value is present.
"""

from __future__ import annotations

import json
import os
from typing import Mapping
from urllib import error, request


SLACK_API_URL = "https://slack.com/api/chat.postMessage"


class SlackConfigurationError(ValueError):
    """Raised when local Slack configuration is missing or malformed."""


def teacher_channel_map(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Parse ``LV_SLACK_TEACHER_CHANNEL_MAP`` as channel-to-teacher JSON."""
    env = os.environ if environ is None else environ
    raw = str(env.get("LV_SLACK_TEACHER_CHANNEL_MAP", "")).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SlackConfigurationError(
            "LV_SLACK_TEACHER_CHANNEL_MAP must be a JSON object."
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(channel, str)
        and channel.strip()
        and isinstance(teacher, str)
        and teacher.strip()
        for channel, teacher in parsed.items()
    ):
        raise SlackConfigurationError(
            "LV_SLACK_TEACHER_CHANNEL_MAP must map channel IDs to teacher IDs."
        )
    return {channel.strip(): teacher.strip() for channel, teacher in parsed.items()}


def slack_status(environ: Mapping[str, str] | None = None) -> dict:
    """Return a secret-free readiness summary for the local app UI."""
    env = os.environ if environ is None else environ
    signing_secret_set = bool(str(env.get("LV_SLACK_SIGNING_SECRET", "")).strip())
    bot_token_set = bool(str(env.get("LV_SLACK_BOT_TOKEN", "")).strip())
    config_error = None
    try:
        channels = teacher_channel_map(env)
    except SlackConfigurationError as exc:
        channels = {}
        config_error = str(exc)
    channel_map_set = bool(channels)
    return {
        "configured": signing_secret_set and bot_token_set and channel_map_set and not config_error,
        "mode": "events_api",
        "event_path": "/api/slack/events",
        "signing_secret_set": signing_secret_set,
        "bot_token_set": bot_token_set,
        "channel_map_set": channel_map_set,
        "registered_channel_count": len(channels),
        "config_error": config_error,
        "local_only_capture": True,
        "voice_transcripts_supported": True,
    }


def require_slack_config(environ: Mapping[str, str] | None = None) -> tuple[str, str, dict[str, str]]:
    """Return validated credentials and routing without logging their values."""
    env = os.environ if environ is None else environ
    signing_secret = str(env.get("LV_SLACK_SIGNING_SECRET", "")).strip()
    bot_token = str(env.get("LV_SLACK_BOT_TOKEN", "")).strip()
    channels = teacher_channel_map(env)
    missing = []
    if not signing_secret:
        missing.append("LV_SLACK_SIGNING_SECRET")
    if not bot_token:
        missing.append("LV_SLACK_BOT_TOKEN")
    if not channels:
        missing.append("LV_SLACK_TEACHER_CHANNEL_MAP")
    if missing:
        raise SlackConfigurationError(
            "Slack is not configured. Missing: " + ", ".join(missing)
        )
    return signing_secret, bot_token, channels


def post_slack_message(bot_token: str, channel: str, text: str) -> None:
    """Post one fixed bot acknowledgement through Slack's Web API."""
    body = json.dumps({"channel": channel, "text": text}).encode("utf-8")
    outgoing = request.Request(
        SLACK_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with request.urlopen(outgoing, timeout=10) as response:
            result = json.loads(response.read(64 * 1024).decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Slack acknowledgement could not be delivered.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Slack acknowledgement returned an invalid response.")
    if not result.get("ok"):
        raise RuntimeError(
            f"Slack acknowledgement failed: {result.get('error', 'unknown_error')}"
        )
