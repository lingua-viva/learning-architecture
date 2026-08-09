"""Notification drain (integration, 2026-08-09): the delivery side of the
safeguarding outbox. Content-free by construction; fail-soft on errors."""

import json

import pytest

from src.lingua_viva import safeguarding as sg
from src.lingua_viva.notification_drain import drain_notifications


@pytest.fixture()
def state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    return tmp_path


def _configure_channel(channel="C-SAFEGUARDING"):
    path = sg.safeguarding_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"safeguarding_channel": channel}), encoding="utf-8")


def test_pending_config_entries_are_never_delivered(state_home):
    sg.enqueue_notification(kind="red_observation", ref_id="sg-1")
    sent = []
    result = drain_notifications(transport=lambda t, c, x: sent.append((c, x)))
    assert result["pending_config"] == 1
    assert result["delivered"] == 0
    assert sent == []


def test_queued_entries_deliver_content_free_summary(state_home, monkeypatch):
    _configure_channel()
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    entry = sg.enqueue_notification(kind="red_observation", ref_id="sg-2")
    assert entry["status"] == "queued"

    sent = []
    result = drain_notifications(transport=lambda t, c, x: sent.append((c, x)))
    assert result["delivered"] == 1
    (channel, text), = sent
    assert channel == "C-SAFEGUARDING"
    # Content discipline: generic summary only, no ids of students, no narrative.
    assert "restricted item requires review" in text

    # Entry is marked delivered; a second drain sends nothing.
    assert sg.pending_notifications() == []
    again = drain_notifications(transport=lambda t, c, x: sent.append((c, x)))
    assert again["delivered"] == 0 and len(sent) == 1


def test_transport_failure_keeps_entry_queued(state_home, monkeypatch):
    _configure_channel()
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    sg.enqueue_notification(kind="red_observation", ref_id="sg-3")

    def boom(token, channel, text):
        raise RuntimeError("network down")

    result = drain_notifications(transport=boom)
    assert result["failed"] == 1
    pending = sg.pending_notifications()
    assert len(pending) == 1
    assert pending[0]["last_error"] == "network down"


def test_missing_token_fails_honestly(state_home):
    _configure_channel()
    sg.enqueue_notification(kind="red_observation", ref_id="sg-4")
    result = drain_notifications(transport=lambda t, c, x: None)
    assert result["failed"] == 1
    assert sg.pending_notifications()[0]["last_error"].startswith("missing")
