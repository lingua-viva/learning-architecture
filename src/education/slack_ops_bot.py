"""
Slack Ops Bot — conversation layer for the Daily Operations Assistant.

Spec: dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md §3.5 (Lane D).

Design decisions (operator-locked 2026-07-27):
  - This bot is a *separate module* from slack_bot.py (the dormant
    observation path). It never imports ObservationCapturePipeline or
    StudentLensStore — Slack messages NEVER touch student lenses (§0).
  - Restrained voice: in the ops channel the bot only speaks when a
    workflow needs it (coverage cards, one-question clarifications, claim
    confirmations). Announcements and schedule changes are captured
    silently — the daily file is the acknowledgement. In DMs it always
    confirms briefly, because a teacher talking to the bot deserves a
    receipt.
  - One question, few buttons (§3.5): every clarification is a single
    question with at most four buttons; unresolved items land in the
    daily file's To Review section, never dropped.
  - Reply discipline inherited from slack_bot.py: short fixed templates,
    never echo full message text back into a shared channel, no student
    detail in channel messages.
  - Coverage cards: the Claim button's value carries the record id; on a
    click, the interactive payload itself supplies channel + message_ts,
    so claiming survives a bot restart with no in-memory card registry.
    The card ts is *also* stored in the record's extra (card_ts) so the
    Cancel flow can rewrite the card.
  - Time: `today` (local date) and `now` are injectable for hermetic
    tests. Slack event handling resolves relative dates against the
    teacher's local day, matching ops_records' date_for convention.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Awaitable, Callable, Optional

from src.education import ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_classifier import (
    CONFIDENCE_LOW,
    classify_ops_message,
)
from src.education.ops_packs import CompiledRuleSet
from src.education.ops_records import OpsRecord, OpsRecordStore, utc_now_iso

logger = logging.getLogger(__name__)

PENDING_NOTES_WINDOW_SECONDS = 600  # same 10-minute rhythm as slack_bot.py

# --- fixed reply templates (never echo observation text into channels) ------

MSG_DM_SAVED = "Saved to your daily file."
MSG_ABSENCE_LOGGED = (
    "I'll log your absence for {date}.{coverage} "
    "Do you want to attach lesson notes?"
)
MSG_ABSENCE_COVERAGE_SENT = " I've sent a coverage request to the ops channel."
MSG_COVERAGE_CARD = "Coverage needed: {who}{window}{date}. Tap to claim."
MSG_COVERAGE_FILLED = "Coverage filled: {claimer}{window}."
MSG_COVERAGE_ALREADY = "This one is already covered."
MSG_COVERAGE_WITHDRAWN = "Coverage request withdrawn."
MSG_COVERAGE_CLAIM_TEXT_AMBIGUOUS = (
    "Please use the Claim coverage button on the request so I update the right one."
)
MSG_NOTES_PROMPT = "Send your lesson notes here as your next message and I'll attach them."
MSG_NOTES_ATTACHED = "Lesson notes attached to your absence."
MSG_EMERGENCY_PLAN = "Noted — the emergency plan will be used."
MSG_CANCELLED = "Cancelled. Your absence entry has been removed from the daily file."
MSG_REVIEW_LOGGED = "Logged."
MSG_REVIEW_IGNORED = "Ignored — it won't appear in the daily file."
MSG_BRIEFING = "Good morning, {name}. You have {count} update{s} today{items}."
MSG_BRIEFING_NONE = "Good morning, {name}. No updates for today yet."
MSG_EOD = (
    "Your daily file is ready. {count} item{s} captured today."
    "{review}"
)
MSG_EOD_REVIEW = " {n} still need{review_s} review."
MSG_OPEN_FILE = "Your daily file: {path}"
MSG_REMIND_LATER = "Okay — I'll remind you in an hour."
MSG_UNKNOWN_USER = (
    "I don't have you on the teacher roster yet, so I can't log this. "
    "Please ask your admin to add you to the LV teacher map."
)
# First-contact standard (operator ruling 2026-07-27): the teacher should
# never experience "bot setup" — a greeting or help request gets a plain
# statement of the jobs the bot knows, with one worked example.
MSG_HELP = (
    "Hi {name} — I can help with absences, coverage, schedule changes, "
    "and daily updates.\n"
    "Just tell me things like: \"I'm out tomorrow. Need coverage for 2nd "
    "period.\" Everything lands in your daily file on the Desktop "
    "(Today - {name}.md)."
)
MSG_VOICE_CLIP = (
    "I can't listen to voice clips yet — type it as a message and I'll "
    "log it."
)
MSG_ABSENCE_MODAL_RECEIPT = (
    "Got it — your absence for {date} has been recorded.{coverage}"
)
MSG_ABSENCE_MODAL_COVERAGE_SENT = " A coverage request has been posted to the ops channel."
MSG_COVERAGE_CLAIMED_PENDING = (
    "Coverage claimed: {claimer}{window}. Awaiting coordinator confirmation."
)
MSG_COVERAGE_COORDINATOR_CONFIRM = (
    "Please confirm coverage for {who}{window}{date}. "
    "Claimed by {claimer}."
)
MSG_COVERAGE_CONFIRMED = "Coverage confirmed: {claimer}{window}."
MSG_PARTIAL_CLAIM_NOTED = (
    "Partial coverage noted: {claimer} can cover {detail}. "
    "Full coverage is not yet confirmed — this request needs review."
)

SIR_ABSENCE_MODAL_CALLBACK_ID = "sir_absence_modal"
SIR_PARTIAL_CLAIM_CALLBACK_ID = "sir_partial_claim_modal"
SIR_OPS_REQUEST_MODAL_CALLBACK_ID = "sir_ops_request_modal"
SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID = "sir_schedule_change_modal"

MSG_SCHEDULE_CARD = (
    "Schedule change: {item} -> {new_time}, {campus}."
)
MSG_SCHEDULE_ACK_STATUS = (
    " Acknowledged: {seen}/{total}. Conflicts: {conflicts}. Needs clarification: {clarify}."
)
MSG_SCHEDULE_ACK_DM = (
    "Schedule change on {date}: {item} -> {new_time} ({campus}). "
    "Please acknowledge below."
)
MSG_SCHEDULE_SEEN = "Noted — thank you."
MSG_SCHEDULE_CONFLICT = "Conflict recorded. The coordinator will follow up."
MSG_SCHEDULE_CLARIFY = "Clarification needed — the coordinator will follow up."
MSG_SCHEDULE_NOT_TARGETED = "This change doesn't target you — no action needed."
MSG_SCHEDULE_INVALID_ACK = "I couldn't record that acknowledgement."
MSG_SCHEDULE_RECEIPT = "Schedule change posted. {ack_note}"
MSG_SCHEDULE_ACK_REQUIRED_NOTE = "Acknowledgement requests sent to {count} staff."
SCHEDULE_ACK_STATUSES = frozenset({"seen", "conflict", "need_clarification"})

MSG_OPS_REQUEST_CARD = (
    "Ops request [{request_type}]: {campus}, {location} — {severity}. {description}"
)
MSG_OPS_REQUEST_RECEIPT = (
    "Got it — your {request_type} request has been logged.{teaching_note}"
)
MSG_OPS_REQUEST_TEACHING_BLOCKED = " This is marked as blocking teaching."
MSG_OPS_REQUEST_CLAIMED = "Claimed by {owner}. Working on it."
MSG_OPS_REQUEST_RESOLVED = "Resolved by {owner}. {note}"
MSG_OPS_REQUEST_REOPENED = "Reopened — still blocked. A new follow-up has been created."
MSG_OPS_REQUEST_NOT_REQUESTER = "Only the original requester can reopen this request."

# Greetings / help asks in a DM. Deliberately narrow: only short messages
# that are *entirely* a greeting or a help request, so real operational
# text ("hi, I'm out tomorrow") still reaches the classifier.
_HELP_RE = re.compile(
    r"^\s*(?:hi|hello|hey|help|start|what can you do|how do you work)"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def _button(text: str, action_id: str, value: str = "") -> dict:
    button: dict = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": action_id,
    }
    if value:
        button["value"] = value
    return button


def _blocks(text: str, buttons: list) -> list:
    blocks: list = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    if buttons:
        blocks.append({"type": "actions", "elements": buttons})
    return blocks


class SlackOpsBot:
    """Dispatches Socket Mode envelopes into ops records + daily files."""

    def __init__(
        self,
        *,
        store: OpsRecordStore,
        daily: DailyFileEngine,
        client,  # SlackSocketClient-compatible: post_message/update_message/open_dm
        ops_channel: str,
        teacher_map: dict,
        today: Optional[Callable[[], date]] = None,
        now: Callable[[], float] = None,
        schedule_later: Optional[Callable[[float, Callable[[], Awaitable[None]]], None]] = None,
        rule_set: Optional[CompiledRuleSet] = None,
    ):
        self.store = store
        self.daily = daily
        self.client = client
        self.ops_channel = ops_channel
        self.teacher_map = dict(teacher_map or {})
        self._today = today or date.today
        self._now = now or (lambda: datetime.now().timestamp())
        self._schedule_later = schedule_later or self._default_schedule_later
        # Explicit rule_set pins the compile (tests); None reads through
        # the process-wide current compile on every message, so a
        # bot-spec swap (spec v2 §3.2) takes effect without a restart.
        self._rule_set = rule_set
        # slack_user_id -> {"kind": "lesson_notes", "record_id": ..., "expires": ...}
        self._pending: dict = {}

    def _rules(self) -> CompiledRuleSet:
        return self._rule_set if self._rule_set is not None else ops_packs.current_rule_set()

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    def _teacher_for(self, slack_user_id: str) -> tuple[str, str]:
        entry = self.teacher_map.get(slack_user_id) or {}
        return (
            entry.get("teacher_id", slack_user_id or "unknown"),
            entry.get("display_name", slack_user_id or "unknown"),
        )

    def _slack_user_for_teacher(self, teacher_id: str) -> Optional[str]:
        for slack_id, entry in self.teacher_map.items():
            if entry.get("teacher_id") == teacher_id:
                return slack_id
        return None

    def _teacher_for_name(self, name: Optional[str]) -> Optional[tuple[str, str]]:
        if not name:
            return None
        lowered = name.lower()
        for entry in self.teacher_map.values():
            display = entry.get("display_name", "")
            if lowered in (part.lower() for part in display.split()) or lowered == display.lower():
                return entry.get("teacher_id", ""), display
        return None

    # ------------------------------------------------------------------
    # Envelope entry point (wired to SlackSocketClient.on_envelope)
    # ------------------------------------------------------------------

    async def on_envelope(self, envelope_type: str, payload: dict) -> None:
        try:
            if envelope_type == "events_api":
                event = (payload or {}).get("event") or {}
                if event.get("type") == "message":
                    await self._handle_message(event)
            elif envelope_type == "interactive":
                ptype = (payload or {}).get("type", "")
                if ptype == "block_actions":
                    await self._handle_block_actions(payload)
                elif ptype == "view_submission":
                    await self._handle_view_submission(payload)
            elif envelope_type == "slash_commands":
                await self._handle_slash_command(payload)
        except Exception:  # never kill the transport loop
            logger.exception("[slack-ops] envelope handler failed")

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def _handle_message(self, event: dict) -> None:
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text")
        channel = event.get("channel", "")
        user = event.get("user", "")
        ts = event.get("ts", "")
        if not isinstance(text, str) or not channel or not user:
            return

        # Strictly 1:1 DMs ("im"/D-channels): a group DM (mpim) has other
        # members, so treating it as a private DM would leak receipts and
        # absence detail to whoever else is in it (hardening pass 14,
        # 2026-07-27).
        is_dm = event.get("channel_type") == "im" or channel.startswith("D")
        is_ops = channel == self.ops_channel
        if not (is_dm or is_ops):
            return  # privacy boundary: only the ops channel and DMs (§3.6)

        today = self._today()
        self.daily.archive_if_new_day(today.isoformat())

        if is_dm and await self._consume_pending_notes(user, channel, text):
            return

        if not text.strip() and event.get("files"):
            # Voice clip / file-only message: nothing readable to capture.
            # In a DM, be honest about it; in the ops channel stay silent
            # rather than filing a useless "(no detail)" review item.
            if is_dm:
                await self.client.post_message(channel, MSG_VOICE_CLIP)
            return

        if is_dm:
            # First-contact / discoverability (operator ruling 2026-07-27):
            # a greeting or "help" gets the capability statement — never
            # the classifier's "should I log this as an announcement?"
            # non-answer.
            if _HELP_RE.match(text):
                if user in self.teacher_map:
                    _tid, name = self._teacher_for(user)
                    await self.client.post_message(
                        channel, MSG_HELP.format(name=name)
                    )
                else:
                    await self.client.post_message(channel, MSG_UNKNOWN_USER)
                return

        rules = self._rules()
        msg = classify_ops_message(
            text, today=today, is_dm=is_dm, is_ops_channel=is_ops, rule_set=rules
        )
        teacher_id, display_name = self._teacher_for(user)
        source = dict(
            actor_slack_id=user,
            actor_name=display_name,
            source_channel=channel,
            source_ts=ts,
            thread_ts=event.get("thread_ts", "") or "",
        )

        if user not in self.teacher_map:
            # Hardening pass 8 (2026-07-27): the teacher map is the roster.
            # An unmapped DM sender gets an honest answer instead of a
            # fabricated identity (which used to create a Desktop file
            # named by the raw Slack id). An unmapped ops-channel sender
            # is capture-only: broadcasts behave normally, per-teacher
            # categories are stored unattributed (visible in the web
            # records audit, never fabricated into anyone's daily file).
            if is_dm:
                await self.client.post_message(channel, MSG_UNKNOWN_USER)
                return
            await self._flow_capture(msg, "", channel, is_dm, is_ops, source)
            return

        # Dispatch keys on the category's CAPABILITY id (spec v2 §3(b)):
        # a pack enables a code-backed flow; categories without one are
        # capture-only. Flows stay code — this is the entire dispatch.
        capability = rules.capability_for(msg.category)
        if capability == "absence_flow":
            await self._flow_absence(msg, teacher_id, display_name, channel, source)
        elif capability == "coverage_machine":
            await self._flow_coverage_request(
                msg, teacher_id, display_name, channel, is_dm, source
            )
        elif capability == "text_claim":
            await self._flow_coverage_claim_text(display_name, channel, source)
        else:
            await self._flow_capture(msg, teacher_id, channel, is_dm, is_ops, source)

    def _refresh_daily(self, record) -> None:
        # Always render for the bot's (injectable) today — the Desktop file
        # is today's picture even when the record is for a future date
        # (hardening pass 5, 2026-07-27).
        self.daily.refresh_for_record(record, self._today().isoformat())

    async def _flow_absence(self, msg, teacher_id, display_name, channel, source):
        review_required = "absence" in self._rules().review_required
        record = self.store.add_record(
            category="absence",
            teacher_id=teacher_id,
            date_for=msg.date_for or self._today().isoformat(),
            time_window=msg.time_window or "",
            periods=msg.periods,
            text_raw=msg.text_clean,
            text_clean=msg.text_clean,
            needs_review=review_required,
            review_reason="requires review before filing" if review_required else "",
            **source,
        )
        self._refresh_daily(record)

        coverage_id = ""
        coverage_note = ""
        if msg.wants_coverage:
            cov = await self._post_coverage_card(
                teacher_display=display_name,
                teacher_id=teacher_id,
                date_for=record.date_for,
                time_window=record.time_window,
                periods=record.periods,
                text_clean=msg.text_clean,
                source=source,
            )
            coverage_id = cov.id
            coverage_note = MSG_ABSENCE_COVERAGE_SENT

        value = json.dumps({"absence": record.id, "coverage": coverage_id})
        await self.client.post_message(
            channel,
            MSG_ABSENCE_LOGGED.format(date=record.date_for, coverage=coverage_note),
            blocks=_blocks(
                MSG_ABSENCE_LOGGED.format(date=record.date_for, coverage=coverage_note),
                [
                    _button("Add lesson notes", "ops_absence_notes", value),
                    _button("Use emergency plan", "ops_absence_emergency", value),
                    _button("Cancel", "ops_absence_cancel", value),
                ],
            ),
        )

    async def _post_coverage_card(
        self, *, teacher_display, teacher_id, date_for, time_window, periods,
        text_clean, source,
    ) -> OpsRecord:
        # Review-required gate (spec v2 §6). A flagged coverage request
        # stays claimable — the store keeps coverage open+flagged (v1
        # spec §3.3), so review never blocks the claim machine.
        review_required = "coverage_request" in self._rules().review_required
        cov = self.store.add_record(
            category="coverage_request",
            teacher_id=teacher_id,
            date_for=date_for or self._today().isoformat(),
            time_window=time_window or "",
            periods=periods or [],
            text_raw=text_clean,
            text_clean=text_clean,
            needs_review=review_required,
            review_reason="requires review before filing" if review_required else "",
            **source,
        )
        window = self._window_label(cov)
        card_text = MSG_COVERAGE_CARD.format(
            who=teacher_display,
            window=f", {window}" if window else "",
            date=f" on {cov.date_for}" if cov.date_for else "",
        )
        response = await self.client.post_message(
            self.ops_channel,
            card_text,
            blocks=_blocks(
                card_text, [
                    _button("Claim all", "ops_coverage_claim", cov.id),
                    _button("Claim part", "ops_coverage_claim_part", cov.id),
                ]
            ),
        )
        card_ts = (response or {}).get("ts", "")
        if card_ts:
            cov = self.store.update_extra(cov.id, card_ts=card_ts)
        self._refresh_daily(cov)
        return cov

    async def _flow_coverage_request(
        self, msg, teacher_id, display_name, channel, is_dm, source
    ):
        # "Need substitute for Claudia" — the named teacher is the subject.
        named = self._teacher_for_name(msg.subject)
        target_id, target_display = named if named else (teacher_id, display_name)

        if msg.confidence == CONFIDENCE_LOW:
            cov = self.store.add_record(
                category="coverage_request",
                teacher_id=target_id,
                date_for=msg.date_for or self._today().isoformat(),
                text_raw=msg.text_clean,
                text_clean=msg.text_clean,
                needs_review=True,
                review_reason=msg.clarification or "missing coverage details",
                **source,
            )
            self._refresh_daily(cov)
            await self.client.post_message(
                channel, msg.clarification, thread_ts=source["source_ts"]
            )
            return

        await self._post_coverage_card(
            teacher_display=target_display,
            teacher_id=target_id,
            date_for=msg.date_for,
            time_window=msg.time_window,
            periods=msg.periods,
            text_clean=msg.text_clean,
            source=source,
        )
        if is_dm:
            await self.client.post_message(channel, MSG_DM_SAVED)

    async def _flow_coverage_claim_text(self, display_name, channel, source):
        today_iso = self._today().isoformat()
        open_requests = [
            r
            for r in self.store.records_for_day(today_iso)
            if r.category == "coverage_request" and r.status == "open"
        ]
        if len(open_requests) != 1:
            await self.client.post_message(
                channel, MSG_COVERAGE_CLAIM_TEXT_AMBIGUOUS,
                thread_ts=source["source_ts"],
            )
            return
        await self._claim_coverage(
            open_requests[0].id,
            claimer=display_name,
            card_channel=None,
            card_ts=None,
        )

    async def _flow_capture(self, msg, teacher_id, channel, is_dm, is_ops, source):
        rules = self._rules()
        broadcast = msg.category in rules.broadcast_categories
        # Review-required settings gate (spec v2 §6): admin-listed
        # categories land in To Review even at high confidence.
        review_required = msg.category in rules.review_required
        record = self.store.add_record(
            category=msg.category,
            teacher_id="" if broadcast else teacher_id,
            date_for=msg.date_for or self._today().isoformat(),
            time_window=msg.time_window or "",
            periods=msg.periods,
            text_raw=msg.text_clean,
            text_clean=msg.text_clean,
            needs_review=msg.confidence == CONFIDENCE_LOW or review_required,
            review_reason=msg.clarification
            or ("requires review before filing" if review_required else ""),
            extra={"subject": msg.subject} if msg.subject else None,
            **source,
        )
        self._refresh_daily(record)

        if msg.confidence == CONFIDENCE_LOW and msg.clarification:
            buttons = []
            if msg.category == "other":
                buttons = [
                    _button("Log it", "ops_review_log", record.id),
                    _button("Ignore", "ops_review_ignore", record.id),
                ]
            await self.client.post_message(
                channel,
                msg.clarification,
                blocks=_blocks(msg.clarification, buttons) if buttons else None,
                thread_ts=None if is_dm else source["source_ts"],
            )
        elif is_dm:
            await self.client.post_message(channel, MSG_DM_SAVED)
        # In the ops channel, high-confidence captures are silent (§3.5) —
        # the daily file is the acknowledgement.

    async def _consume_pending_notes(self, user, channel, text) -> bool:
        pending = self._pending.get(user)
        if not pending or pending.get("kind") != "lesson_notes":
            return False
        if self._now() > pending.get("expires", 0):
            self._pending.pop(user, None)
            return False
        self._pending.pop(user, None)
        record = self.store.update_extra(pending["record_id"], lesson_notes=text)
        self._refresh_daily(record)
        await self.client.post_message(channel, MSG_NOTES_ATTACHED)
        return True

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    async def _handle_block_actions(self, payload: dict) -> None:
        actions = payload.get("actions") or []
        if not actions:
            return
        action = actions[0]
        action_id = action.get("action_id", "")
        value = action.get("value", "")
        user = (payload.get("user") or {}).get("id", "")
        channel = (payload.get("channel") or {}).get("id", "")
        message_ts = (payload.get("container") or {}).get("message_ts", "")
        _teacher_id, display_name = self._teacher_for(user)

        if action_id == "ops_coverage_claim":
            if user not in self.teacher_map:
                # Roster boundary (hardening pass 12, 2026-07-27): a claim
                # writes the claimer's name into the card and the
                # requester's daily file — never a raw Slack id.
                if channel:
                    await self.client.post_message(
                        channel, MSG_UNKNOWN_USER, thread_ts=message_ts or None
                    )
                return
            await self._claim_coverage(
                value, claimer=display_name, card_channel=channel, card_ts=message_ts
            )
        elif action_id == "ops_absence_notes":
            ids = self._parse_value(value)
            self._pending[user] = {
                "kind": "lesson_notes",
                "record_id": ids.get("absence", ""),
                "expires": self._now() + PENDING_NOTES_WINDOW_SECONDS,
            }
            await self.client.post_message(channel, MSG_NOTES_PROMPT)
        elif action_id == "ops_absence_emergency":
            ids = self._parse_value(value)
            if ids.get("absence") and self.store.get_record(ids["absence"]) is not None:
                record = self.store.update_extra(ids["absence"], emergency_plan=True)
                self._refresh_daily(record)
            await self.client.post_message(channel, MSG_EMERGENCY_PLAN)
        elif action_id == "ops_absence_cancel":
            await self._cancel_absence(self._parse_value(value), channel)
        elif action_id == "ops_review_log":
            # Stale/replayed button values must degrade gracefully, not
            # raise out of the handler (hardening pass 6, 2026-07-27).
            if self.store.get_record(value) is not None:
                record = self.store.mark_reviewed(value)
                self._refresh_daily(record)
            await self.client.post_message(channel, MSG_REVIEW_LOGGED)
        elif action_id == "ops_review_ignore":
            record = self.store.get_record(value)
            if record is not None and record.status != "resolved":
                try:
                    record = self.store.update_status(value, "resolved")
                except ValueError:
                    # e.g. a flagged coverage request that a colleague
                    # confirmed while review was pending — the machine
                    # status is terminal, so just clear the review flag
                    # (hardening pass 6, 2026-07-27).
                    record = self.store.mark_reviewed(value)
                self._refresh_daily(record)
            await self.client.post_message(channel, MSG_REVIEW_IGNORED)
        elif action_id == "ops_brief_open":
            await self.client.post_message(
                channel,
                MSG_OPEN_FILE.format(path=self.daily.daily_file_path(display_name)),
            )
        elif action_id == "ops_brief_later":
            await self.client.post_message(channel, MSG_REMIND_LATER)
            slack_user = user

            async def resend() -> None:
                await self.send_morning_briefing(slack_user)

            self._schedule_later(3600.0, resend)
        elif action_id == "ops_eod_archive":
            # Archive is automatic at the next day's first event; the button
            # acknowledges intent so the teacher gets closure now.
            await self.client.post_message(
                channel,
                "Today's file will move to Daily Updates at the start of the next school day.",
            )
        elif action_id == "ops_coverage_coordinator_confirm":
            await self._confirm_coverage(
                value, confirmed_by=display_name, card_channel=channel, card_ts=message_ts
            )
        elif action_id == "ops_coverage_coordinator_reject":
            await self._reject_coverage_claim(value, card_channel=channel, card_ts=message_ts)
        elif action_id == "ops_coverage_claim_part":
            if user not in self.teacher_map:
                if channel:
                    await self.client.post_message(
                        channel, MSG_UNKNOWN_USER, thread_ts=message_ts or None
                    )
                return
            await self._handle_partial_claim(
                value, claimer=display_name, claimer_user_id=user,
                card_channel=channel, card_ts=message_ts,
            )
        elif action_id == "ops_request_claim":
            if user not in self.teacher_map:
                if channel:
                    await self.client.post_message(
                        channel, MSG_UNKNOWN_USER, thread_ts=message_ts or None
                    )
                return
            await self._claim_ops_request(
                value, claimer=display_name, claimer_user_id=user,
                card_channel=channel, card_ts=message_ts,
            )
        elif action_id == "ops_request_resolve":
            if user not in self.teacher_map:
                if channel:
                    await self.client.post_message(
                        channel, MSG_UNKNOWN_USER, thread_ts=message_ts or None
                    )
                return
            await self._resolve_ops_request(
                value, resolved_by=display_name,
                card_channel=channel, card_ts=message_ts,
            )
        elif action_id == "ops_request_still_blocked":
            record = self.store.get_record(value)
            if record is None:
                return
            if user != (record.extra or {}).get("requester_slack_id"):
                if channel:
                    await self.client.post_message(
                        channel, MSG_OPS_REQUEST_NOT_REQUESTER, thread_ts=message_ts or None
                    )
                return
            await self._reopen_ops_request(
                value, reporter_user_id=user, card_channel=channel,
            )
        elif action_id == "ops_schedule_seen":
            await self._handle_schedule_ack(value, user, "seen", channel)
        elif action_id == "ops_schedule_conflict":
            await self._handle_schedule_ack(value, user, "conflict", channel)
        elif action_id == "ops_schedule_clarify":
            await self._handle_schedule_ack(value, user, "need_clarification", channel)

    async def _claim_coverage(self, record_id, *, claimer, card_channel, card_ts):
        record = self.store.get_record(record_id)
        if record is None:
            return
        if record.status != "open":
            if card_channel:
                await self.client.post_message(
                    card_channel, MSG_COVERAGE_ALREADY, thread_ts=card_ts
                )
            return
        record = self.store.update_status(
            record_id, "claimed", claim_by=claimer, claim_at=utc_now_iso()
        )
        record = self.store.update_status(record_id, "confirmed")  # v1 auto-confirm
        self._refresh_daily(record)

        window = self._window_label(record)
        filled = MSG_COVERAGE_FILLED.format(
            claimer=claimer, window=f", {window}" if window else ""
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(channel, ts, filled)
        else:
            await self.client.post_message(self.ops_channel, filled)

        requester_slack = self._slack_user_for_teacher(record.teacher_id)
        if requester_slack:
            dm = await self.client.open_dm(requester_slack)
            if dm:
                await self.client.post_message(dm, filled)

    async def _cancel_absence(self, ids: dict, channel: str) -> None:
        absence_id = ids.get("absence", "")
        coverage_id = ids.get("coverage", "")
        if absence_id:
            record = self.store.get_record(absence_id)
            if record is not None and record.status == "logged":
                record = self.store.update_status(absence_id, "resolved")
                self._refresh_daily(record)
        if coverage_id:
            cov = self.store.get_record(coverage_id)
            if cov is not None and cov.status == "open":
                cov = self.store.update_status(coverage_id, "resolved")
                self._refresh_daily(cov)
                card_ts = cov.extra.get("card_ts", "")
                if card_ts:
                    await self.client.update_message(
                        self.ops_channel, card_ts, MSG_COVERAGE_WITHDRAWN
                    )
        await self.client.post_message(channel, MSG_CANCELLED)

    # ------------------------------------------------------------------
    # Still I Rise: /absence slash command + modal
    # ------------------------------------------------------------------

    async def _handle_slash_command(self, payload: dict) -> None:
        command = str(payload.get("command") or "").strip().lower()
        trigger_id = payload.get("trigger_id", "")
        if command == "/absence":
            if trigger_id and hasattr(self.client, "open_view"):
                await self.client.open_view(trigger_id, self._build_absence_modal())
        elif command == "/ops-request":
            if trigger_id and hasattr(self.client, "open_view"):
                await self.client.open_view(trigger_id, self._build_ops_request_modal())
        elif command == "/schedule-change":
            if trigger_id and hasattr(self.client, "open_view"):
                await self.client.open_view(trigger_id, self._build_schedule_change_modal())

    @staticmethod
    def _build_absence_modal() -> dict:
        """Construct the /absence modal view payload."""
        def _text_input(block_id: str, label: str, *, optional: bool = False, multiline: bool = False, placeholder: str = "") -> dict:
            element: dict = {"type": "plain_text_input", "action_id": block_id}
            if multiline:
                element["multiline"] = True
            if placeholder:
                element["placeholder"] = {"type": "plain_text", "text": placeholder}
            return {
                "type": "input",
                "block_id": block_id,
                "optional": optional,
                "label": {"type": "plain_text", "text": label},
                "element": element,
            }

        def _static_select(block_id: str, label: str, options: list[str], *, optional: bool = False) -> dict:
            return {
                "type": "input",
                "block_id": block_id,
                "optional": optional,
                "label": {"type": "plain_text", "text": label},
                "element": {
                    "type": "static_select",
                    "action_id": block_id,
                    "options": [
                        {"text": {"type": "plain_text", "text": o}, "value": o}
                        for o in options
                    ],
                },
            }

        def _datepicker(block_id: str, label: str) -> dict:
            return {
                "type": "input",
                "block_id": block_id,
                "label": {"type": "plain_text", "text": label},
                "element": {"type": "datepicker", "action_id": block_id},
            }

        def _radio(block_id: str, label: str, options: list[str]) -> dict:
            return {
                "type": "input",
                "block_id": block_id,
                "label": {"type": "plain_text", "text": label},
                "element": {
                    "type": "radio_buttons",
                    "action_id": block_id,
                    "options": [
                        {"text": {"type": "plain_text", "text": o}, "value": o}
                        for o in options
                    ],
                },
            }

        return {
            "type": "modal",
            "callback_id": SIR_ABSENCE_MODAL_CALLBACK_ID,
            "title": {"type": "plain_text", "text": "Report Absence"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                _text_input("campus", "Campus", placeholder="e.g. Nairobi"),
                _datepicker("date_for", "Date"),
                _static_select("periods", "Full day or periods",
                               ["Full day", "Period 1", "Period 2", "Period 3",
                                "Period 4", "Period 5", "Period 6",
                                "Morning only", "Afternoon only"]),
                _text_input("grade_class", "Grade / Class", optional=True, placeholder="e.g. Grade 7"),
                _text_input("subject", "Subject / Responsibility", optional=True, placeholder="e.g. Mathematics"),
                _static_select("absence_type", "Absence type",
                               ["planned_leave", "illness", "emergency", "late_arrival"]),
                _radio("coverage_needed", "Coverage needed?", ["Yes", "No"]),
                _text_input("handover_link", "Handover or lesson-plan link", optional=True),
                _radio("emergency_plan", "Emergency plan available?", ["Yes", "No"]),
                _radio("contact_teacher", "Coordinator should contact you?", ["Yes", "No"]),
                _text_input("private_note", "Private note (not shared publicly)", optional=True, multiline=True),
            ],
        }

    @staticmethod
    def _build_ops_request_modal() -> dict:
        """Construct the /ops-request modal view payload."""
        def _inp(block_id, label, *, optional=False, multiline=False, placeholder=""):
            el: dict = {"type": "plain_text_input", "action_id": block_id}
            if multiline:
                el["multiline"] = True
            if placeholder:
                el["placeholder"] = {"type": "plain_text", "text": placeholder}
            return {"type": "input", "block_id": block_id, "optional": optional,
                    "label": {"type": "plain_text", "text": label}, "element": el}

        def _sel(block_id, label, options, *, optional=False):
            return {"type": "input", "block_id": block_id, "optional": optional,
                    "label": {"type": "plain_text", "text": label},
                    "element": {"type": "static_select", "action_id": block_id,
                                "options": [{"text": {"type": "plain_text", "text": o}, "value": o} for o in options]}}

        def _radio(block_id, label, options):
            return {"type": "input", "block_id": block_id,
                    "label": {"type": "plain_text", "text": label},
                    "element": {"type": "radio_buttons", "action_id": block_id,
                                "options": [{"text": {"type": "plain_text", "text": o}, "value": o} for o in options]}}

        return {
            "type": "modal",
            "callback_id": SIR_OPS_REQUEST_MODAL_CALLBACK_ID,
            "title": {"type": "plain_text", "text": "Ops Request"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                _sel("request_type", "Request type", ["facilities", "it", "supplies"]),
                _inp("campus", "Campus", placeholder="e.g. Nairobi"),
                _inp("location", "Room / Location", placeholder="e.g. Room 12"),
                _sel("severity", "Severity", ["routine", "same_day", "teaching_blocked", "urgent"]),
                _inp("description", "Short description", placeholder="What's the problem?"),
                _radio("teaching_blocked", "Is teaching currently blocked?", ["Yes", "No"]),
                _inp("photo_link", "Photo or link (optional)", optional=True),
                _sel("followup_pref", "Preferred follow-up", ["thread", "DM"], optional=True),
            ],
        }

    @staticmethod
    def _build_schedule_change_modal() -> dict:
        def _inp(bid, label, *, optional=False, placeholder=""):
            el: dict = {"type": "plain_text_input", "action_id": bid}
            if placeholder:
                el["placeholder"] = {"type": "plain_text", "text": placeholder}
            return {"type": "input", "block_id": bid, "optional": optional,
                    "label": {"type": "plain_text", "text": label}, "element": el}

        def _sel(bid, label, options, *, optional=False):
            return {"type": "input", "block_id": bid, "optional": optional,
                    "label": {"type": "plain_text", "text": label},
                    "element": {"type": "static_select", "action_id": bid,
                                "options": [{"text": {"type": "plain_text", "text": o}, "value": o} for o in options]}}

        def _dp(bid, label):
            return {"type": "input", "block_id": bid,
                    "label": {"type": "plain_text", "text": label},
                    "element": {"type": "datepicker", "action_id": bid}}

        def _radio(bid, label, options):
            return {"type": "input", "block_id": bid,
                    "label": {"type": "plain_text", "text": label},
                    "element": {"type": "radio_buttons", "action_id": bid,
                                "options": [{"text": {"type": "plain_text", "text": o}, "value": o} for o in options]}}

        return {
            "type": "modal",
            "callback_id": SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID,
            "title": {"type": "plain_text", "text": "Schedule Change"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                _inp("campus", "Campus", placeholder="e.g. Nairobi"),
                _sel("affected_scope", "Affected scope",
                     ["whole_campus", "grade", "department", "named_staff"]),
                _inp("affected_staff", "Affected staff (Slack IDs or names, comma-separated)",
                     optional=True, placeholder="Leave blank for all staff"),
                _dp("effective_date", "Effective date"),
                _inp("changed_item", "Changed item", placeholder="e.g. Assembly"),
                _inp("old_time", "Old time/location (optional)", optional=True),
                _inp("new_time", "New time/location"),
                _inp("description", "Short description", optional=True),
                _radio("ack_required", "Acknowledgement required?", ["Yes", "No"]),
            ],
        }

    # ------------------------------------------------------------------
    # Still I Rise: modal submission handling
    # ------------------------------------------------------------------

    async def _handle_view_submission(self, payload: dict) -> None:
        callback_id = (payload.get("view") or {}).get("callback_id", "")
        if callback_id == SIR_ABSENCE_MODAL_CALLBACK_ID:
            await self._handle_absence_submission(payload)
        elif callback_id == SIR_OPS_REQUEST_MODAL_CALLBACK_ID:
            await self._handle_ops_request_submission(payload)
        elif callback_id == SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID:
            await self._handle_schedule_change_submission(payload)
        elif callback_id == SIR_PARTIAL_CLAIM_CALLBACK_ID:
            await self._handle_partial_claim_submission(payload)

    async def _handle_absence_submission(self, payload: dict) -> None:
        user_id = (payload.get("user") or {}).get("id", "")
        if user_id not in self.teacher_map:
            # Unrostered user — cannot create records
            dm = await self.client.open_dm(user_id) if user_id else None
            if dm:
                await self.client.post_message(dm, MSG_UNKNOWN_USER)
            return

        teacher_id, display_name = self._teacher_for(user_id)
        values = self._extract_modal_values(payload)

        date_for = values.get("date_for") or self._today().isoformat()
        coverage_needed = values.get("coverage_needed", "").lower() == "yes"
        periods_val = values.get("periods", "Full day")
        periods_list = [periods_val] if periods_val != "Full day" else []

        # Create absence record — private fields go in extra only
        extra: dict = {
            "campus": values.get("campus", ""),
            "grade_class": values.get("grade_class", ""),
            "subject": values.get("subject", ""),
            "absence_type": values.get("absence_type", ""),
            "handover_link": values.get("handover_link", ""),
            "emergency_plan": values.get("emergency_plan", "").lower() == "yes",
            "contact_teacher": values.get("contact_teacher", "").lower() == "yes",
            "private_note_present": bool(values.get("private_note", "").strip()),
            "source": "sir_absence_modal",
        }
        # Store private note in extra — never in public channels
        private_note = values.get("private_note", "").strip()
        if private_note:
            extra["private_note"] = private_note

        absence = self.store.add_record(
            category="absence",
            teacher_id=teacher_id,
            date_for=date_for,
            time_window=periods_val if periods_val != "Full day" else "",
            periods=periods_list,
            text_raw=f"Absence: {display_name}, {date_for}",
            text_clean=f"Absence: {display_name}, {date_for}",
            source_channel="",
            source_ts="",
            extra=extra,
        )
        self._refresh_daily(absence)

        # If coverage is needed, post a coverage card
        coverage_msg = ""
        coverage_record = None
        if coverage_needed:
            coverage_record = await self._post_coverage_card(
                teacher_display=display_name,
                teacher_id=teacher_id,
                date_for=date_for,
                time_window=periods_val if periods_val != "Full day" else "",
                periods=periods_list,
                text_clean=f"Coverage needed: {display_name}, {date_for}",
                source={"source_channel": "", "source_ts": ""},
            )
            coverage_msg = MSG_ABSENCE_MODAL_COVERAGE_SENT

        # DM receipt to requester
        dm = await self.client.open_dm(user_id)
        if dm:
            receipt = MSG_ABSENCE_MODAL_RECEIPT.format(
                date=date_for, coverage=coverage_msg
            )
            await self.client.post_message(dm, receipt)

    @staticmethod
    def _extract_modal_values(payload: dict) -> dict:
        """Extract flat key-value pairs from Slack view_submission state."""
        values: dict = {}
        state = (payload.get("view") or {}).get("state", {}).get("values", {})
        for block_id, block_data in state.items():
            for action_id, action_data in block_data.items():
                atype = action_data.get("type", "")
                if atype == "plain_text_input":
                    values[block_id] = action_data.get("value") or ""
                elif atype == "static_select":
                    sel = action_data.get("selected_option") or {}
                    values[block_id] = sel.get("value", "")
                elif atype == "radio_buttons":
                    sel = action_data.get("selected_option") or {}
                    values[block_id] = sel.get("value", "")
                elif atype == "datepicker":
                    values[block_id] = action_data.get("selected_date") or ""
        return values

    # ------------------------------------------------------------------
    # Still I Rise: schedule-change acknowledgements (Phase 2B)
    # ------------------------------------------------------------------

    def _resolve_affected_staff_detail(self, raw_input: str) -> tuple[list[str], list[str]]:
        if not raw_input.strip():
            return list(self.teacher_map.keys()), []
        targets: list[str] = []
        unmatched: list[str] = []
        seen: set[str] = set()
        for token in raw_input.split(","):
            token = token.strip()
            if not token:
                continue
            matched = None
            if token in self.teacher_map:
                matched = token
            else:
                for slack_id, entry in self.teacher_map.items():
                    if token.lower() in entry.get("display_name", "").lower():
                        matched = slack_id
                        break
            if matched:
                if matched not in seen:
                    targets.append(matched)
                    seen.add(matched)
            else:
                unmatched.append(token)
        return targets, unmatched

    def _resolve_affected_staff(self, raw_input: str) -> list[str]:
        targets, _unmatched = self._resolve_affected_staff_detail(raw_input)
        return targets

    async def _handle_schedule_change_submission(self, payload: dict) -> None:
        user_id = (payload.get("user") or {}).get("id", "")
        if user_id not in self.teacher_map:
            dm = await self.client.open_dm(user_id) if user_id else None
            if dm:
                await self.client.post_message(dm, MSG_UNKNOWN_USER)
            return

        teacher_id, display_name = self._teacher_for(user_id)
        values = self._extract_modal_values(payload)

        campus = values.get("campus", "")
        affected_staff_raw = values.get("affected_staff", "")
        effective_date = values.get("effective_date") or self._today().isoformat()
        changed_item = values.get("changed_item", "")
        old_time = values.get("old_time", "")
        new_time = values.get("new_time", "")
        description = values.get("description", "")
        ack_required = values.get("ack_required", "").lower() == "yes"

        affected_ids, unmatched_targets = self._resolve_affected_staff_detail(affected_staff_raw)

        extra: dict = {
            "workflow": "sir_schedule_ack",
            "campus": campus,
            "affected_scope": values.get("affected_scope", "whole_campus"),
            "affected_slack_ids": affected_ids,
            "unmatched_targets": unmatched_targets,
            "changed_item": changed_item,
            "old_time": old_time,
            "new_time": new_time,
            "effective_date": effective_date,
            "ack_required": ack_required,
            "acknowledgements": {},
            "submitted_by": display_name,
        }

        text_clean = f"Schedule change: {changed_item} -> {new_time}, {campus}. {description}".strip()
        record = self.store.add_record(
            category="schedule_change",
            teacher_id=teacher_id,
            date_for=effective_date,
            text_raw=text_clean,
            text_clean=text_clean,
            source_channel="",
            source_ts="",
            extra=extra,
        )
        self._refresh_daily(record)

        card_text = MSG_SCHEDULE_CARD.format(item=changed_item, new_time=new_time, campus=campus)
        if ack_required:
            ack_summary = self._schedule_ack_summary(extra)
            card_text += MSG_SCHEDULE_ACK_STATUS.format(**ack_summary)

        response = await self.client.post_message(self.ops_channel, card_text)
        card_ts = (response or {}).get("ts", "")
        if card_ts:
            self.store.update_extra(record.id, card_ts=card_ts)

        if ack_required:
            dm_text = MSG_SCHEDULE_ACK_DM.format(
                date=effective_date, item=changed_item, new_time=new_time, campus=campus,
            )
            for slack_id in affected_ids:
                if slack_id in self.teacher_map:
                    dm = await self.client.open_dm(slack_id)
                    if dm:
                        await self.client.post_message(
                            dm, dm_text,
                            blocks=_blocks(dm_text, [
                                _button("Seen", "ops_schedule_seen", record.id),
                                _button("Conflict", "ops_schedule_conflict", record.id),
                                _button("Need clarification", "ops_schedule_clarify", record.id),
                            ]),
                        )

        dm = await self.client.open_dm(user_id)
        if dm:
            ack_note = MSG_SCHEDULE_ACK_REQUIRED_NOTE.format(count=len(affected_ids)) if ack_required else ""
            await self.client.post_message(dm, MSG_SCHEDULE_RECEIPT.format(ack_note=ack_note))

    async def _handle_schedule_ack(self, record_id: str, user_id: str, status: str, card_channel: str):
        record = self.store.get_record(record_id)
        if record is None:
            return
        if status not in SCHEDULE_ACK_STATUSES:
            dm = await self.client.open_dm(user_id)
            if dm:
                await self.client.post_message(dm, MSG_SCHEDULE_INVALID_ACK)
            return
        if user_id not in self.teacher_map:
            dm = await self.client.open_dm(user_id)
            if dm:
                await self.client.post_message(dm, MSG_UNKNOWN_USER)
            return
        affected = (record.extra or {}).get("affected_slack_ids", [])
        if user_id not in affected:
            dm = await self.client.open_dm(user_id)
            if dm:
                await self.client.post_message(dm, MSG_SCHEDULE_NOT_TARGETED)
            return

        _tid, display_name = self._teacher_for(user_id)
        acks = dict(record.extra.get("acknowledgements", {}))
        acks[user_id] = {"status": status, "display_name": display_name, "at": utc_now_iso()}
        record = self.store.update_extra(record_id, acknowledgements=acks)

        if status in ("conflict", "need_clarification") and not record.needs_review:
            record = self.store.mark_needs_review(
                record_id, f"schedule ack: {status} from {display_name}"
            )
        self._refresh_daily(record)

        card_ts = record.extra.get("card_ts", "")
        if card_ts:
            ack_summary = self._schedule_ack_summary(record.extra)
            card_text = MSG_SCHEDULE_CARD.format(
                item=record.extra.get("changed_item", ""),
                new_time=record.extra.get("new_time", ""),
                campus=record.extra.get("campus", ""),
            ) + MSG_SCHEDULE_ACK_STATUS.format(**ack_summary)
            await self.client.update_message(self.ops_channel, card_ts, card_text)

        dm = await self.client.open_dm(user_id)
        if dm:
            msg = {"seen": MSG_SCHEDULE_SEEN, "conflict": MSG_SCHEDULE_CONFLICT,
                   "need_clarification": MSG_SCHEDULE_CLARIFY}.get(status, MSG_SCHEDULE_SEEN)
            await self.client.post_message(dm, msg)

    @staticmethod
    def _schedule_ack_summary(extra: dict) -> dict:
        affected = extra.get("affected_slack_ids", [])
        acks = extra.get("acknowledgements", {})
        targeted_acks = [
            acks[slack_id] for slack_id in affected
            if slack_id in acks and acks[slack_id].get("status") in SCHEDULE_ACK_STATUSES
        ]
        seen = sum(1 for a in targeted_acks if a.get("status") == "seen")
        conflicts = sum(1 for a in targeted_acks if a.get("status") == "conflict")
        clarify = sum(1 for a in targeted_acks if a.get("status") == "need_clarification")
        return {"seen": seen, "total": len(affected), "conflicts": conflicts,
                "clarify": clarify, "missing": max(0, len(affected) - len(targeted_acks))}

    # ------------------------------------------------------------------
    # Still I Rise: operational request center (Phase 2A)
    # ------------------------------------------------------------------

    async def _handle_ops_request_submission(self, payload: dict) -> None:
        user_id = (payload.get("user") or {}).get("id", "")
        if user_id not in self.teacher_map:
            dm = await self.client.open_dm(user_id) if user_id else None
            if dm:
                await self.client.post_message(dm, MSG_UNKNOWN_USER)
            return

        teacher_id, display_name = self._teacher_for(user_id)
        values = self._extract_modal_values(payload)

        request_type = values.get("request_type", "facilities")
        campus = values.get("campus", "")
        location = values.get("location", "")
        severity = values.get("severity", "routine")
        description = values.get("description", "")
        teaching_blocked = values.get("teaching_blocked", "").lower() == "yes"
        photo_link = values.get("photo_link", "")

        extra: dict = {
            "workflow": "sir_ops_request",
            "request_type": request_type,
            "campus": campus,
            "location": location,
            "severity": severity,
            "description": description,
            "teaching_blocked": teaching_blocked,
            "photo_url": photo_link,
            "followup_pref": values.get("followup_pref", ""),
            "requester_slack_id": user_id,
            "requester_name": display_name,
            "requester_confirmation_required": severity in ("teaching_blocked", "urgent"),
        }

        needs_review = severity in ("teaching_blocked", "urgent")
        text_clean = f"Ops request [{request_type}]: {campus}, {location} — {severity}. {description}"

        record = self.store.add_record(
            category="facilities",
            teacher_id=teacher_id,
            date_for=self._today().isoformat(),
            text_raw=text_clean,
            text_clean=text_clean,
            needs_review=needs_review,
            review_reason=f"{severity} ops request" if needs_review else "",
            source_channel="",
            source_ts="",
            extra=extra,
        )
        self._refresh_daily(record)

        # Post triage card to ops channel
        card_text = MSG_OPS_REQUEST_CARD.format(
            request_type=request_type, campus=campus,
            location=location, severity=severity, description=description[:80],
        )
        response = await self.client.post_message(
            self.ops_channel, card_text,
            blocks=_blocks(card_text, [
                _button("Claim", "ops_request_claim", record.id),
                _button("Resolve", "ops_request_resolve", record.id),
            ]),
        )
        card_ts = (response or {}).get("ts", "")
        if card_ts:
            self.store.update_extra(record.id, card_ts=card_ts)

        # DM receipt to requester
        dm = await self.client.open_dm(user_id)
        if dm:
            teaching_note = MSG_OPS_REQUEST_TEACHING_BLOCKED if teaching_blocked else ""
            receipt = MSG_OPS_REQUEST_RECEIPT.format(
                request_type=request_type, teaching_note=teaching_note,
            )
            await self.client.post_message(dm, receipt)

    async def _claim_ops_request(self, record_id, *, claimer, claimer_user_id, card_channel, card_ts):
        """Owner claims an operational request."""
        record = self.store.get_record(record_id)
        if record is None:
            return
        if record.extra.get("owner_slack_id"):
            if card_channel:
                await self.client.post_message(
                    card_channel, "This request already has an owner.", thread_ts=card_ts
                )
            return

        record = self.store.update_extra(
            record_id,
            owner_slack_id=claimer_user_id,
            owner_name=claimer,
            owner_claimed_at=utc_now_iso(),
        )
        # Move needs_review -> logged if applicable
        if record.needs_review:
            record = self.store.mark_reviewed(record_id)
        self._refresh_daily(record)

        # Update card
        claimed_text = MSG_OPS_REQUEST_CLAIMED.format(owner=claimer)
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(
                channel, ts, claimed_text,
                blocks=_blocks(claimed_text, [
                    _button("Resolve", "ops_request_resolve", record_id),
                ]),
            )

        # Notify requester
        requester_slack = record.extra.get("requester_slack_id", "")
        if requester_slack:
            dm = await self.client.open_dm(requester_slack)
            if dm:
                await self.client.post_message(dm, claimed_text)

    async def _resolve_ops_request(self, record_id, *, resolved_by, card_channel, card_ts):
        """Mark an operational request as resolved."""
        record = self.store.get_record(record_id)
        if record is None or record.status == "resolved":
            return
        # Ensure we're at 'logged' before resolving
        if record.needs_review:
            record = self.store.mark_reviewed(record_id)
        record = self.store.update_status(record_id, "resolved")
        record = self.store.update_extra(
            record_id, resolved_by=resolved_by, resolved_at=utc_now_iso(),
        )
        self._refresh_daily(record)

        resolved_text = MSG_OPS_REQUEST_RESOLVED.format(
            owner=resolved_by, note=record.extra.get("description", ""),
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(channel, ts, resolved_text)

        # Notify requester with a "Still blocked?" option
        requester_slack = record.extra.get("requester_slack_id", "")
        if requester_slack:
            dm = await self.client.open_dm(requester_slack)
            if dm:
                await self.client.post_message(
                    dm, resolved_text,
                    blocks=_blocks(resolved_text, [
                        _button("Still blocked", "ops_request_still_blocked", record_id),
                    ]),
                )

    async def _reopen_ops_request(self, original_record_id, *, reporter_user_id, card_channel):
        """Create a follow-up record linked to the original."""
        original = self.store.get_record(original_record_id)
        if original is None:
            return

        # Copy safe fields from original
        extra = dict(original.extra or {})
        extra["reopened_from"] = original_record_id
        extra["workflow"] = "sir_ops_request"
        extra.pop("owner_slack_id", None)
        extra.pop("owner_name", None)
        extra.pop("owner_claimed_at", None)
        extra.pop("resolved_by", None)
        extra.pop("resolved_at", None)
        extra.pop("card_ts", None)

        followup = self.store.add_record(
            category="facilities",
            teacher_id=original.teacher_id,
            date_for=self._today().isoformat(),
            text_raw=f"Reopened: {original.text_clean}",
            text_clean=f"Reopened: {original.text_clean}",
            needs_review=True,
            review_reason="reopened — still blocked",
            source_channel="",
            source_ts="",
            extra=extra,
        )
        self._refresh_daily(followup)

        # Post new triage card
        card_text = f"Reopened ops request: {original.text_clean}"
        response = await self.client.post_message(
            self.ops_channel, card_text,
            blocks=_blocks(card_text, [
                _button("Claim", "ops_request_claim", followup.id),
            ]),
        )
        card_ts = (response or {}).get("ts", "")
        if card_ts:
            self.store.update_extra(followup.id, card_ts=card_ts)

        # Notify requester
        if reporter_user_id:
            dm = await self.client.open_dm(reporter_user_id)
            if dm:
                await self.client.post_message(dm, MSG_OPS_REQUEST_REOPENED)

    # ------------------------------------------------------------------
    # Still I Rise: coordinator-confirmed coverage
    # ------------------------------------------------------------------

    async def _claim_coverage_with_confirmation(
        self, record_id, *, claimer, claimer_user_id, card_channel, card_ts
    ):
        """Claim coverage with coordinator approval step."""
        record = self.store.get_record(record_id)
        if record is None:
            return
        if record.status != "open":
            if card_channel:
                await self.client.post_message(
                    card_channel, MSG_COVERAGE_ALREADY, thread_ts=card_ts
                )
            return

        # Transition open -> claimed (not yet confirmed)
        record = self.store.update_status(
            record_id, "claimed", claim_by=claimer, claim_at=utc_now_iso()
        )
        record = self.store.update_extra(
            record_id, coordinator_pending=True, claimer_user_id=claimer_user_id
        )
        self._refresh_daily(record)

        # Update original card to show tentative
        window = self._window_label(record)
        pending_text = MSG_COVERAGE_CLAIMED_PENDING.format(
            claimer=claimer, window=f", {window}" if window else ""
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            confirm_blocks = _blocks(pending_text, [
                _button("Confirm assignment", "ops_coverage_coordinator_confirm", record_id),
                _button("Choose another", "ops_coverage_coordinator_reject", record_id),
            ])
            await self.client.update_message(channel, ts, pending_text, blocks=confirm_blocks)
        else:
            await self.client.post_message(self.ops_channel, pending_text)

    async def _confirm_coverage(self, record_id, *, confirmed_by, card_channel, card_ts):
        """Coordinator confirms a claimed coverage assignment."""
        record = self.store.get_record(record_id)
        if record is None or record.status != "claimed":
            return
        record = self.store.update_status(record_id, "confirmed")
        record = self.store.update_extra(
            record_id,
            coordinator_confirmed_by=confirmed_by,
            coordinator_confirmed_at=utc_now_iso(),
            coordinator_pending=False,
        )
        self._refresh_daily(record)

        window = self._window_label(record)
        confirmed_text = MSG_COVERAGE_CONFIRMED.format(
            claimer=record.claim_by or "unknown",
            window=f", {window}" if window else "",
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(channel, ts, confirmed_text)
        else:
            await self.client.post_message(self.ops_channel, confirmed_text)

        # DM the requester
        requester_slack = self._slack_user_for_teacher(record.teacher_id)
        if requester_slack:
            dm = await self.client.open_dm(requester_slack)
            if dm:
                await self.client.post_message(dm, confirmed_text)

    async def _reject_coverage_claim(self, record_id, *, card_channel, card_ts):
        """Coordinator rejects a claim — revert to open."""
        record = self.store.get_record(record_id)
        if record is None or record.status != "claimed":
            return
        # Revert to open by creating a fresh coverage request at the same slot
        record = self.store.update_status(record_id, "open")
        record = self.store.update_extra(
            record_id, coordinator_pending=False, claimer_user_id=""
        )
        self._refresh_daily(record)

        window = self._window_label(record)
        card_text = MSG_COVERAGE_CARD.format(
            who=record.actor_name or "a teacher",
            window=f", {window}" if window else "",
            date=f" on {record.date_for}" if record.date_for else "",
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(
                channel, ts, card_text,
                blocks=_blocks(card_text, [
                    _button("Claim coverage", "ops_coverage_claim", record_id),
                ]),
            )

    # ------------------------------------------------------------------
    # Still I Rise: partial coverage claim
    # ------------------------------------------------------------------

    async def _handle_partial_claim(self, record_id, *, claimer, claimer_user_id, card_channel, card_ts):
        """Open a partial claim modal or store a simplified partial claim."""
        record = self.store.get_record(record_id)
        if record is None or record.status not in ("open", "claimed"):
            return
        # Store partial claim in extra, mark needs_review
        record = self.store.update_extra(
            record_id,
            partial_claim={"claimer": claimer, "claimer_user_id": claimer_user_id},
        )
        record = self.store.update_status(
            record_id, "claimed", claim_by=claimer, claim_at=utc_now_iso()
        ) if record.status == "open" else record
        # Mark as needing review since full coverage isn't proven
        if not record.needs_review:
            self.store._conn.execute(
                "UPDATE ops_records SET needs_review = 1, review_reason = ? WHERE id = ?",
                ("partial coverage — not all periods confirmed", record_id),
            )
            self.store._conn.commit()
        self._refresh_daily(record)

        window = self._window_label(record)
        partial_text = MSG_PARTIAL_CLAIM_NOTED.format(
            claimer=claimer, detail=window or "some periods",
        )
        channel = card_channel or self.ops_channel
        ts = card_ts or record.extra.get("card_ts", "")
        if ts:
            await self.client.update_message(channel, ts, partial_text)
        else:
            await self.client.post_message(self.ops_channel, partial_text)

    async def _handle_partial_claim_submission(self, payload: dict) -> None:
        """Handle partial claim modal submission (future expansion)."""
        pass  # Minimal path: partial claims use button-based flow above

    # ------------------------------------------------------------------
    # Briefings (called by the scheduler or buttons)
    # ------------------------------------------------------------------

    def _day_counts(self, teacher_id: str) -> tuple[list, int]:
        today_iso = self._today().isoformat()
        records = [
            r
            for r in self.store.records_for_day(today_iso, teacher_id=teacher_id)
            if r.status != "resolved"
        ]
        review = sum(1 for r in records if r.needs_review)
        return records, review

    async def send_morning_briefing(self, slack_user_id: str) -> None:
        teacher_id, display_name = self._teacher_for(slack_user_id)
        records, _review = self._day_counts(teacher_id)
        first_name = display_name.split()[0] if display_name else "there"
        if records:
            highlights = "; ".join(
                (r.text_clean or "").strip()[:80] for r in records[:3] if r.text_clean
            )
            text = MSG_BRIEFING.format(
                name=first_name,
                count=len(records),
                s="" if len(records) == 1 else "s",
                items=f": {highlights}" if highlights else "",
            )
        else:
            text = MSG_BRIEFING_NONE.format(name=first_name)
        dm = await self.client.open_dm(slack_user_id)
        if not dm:
            return
        await self.client.post_message(
            dm,
            text,
            blocks=_blocks(
                text,
                [
                    _button("Open daily file", "ops_brief_open"),
                    _button("Remind me later", "ops_brief_later"),
                ],
            ),
        )

    async def send_end_of_day_summary(self, slack_user_id: str) -> None:
        teacher_id, display_name = self._teacher_for(slack_user_id)
        records, review = self._day_counts(teacher_id)
        text = MSG_EOD.format(
            count=len(records),
            s="" if len(records) == 1 else "s",
            review=MSG_EOD_REVIEW.format(n=review, review_s="s" if review == 1 else "")
            if review
            else "",
        )
        dm = await self.client.open_dm(slack_user_id)
        if not dm:
            return
        await self.client.post_message(
            dm,
            text,
            blocks=_blocks(
                text,
                [
                    _button("Open file", "ops_brief_open"),
                    _button("Archive today", "ops_eod_archive"),
                ],
            ),
        )

    async def send_all_briefings(self, kind: str) -> None:
        for slack_user_id in self.teacher_map:
            try:
                if kind == "morning":
                    await self.send_morning_briefing(slack_user_id)
                else:
                    await self.send_end_of_day_summary(slack_user_id)
            except Exception:
                logger.exception("[slack-ops] briefing failed for a teacher")

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    @staticmethod
    def _default_schedule_later(delay: float, coro_factory) -> None:
        async def runner() -> None:
            await asyncio.sleep(delay)
            await coro_factory()

        asyncio.get_event_loop().create_task(runner())

    async def run_schedules(
        self,
        *,
        briefing_hhmm: str = "07:30",
        eod_hhmm: str = "16:30",
        poll_seconds: float = 30.0,
        sleep=asyncio.sleep,
        local_now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        """Fire the morning briefing and end-of-day summary once per day.

        Wall-clock poller (not cron): checks every poll_seconds whether a
        configured local time has passed and hasn't fired today. Cheap,
        drift-tolerant, and safe across laptop sleep (fires late rather
        than never).
        """
        get_now = local_now or datetime.now
        fired: dict = {}
        while True:
            now = get_now()
            day = now.date().isoformat()
            for kind, hhmm in (("morning", briefing_hhmm), ("eod", eod_hhmm)):
                try:
                    hour, minute = (int(part) for part in hhmm.split(":"))
                except ValueError:
                    continue
                due = now.hour > hour or (now.hour == hour and now.minute >= minute)
                if due and fired.get(kind) != day:
                    # Marked fired BEFORE sending: a Slack failure must not
                    # hot-retry every poll, and (hardening pass 10,
                    # 2026-07-27) must not kill this loop — a dead scheduler
                    # means no briefings ever again until restart.
                    fired[kind] = day
                    try:
                        await self.send_all_briefings(kind)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(
                            "%s briefing failed (%s)", kind, type(exc).__name__
                        )
            await sleep(poll_seconds)

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_value(value: str) -> dict:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _window_label(record: OpsRecord) -> str:
        if record.time_window:
            return record.time_window
        if record.periods:
            labels = " and ".join(f"{p}" for p in record.periods)
            return f"period{'s' if len(record.periods) > 1 else ''} {labels}"
        return ""
