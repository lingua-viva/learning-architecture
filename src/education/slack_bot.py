"""
Slack Bot Integration — Product A input surface

Receives a teacher's observation (typed, or a Slack audio-clip
transcription) from the teacher's own private Slack channel, verifies
the request actually came from Slack, extracts the transcript text and
a student tag, and routes it into ObservationCapturePipeline.capture().

RESEARCH (mandatory per build rules before writing Slack integration
code): ran
  mc research "Slack Events API: how to set up a bot that receives
  message events from specific channels, extracts text content from
  voice note transcriptions, and posts structured responses?"
Finding: Slack's own documentation covers standard event handling well,
but there is no authoritative end-to-end pattern for channel-scoped,
voice-note-aware, structured extraction — the recommended shape is an
Events API receiver (this module) that normalizes each event into a
structured record before any downstream logic runs, with attention to
idempotency (Slack retries event delivery; a handler must not double-
process the same event_id). See BUILD_JOURNAL.md Turn 6 for the full
citation-backed summary.

Cannot be live-tested without a real Slack workspace + bot token (per
BUILD_JOURNAL.md Turn 0 scope decision). Everything here is real,
runnable integration code: signature verification uses Slack's
documented HMAC-SHA256 request-signing scheme, the event-shape parsing
matches Slack's documented Events API + file-transcription payloads.
`post_message` is injectable — defaults to a local no-op recorder so
this module is fully unit-testable offline; a real deployment passes a
callable that does `requests.post("https://slack.com/api/chat.postMessage", ...)`.

PII boundary note: the teacher's spoken words already exist in Slack's
own systems the moment they're posted to their Slack channel — that's a
property of choosing Slack as the input surface, governed by the
school's own Slack workspace data policy, not something this module can
control. What this module DOES guarantee: it never echoes observation
content back out (replies are fixed acknowledgement templates only,
never a restatement of what the teacher said), and the observation text
itself is written straight to the local StudentLensStore — it is never
passed to any external model or third-party API. `slack.com` is on the
exit-gate allowlist (src/gates/exit.py) for posting acknowledgements
only; the ontology governance gate (blocks_external/requires_local on
LV-TCH-*/LV-STU-* nodes, see BUILD_JOURNAL.md Turn 1) still governs
whether observation content could ever be routed to a model — it can't,
because this module never calls one.

Idempotency: Slack retries event delivery (e.g. on slow 200 responses).
`SlackObservationBot` tracks seen event_ids in-memory for the process
lifetime and skips duplicates. A production deployment should persist
this (e.g. a small local seen-events table) — noted as a follow-up, not
built here, since the vertical slice runs as a single long-lived process
where in-memory tracking is sufficient for a first pilot week.
"""

from __future__ import annotations

import hmac
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.education.observation_capture import ObservationCapturePipeline
from src.education.student_lens import LensNotFoundError

STUDENT_TAG_RE = re.compile(r"^\s*\[student:([\w\-]+)\]\s*(.*)$", re.IGNORECASE | re.DOTALL)

# Slack rejects/should-reject requests whose timestamp is more than 5
# minutes old, to prevent replay attacks (Slack's documented signing
# scheme).
MAX_REQUEST_AGE_SECONDS = 60 * 5

ACK_SAVED = "✓ Observation saved."
ACK_NEEDS_STUDENT_TAG = (
    "⚠️ I couldn't tell which student this is about. Start your message with "
    "`[student:<id>]` and I'll save it — nothing was recorded yet."
)
ACK_ESCALATION = "🔔 This observation triggered a review flag — check your dashboard."
ACK_UNKNOWN_STUDENT = (
    "⚠️ I don't have a student record for that ID yet — nothing was recorded. "
    "Check the `[student:<id>]` tag, or ask an admin to add this student first."
)


class InvalidSlackSignatureError(PermissionError):
    """Raised when a request's Slack signature doesn't verify."""


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    raw_body: str,
    slack_signature: str,
    now: Optional[float] = None,
) -> bool:
    """
    Slack's documented request-signing scheme:
      base_string = "v0:{timestamp}:{raw_body}"
      expected    = "v0=" + HMAC-SHA256(signing_secret, base_string).hexdigest()
    Rejects stale timestamps (replay-attack protection) regardless of
    whether the HMAC itself would match.
    """
    now = now if now is not None else time.time()
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(now - ts) > MAX_REQUEST_AGE_SECONDS:
        return False

    base_string = f"v0:{timestamp}:{raw_body}"
    digest = hmac.new(
        signing_secret.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, slack_signature or "")


