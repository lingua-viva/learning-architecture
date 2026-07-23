"""
Slack Bot Integration Tests — Product A input surface.
"""

import hmac
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.observation_capture import ObservationCapturePipeline
from src.education.student_lens import StudentLensStore
from src.education.slack_bot import (
    SlackObservationBot,
    ACK_SAVED,
    ACK_NEEDS_STUDENT_TAG,
    ACK_ESCALATION,
    ACK_UNKNOWN_STUDENT,
    ACK_NEEDS_OBSERVATION_TEXT,
    ACK_OBSERVATION_TOO_LONG,
    InvalidSlackSignatureError,
    verify_slack_signature,
    parse_student_tag,
    extract_transcript,
)

SIGNING_SECRET = "test-signing-secret"


def make_signature(timestamp: str, raw_body: str) -> str:
    base_string = f"v0:{timestamp}:{raw_body}"
    digest = hmac.new(
        SIGNING_SECRET.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"v0={digest}"


def make_bot(tmp_path, post_log=None):
    store = StudentLensStore(db_path=tmp_path / "test.db")
    pipeline = ObservationCapturePipeline(store=store)
    log = post_log if post_log is not None else []

    def post_message(channel, text):
        log.append((channel, text))

    bot = SlackObservationBot(
        capture_pipeline=pipeline,
        teacher_channel_map={"C123": "teacher_1"},
        signing_secret=SIGNING_SECRET,
        post_message=post_message,
    )
    return bot, store, log


# --- signature verification ---

def test_verify_slack_signature_valid():
    ts = str(time.time())
    body = '{"type":"event_callback"}'
    sig = make_signature(ts, body)
    assert verify_slack_signature(SIGNING_SECRET, ts, body, sig) is True


def test_verify_slack_signature_invalid_hmac():
    ts = str(time.time())
    body = '{"type":"event_callback"}'
    assert verify_slack_signature(SIGNING_SECRET, ts, body, "v0=deadbeef") is False


def test_verify_slack_signature_stale_timestamp_rejected():
    ts = str(time.time() - 60 * 10)  # 10 minutes old
    body = '{"type":"event_callback"}'
    sig = make_signature(ts, body)
    assert verify_slack_signature(SIGNING_SECRET, ts, body, sig) is False


def test_verify_slack_signature_rejects_empty_secret_and_nonfinite_timestamp():
    assert verify_slack_signature("", "1", "{}", "v0=anything", now=1) is False
    assert verify_slack_signature(SIGNING_SECRET, "nan", "{}", "v0=anything", now=1) is False
    assert verify_slack_signature(SIGNING_SECRET, "1", "{}", "v0=anything", now=float("inf")) is False


# --- parsing helpers ---

def test_parse_student_tag_present():
    student_id, text = parse_student_tag("[student:s1] Reads well today")
    assert student_id == "s1"
    assert text == "Reads well today"


def test_parse_student_tag_absent():
    student_id, text = parse_student_tag("no tag here")
    assert student_id is None
    assert text == "no tag here"


def test_extract_transcript_prefers_text():
    event = {"text": "hello", "files": [{"transcription": {"status": "complete", "preview": {"content": "ignored"}}}]}
    assert extract_transcript(event) == "hello"


def test_extract_transcript_falls_back_to_file_transcription():
    event = {"text": "", "files": [{"transcription": {"status": "complete", "preview": {"content": "voice note text"}}}]}
    assert extract_transcript(event) == "voice note text"


def test_extract_transcript_none_when_incomplete():
    event = {"text": "", "files": [{"transcription": {"status": "processing", "preview": {"content": "partial"}}}]}
    assert extract_transcript(event) is None


# --- handle_event_payload / handle_request ---

def test_handle_request_raises_on_bad_signature(tmp_path):
    bot, _, _ = make_bot(tmp_path)
    with pytest.raises(InvalidSlackSignatureError):
        bot.handle_request({"x-slack-request-timestamp": str(time.time()), "x-slack-signature": "v0=bad"}, "{}")


def test_url_verification_handshake(tmp_path):
    bot, _, _ = make_bot(tmp_path)
    result = bot.handle_event_payload({"type": "url_verification", "challenge": "abc123"})
    assert result == {"challenge": "abc123"}


def test_event_id_deduplication(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")
    payload = {
        "type": "event_callback",
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C123",
            "text": "[student:s1] I noticed she read fluently today",
        },
    }
    first = bot.handle_event_payload(payload)
    second = bot.handle_event_payload(payload)
    assert first.get("skipped") != "duplicate_event_id"
    assert second == {"ok": True, "skipped": "duplicate_event_id"}


def test_event_callback_without_event_id_is_not_processed(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event": {"type": "message", "channel": "C123", "text": "[student:s1] note"},
    })
    assert result == {"ok": True, "skipped": "missing_event_id"}
    assert log == []


