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
    assert log == [("C123", ACK_SAVED)]


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
