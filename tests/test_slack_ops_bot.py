"""
Tests for src/education/slack_ops_bot.py (Lane D, spec §3.5).

Covers: envelope dispatch, the absence flow (record + coverage card +
buttons), coverage claim via button and via text, cancel/withdrawal,
lesson-notes pending window (attach + expiry), silent ops-channel
capture, broadcast fan-out to every teacher's file, low-confidence
clarifications with Log it / Ignore, privacy boundary (only ops channel
+ DMs), morning briefing / end-of-day summary, Remind-me-later
scheduling, and handler resilience (bad envelopes never raise).

Everything is hermetic: fake Slack client, injected `today`/`now`,
LV_OPS_* env redirected into tmp_path by the fixtures below.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.education.daily_file import DailyFileEngine
from src.education.ops_records import OpsRecordStore
from src.education.slack_ops_bot import (
    MSG_CANCELLED,
    MSG_COVERAGE_ALREADY,
    MSG_COVERAGE_CLAIM_TEXT_AMBIGUOUS,
    MSG_COVERAGE_WITHDRAWN,
    MSG_DM_SAVED,
    MSG_EMERGENCY_PLAN,
    MSG_NOTES_ATTACHED,
    MSG_NOTES_PROMPT,
    MSG_REMIND_LATER,
    MSG_REVIEW_IGNORED,
    MSG_REVIEW_LOGGED,
    MSG_UNKNOWN_USER,
    MSG_VOICE_CLIP,
    PENDING_NOTES_WINDOW_SECONDS,
    SlackOpsBot,
)


OPS_CHANNEL = "C0PS"
TODAY = date(2026, 7, 28)  # a Tuesday
TOMORROW = "2026-07-29"

TEACHER_MAP = {
    "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
    "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
}


class FakeClient:
    """Records post_message / update_message / open_dm calls."""

    def __init__(self):
        self.posts: list[dict] = []
        self.updates: list[dict] = []
        self.dm_opens: list[str] = []
        self._counter = 0

    async def post_message(self, channel, text, blocks=None, thread_ts=None):
        self._counter += 1
        ts = f"1721990400.{self._counter:06d}"
        self.posts.append(
            {"channel": channel, "text": text, "blocks": blocks,
             "thread_ts": thread_ts, "ts": ts}
        )
        return {"ok": True, "ts": ts, "channel": channel}

    async def update_message(self, channel, ts, text, blocks=None):
        self.updates.append(
            {"channel": channel, "ts": ts, "text": text, "blocks": blocks}
        )
        return {"ok": True, "ts": ts}

    async def open_dm(self, user_id):
        self.dm_opens.append(user_id)
        return f"D{user_id}"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops_records.db"))
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(tmp_path / "desktop"))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(tmp_path / "ops_state.json"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy_events.ndjson"))
    store = OpsRecordStore()
    yield store, tmp_path / "desktop"
    store.close()


@pytest.fixture
def rig(env):
    store, desktop = env
    client = FakeClient()
    daily = DailyFileEngine(store, teacher_map=TEACHER_MAP)
    clock = {"t": 1_000_000.0}
    scheduled: list[tuple[float, object]] = []
    bot = SlackOpsBot(
        store=store,
        daily=daily,
        client=client,
        ops_channel=OPS_CHANNEL,
        teacher_map=TEACHER_MAP,
        today=lambda: TODAY,
        now=lambda: clock["t"],
        schedule_later=lambda delay, factory: scheduled.append((delay, factory)),
    )
    return {
        "store": store, "daily": daily, "client": client, "bot": bot,
        "clock": clock, "scheduled": scheduled, "desktop": desktop,
    }


def message_envelope(text, *, user="U111", channel="DU111", ts="1721990000.000001",
                     channel_type=None, **extra):
    event = {"type": "message", "text": text, "user": user, "channel": channel,
             "ts": ts}
    if channel_type is not None:
        event["channel_type"] = channel_type
    event.update(extra)
    return {"event": event}


def action_envelope(action_id, value, *, user="U111", channel=OPS_CHANNEL,
                    message_ts=""):
    return {
        "type": "block_actions",
        "user": {"id": user},
        "channel": {"id": channel},
        "container": {"message_ts": message_ts},
        "actions": [{"action_id": action_id, "value": value}],
    }


def button_value(post, action_id):
    """Pull a button's value out of a recorded post's blocks."""
    for block in post["blocks"] or []:
        if block.get("type") != "actions":
            continue
        for element in block.get("elements", []):
            if element.get("action_id") == action_id:
                return element.get("value", "")
    raise AssertionError(f"no button {action_id!r} in {post['blocks']!r}")


async def send_dm(bot, text, *, user="U111", ts="1721990000.000001"):
    await bot.on_envelope(
        "events_api",
        message_envelope(text, user=user, channel=f"D{user}",
                         channel_type="im", ts=ts),
    )


async def send_ops(bot, text, *, user="U111", ts="1721990000.000002"):
    await bot.on_envelope(
        "events_api",
        message_envelope(text, user=user, channel=OPS_CHANNEL,
                         channel_type="channel", ts=ts),
    )


def coverage_records(store, date_iso=TODAY.isoformat()):
    return [
        r for r in store.records_for_day(date_iso)
        if r.category == "coverage_request"
    ]


# ------------------------------------------------------------------ absence


async def test_absence_dm_creates_record_card_and_buttons(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_dm(bot, "I'm out tomorrow. Need coverage for 2nd period.")

    records = store.records_for_day(TOMORROW, teacher_id="t-ana")
    categories = {r.category for r in records}
    assert categories == {"absence", "coverage_request"}
    absence = next(r for r in records if r.category == "absence")
    cov = next(r for r in records if r.category == "coverage_request")
    assert absence.status == "logged"
    assert cov.status == "open"
    assert cov.periods == [2]
    assert cov.extra.get("card_ts")  # card ts persisted for restart-safe cancel

    # First post: coverage card in the ops channel with a Claim button.
    card = client.posts[0]
    assert card["channel"] == OPS_CHANNEL
    assert "Coverage needed: Ana Ruiz" in card["text"]
    assert "period 2" in card["text"]
    assert TOMORROW in card["text"]
    assert button_value(card, "ops_coverage_claim") == cov.id

    # Second post: DM confirmation with the three absence buttons.
    confirm = client.posts[1]
    assert confirm["channel"] == "DU111"
    assert "log your absence for " + TOMORROW in confirm["text"]
    assert "coverage request" in confirm["text"]
    value = json.loads(button_value(confirm, "ops_absence_cancel"))
    assert value == {"absence": absence.id, "coverage": cov.id}
    button_value(confirm, "ops_absence_notes")
    button_value(confirm, "ops_absence_emergency")


async def test_absence_writes_daily_file(rig):
    # A tomorrow-dated absence refreshes TODAY's file (which stays today's
    # picture — the absence surfaces tomorrow via rotation); the DM receipt
    # is what confirms the logging (hardening pass 5).
    bot, daily = rig["bot"], rig["daily"]
    await send_dm(bot, "I'm out tomorrow. Need coverage for 2nd period.")
    path = daily.daily_file_path("Ana Ruiz")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "# Today - Ana Ruiz" in content
    assert "## Coverage" in content
    assert "out tomorrow" not in content


async def test_same_day_absence_shows_in_todays_file(rig):
    bot, daily = rig["bot"], rig["daily"]
    await send_dm(bot, "I'm sick today, staying home.")
    content = daily.daily_file_path("Ana Ruiz").read_text(encoding="utf-8")
    assert "sick today" in content


async def test_absence_without_coverage_posts_no_card(rig):
    bot, client, store = rig["bot"], rig["client"], rig["store"]
    await send_dm(bot, "I'm sick today, staying home.")
    assert coverage_records(store) == []
    assert len(client.posts) == 1
    assert client.posts[0]["channel"] == "DU111"


async def test_at_absence_signal_creates_simple_absence_record(rig):
    bot, client, store = rig["bot"], rig["client"], rig["store"]
    await send_dm(bot, "@absence tomorrow")

    records = store.records_for_day(TOMORROW, teacher_id="t-ana")
    assert [r.category for r in records] == ["absence"]
    assert records[0].text_clean == "@absence tomorrow"
    assert records[0].actor_name == "Ana Ruiz"
    assert "log your absence for " + TOMORROW in client.posts[0]["text"]


# ------------------------------------------------------------------ claim


async def claim_setup(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_dm(bot, "I'm out tomorrow. Need coverage for 2nd period.")
    cov = coverage_records(store, TOMORROW)[0]
    card_ts = client.posts[0]["ts"]
    return cov, card_ts


async def test_claim_button_updates_card_and_dms_requester(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    cov, card_ts = await claim_setup(rig)

    await bot.on_envelope(
        "interactive",
        action_envelope("ops_coverage_claim", cov.id, user="U222",
                        message_ts=card_ts),
    )

    updated = store.get_record(cov.id)
    assert updated.status == "confirmed"  # v1 auto-confirm
    assert updated.claim_by == "Ben Ali"
    assert updated.claim_at

    # Card rewritten in place.
    assert len(client.updates) == 1
    update = client.updates[0]
    assert update["channel"] == OPS_CHANNEL
    assert update["ts"] == card_ts
    assert "Coverage filled: Ben Ali" in update["text"]

    # Requester (Ana) gets a DM.
    assert "U111" in client.dm_opens
    assert any(
        p["channel"] == "DU111" and "Coverage filled: Ben Ali" in p["text"]
        for p in client.posts
    )


async def test_double_claim_says_already_covered(rig):
    bot, client = rig["bot"], rig["client"]
    cov, card_ts = await claim_setup(rig)
    envelope = action_envelope("ops_coverage_claim", cov.id, user="U222",
                               message_ts=card_ts)
    await bot.on_envelope("interactive", envelope)
    updates_before = len(client.updates)
    await bot.on_envelope("interactive", envelope)
    assert len(client.updates) == updates_before  # card not rewritten again
    assert client.posts[-1]["text"] == MSG_COVERAGE_ALREADY
    assert client.posts[-1]["thread_ts"] == card_ts


async def test_text_claim_with_single_open_request(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_ops(bot, "Need coverage for period 3 today.", user="U111")
    cov = coverage_records(store)[0]
    card_ts = cov.extra["card_ts"]

    await send_ops(bot, "I'll cover it.", user="U222", ts="1721990001.000009")

    assert store.get_record(cov.id).status == "confirmed"
    assert store.get_record(cov.id).claim_by == "Ben Ali"
    # Card found via persisted card_ts (no interactive payload here).
    assert client.updates[0]["ts"] == card_ts
    assert "Coverage filled: Ben Ali" in client.updates[0]["text"]


async def test_text_claim_ambiguous_when_multiple_open(rig):
    bot, client = rig["bot"], rig["client"]
    await send_ops(bot, "Need coverage for period 3 today.", user="U111")
    await send_ops(bot, "Need coverage for period 5 today.", user="U111",
                   ts="1721990001.000003")
    await send_ops(bot, "I can cover it.", user="U222", ts="1721990001.000004")
    assert client.posts[-1]["text"] == MSG_COVERAGE_CLAIM_TEXT_AMBIGUOUS


# ------------------------------------------------------------------ cancel


async def test_cancel_withdraws_absence_and_coverage(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    cov, card_ts = await claim_setup(rig)
    value = button_value(client.posts[1], "ops_absence_cancel")
    ids = json.loads(value)

    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_cancel", value, user="U111",
                        channel="DU111"),
    )

    assert store.get_record(ids["absence"]).status == "resolved"
    assert store.get_record(ids["coverage"]).status == "resolved"
    withdrawn = client.updates[0]
    assert withdrawn["channel"] == OPS_CHANNEL
    assert withdrawn["ts"] == card_ts
    assert withdrawn["text"] == MSG_COVERAGE_WITHDRAWN
    assert client.posts[-1]["text"] == MSG_CANCELLED
    # Resolved records leave the daily file.
    content = daily.render_markdown("t-ana", "Ana Ruiz", TOMORROW)
    assert "out tomorrow" not in content
    assert "No coverage assigned" in content


async def test_cancel_after_claim_leaves_coverage_confirmed(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    cov, card_ts = await claim_setup(rig)
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_coverage_claim", cov.id, user="U222",
                        message_ts=card_ts),
    )
    value = button_value(client.posts[1], "ops_absence_cancel")
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_cancel", value, user="U111",
                        channel="DU111"),
    )
    # Confirmed coverage is terminal — cancel doesn't rewrite the filled card.
    assert store.get_record(cov.id).status == "confirmed"
    assert all(u["text"] != MSG_COVERAGE_WITHDRAWN for u in client.updates)
    assert client.posts[-1]["text"] == MSG_CANCELLED


# ------------------------------------------------------------------ lesson notes


async def test_lesson_notes_attach_within_window(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    _cov, _ts = await claim_setup(rig)
    value = button_value(client.posts[1], "ops_absence_notes")
    absence_id = json.loads(value)["absence"]

    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_notes", value, user="U111", channel="DU111"),
    )
    assert client.posts[-1]["text"] == MSG_NOTES_PROMPT

    await send_dm(bot, "Worksheets are in the blue folder on my desk.",
                  ts="1721990002.000001")
    assert client.posts[-1]["text"] == MSG_NOTES_ATTACHED
    record = store.get_record(absence_id)
    assert "blue folder" in record.extra["lesson_notes"]


async def test_lesson_notes_window_expires(rig):
    bot, store, client, clock = rig["bot"], rig["store"], rig["client"], rig["clock"]
    _cov, _ts = await claim_setup(rig)
    value = button_value(client.posts[1], "ops_absence_notes")
    absence_id = json.loads(value)["absence"]

    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_notes", value, user="U111", channel="DU111"),
    )
    clock["t"] += PENDING_NOTES_WINDOW_SECONDS + 1

    await send_dm(bot, "Worksheets are in the blue folder on my desk.",
                  ts="1721990002.000002")
    assert "lesson_notes" not in store.get_record(absence_id).extra
    assert client.posts[-1]["text"] != MSG_NOTES_ATTACHED  # classified normally


async def test_emergency_plan_button(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    _cov, _ts = await claim_setup(rig)
    value = button_value(client.posts[1], "ops_absence_emergency")
    absence_id = json.loads(value)["absence"]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_emergency", value, user="U111",
                        channel="DU111"),
    )
    assert store.get_record(absence_id).extra["emergency_plan"] is True
    assert client.posts[-1]["text"] == MSG_EMERGENCY_PLAN


# ------------------------------------------------------------------ capture


async def test_ops_channel_announcement_is_silent_and_broadcasts(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    await send_ops(bot, "Welcome to our new music teacher joining us today.")
    assert client.posts == []  # silent capture — the file is the ack (§3.5)
    records = store.records_for_day(TODAY.isoformat())
    assert [r.category for r in records] == ["announcement"]
    assert records[0].teacher_id == ""  # broadcast
    # Every teacher's file carries it.
    for name in ("Ana Ruiz", "Ben Ali"):
        content = daily.daily_file_path(name).read_text(encoding="utf-8")
        assert "music teacher" in content


async def test_schedule_change_lands_in_every_file(rig):
    bot, daily = rig["bot"], rig["daily"]
    await send_ops(bot, "Assembly moved to 10:30 today.")
    for name in ("Ana Ruiz", "Ben Ali"):
        content = daily.daily_file_path(name).read_text(encoding="utf-8")
        assert "## Schedule Changes" in content
        assert "Assembly moved to 10:30" in content


async def test_dm_capture_confirms_with_receipt(rig):
    bot, client = rig["bot"], rig["client"]
    await send_dm(bot, "Early pickup at 14:00 for Sofia today.")
    assert client.posts[-1]["text"] == MSG_DM_SAVED


async def test_named_teacher_coverage_request_targets_them(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_ops(bot, "Need a substitute for Ana on Monday.", user="U222")
    cov = coverage_records(store, "2026-08-03")[0]  # next Monday
    assert cov.teacher_id == "t-ana"
    assert "Coverage needed: Ana Ruiz" in client.posts[0]["text"]


# ------------------------------------------------------------------ review


async def test_low_confidence_other_gets_log_ignore_buttons(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    await send_dm(bot, "hello there")
    post = client.posts[-1]
    record = store.records_for_day(TODAY.isoformat(), teacher_id="t-ana")[0]
    assert record.needs_review is True
    assert button_value(post, "ops_review_log") == record.id
    assert button_value(post, "ops_review_ignore") == record.id
    content = daily.render_markdown("t-ana", "Ana Ruiz", TODAY.isoformat())
    assert "## To Review" in content


async def test_review_log_clears_flag(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    await send_dm(bot, "hello there")
    record = store.records_for_day(TODAY.isoformat(), teacher_id="t-ana")[0]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_review_log", record.id, user="U111", channel="DU111"),
    )
    assert store.get_record(record.id).needs_review is False
    assert client.posts[-1]["text"] == MSG_REVIEW_LOGGED
    content = daily.render_markdown("t-ana", "Ana Ruiz", TODAY.isoformat())
    assert "## To Review" not in content
    assert "hello there" in content  # now in its category section


async def test_review_ignore_removes_from_file(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    await send_dm(bot, "hello there")
    record = store.records_for_day(TODAY.isoformat(), teacher_id="t-ana")[0]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_review_ignore", record.id, user="U111",
                        channel="DU111"),
    )
    assert store.get_record(record.id).status == "resolved"
    assert client.posts[-1]["text"] == MSG_REVIEW_IGNORED
    content = daily.render_markdown("t-ana", "Ana Ruiz", TODAY.isoformat())
    assert "hello there" not in content


async def test_review_ignore_on_confirmed_coverage_clears_flag_only(rig):
    # A flagged coverage request that a colleague confirms while review is
    # pending has a terminal machine status — Ignore must clear the flag,
    # not raise on the illegal confirmed->resolved transition.
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_dm(bot, "Can someone cover my class?")
    cov = coverage_records(store)[0]
    assert cov.needs_review is True
    store.update_status(cov.id, "claimed", claim_by="Ben Ali")
    store.update_status(cov.id, "confirmed")
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_review_ignore", cov.id, user="U111", channel="DU111"),
    )
    updated = store.get_record(cov.id)
    assert updated.status == "confirmed"
    assert updated.needs_review is False
    assert client.posts[-1]["text"] == MSG_REVIEW_IGNORED


async def test_stale_review_and_emergency_buttons_degrade_gracefully(rig):
    bot, client = rig["bot"], rig["client"]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_review_log", "gone-record-id", user="U111",
                        channel="DU111"),
    )
    assert client.posts[-1]["text"] == MSG_REVIEW_LOGGED
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_review_ignore", "gone-record-id", user="U111",
                        channel="DU111"),
    )
    assert client.posts[-1]["text"] == MSG_REVIEW_IGNORED
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_emergency", '{"absence": "gone-record-id"}',
                        user="U111", channel="DU111"),
    )  # no raise; acknowledgement still sent
    assert len(client.posts) == 3


async def test_low_confidence_coverage_request_lands_in_to_review(rig):
    bot, store, client, daily = rig["bot"], rig["store"], rig["client"], rig["daily"]
    await send_dm(bot, "Can someone cover my class?")
    cov = coverage_records(store)[0]
    assert cov.needs_review is True
    assert cov.status == "open"  # still claimable while ambiguous
    assert "Which class, period, or time" in client.posts[-1]["text"]
    content = daily.render_markdown("t-ana", "Ana Ruiz", TODAY.isoformat())
    assert "## To Review" in content


# ------------------------------------------------------------------ boundaries


async def test_help_and_greetings_get_capability_statement(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    for text in ("help", "Hi!", "hello", "What can you do?"):
        await send_dm(bot, text)
        reply = client.posts[-1]["text"]
        assert "absences, coverage, schedule changes" in reply
        assert "Ana Ruiz" in reply  # personal, names their daily file
    assert store.records_for_day(TODAY.isoformat()) == []  # no junk records


async def test_greeting_with_real_content_still_classifies(rig):
    bot, store = rig["bot"], rig["store"]
    await send_dm(bot, "Hi, I'm out tomorrow. Need coverage for 2nd period.")
    assert any(
        r.category == "absence" for r in store.records_for_day(TOMORROW)
    )


async def test_voice_clip_dm_gets_honest_answer(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await bot.on_envelope(
        "events_api",
        message_envelope("", channel="DU111", channel_type="im",
                         files=[{"mimetype": "audio/mp4"}]),
    )
    assert client.posts[-1]["text"] == MSG_VOICE_CLIP
    assert store.records_for_day(TODAY.isoformat()) == []


async def test_voice_clip_in_ops_channel_stays_silent(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await bot.on_envelope(
        "events_api",
        message_envelope("", channel=OPS_CHANNEL, channel_type="channel",
                         files=[{"mimetype": "audio/mp4"}]),
    )
    assert client.posts == []
    assert store.records_for_day(TODAY.isoformat()) == []


async def test_unmapped_user_cannot_claim_coverage(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await send_dm(bot, "I'm out today. Need coverage for 2nd period.")
    cov = coverage_records(store, TODAY.isoformat())[0]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_coverage_claim", cov.id, user="U999",
                        message_ts="1721990400.000001"),
    )
    assert store.get_record(cov.id).status == "open"  # still claimable
    assert client.updates == []  # card untouched
    assert client.posts[-1]["text"] == MSG_UNKNOWN_USER


async def test_unmapped_dm_user_gets_honest_reply_and_no_record(rig):
    bot, store, client, desktop = rig["bot"], rig["store"], rig["client"], rig["desktop"]
    await send_dm(bot, "I'm out tomorrow. Need coverage for 2nd period.", user="U999")
    assert store.records_for_day(TOMORROW) == []
    assert store.records_for_day(TODAY.isoformat()) == []
    assert client.posts[-1]["text"] == MSG_UNKNOWN_USER
    # Never a Desktop file named by a raw Slack id.
    assert not list(desktop.glob("Today - U999*.md")) if desktop.exists() else True


async def test_unmapped_ops_sender_broadcast_still_reaches_everyone(rig):
    bot, store, daily = rig["bot"], rig["store"], rig["daily"]
    await send_ops(bot, "Reminder: field trip forms are due.", user="U999")
    records = store.records_for_day(TODAY.isoformat())
    assert len(records) == 1 and records[0].teacher_id == ""
    content = daily.render_markdown("t-ana", "Ana Ruiz", TODAY.isoformat())
    assert "field trip forms" in content


async def test_unmapped_ops_sender_per_teacher_message_never_fabricates_file(rig):
    bot, store, desktop = rig["bot"], rig["store"], rig["desktop"]
    await send_ops(bot, "I'm out tomorrow. Need coverage for 2nd period.", user="U999")
    # Captured unattributed (audit surface), no absence/coverage flow under
    # a fabricated roster identity, no Desktop file named by a Slack id.
    for day in (TODAY.isoformat(), TOMORROW):
        for record in store.records_for_day(day):
            assert record.teacher_id == ""
    if desktop.exists():
        assert not list(desktop.glob("Today - U999*.md"))


async def test_other_channels_are_ignored(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await bot.on_envelope(
        "events_api",
        message_envelope("I'm out tomorrow.", channel="C0THER",
                         channel_type="channel"),
    )
    assert store.records_for_day(TOMORROW) == []
    assert client.posts == []


async def test_group_dm_mpim_is_not_treated_as_private_dm(rig):
    bot, store, client = rig["bot"], rig["store"], rig["client"]
    await bot.on_envelope(
        "events_api",
        message_envelope("I'm out tomorrow.", channel="G0GROUP",
                         channel_type="mpim"),
    )
    assert store.records_for_day(TOMORROW) == []
    assert client.posts == []


async def test_bot_and_subtype_messages_are_ignored(rig):
    bot, store = rig["bot"], rig["store"]
    await bot.on_envelope(
        "events_api",
        message_envelope("I'm out tomorrow.", channel=OPS_CHANNEL,
                         bot_id="B0BOT"),
    )
    await bot.on_envelope(
        "events_api",
        message_envelope("I'm out tomorrow.", channel=OPS_CHANNEL,
                         subtype="message_changed"),
    )
    assert store.records_for_day(TOMORROW) == []


async def test_malformed_envelopes_never_raise(rig):
    bot = rig["bot"]
    await bot.on_envelope("events_api", None)
    await bot.on_envelope("events_api", {})
    await bot.on_envelope("events_api", {"event": {"type": "message"}})
    await bot.on_envelope("interactive", {})
    await bot.on_envelope("interactive", {"type": "block_actions"})
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_coverage_claim", "nonexistent-id"),
    )
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_absence_cancel", "not json"),
    )
    await bot.on_envelope("slash_commands", {"command": "/whatever"})


# ------------------------------------------------------------------ briefings


async def test_morning_briefing_with_updates(rig):
    bot, client = rig["bot"], rig["client"]
    await send_ops(bot, "Assembly moved to 10:30 today.")
    await bot.send_morning_briefing("U111")
    assert client.dm_opens[-1] == "U111"
    brief = client.posts[-1]
    assert brief["channel"] == "DU111"
    assert "Good morning, Ana" in brief["text"]
    assert "1 update" in brief["text"]
    button_value(brief, "ops_brief_open")
    button_value(brief, "ops_brief_later")


async def test_morning_briefing_no_updates(rig):
    bot, client = rig["bot"], rig["client"]
    await bot.send_morning_briefing("U222")
    assert "Good morning, Ben. No updates" in client.posts[-1]["text"]


async def test_end_of_day_summary_counts_review(rig):
    bot, client = rig["bot"], rig["client"]
    await send_dm(bot, "hello there")  # 1 item, needs review
    await bot.send_end_of_day_summary("U111")
    text = client.posts[-1]["text"]
    assert "1 item captured today" in text
    assert "1 still needs review" in text
    button_value(client.posts[-1], "ops_eod_archive")


async def test_brief_open_posts_file_path(rig):
    bot, client, daily = rig["bot"], rig["client"], rig["daily"]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_brief_open", "", user="U111", channel="DU111"),
    )
    assert str(daily.daily_file_path("Ana Ruiz")) in client.posts[-1]["text"]


async def test_brief_later_schedules_resend(rig):
    bot, client, scheduled = rig["bot"], rig["client"], rig["scheduled"]
    await bot.on_envelope(
        "interactive",
        action_envelope("ops_brief_later", "", user="U111", channel="DU111"),
    )
    assert client.posts[-1]["text"] == MSG_REMIND_LATER
    assert len(scheduled) == 1
    assert scheduled[0][0] == 3600.0
    # The scheduled factory resends the briefing when invoked.
    await scheduled[0][1]()
    assert "Good morning, Ana" in client.posts[-1]["text"]


async def test_send_all_briefings_covers_every_teacher(rig):
    bot, client = rig["bot"], rig["client"]
    await bot.send_all_briefings("morning")
    assert set(client.dm_opens) == {"U111", "U222"}
    await bot.send_all_briefings("eod")
    assert len(client.posts) == 4


# ------------------------------------------------------------------ scheduler


async def test_run_schedules_fires_each_kind_once_per_day(rig):
    import datetime as dt

    bot, client = rig["bot"], rig["client"]
    times = iter(
        [
            dt.datetime(2026, 7, 28, 7, 0),    # before briefing — nothing
            dt.datetime(2026, 7, 28, 7, 31),   # morning fires
            dt.datetime(2026, 7, 28, 7, 32),   # already fired — nothing
            dt.datetime(2026, 7, 28, 16, 31),  # eod fires
            dt.datetime(2026, 7, 29, 7, 31),   # new day — morning fires again
        ]
    )
    fired: list[str] = []

    async def fake_send_all(kind):
        fired.append(kind)

    bot.send_all_briefings = fake_send_all

    async def stop_sleep(_seconds):
        try:
            stop_sleep.remaining -= 1
        except AttributeError:
            raise
        if stop_sleep.remaining <= 0:
            raise StopAsyncIteration

    stop_sleep.remaining = 5

    def fake_now():
        return next(times)

    with pytest.raises(StopAsyncIteration):
        await bot.run_schedules(sleep=stop_sleep, local_now=fake_now)

    assert fired == ["morning", "eod", "morning"]