def test_seen_event_cache_is_bounded(tmp_path, monkeypatch):
    import src.education.slack_bot as slack_bot_module

    monkeypatch.setattr(slack_bot_module, "MAX_SEEN_EVENT_IDS", 3)
    bot, _, _ = make_bot(tmp_path)
    for i in range(5):
        bot.handle_event_payload({
            "type": "event_callback",
            "event_id": f"EvBounded{i}",
            "event": {"type": "not-a-message"},
        })
    assert len(bot._seen_event_ids) == 3
    assert list(bot._seen_event_order) == ["EvBounded2", "EvBounded3", "EvBounded4"]


def test_unregistered_channel_silently_ignored(tmp_path):
    bot, _, log = make_bot(tmp_path)
    payload = {
        "type": "event_callback",
        "event_id": "Ev1",
        "event": {"type": "message", "channel": "C999", "text": "[student:s1] hello"},
    }
    result = bot.handle_event_payload(payload)
    assert result == {"ok": True, "skipped": "unregistered_channel"}
    assert log == []


def test_missing_student_tag_posts_ack_and_does_not_capture(tmp_path):
    bot, store, log = make_bot(tmp_path)
    payload = {
        "type": "event_callback",
        "event_id": "Ev2",
        "event": {"type": "message", "channel": "C123", "text": "I noticed she read fluently today"},
    }
    result = bot.handle_event_payload(payload)
    assert result["skipped"] == "missing_student_tag"
    assert log == [("C123", ACK_NEEDS_STUDENT_TAG)]


def test_student_tag_without_observation_is_rejected(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "EvEmpty",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1]"},
    })
    assert result["skipped"] == "missing_observation_text"
    assert log == [("C123", ACK_NEEDS_OBSERVATION_TEXT)]


def test_oversized_observation_is_rejected_before_capture(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "EvHuge",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] " + ("x" * 20_001)},
    })
    assert result["skipped"] == "observation_too_long"
    assert log == [("C123", ACK_OBSERVATION_TOO_LONG)]


def test_successful_capture_posts_ack_saved(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")
    payload = {
        "type": "event_callback",
        "event_id": "Ev3",
        "event": {
            "type": "message",
            "channel": "C123",
            "text": "[student:s1] I noticed she read the passage fluently today",
        },
    }
    result = bot.handle_event_payload(payload)
    assert result["ok"] is True
    assert "capture_result" in result
    assert result["acknowledgement_delivered"] is True
    assert log == [("C123", ACK_SAVED)]


def test_ack_transport_failure_does_not_replay_or_lose_local_capture(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "test.db")
    store.create_lens(student_id="s1", display_name="Test Student")

    def fail_post(_channel, _text):
        raise RuntimeError("simulated Slack outage")

    bot = SlackObservationBot(
        capture_pipeline=ObservationCapturePipeline(store=store),
        teacher_channel_map={"C123": "teacher_1"},
        signing_secret=SIGNING_SECRET,
        post_message=fail_post,
    )
    payload = {
        "type": "event_callback",
        "event_id": "EvAckFailure",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U1",
            "text": "[student:s1] Local write survives transport failure",
        },
    }
    result = bot.handle_event_payload(payload)
    assert result["ok"] is True
    assert result["acknowledgement_delivered"] is False
    assert len(store.export_lens("s1")["observations"]) == 1
    assert bot.handle_event_payload(payload)["skipped"] == "duplicate_event_id"


