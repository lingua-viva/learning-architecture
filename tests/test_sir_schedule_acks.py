"""
Tests for Still I Rise Schedule Change Acknowledgements (Phase 2B).

Spec: dev/SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30.md
"""

from __future__ import annotations

from datetime import date

import pytest

from src.education import ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_records import OpsRecordStore
from src.education.slack_ops_bot import (
    MSG_SCHEDULE_CONFLICT,
    MSG_SCHEDULE_INVALID_ACK,
    MSG_SCHEDULE_NOT_TARGETED,
    MSG_SCHEDULE_SEEN,
    MSG_UNKNOWN_USER,
    SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID,
    SlackOpsBot,
)

OPS_CHANNEL = "C0PS"
TODAY = date(2026, 7, 30)

TEACHER_MAP = {
    "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
    "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
    "U333": {"teacher_id": "t-clara", "display_name": "Clara Diaz"},
}


class FakeClient:
    def __init__(self):
        self.posts: list[dict] = []
        self.updates: list[dict] = []
        self.dm_opens: list[str] = []
        self.views_opened: list[dict] = []
        self._counter = 0

    async def post_message(self, channel, text, blocks=None, thread_ts=None):
        self._counter += 1
        ts = f"1722100000.{self._counter:06d}"
        self.posts.append({"channel": channel, "text": text, "blocks": blocks, "thread_ts": thread_ts, "ts": ts})
        return {"ok": True, "ts": ts, "channel": channel}

    async def update_message(self, channel, ts, text, blocks=None):
        self.updates.append({"channel": channel, "ts": ts, "text": text, "blocks": blocks})
        return {"ok": True, "ts": ts}

    async def open_dm(self, user_id):
        self.dm_opens.append(user_id)
        return f"D{user_id}"

    async def open_view(self, trigger_id, view):
        self.views_opened.append({"trigger_id": trigger_id, "view": view})
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops_records.db"))
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(tmp_path / "desktop"))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(tmp_path / "ops_state.json"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy_events.ndjson"))
    store = OpsRecordStore()
    yield store, tmp_path
    store.close()


@pytest.fixture
def rig(env):
    store, tmp_path = env
    client = FakeClient()
    rule_set = ops_packs.default_rule_set()
    daily = DailyFileEngine(store, teacher_map=TEACHER_MAP, rule_set=rule_set)
    bot = SlackOpsBot(
        store=store, daily=daily, client=client,
        ops_channel=OPS_CHANNEL, teacher_map=TEACHER_MAP,
        today=lambda: TODAY, now=lambda: 1_000_000.0,
        rule_set=rule_set,
    )
    return bot, client, store


def _schedule_payload(user_id="U111", ack_required="Yes", affected_staff="", **overrides):
    vals = {
        "campus": {"campus": {"type": "plain_text_input", "value": "Nairobi"}},
        "affected_scope": {"affected_scope": {"type": "static_select", "selected_option": {"value": "whole_campus"}}},
        "affected_staff": {"affected_staff": {"type": "plain_text_input", "value": affected_staff}},
        "effective_date": {"effective_date": {"type": "datepicker", "selected_date": "2026-07-31"}},
        "changed_item": {"changed_item": {"type": "plain_text_input", "value": "Assembly"}},
        "old_time": {"old_time": {"type": "plain_text_input", "value": "09:00"}},
        "new_time": {"new_time": {"type": "plain_text_input", "value": "10:30"}},
        "description": {"description": {"type": "plain_text_input", "value": "Moved for staff meeting"}},
        "ack_required": {"ack_required": {"type": "radio_buttons", "selected_option": {"value": ack_required}}},
    }
    for k, v in overrides.items():
        if k in vals:
            inner_key = list(vals[k].keys())[0]
            if vals[k][inner_key]["type"] == "plain_text_input":
                vals[k][inner_key]["value"] = v
            elif vals[k][inner_key]["type"] in ("static_select", "radio_buttons"):
                vals[k][inner_key]["selected_option"] = {"value": v}
            elif vals[k][inner_key]["type"] == "datepicker":
                vals[k][inner_key]["selected_date"] = v
    return {
        "type": "view_submission",
        "user": {"id": user_id},
        "view": {
            "callback_id": SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID,
            "state": {"values": vals},
        },
    }


async def _submit_schedule(bot, **kwargs):
    await bot.on_envelope("interactive", _schedule_payload(**kwargs))


# --- 1. /schedule-change opens modal ---

@pytest.mark.asyncio
async def test_schedule_change_opens_modal(rig):
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/schedule-change", "trigger_id": "T1"})
    assert len(client.views_opened) == 1
    view = client.views_opened[0]["view"]
    assert view["callback_id"] == SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID
    block_ids = [b.get("block_id") for b in view["blocks"]]
    assert "campus" in block_ids
    assert "changed_item" in block_ids
    assert "ack_required" in block_ids


# --- 2. Modal creates schedule_change record ---

@pytest.mark.asyncio
async def test_modal_creates_schedule_record(rig):
    bot, client, store = rig
    await _submit_schedule(bot)
    records = store.records_for_day("2026-07-31")
    sched = [r for r in records if r.category == "schedule_change"]
    assert len(sched) == 1
    assert sched[0].extra.get("workflow") == "sir_schedule_ack"
    assert sched[0].extra.get("changed_item") == "Assembly"
    assert sched[0].extra.get("new_time") == "10:30"
    assert sched[0].extra.get("ack_required") is True


# --- 3. Blank affected staff targets all teachers ---

@pytest.mark.asyncio
async def test_blank_affected_targets_all(rig):
    bot, client, store = rig
    await _submit_schedule(bot, affected_staff="")
    records = store.records_for_day("2026-07-31")
    sched = [r for r in records if r.category == "schedule_change"][0]
    assert set(sched.extra["affected_slack_ids"]) == {"U111", "U222", "U333"}


# --- 4. Explicit affected staff targets only those ---

@pytest.mark.asyncio
async def test_explicit_affected_targets_subset(rig):
    bot, client, store = rig
    await _submit_schedule(bot, affected_staff="U222, Ana")
    records = store.records_for_day("2026-07-31")
    sched = [r for r in records if r.category == "schedule_change"][0]
    assert set(sched.extra["affected_slack_ids"]) == {"U111", "U222"}


@pytest.mark.asyncio
async def test_affected_staff_dedupes_and_tracks_unmatched_targets(rig):
    bot, client, store = rig
    await _submit_schedule(bot, affected_staff="U222, Ben, Missing Person")
    records = store.records_for_day("2026-07-31")
    sched = [r for r in records if r.category == "schedule_change"][0]
    assert sched.extra["affected_slack_ids"] == ["U222"]
    assert sched.extra["unmatched_targets"] == ["Missing Person"]


# --- 5. Ack required DMs all targets ---

@pytest.mark.asyncio
async def test_ack_required_dms_targets(rig):
    bot, client, store = rig
    await _submit_schedule(bot, ack_required="Yes")
    # Should DM all 3 teachers + the submitter receipt = at least 4 DMs
    dm_channels = [p["channel"] for p in client.posts if p["channel"].startswith("D")]
    assert len(dm_channels) >= 4
    # Each target gets ack buttons
    ack_posts = [p for p in client.posts if p.get("blocks") and any(
        "ops_schedule_seen" in str(b) for b in (p.get("blocks") or [])
    )]
    assert len(ack_posts) == 3  # one per teacher


# --- 6. Seen button records status ---

@pytest.mark.asyncio
async def test_seen_records_status(rig):
    bot, client, store = rig
    await _submit_schedule(bot)
    records = store.records_for_day("2026-07-31")
    record_id = [r for r in records if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U222", "seen", OPS_CHANNEL)
    record = store.get_record(record_id)
    acks = record.extra.get("acknowledgements", {})
    assert "U222" in acks
    assert acks["U222"]["status"] == "seen"
    assert any(MSG_SCHEDULE_SEEN in p["text"] for p in client.posts)


# --- 7. Conflict marks review-needed ---

@pytest.mark.asyncio
async def test_conflict_marks_review_needed(rig):
    bot, client, store = rig
    await _submit_schedule(bot)
    records = store.records_for_day("2026-07-31")
    record_id = [r for r in records if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U222", "conflict", OPS_CHANNEL)
    record = store.get_record(record_id)
    assert record.extra["acknowledgements"]["U222"]["status"] == "conflict"
    assert record.needs_review is True
    assert "schedule ack: conflict from Ben Ali" in record.review_reason


# --- 8. Need clarification marks review-needed ---

@pytest.mark.asyncio
async def test_clarification_marks_review_needed(rig):
    bot, client, store = rig
    await _submit_schedule(bot)
    records = store.records_for_day("2026-07-31")
    record_id = [r for r in records if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U333", "need_clarification", OPS_CHANNEL)
    record = store.get_record(record_id)
    assert record.extra["acknowledgements"]["U333"]["status"] == "need_clarification"
    assert record.needs_review is True


# --- 9. Unaffected user cannot acknowledge ---

@pytest.mark.asyncio
async def test_unaffected_user_cannot_ack(rig):
    bot, client, store = rig
    await _submit_schedule(bot, affected_staff="U111")  # only U111 affected
    records = store.records_for_day("2026-07-31")
    record_id = [r for r in records if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U222", "seen", OPS_CHANNEL)
    record = store.get_record(record_id)
    assert "U222" not in record.extra.get("acknowledgements", {})
    assert any(MSG_SCHEDULE_NOT_TARGETED in p["text"] for p in client.posts)


@pytest.mark.asyncio
async def test_unrostered_user_cannot_ack_even_if_stale_record_targets_them(rig):
    bot, client, store = rig
    record = store.add_record(
        category="schedule_change", teacher_id="t-ana", date_for="2026-07-31",
        text_raw="sched", text_clean="sched",
        extra={
            "workflow": "sir_schedule_ack",
            "ack_required": True,
            "affected_slack_ids": ["U999"],
            "acknowledgements": {},
        },
    )

    await bot._handle_schedule_ack(record.id, "U999", "seen", OPS_CHANNEL)
    updated = store.get_record(record.id)
    assert updated.extra.get("acknowledgements") == {}
    assert any(MSG_UNKNOWN_USER in p["text"] for p in client.posts)


@pytest.mark.asyncio
async def test_invalid_schedule_ack_status_is_rejected(rig):
    bot, client, store = rig
    await _submit_schedule(bot, affected_staff="U111")
    record_id = [r for r in store.records_for_day("2026-07-31") if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U111", "approved", OPS_CHANNEL)
    record = store.get_record(record_id)
    assert record.extra.get("acknowledgements") == {}
    assert any(MSG_SCHEDULE_INVALID_ACK in p["text"] for p in client.posts)


# --- 10. Ops card updates after ack ---

@pytest.mark.asyncio
async def test_ops_card_updates_after_ack(rig):
    bot, client, store = rig
    await _submit_schedule(bot)
    records = store.records_for_day("2026-07-31")
    record_id = [r for r in records if r.category == "schedule_change"][0].id

    await bot._handle_schedule_ack(record_id, "U111", "seen", OPS_CHANNEL)
    assert any("Acknowledged: 1/3" in u["text"] for u in client.updates)


# --- 11. Natural-language schedule change still works ---

@pytest.mark.asyncio
async def test_natural_language_schedule_capture(rig):
    bot, client, store = rig
    event = {
        "type": "message",
        "text": "Assembly moved to 10:30 today.",
        "channel": OPS_CHANNEL,
        "user": "U111",
        "ts": "1722100000.001",
    }
    await bot.on_envelope("events_api", {"event": event})
    records = store.records_for_day("2026-07-30")
    sched = [r for r in records if r.category == "schedule_change"]
    assert len(sched) >= 1


# --- 12. Summary endpoint ---

def test_schedule_ack_summary_endpoint(env):
    store, tmp_path = env
    from fastapi.testclient import TestClient
    from src.web import app
    client = TestClient(app)

    r = store.add_record(
        category="schedule_change", teacher_id="t-ana", date_for="2026-07-31",
        text_raw="sched", text_clean="sched",
        extra={
            "workflow": "sir_schedule_ack",
            "campus": "Nairobi",
            "changed_item": "Assembly",
            "ack_required": True,
            "affected_slack_ids": ["U111", "U222", "U333"],
            "acknowledgements": {
                "U111": {"status": "seen", "display_name": "Ana", "at": "2026-07-30T19:00:00Z"},
                "U222": {"status": "conflict", "display_name": "Ben", "at": "2026-07-30T19:05:00Z"},
            },
        },
    )

    resp = client.get("/api/ops/schedule-ack-summary?date=2026-07-31")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedule_changes"] == 1
    assert data["ack_required"] == 1
    assert data["conflicts"] == 1
    assert data["missing_acknowledgement"] == 1
    assert len(data["changes"]) == 1
    change = data["changes"][0]
    assert change["target_count"] == 3
    assert change["seen_count"] == 1
    assert change["conflict_count"] == 1
    assert change["missing_count"] == 1


def test_schedule_ack_summary_ignores_stale_or_invalid_ack_entries(env):
    store, tmp_path = env
    from fastapi.testclient import TestClient
    from src.web import app
    client = TestClient(app)

    store.add_record(
        category="schedule_change", teacher_id="t-ana", date_for="2026-07-31",
        text_raw="sched", text_clean="sched",
        extra={
            "workflow": "sir_schedule_ack",
            "campus": "Nairobi",
            "changed_item": "Assembly",
            "ack_required": True,
            "affected_slack_ids": ["U111", "U222"],
            "acknowledgements": {
                "U111": {"status": "seen", "display_name": "Ana", "at": "2026-07-30T19:00:00Z"},
                "U222": {"status": "approved", "display_name": "Ben", "at": "2026-07-30T19:01:00Z"},
                "U999": {"status": "conflict", "display_name": "Ghost", "at": "2026-07-30T19:02:00Z"},
            },
        },
    )

    resp = client.get("/api/ops/schedule-ack-summary?date=2026-07-31")
    assert resp.status_code == 200
    change = resp.json()["changes"][0]
    assert change["target_count"] == 2
    assert change["seen_count"] == 1
    assert change["conflict_count"] == 0
    assert change["missing_count"] == 1