def parse_student_tag(text: str) -> tuple[Optional[str], str]:
    """Extract a leading `[student:<id>]` tag. Returns (student_id, remaining_text).
    student_id is None if no tag is present — callers must not guess which
    student an untagged observation belongs to."""
    match = STUDENT_TAG_RE.match(text or "")
    if not match:
        return None, (text or "").strip()
    return match.group(1), match.group(2).strip()


def extract_transcript(event: dict) -> Optional[str]:
    """
    Pull observation text from a Slack message event. Prefers plain
    `text` (typed messages, or a transcription already inserted by an
    upstream integration). Falls back to Slack's documented audio-clip
    transcription shape on shared files:
      event["files"][i]["transcription"] = {
          "status": "complete" | "processing" | "failed" | "none",
          "locale": "en-US",
          "preview": {"content": "...", "has_more": bool},
      }
    """
    text = (event.get("text") or "").strip()
    if text:
        return text
    for f in event.get("files", []) or []:
        transcription = f.get("transcription") or {}
        if transcription.get("status") == "complete":
            content = (transcription.get("preview") or {}).get("content", "").strip()
            if content:
                return content
    return None


@dataclass
class SlackObservationBot:
    """
    Events API receiver for Product A. Wire this behind an HTTP endpoint
    that Slack's Events API subscription posts to (e.g.
    POST /slack/events on the school's local server, tunneled or on a
    school-LAN-reachable address per the school's Slack app config).
    """

    capture_pipeline: ObservationCapturePipeline
    teacher_channel_map: dict[str, str]  # slack_channel_id -> teacher_id
    signing_secret: str
    post_message: Callable[[str, str], None] = field(
        default_factory=lambda: (lambda channel, text: None)
    )
    default_template_type: str = "literacy"
    _seen_event_ids: set = field(default_factory=set, repr=False)

    def handle_request(self, headers: dict, raw_body: str) -> dict:
        """Verify signature, parse JSON, dispatch. `headers` keys are
        expected lowercase (x-slack-request-timestamp, x-slack-signature) —
        normalize upstream if your HTTP framework preserves original case."""
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")
        if not verify_slack_signature(self.signing_secret, timestamp, raw_body, signature):
            raise InvalidSlackSignatureError("Slack request signature verification failed")

        import json

        payload = json.loads(raw_body)
        return self.handle_event_payload(payload)

    def handle_event_payload(self, payload: dict) -> dict:
        payload_type = payload.get("type")
        if payload_type == "url_verification":
            # One-time handshake Slack performs when the Events API
            # subscription URL is first configured.
            return {"challenge": payload.get("challenge", "")}

        if payload_type != "event_callback":
            return {"ok": True, "skipped": "unsupported_payload_type"}

        event_id = payload.get("event_id")
        if event_id and event_id in self._seen_event_ids:
            return {"ok": True, "skipped": "duplicate_event_id"}
        if event_id:
            self._seen_event_ids.add(event_id)

        event = payload.get("event", {})
        if event.get("type") != "message" or event.get("subtype") is not None:
            # Ignore edits/deletes/bot-echoes/join-messages etc. — only
            # plain new messages are observations.
            return {"ok": True, "skipped": "non_observation_event"}

        return self._handle_message_event(event)

    def _handle_message_event(self, event: dict) -> dict:
        channel = event.get("channel")
        teacher_id = self.teacher_channel_map.get(channel)
        if not teacher_id:
            # Not a registered teacher observation channel — ignore
            # silently rather than replying (avoids noise in unrelated
            # channels the bot happens to be invited to).
            return {"ok": True, "skipped": "unregistered_channel"}

        transcript = extract_transcript(event)
        if not transcript:
            return {"ok": True, "skipped": "no_transcript_available"}

        student_id, observation_text = parse_student_tag(transcript)
        if not student_id:
            self.post_message(channel, ACK_NEEDS_STUDENT_TAG)
            return {"ok": True, "skipped": "missing_student_tag"}

        try:
            result = self.capture_pipeline.capture(
                student_id=student_id,
                teacher_id=teacher_id,
                raw_transcript=observation_text,
                template_type=self.default_template_type,
            )
        except LensNotFoundError:
            # Unknown student ID (typo, or roster not yet provisioned).
            # Same "never guess" policy as a missing tag: tell the teacher
            # nothing was saved rather than silently dropping the message
            # or letting the exception propagate (which would cause Slack
            # to retry delivery indefinitely with no useful ack).
            self.post_message(channel, ACK_UNKNOWN_STUDENT)
            return {"ok": True, "skipped": "unknown_student_id"}

        if result["escalations"]:
            self.post_message(channel, ACK_ESCALATION)
        else:
            self.post_message(channel, ACK_SAVED)

        return {"ok": True, "capture_result": result}