def test_unknown_student_id_posts_ack_and_does_not_crash(tmp_path):
    bot, store, log = make_bot(tmp_path)
    # Note: no lens created for "s404" — simulates typo'd tag or
    # student not yet provisioned in the roster.
    payload = {
        "type": "event_callback",
        "event_id": "Ev5",
        "event": {
            "type": "message",
            "channel": "C123",
            "text": "[student:s404] I noticed she read fluently today",
        },
    }
    result = bot.handle_event_payload(payload)
    assert result == {"ok": True, "skipped": "unknown_student_id"}
    assert log == [("C123", ACK_UNKNOWN_STUDENT)]


def test_non_message_subtype_events_ignored(tmp_path):
    bot, _, log = make_bot(tmp_path)
    payload = {
        "type": "event_callback",
        "event_id": "Ev4",
        "event": {"type": "message", "subtype": "message_changed", "channel": "C123", "text": "edited"},
    }
    result = bot.handle_event_payload(payload)
    assert result == {"ok": True, "skipped": "non_observation_event"}
    assert log == []


# --- continuation window (UX pass) ---

def test_untagged_followup_within_window_continues_same_student(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")

    tagged = {
        "type": "event_callback",
        "event_id": "Ev10",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] Reads well today"},
    }
    followup = {
        "type": "event_callback",
        "event_id": "Ev11",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "Also finished her worksheet"},
    }
    bot.handle_event_payload(tagged)
    result = bot.handle_event_payload(followup)

    assert result["ok"] is True
    assert "capture_result" in result
    assert log == [("C123", ACK_SAVED), ("C123", ACK_SAVED)]


def test_untagged_message_outside_window_still_requires_tag(tmp_path):
    clock = {"t": 1000.0}
    bot, store, log = make_bot(tmp_path)
    bot.now = lambda: clock["t"]
    store.create_lens(student_id="s1", display_name="Test Student")

    tagged = {
        "type": "event_callback",
        "event_id": "Ev12",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] Reads well today"},
    }
    bot.handle_event_payload(tagged)

    clock["t"] += bot.continuation_window_seconds + 1  # past the window
    followup = {
        "type": "event_callback",
        "event_id": "Ev13",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "Also finished her worksheet"},
    }
    result = bot.handle_event_payload(followup)

    assert result["skipped"] == "missing_student_tag"
    assert log[-1] == ("C123", ACK_NEEDS_STUDENT_TAG)


def test_clock_rollback_does_not_reuse_student_context(tmp_path):
    clock = {"t": 1000.0}
    bot, store, log = make_bot(tmp_path)
    bot.now = lambda: clock["t"]
    store.create_lens(student_id="s1", display_name="Test Student")
    bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "EvClock1",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] First"},
    })
    clock["t"] = 900.0
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "EvClock2",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "Second"},
    })
    assert result["skipped"] == "missing_student_tag"


def test_new_tag_switches_student_immediately(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    store.create_lens(student_id="s2", display_name="Student Two")

    events = [
        {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] First note"},
        {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s2] Switching to a different student"},
        {"type": "message", "channel": "C123", "user": "U1", "text": "Untagged follow-up should belong to s2"},
    ]
    results = []
    for i, event in enumerate(events):
        results.append(bot.handle_event_payload({"type": "event_callback", "event_id": f"EvSwitch{i}", "event": event}))

    assert all(r["ok"] for r in results)
    assert log == [("C123", ACK_SAVED)] * 3


def test_untagged_message_from_different_user_still_requires_tag(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")

    bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev20",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s1] Reads well today"},
    })
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev21",
        "event": {"type": "message", "channel": "C123", "user": "U2", "text": "Untagged from a different sender"},
    })

    assert result["skipped"] == "missing_student_tag"
    assert log[-1] == ("C123", ACK_NEEDS_STUDENT_TAG)


