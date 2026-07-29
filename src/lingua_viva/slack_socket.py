"""Socket Mode transport for the LV Slack daily operations assistant.

Spec: dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md §3.1 (Lane A).

Design decisions, in the order they matter:

- Socket Mode over `websockets` + stdlib urllib only. No slack_sdk, no
  slack_bolt: no public URL or tunnel exists on a teacher's laptop, and
  the frozen-binary discipline (see slack_integration.py, Jul 22 spec)
  forbids new dependencies. `websockets` is already a core dependency.
- This module is TRANSPORT ONLY. It knows how to open a Socket Mode
  connection, ack envelopes, dedup, reconnect, and call three Web API
  methods. It never inspects message text, never touches student data,
  and never calls ObservationCapturePipeline or StudentLensStore — the
  conversation layer (`src/education/slack_ops_bot.py`, Lane D) receives
  every envelope through one injected async callback and does all
  filtering there.
- Ack-before-processing: Slack requires an envelope ack within 3s or it
  redelivers. The read loop sends `{"envelope_id": ...}` back on the
  socket IMMEDIATELY on receipt — before dedup, before dispatch — and
  queues the payload for a separate worker task, so a slow handler can
  never cause redelivery storms.
- Dedup mirrors slack_bot.py's `_seen_event_ids` pattern: one bounded
  LRU set (cap 10_000) fed by a deque, keyed by envelope_id AND, for
  events_api payloads, the inner event's `client_msg_id` or
  (channel, ts) — Slack redelivers the same event under fresh envelope
  ids, so envelope_id alone is not enough.
- Reconnect: Slack sends a `disconnect` message before refreshing a
  connection, and wss URLs from `apps.connections.open` are single-use.
  Any disconnect or connection error re-calls apps.connections.open and
  reconnects with jittered exponential backoff (base 1s, cap 60s).
- Secrets stay in the process environment. `require_ops_config()` fails
  closed with the names of missing/malformed variables only — values are
  never persisted and never logged, and `ops_status()` reports presence
  booleans and counts only (same contract as slack_integration.py).
- Testability: the websocket connect call, the apps.connections.open
  call, urlopen, sleep, and the jitter source are all injectable
  constructor seams, so the full loop runs offline under pytest with no
  network — the same injection style slack_bot.py uses for
  post_message/now.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional
from urllib import error, request

APPS_CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"
AUTH_TEST_URL = "https://slack.com/api/auth.test"
CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
CHAT_UPDATE_URL = "https://slack.com/api/chat.update"
CONVERSATIONS_OPEN_URL = "https://slack.com/api/conversations.open"

WEB_API_TIMEOUT_SECONDS = 10
WEB_API_MAX_RESPONSE_BYTES = 512 * 1024
MAX_SEEN_KEYS = 10_000
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 60.0

DISPATCHED_ENVELOPE_TYPES = ("events_api", "interactive", "slash_commands")

logger = logging.getLogger(__name__)

OnEnvelope = Callable[[str, dict], Awaitable[None]]


class SlackOpsConfigurationError(ValueError):
    """Raised when Slack ops assistant configuration is missing or malformed."""


class SlackSocketOpenError(RuntimeError):
    """Raised internally when apps.connections.open does not yield a wss URL."""


@dataclass(frozen=True)
class SlackOpsConfig:
    """Validated, in-memory-only Slack ops credentials and routing."""

    bot_token: str
    app_token: str
    ops_channel: str
    teacher_map: dict[str, dict[str, str]]

    def __repr__(self) -> str:  # never leak secrets via repr/logging
        return (
            "SlackOpsConfig(bot_token=***, app_token=***, "
            f"ops_channel=***, teachers={len(self.teacher_map)})"
        )


def _parse_teacher_map(raw: str) -> dict[str, dict[str, str]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SlackOpsConfigurationError(
            "LV_SLACK_TEACHER_MAP must be a JSON object."
        ) from exc
    if not isinstance(parsed, dict):
        raise SlackOpsConfigurationError(
            "LV_SLACK_TEACHER_MAP must be a JSON object mapping Slack user IDs "
            "to {teacher_id, display_name}."
        )
    teachers: dict[str, dict[str, str]] = {}
    for user_id, entry in parsed.items():
        if not isinstance(user_id, str) or not user_id.strip():
            raise SlackOpsConfigurationError(
                "LV_SLACK_TEACHER_MAP keys must be non-empty Slack user IDs."
            )
        if not isinstance(entry, dict):
            raise SlackOpsConfigurationError(
                "LV_SLACK_TEACHER_MAP values must be objects with "
                "teacher_id and display_name."
            )
        teacher_id = entry.get("teacher_id")
        display_name = entry.get("display_name")
        if (
            not isinstance(teacher_id, str)
            or not teacher_id.strip()
            or not isinstance(display_name, str)
            or not display_name.strip()
        ):
            raise SlackOpsConfigurationError(
                "LV_SLACK_TEACHER_MAP entries need non-empty string "
                "teacher_id and display_name."
            )
        teachers[user_id.strip()] = {
            "teacher_id": teacher_id.strip(),
            "display_name": display_name.strip(),
        }
    return teachers


def _resolved_env(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    """Effective configuration source.

    When a caller passes an explicit mapping (tests, callers that already
    resolved) it is used verbatim. Otherwise the in-app credential store is
    layered under the real environment (env > stored, per variable) so
    credentials a teacher saved in Settings configure the assistant exactly
    as exported environment variables would.
    """
    if environ is not None:
        return environ
    try:
        # lazy: slack_credentials pulls in the Drive module — avoids a cycle
        from src.lingua_viva.slack_credentials import effective_env

        return effective_env()
    except Exception:  # pragma: no cover - store must never break startup
        logger.warning("Slack credential store unreadable; using environment only")
        return os.environ


def require_ops_config(environ: Mapping[str, str] | None = None) -> SlackOpsConfig:
    """Return validated ops configuration without logging any values.

    Fails closed: every missing variable is named in one error; malformed
    values (wrong token prefix, bad teacher-map JSON) raise with the
    variable name only, never its content.
    """
    env = _resolved_env(environ)
    bot_token = str(env.get("LV_SLACK_BOT_TOKEN", "")).strip()
    app_token = str(env.get("LV_SLACK_APP_TOKEN", "")).strip()
    ops_channel = str(env.get("LV_SLACK_OPS_CHANNEL", "")).strip()
    raw_teacher_map = str(env.get("LV_SLACK_TEACHER_MAP", "")).strip()

    missing = []
    if not bot_token:
        missing.append("LV_SLACK_BOT_TOKEN")
    if not app_token:
        missing.append("LV_SLACK_APP_TOKEN")
    if not ops_channel:
        missing.append("LV_SLACK_OPS_CHANNEL")
    if not raw_teacher_map:
        missing.append("LV_SLACK_TEACHER_MAP")
    if missing:
        raise SlackOpsConfigurationError(
            "Slack ops assistant is not configured. Missing: " + ", ".join(missing)
        )

    if not bot_token.startswith("xoxb-"):
        raise SlackOpsConfigurationError(
            "LV_SLACK_BOT_TOKEN must be a bot token (xoxb-...)."
        )
    if not app_token.startswith("xapp-"):
        raise SlackOpsConfigurationError(
            "LV_SLACK_APP_TOKEN must be an app-level token (xapp-...)."
        )
    teacher_map = _parse_teacher_map(raw_teacher_map)
    if not teacher_map:
        raise SlackOpsConfigurationError(
            "LV_SLACK_TEACHER_MAP must contain at least one teacher."
        )
    return SlackOpsConfig(
        bot_token=bot_token,
        app_token=app_token,
        ops_channel=ops_channel,
        teacher_map=teacher_map,
    )


# Slack error codes worth translating for a teacher. Anything else falls
# through to the raw code so support can still act on it.
_AUTH_TEST_MESSAGES = {
    "invalid_auth": "Slack rejected this bot token. Copy it again from your "
                    "Slack app's OAuth & Permissions page.",
    "account_inactive": "This token belongs to a Slack app that has been "
                        "disabled or uninstalled from the workspace.",
    "token_revoked": "This token was revoked. Reinstall the app in Slack and "
                     "copy the new bot token.",
    "not_authed": "No token was sent to Slack.",
    "URLError": "Could not reach Slack. Check the computer's internet connection.",
    "TimeoutError": "Slack did not answer in time. Try again in a moment.",
}


def auth_test(token: str, urlopen: Optional[Callable[..., Any]] = None) -> dict:
    """Verify a bot token against Slack's ``auth.test``.

    Returns a secret-free dict: ``{"ok": bool, "team": str, "bot_user": str}``
    on success, or ``{"ok": False, "error": code, "message": text}``. The token
    is never echoed back, never logged, and never stored by this call — saving
    is a separate, explicit step.
    """
    opener = urlopen if urlopen is not None else request.urlopen
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "not_authed", "message": _AUTH_TEST_MESSAGES["not_authed"]}

    outgoing = request.Request(
        AUTH_TEST_URL,
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with opener(outgoing, timeout=WEB_API_TIMEOUT_SECONDS) as response:
            result = json.loads(
                response.read(WEB_API_MAX_RESPONSE_BYTES).decode("utf-8")
            )
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        code = type(exc).__name__
        logger.warning("Slack auth.test failed (%s)", code)
        return {
            "ok": False,
            "error": code,
            "message": _AUTH_TEST_MESSAGES.get(code, "Could not reach Slack."),
        }

    if not isinstance(result, dict):
        return {"ok": False, "error": "invalid_response_shape",
                "message": "Slack returned an unexpected response."}
    if not result.get("ok"):
        code = str(result.get("error") or "unknown_error")
        logger.warning("Slack auth.test not ok (%s)", code)
        return {
            "ok": False,
            "error": code,
            "message": _AUTH_TEST_MESSAGES.get(code, f"Slack rejected the token ({code})."),
        }
    return {
        "ok": True,
        "team": str(result.get("team") or ""),
        "bot_user": str(result.get("user") or ""),
    }


_registered_client: Optional["SlackSocketClient"] = None


def register_ops_client(client: Optional["SlackSocketClient"]) -> None:
    """Register the running client so ops_status() can report liveness."""
    global _registered_client
    _registered_client = client


def ops_status(
    environ: Mapping[str, str] | None = None,
    client: Optional["SlackSocketClient"] = None,
) -> dict:
    """Return a secret-free readiness/liveness summary for the local app UI."""
    env = _resolved_env(environ)
    bot_token_set = bool(str(env.get("LV_SLACK_BOT_TOKEN", "")).strip())
    app_token_set = bool(str(env.get("LV_SLACK_APP_TOKEN", "")).strip())
    ops_channel_set = bool(str(env.get("LV_SLACK_OPS_CHANNEL", "")).strip())
    teacher_map_set = bool(str(env.get("LV_SLACK_TEACHER_MAP", "")).strip())
    teacher_count = 0
    config_error = None
    configured = False
    try:
        config = require_ops_config(env)
        teacher_count = len(config.teacher_map)
        configured = True
    except SlackOpsConfigurationError as exc:
        config_error = str(exc)

    active = client if client is not None else _registered_client
    return {
        "configured": configured,
        "mode": "socket_mode",
        "bot_token_set": bot_token_set,
        "app_token_set": app_token_set,
        "ops_channel_set": ops_channel_set,
        "teacher_map_set": teacher_map_set,
        "teacher_count": teacher_count,
        "config_error": config_error,
        "connected": bool(active.connected) if active is not None else False,
        "last_event_at": active.last_event_at if active is not None else None,
        "events_received": active.events_received if active is not None else 0,
    }


def _default_connect_factory() -> Callable[[str], Awaitable[Any]]:
    async def _connect(url: str) -> Any:
        import websockets

        return await websockets.connect(url, max_size=1024 * 1024)

    return _connect


class SlackSocketClient:
    """Asyncio Socket Mode client: connect, ack, dedup, dispatch, reconnect.

    All network touchpoints are injectable for offline tests:
      - ``connect``: async callable ``url -> websocket`` (recv/send/close)
      - ``urlopen``: stands in for ``urllib.request.urlopen``
      - ``sleep``: async backoff sleep (assertable in tests)
      - ``rng``: jitter source with ``uniform(a, b)``
      - ``now``: clock for ``last_event_at``
    """

    def __init__(
        self,
        config: SlackOpsConfig,
        on_envelope: OnEnvelope,
        *,
        connect: Optional[Callable[[str], Awaitable[Any]]] = None,
        urlopen: Optional[Callable[..., Any]] = None,
        sleep: Optional[Callable[[float], Awaitable[None]]] = None,
        rng: Optional[random.Random] = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._on_envelope = on_envelope
        self._connect = connect if connect is not None else _default_connect_factory()
        self._urlopen = urlopen if urlopen is not None else request.urlopen
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._rng = rng if rng is not None else random.Random()
        self._now = now

        self.connected: bool = False
        self.last_event_at: Optional[float] = None
        self.events_received: int = 0

        self._stopping = False
        self._run_task: Optional[asyncio.Task] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._websocket: Any = None
        self._backoff_attempt = 0
        self._seen_keys: set = set()
        self._seen_order: deque = deque()

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> asyncio.Task:
        """Start the connection loop; returns the long-running task."""
        if self._run_task is not None and not self._run_task.done():
            return self._run_task
        self._stopping = False
        self._worker_task = asyncio.create_task(self._dispatch_worker())
        self._run_task = asyncio.create_task(self._run())
        return self._run_task

    async def stop(self) -> None:
        """Close the socket and cancel both loop tasks cleanly."""
        self._stopping = True
        websocket = self._websocket
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass
        for task in (self._run_task, self._worker_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._run_task = None
        self._worker_task = None
        self.connected = False

    async def drain(self) -> None:
        """Wait for all queued envelope dispatches to finish (tests/shutdown)."""
        await self._queue.join()

    # ---------------------------------------------------------------- socket loop

    async def _run(self) -> None:
        while not self._stopping:
            try:
                url = await asyncio.to_thread(self._request_socket_url)
            except SlackSocketOpenError as exc:
                logger.warning("Socket Mode open failed (%s)", exc)
                await self._backoff()
                continue
            except Exception as exc:
                logger.warning(
                    "Socket Mode open failed unexpectedly (%s)", type(exc).__name__
                )
                await self._backoff()
                continue

            try:
                websocket = await self._connect(url)
            except Exception as exc:
                logger.warning(
                    "Socket Mode websocket connect failed (%s)", type(exc).__name__
                )
                await self._backoff()
                continue

            self._websocket = websocket
            try:
                await self._read_loop(websocket)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Socket Mode connection dropped (%s)", type(exc).__name__
                )
            finally:
                self.connected = False
                self._websocket = None
                try:
                    await websocket.close()
                except Exception:
                    pass
            if not self._stopping:
                await self._backoff()

    async def _read_loop(self, websocket: Any) -> None:
        while not self._stopping:
            raw = await websocket.recv()
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(message, dict):
                continue

            message_type = message.get("type")
            if message_type == "hello":
                self.connected = True
                self._backoff_attempt = 0
                logger.info("Socket Mode connected")
                continue
            if message_type == "disconnect":
                # Slack rotates connections; the wss URL is single-use, so
                # return to the run loop for a fresh apps.connections.open.
                logger.info("Socket Mode disconnect requested; reconnecting")
                return

            envelope_id = message.get("envelope_id")
            if not isinstance(envelope_id, str) or not envelope_id:
                continue

            # Ack FIRST — always, even for duplicates (Slack redelivers
            # precisely because an earlier ack was not seen).
            await websocket.send(json.dumps({"envelope_id": envelope_id}))

            self.events_received += 1
            self.last_event_at = self._now()

            if not isinstance(message_type, str) or message_type not in DISPATCHED_ENVELOPE_TYPES:
                continue
            payload = message.get("payload")
            if not isinstance(payload, dict):
                continue
            if self._is_duplicate(envelope_id, message_type, payload):
                continue
            self._queue.put_nowait((message_type, payload))

    async def _dispatch_worker(self) -> None:
        while True:
            envelope_type, payload = await self._queue.get()
            try:
                await self._on_envelope(envelope_type, payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A handler bug must never take down the transport.
                logger.warning(
                    "Envelope handler failed for type %s (%s)",
                    envelope_type,
                    type(exc).__name__,
                )
            finally:
                self._queue.task_done()

    def _is_duplicate(self, envelope_id: str, envelope_type: str, payload: dict) -> bool:
        keys: list[tuple] = [("envelope", envelope_id)]
        if envelope_type == "events_api":
            event = payload.get("event")
            if isinstance(event, dict):
                client_msg_id = event.get("client_msg_id")
                if isinstance(client_msg_id, str) and client_msg_id:
                    keys.append(("client_msg_id", client_msg_id))
                else:
                    channel = event.get("channel")
                    ts = event.get("ts")
                    if isinstance(channel, str) and isinstance(ts, str) and channel and ts:
                        keys.append(("channel_ts", channel, ts))
        if any(key in self._seen_keys for key in keys):
            return True
        for key in keys:
            self._seen_keys.add(key)
            self._seen_order.append(key)
        while len(self._seen_order) > MAX_SEEN_KEYS:
            expired = self._seen_order.popleft()
            self._seen_keys.discard(expired)
        return False

    async def _backoff(self) -> None:
        if self._stopping:
            return
        delay = min(
            BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** self._backoff_attempt)
        )
        delay = min(BACKOFF_CAP_SECONDS, delay * self._rng.uniform(0.5, 1.5))
        self._backoff_attempt += 1
        await self._sleep(delay)

    # ---------------------------------------------------------------- web api

    def _request_socket_url(self) -> str:
        result = self._call_web_api_sync(
            APPS_CONNECTIONS_OPEN_URL, {}, self._config.app_token
        )
        if not result.get("ok"):
            raise SlackSocketOpenError(
                f"apps.connections.open failed: {result.get('error', 'unknown_error')}"
            )
        url = result.get("url")
        if not isinstance(url, str) or not url.startswith("wss://"):
            raise SlackSocketOpenError("apps.connections.open returned no wss URL")
        return url

    def _call_web_api_sync(self, api_url: str, payload: dict, token: str) -> dict:
        """One Slack Web API POST via urllib. Returns a dict; never raises
        secrets — failures come back as {"ok": False, "error": ...}."""
        body = json.dumps(payload).encode("utf-8")
        outgoing = request.Request(
            api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with self._urlopen(outgoing, timeout=WEB_API_TIMEOUT_SECONDS) as response:
                result = json.loads(
                    response.read(WEB_API_MAX_RESPONSE_BYTES).decode("utf-8")
                )
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Slack Web API call to %s failed (%s)", api_url, type(exc).__name__
            )
            return {"ok": False, "error": type(exc).__name__}
        if not isinstance(result, dict):
            logger.warning("Slack Web API call to %s returned a non-object", api_url)
            return {"ok": False, "error": "invalid_response_shape"}
        if not result.get("ok"):
            logger.warning(
                "Slack Web API call to %s not ok (%s)",
                api_url,
                result.get("error", "unknown_error"),
            )
        return result

    async def post_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[list] = None,
        thread_ts: Optional[str] = None,
    ) -> dict:
        """chat.postMessage — returns the parsed response dict."""
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        return await asyncio.to_thread(
            self._call_web_api_sync, CHAT_POST_MESSAGE_URL, payload, self._config.bot_token
        )

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[list] = None,
    ) -> dict:
        """chat.update — returns the parsed response dict."""
        payload: dict[str, Any] = {"channel": channel, "ts": ts, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        return await asyncio.to_thread(
            self._call_web_api_sync, CHAT_UPDATE_URL, payload, self._config.bot_token
        )

    async def open_dm(self, user_id: str) -> Optional[str]:
        """conversations.open — returns the DM channel ID, or None on failure."""
        result = await asyncio.to_thread(
            self._call_web_api_sync,
            CONVERSATIONS_OPEN_URL,
            {"users": user_id},
            self._config.bot_token,
        )
        if not result.get("ok"):
            return None
        channel = result.get("channel")
        if isinstance(channel, dict):
            channel_id = channel.get("id")
            if isinstance(channel_id, str) and channel_id:
                return channel_id
        logger.warning("conversations.open returned no channel id")
        return None
