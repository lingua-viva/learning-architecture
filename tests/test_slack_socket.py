"""Transport contracts for the Slack ops Socket Mode client (spec §3.1).

Everything runs offline: the websocket connect, apps.connections.open,
urlopen, sleep, and jitter are all injected through the client's
constructor seams. No test here ever opens a network connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional
from urllib import error as urllib_error

import src.lingua_viva.slack_socket as slack_socket
from src.lingua_viva.slack_socket import (
    APPS_CONNECTIONS_OPEN_URL,
    CHAT_POST_MESSAGE_URL,
    CHAT_UPDATE_URL,
    CONVERSATIONS_OPEN_URL,
    SlackOpsConfigurationError,
    SlackSocketClient,
    ops_status,
    register_ops_client,
    require_ops_config,
)


VALID_ENV = {
    "LV_SLACK_BOT_TOKEN": "xoxb-secret-bot-token",
    "LV_SLACK_APP_TOKEN": "xapp-secret-app-token",
    "LV_SLACK_OPS_CHANNEL": "C0PSCHAN",
    "LV_SLACK_TEACHER_MAP": json.dumps(
        {
            "U111": {"teacher_id": "teacher-1", "display_name": "Ms. One"},
            "U222": {"teacher_id": "teacher-2", "display_name": "Mr. Two"},
        }
    ),
}


def make_config():
    return require_ops_config(VALID_ENV)


def expect_config_error(env: dict, fragment: str) -> None:
    try:
        require_ops_config(env)
    except SlackOpsConfigurationError as exc:
        assert fragment in str(exc)
    else:
        raise AssertionError(f"configuration accepted; expected error mentioning {fragment!r}")


# ------------------------------------------------------------------ test fakes


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return self._body


def make_urlopen(bodies: Optional[list] = None, capture: Optional[list] = None):
    """urlopen stand-in. `bodies` is consumed in order (last one repeats);
    an Exception entry is raised instead of returned."""
    queue = list(bodies) if bodies else [b'{"ok":true,"url":"wss://fake.slack/link"}']

    def fake_urlopen(outgoing, timeout):
        if capture is not None:
            capture.append(
                {
                    "url": outgoing.full_url,
                    "authorization": outgoing.get_header("Authorization"),
                    "body": json.loads(outgoing.data),
                    "timeout": timeout,
                }
            )
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    return fake_urlopen


class FakeWebSocket:
    def __init__(self, messages: list, order: Optional[list] = None):
        self._messages = list(messages)
        self.sent: list[dict] = []
        self.closed = False
        self.order = order if order is not None else []
        self._blocker = asyncio.Event()

    async def recv(self):
        if self._messages:
            return self._messages.pop(0)
        await self._blocker.wait()
        raise ConnectionError("fake websocket closed")

    async def send(self, raw):
        data = json.loads(raw)
        self.sent.append(data)
        self.order.append(("ack", data.get("envelope_id")))

    async def close(self):
        self.closed = True
        self._blocker.set()


def make_connect(sockets: list):
    """Connect seam yielding sockets (or raising Exception entries) in order;
    blocks forever once exhausted so a reconnect loop cannot spin."""

    async def connect(url):
        connect.calls.append(url)
        if not sockets:
            await asyncio.Event().wait()
        item = sockets.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    connect.calls = []
    return connect


class FixedRng:
    def uniform(self, _a, _b):
        return 1.0


def make_sleep(record: list):
    async def _sleep(delay):
        record.append(delay)
        await asyncio.sleep(0)

    return _sleep


async def eventually(predicate, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not met within timeout")


def hello() -> str:
    return json.dumps({"type": "hello"})


def envelope(envelope_id: str, envelope_type: str = "events_api", payload: Optional[dict] = None) -> str:
    if payload is None:
        payload = {"event": {"type": "message", "channel": "C0PSCHAN", "ts": envelope_id}}
    return json.dumps({"envelope_id": envelope_id, "type": envelope_type, "payload": payload})


def make_client(on_envelope=None, sockets=None, urlopen=None, sleeps=None):
    async def _ignore(_envelope_type, _payload):
        return None

    return SlackSocketClient(
        make_config(),
        on_envelope if on_envelope is not None else _ignore,
        connect=make_connect(sockets if sockets is not None else []),
        urlopen=urlopen if urlopen is not None else make_urlopen(),
        sleep=make_sleep(sleeps if sleeps is not None else []),
        rng=FixedRng(),
    )


# ------------------------------------------------------------------ config


def test_require_ops_config_names_all_missing_variables():
    try:
        require_ops_config({})
    except SlackOpsConfigurationError as exc:
        message = str(exc)
        for name in (
            "LV_SLACK_BOT_TOKEN",
            "LV_SLACK_APP_TOKEN",
            "LV_SLACK_OPS_CHANNEL",
            "LV_SLACK_TEACHER_MAP",
        ):
            assert name in message
    else:
        raise AssertionError("empty environment was accepted")


def test_require_ops_config_names_single_missing_variable():
    env = dict(VALID_ENV)
    del env["LV_SLACK_OPS_CHANNEL"]
    expect_config_error(env, "LV_SLACK_OPS_CHANNEL")


def test_require_ops_config_rejects_wrong_bot_token_prefix():
    env = dict(VALID_ENV, LV_SLACK_BOT_TOKEN="xoxp-user-token")
    expect_config_error(env, "xoxb-")


def test_require_ops_config_rejects_wrong_app_token_prefix():
    env = dict(VALID_ENV, LV_SLACK_APP_TOKEN="xoxb-not-an-app-token")
    expect_config_error(env, "xapp-")


def test_teacher_map_rejects_invalid_json():
    env = dict(VALID_ENV, LV_SLACK_TEACHER_MAP="{not json")
    expect_config_error(env, "LV_SLACK_TEACHER_MAP")


def test_teacher_map_rejects_non_object():
    env = dict(VALID_ENV, LV_SLACK_TEACHER_MAP='["U111"]')
    expect_config_error(env, "LV_SLACK_TEACHER_MAP")


def test_teacher_map_rejects_non_object_entry():
    env = dict(VALID_ENV, LV_SLACK_TEACHER_MAP='{"U111": "teacher-1"}')
    expect_config_error(env, "LV_SLACK_TEACHER_MAP")


def test_teacher_map_rejects_entry_missing_fields():
    env = dict(VALID_ENV, LV_SLACK_TEACHER_MAP='{"U111": {"teacher_id": "teacher-1"}}')
    expect_config_error(env, "display_name")


def test_teacher_map_rejects_empty_object():
    env = dict(VALID_ENV, LV_SLACK_TEACHER_MAP="{}")
    expect_config_error(env, "LV_SLACK_TEACHER_MAP")


def test_valid_config_parses_and_normalizes():
    config = require_ops_config(VALID_ENV)
    assert config.ops_channel == "C0PSCHAN"
    assert config.teacher_map["U111"] == {
        "teacher_id": "teacher-1",
        "display_name": "Ms. One",
    }
    assert len(config.teacher_map) == 2
    assert "xoxb" not in repr(config)
    assert "xapp" not in repr(config)


def test_empty_injected_environment_does_not_fall_back_to_machine_environment(monkeypatch):
    monkeypatch.setenv("LV_SLACK_BOT_TOKEN", "xoxb-machine")
    expect_config_error({}, "LV_SLACK_BOT_TOKEN")


# ------------------------------------------------------------------ ops_status


def test_ops_status_is_secret_free():
    result = ops_status(VALID_ENV)
    dumped = json.dumps(result)
    assert result["configured"] is True
    assert result["teacher_count"] == 2
    assert "xoxb-secret-bot-token" not in dumped
    assert "xapp-secret-app-token" not in dumped
    assert "C0PSCHAN" not in dumped
    assert "U111" not in dumped
    assert "teacher-1" not in dumped
    assert "Ms. One" not in dumped


def test_ops_status_unconfigured_shape():
    result = ops_status({"LV_SLACK_BOT_TOKEN": "xoxb-only"})
    assert result["configured"] is False
    assert result["bot_token_set"] is True
    assert result["app_token_set"] is False
    assert result["ops_channel_set"] is False
    assert result["teacher_map_set"] is False
    assert result["teacher_count"] == 0
    assert result["connected"] is False
    assert result["last_event_at"] is None
    assert result["events_received"] == 0


def test_ops_status_reflects_passed_client_liveness():
    client = make_client()
    client.connected = True
    client.last_event_at = 1234.5
    client.events_received = 7
    result = ops_status(VALID_ENV, client=client)
    assert result["connected"] is True
    assert result["last_event_at"] == 1234.5
    assert result["events_received"] == 7


def test_ops_status_uses_registered_client():
    client = make_client()
    client.connected = True
    client.events_received = 3
    register_ops_client(client)
    try:
        result = ops_status(VALID_ENV)
        assert result["connected"] is True
        assert result["events_received"] == 3
    finally:
        register_ops_client(None)


# ------------------------------------------------------------------ socket loop


async def test_hello_marks_connected_and_ack_precedes_dispatch():
    order: list = []
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        order.append(("dispatch", envelope_type))
        dispatched.append((envelope_type, payload))

    websocket = FakeWebSocket([hello(), envelope("E1")], order=order)
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(dispatched) == 1)
        assert client.connected is True
        assert order[0] == ("ack", "E1")
        assert order[1] == ("dispatch", "events_api")
        assert websocket.sent == [{"envelope_id": "E1"}]
        assert dispatched[0][0] == "events_api"
        assert client.events_received == 1
        assert client.last_event_at is not None
    finally:
        await client.stop()
    assert client.connected is False


async def test_duplicate_envelope_id_is_acked_but_dispatched_once():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append((envelope_type, payload))

    websocket = FakeWebSocket([hello(), envelope("E1"), envelope("E1")])
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(websocket.sent) == 2)
        await client.drain()
        assert websocket.sent == [{"envelope_id": "E1"}, {"envelope_id": "E1"}]
        assert len(dispatched) == 1
    finally:
        await client.stop()


async def test_duplicate_inner_client_msg_id_is_dispatched_once():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append(payload)

    payload = {"event": {"type": "message", "client_msg_id": "M1", "channel": "C1", "ts": "1.0"}}
    websocket = FakeWebSocket(
        [hello(), envelope("E1", payload=payload), envelope("E2", payload=payload)]
    )
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(websocket.sent) == 2)
        await client.drain()
        assert len(dispatched) == 1
    finally:
        await client.stop()


async def test_duplicate_inner_channel_ts_is_dispatched_once():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append(payload)

    payload = {"event": {"type": "message", "channel": "C1", "ts": "9.9"}}
    websocket = FakeWebSocket(
        [hello(), envelope("E1", payload=payload), envelope("E2", payload=payload)]
    )
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(websocket.sent) == 2)
        await client.drain()
        assert len(dispatched) == 1
    finally:
        await client.stop()


async def test_distinct_events_are_each_dispatched():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append((envelope_type, payload))

    websocket = FakeWebSocket(
        [
            hello(),
            envelope("E1"),
            envelope("E2"),
            envelope("E3", envelope_type="interactive", payload={"actions": []}),
            envelope("E4", envelope_type="slash_commands", payload={"command": "/lv"}),
        ]
    )
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(websocket.sent) == 4)
        await client.drain()
        assert [entry[0] for entry in dispatched] == [
            "events_api",
            "events_api",
            "interactive",
            "slash_commands",
        ]
    finally:
        await client.stop()


async def test_unknown_envelope_type_is_acked_but_not_dispatched():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append(envelope_type)

    websocket = FakeWebSocket([hello(), envelope("E1", envelope_type="mystery", payload={})])
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(websocket.sent) == 1)
        await client.drain()
        assert websocket.sent == [{"envelope_id": "E1"}]
        assert dispatched == []
    finally:
        await client.stop()


async def test_handler_exception_does_not_kill_the_loop():
    dispatched: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append(envelope_type)
        if len(dispatched) == 1:
            raise RuntimeError("handler bug")

    websocket = FakeWebSocket([hello(), envelope("E1"), envelope("E2")])
    client = make_client(on_envelope, sockets=[websocket])
    client.start()
    try:
        await eventually(lambda: len(dispatched) == 2)
    finally:
        await client.stop()


async def test_disconnect_message_triggers_fresh_url_and_reconnect():
    open_calls: list = []
    first = FakeWebSocket([hello(), json.dumps({"type": "disconnect"})])
    second = FakeWebSocket([hello(), envelope("E1")])
    dispatched: list = []
    sleeps: list = []

    async def on_envelope(envelope_type, payload):
        dispatched.append(envelope_type)

    client = SlackSocketClient(
        make_config(),
        on_envelope,
        connect=make_connect([first, second]),
        urlopen=make_urlopen(capture=open_calls),
        sleep=make_sleep(sleeps),
        rng=FixedRng(),
    )
    client.start()
    try:
        await eventually(lambda: len(dispatched) == 1)
        assert len(open_calls) == 2
        assert all(call["url"] == APPS_CONNECTIONS_OPEN_URL for call in open_calls)
        assert all(
            call["authorization"] == "Bearer xapp-secret-app-token" for call in open_calls
        )
        assert sleeps == [1.0]
        assert client.connected is True
    finally:
        await client.stop()


async def test_failed_open_backs_off_exponentially():
    sleeps: list = []
    client = SlackSocketClient(
        make_config(),
        lambda *_: None,
        connect=make_connect([]),
        urlopen=make_urlopen(
            bodies=[b'{"ok":false,"error":"invalid_auth"}'],
        ),
        sleep=make_sleep(sleeps),
        rng=FixedRng(),
    )
    client.start()
    try:
        await eventually(lambda: len(sleeps) >= 3)
        assert sleeps[:3] == [1.0, 2.0, 4.0]
        assert client.connected is False
    finally:
        await client.stop()


async def test_connect_failure_then_success_recovers():
    sleeps: list = []
    websocket = FakeWebSocket([hello()])
    client = SlackSocketClient(
        make_config(),
        lambda *_: None,
        connect=make_connect([ConnectionError("refused"), websocket]),
        urlopen=make_urlopen(),
        sleep=make_sleep(sleeps),
        rng=FixedRng(),
    )
    client.start()
    try:
        await eventually(lambda: client.connected)
        assert sleeps == [1.0]
    finally:
        await client.stop()


async def test_backoff_delay_is_capped():
    client = make_client()
    client._backoff_attempt = 30
    delays: list = []
    client._sleep = make_sleep(delays)
    await client._backoff()
    assert delays == [60.0]


# ------------------------------------------------------------------ web api helpers


async def test_post_message_builds_expected_request():
    capture: list = []
    client = make_client(urlopen=make_urlopen(bodies=[b'{"ok":true,"ts":"1.0"}'], capture=capture))
    result = await client.post_message("C123", "hello there")
    assert result == {"ok": True, "ts": "1.0"}
    assert capture == [
        {
            "url": CHAT_POST_MESSAGE_URL,
            "authorization": "Bearer xoxb-secret-bot-token",
            "body": {"channel": "C123", "text": "hello there"},
            "timeout": 10,
        }
    ]


async def test_post_message_includes_blocks_and_thread_ts_only_when_given():
    capture: list = []
    client = make_client(urlopen=make_urlopen(bodies=[b'{"ok":true}'], capture=capture))
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}]
    await client.post_message("C123", "hello", blocks=blocks, thread_ts="17.5")
    assert capture[0]["body"] == {
        "channel": "C123",
        "text": "hello",
        "blocks": blocks,
        "thread_ts": "17.5",
    }


async def test_update_message_builds_expected_request():
    capture: list = []
    client = make_client(urlopen=make_urlopen(bodies=[b'{"ok":true}'], capture=capture))
    result = await client.update_message("C123", "17.5", "updated", blocks=[{"type": "divider"}])
    assert result["ok"] is True
    assert capture[0]["url"] == CHAT_UPDATE_URL
    assert capture[0]["body"] == {
        "channel": "C123",
        "ts": "17.5",
        "text": "updated",
        "blocks": [{"type": "divider"}],
    }


async def test_open_dm_returns_channel_id():
    capture: list = []
    client = make_client(
        urlopen=make_urlopen(bodies=[b'{"ok":true,"channel":{"id":"D42"}}'], capture=capture)
    )
    channel_id = await client.open_dm("U111")
    assert channel_id == "D42"
    assert capture[0]["url"] == CONVERSATIONS_OPEN_URL
    assert capture[0]["body"] == {"users": "U111"}


async def test_open_dm_returns_none_on_api_error():
    client = make_client(urlopen=make_urlopen(bodies=[b'{"ok":false,"error":"user_not_found"}']))
    assert await client.open_dm("U111") is None


async def test_post_message_network_failure_returns_ok_false_without_raising(caplog):
    client = make_client(urlopen=make_urlopen(bodies=[urllib_error.URLError("down")]))
    with caplog.at_level("WARNING", logger=slack_socket.logger.name):
        result = await client.post_message("C123", "hello")
    assert result == {"ok": False, "error": "URLError"}
    assert "xoxb" not in caplog.text
    assert "hello" not in caplog.text


async def test_post_message_non_object_response_returns_ok_false():
    client = make_client(urlopen=make_urlopen(bodies=[b"[]"]))
    result = await client.post_message("C123", "hello")
    assert result == {"ok": False, "error": "invalid_response_shape"}


async def test_api_error_response_is_returned_and_logged_secret_free(caplog):
    client = make_client(urlopen=make_urlopen(bodies=[b'{"ok":false,"error":"channel_not_found"}']))
    with caplog.at_level("WARNING", logger=slack_socket.logger.name):
        result = await client.post_message("C123", "hello")
    assert result == {"ok": False, "error": "channel_not_found"}
    assert "xoxb" not in caplog.text