# --- hardening sweep 2026-07-14: malformed-payload boundary crashes ---

def test_extract_transcript_survives_non_string_text():
    for bad in [{"x": 1}, 42, ["a", "b"], True]:
        assert extract_transcript({"text": bad}) is None


def test_extract_transcript_survives_malformed_file_shapes():
    assert extract_transcript({"text": "", "files": [{"transcription": {"status": "complete", "preview": {"content": 42}}}]}) is None
    assert extract_transcript({"text": "", "files": [{"transcription": {"status": "complete", "preview": {"content": None}}}]}) is None
    assert extract_transcript({"text": "", "files": {"not": "a list"}}) is None
    assert extract_transcript({"text": "", "files": "oops"}) is None
    assert extract_transcript({"text": "", "files": ["oops"]}) is None
    assert extract_transcript({"text": "", "files": [{"transcription": "oops"}]}) is None
    assert extract_transcript({"text": "", "files": [{"transcription": {"status": "complete", "preview": "oops"}}]}) is None


def test_handle_event_payload_survives_non_dict_event(tmp_path):
    bot, _, log = make_bot(tmp_path)
    for bad_event in [None, [], "oops", 42]:
        result = bot.handle_event_payload({"type": "event_callback", "event_id": f"bad-{bad_event!r}", "event": bad_event})
        assert result == {"ok": True, "skipped": "non_observation_event"}
    assert log == []


def test_handle_message_event_survives_unhashable_channel(tmp_path):
    bot, _, log = make_bot(tmp_path)
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev30",
        "event": {"type": "message", "channel": {"nested": "object"}, "text": "[student:s1] hi"},
    })
    assert result == {"ok": True, "skipped": "unregistered_channel"}
    assert log == []


def test_handle_request_survives_invalid_json_body(tmp_path):
    bot, _, log = make_bot(tmp_path)
    ts = str(time.time())
    body = "{not valid json"
    sig = make_signature(ts, body)
    result = bot.handle_request({"x-slack-request-timestamp": ts, "x-slack-signature": sig}, body)
    assert result == {"ok": False, "skipped": "invalid_json_body"}
    assert log == []


def test_handle_request_survives_non_dict_json_body(tmp_path):
    bot, _, log = make_bot(tmp_path)
    ts = str(time.time())
    body = "[1, 2, 3]"
    sig = make_signature(ts, body)
    result = bot.handle_request({"x-slack-request-timestamp": ts, "x-slack-signature": sig}, body)
    assert result == {"ok": False, "skipped": "invalid_payload_shape"}
    assert log == []


def test_missing_user_key_does_not_cross_contaminate_between_senders(tmp_path):
    bot, store, log = make_bot(tmp_path)
    store.create_lens(student_id="s1", display_name="Test Student")

    bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev40",
        "event": {"type": "message", "channel": "C123", "text": "[student:s1] tagged note, no user key"},
    })
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev41",
        "event": {"type": "message", "channel": "C123", "text": "untagged, also no user key"},
    })

    assert result["skipped"] == "missing_student_tag"
    assert log[-1] == ("C123", ACK_NEEDS_STUDENT_TAG)


def test_unknown_student_tag_does_not_poison_continuation_window(tmp_path):
    bot, store, log = make_bot(tmp_path)
    # Note: "s404" is never created — a typo'd or not-yet-provisioned tag.
    bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev50",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "[student:s404] typo'd tag"},
    })
    result = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev51",
        "event": {"type": "message", "channel": "C123", "user": "U1", "text": "untagged follow-up after the bad tag"},
    })

    # The follow-up must be asked to retag, not silently retried against
    # the same phantom student_id from the failed capture.
    assert result["skipped"] == "missing_student_tag"
    assert log == [("C123", ACK_UNKNOWN_STUDENT), ("C123", ACK_NEEDS_STUDENT_TAG)]
