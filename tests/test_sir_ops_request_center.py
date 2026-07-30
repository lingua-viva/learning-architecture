"""
Tests for Still I Rise Operational Request Center (Phase 2A).

Spec: dev/SPEC_LV_SIR_SLACK_OPS_REQUEST_CENTER_2026-07-30.md
"""

from __future__ import annotations

from datetime import date

import pytest

from src.education import ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_records import OpsRecordStore
from src.education.slack_ops_bot import (
    MSG_OPS_REQUEST_CLAIMED,
    MSG_OPS_REQUEST_NOT_REQUESTER,
    MSG_UNKNOWN_USER,
    SIR_OPS_REQUEST_MODAL_CALLBACK_ID,
    SlackOpsBot,
)

OPS_CHANNEL = "C0PS"
TODAY = date(2026, 7, 30)

TEACHER_MAP = {
    "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
    "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
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
        ts = f"1722000000.{self._counter:06d}"
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


def _ops_request_payload(user_id="U111", **overrides):
    vals = {
        "request_type": {"request_type": {"type": "static_select", "selected_option": {"value": "facilities"}}},
        "campus": {"campus": {"type": "plain_text_input", "value": "Nairobi"}},
        "location": {"location": {"type": "plain_text_input", "value": "Room 12"}},
        "severity": {"severity": {"type": "static_select", "selected_option": {"value": "teaching_blocked"}}},
        "description": {"description": {"type": "plain_text_input", "value": "Projector not working"}},
        "teaching_blocked": {"teaching_blocked": {"type": "radio_buttons", "selected_option": {"value": "Yes"}}},
        "photo_link": {"photo_link": {"type": "plain_text_input", "value": ""}},
        "followup_pref": {"followup_pref": {"type": "static_select", "selected_option": {"value": "DM"}}},
    }
    for k, v in overrides.items():
        if k in vals:
            inner_key = list(vals[k].keys())[0]
            if vals[k][inner_key]["type"] == "plain_text_input":
                vals[k][inner_key]["value"] = v
            elif vals[k][inner_key]["type"] in ("static_select", "radio_buttons"):
                vals[k][inner_key]["selected_option"] = {"value": v}
    return {
        "type": "view_submission",
        "user": {"id": user_id},
        "view": {
            "callback_id": SIR_OPS_REQUEST_MODAL_CALLBACK_ID,
            "state": {"values": vals},
        },
    }


# --- 1. /ops-request opens modal ---

@pytest.mark.asyncio
async def test_ops_request_command_opens_modal(rig):
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/ops-request", "trigger_id": "TRIG456"})
    assert len(client.views_opened) == 1
    view = client.views_opened[0]["view"]
    assert view["callback_id"] == SIR_OPS_REQUEST_MODAL_CALLBACK_ID
    block_ids = [b.get("block_id") for b in view["blocks"]]
    assert "request_type" in block_ids
    assert "campus" in block_ids
    assert "severity" in block_ids
    assert "description" in block_ids


# --- 2. Unknown slash commands ignored ---

@pytest.mark.asyncio
async def test_unknown_slash_command_still_ignored(rig):
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/something-else"})
    assert len(client.views_opened) == 0


# --- 3. Modal submit creates facilities record with extra ---

@pytest.mark.asyncio
async def test_modal_creates_facilities_record(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = store.records_for_day("2026-07-30", teacher_id="t-ana")
    facilities = [r for r in records if r.category == "facilities"]
    assert len(facilities) == 1
    assert facilities[0].extra.get("workflow") == "sir_ops_request"
    assert facilities[0].extra.get("request_type") == "facilities"
    assert facilities[0].extra.get("campus") == "Nairobi"
    assert facilities[0].extra.get("location") == "Room 12"
    assert facilities[0].extra.get("severity") == "teaching_blocked"
    assert facilities[0].extra.get("description") == "Projector not working"
    assert facilities[0].extra.get("followup_pref") == "DM"
    assert facilities[0].extra.get("teaching_blocked") is True


# --- 4. Public card contains operational facts only ---

@pytest.mark.asyncio
async def test_triage_card_has_operational_facts(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    ops_posts = [p for p in client.posts if p["channel"] == OPS_CHANNEL]
    assert len(ops_posts) == 1
    text = ops_posts[0]["text"]
    assert "facilities" in text
    assert "Nairobi" in text
    assert "Room 12" in text


# --- 5. Unrostered submitter rejected ---

@pytest.mark.asyncio
async def test_unrostered_ops_request_rejected(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload(user_id="U999"))
    records = store.records_for_day("2026-07-30")
    facilities = [r for r in records if r.category == "facilities"]
    assert len(facilities) == 0
    dm_posts = [p for p in client.posts if p["channel"].startswith("D")]
    assert any(MSG_UNKNOWN_USER in p["text"] for p in dm_posts)


# --- 6. Claim records owner and updates card ---

@pytest.mark.asyncio
async def test_claim_records_owner_and_updates_card(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    record_id = records[0].id
    card_ts = records[0].extra.get("card_ts", "")

    await bot._claim_ops_request(
        record_id, claimer="Ben Ali", claimer_user_id="U222",
        card_channel=OPS_CHANNEL, card_ts=card_ts,
    )
    record = store.get_record(record_id)
    assert record.extra.get("owner_name") == "Ben Ali"
    assert record.extra.get("owner_slack_id") == "U222"
    assert any("Claimed by Ben Ali" in u["text"] for u in client.updates)


# --- 7. Unrostered claimer rejected ---

@pytest.mark.asyncio
async def test_unrostered_claimer_rejected(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    record_id = records[0].id

    # Dispatch via block_actions with unrostered user
    action_payload = {
        "type": "block_actions",
        "user": {"id": "U999"},
        "channel": {"id": OPS_CHANNEL},
        "container": {"message_ts": "ts1"},
        "actions": [{"action_id": "ops_request_claim", "value": record_id}],
    }
    await bot.on_envelope("interactive", action_payload)
    record = store.get_record(record_id)
    assert not record.extra.get("owner_slack_id")


# --- 8. Resolve moves to resolved ---

@pytest.mark.asyncio
async def test_resolve_moves_to_resolved(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    record_id = records[0].id

    await bot._resolve_ops_request(
        record_id, resolved_by="Ben Ali",
        card_channel=OPS_CHANNEL, card_ts="ts1",
    )
    record = store.get_record(record_id)
    assert record.status == "resolved"
    assert record.extra.get("resolved_by") == "Ben Ali"


@pytest.mark.asyncio
async def test_unrostered_resolver_rejected(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    record_id = records[0].id

    action_payload = {
        "type": "block_actions",
        "user": {"id": "U999"},
        "channel": {"id": OPS_CHANNEL},
        "container": {"message_ts": "ts1"},
        "actions": [{"action_id": "ops_request_resolve", "value": record_id}],
    }
    await bot.on_envelope("interactive", action_payload)

    record = store.get_record(record_id)
    assert record.status != "resolved"
    assert not record.extra.get("resolved_by")
    assert any(MSG_UNKNOWN_USER in p["text"] for p in client.posts)


# --- 9. Still blocked creates linked follow-up ---

@pytest.mark.asyncio
async def test_still_blocked_creates_followup(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    original_id = records[0].id

    # Resolve first
    await bot._resolve_ops_request(
        original_id, resolved_by="Ben Ali",
        card_channel=OPS_CHANNEL, card_ts="ts1",
    )
    # Reopen
    await bot._reopen_ops_request(original_id, reporter_user_id="U111", card_channel=OPS_CHANNEL)

    all_records = store.records_for_day("2026-07-30")
    facilities = [r for r in all_records if r.category == "facilities"]
    followups = [r for r in facilities if r.extra.get("reopened_from") == original_id]
    assert len(followups) == 1
    assert followups[0].needs_review is True
    assert followups[0].extra.get("workflow") == "sir_ops_request"


@pytest.mark.asyncio
async def test_only_requester_can_reopen_ops_request(rig):
    bot, client, store = rig
    await bot.on_envelope("interactive", _ops_request_payload())
    records = [r for r in store.records_for_day("2026-07-30") if r.category == "facilities"]
    record_id = records[0].id
    await bot._resolve_ops_request(
        record_id, resolved_by="Ben Ali",
        card_channel=OPS_CHANNEL, card_ts="ts1",
    )

    action_payload = {
        "type": "block_actions",
        "user": {"id": "U222"},
        "channel": {"id": OPS_CHANNEL},
        "container": {"message_ts": "ts2"},
        "actions": [{"action_id": "ops_request_still_blocked", "value": record_id}],
    }
    await bot.on_envelope("interactive", action_payload)

    all_records = store.records_for_day("2026-07-30")
    followups = [r for r in all_records if r.extra.get("reopened_from") == record_id]
    assert followups == []
    assert any(MSG_OPS_REQUEST_NOT_REQUESTER in p["text"] for p in client.posts)


@pytest.mark.asyncio
async def test_schedule_change_command_opens_modal(rig):
    """Phase 2B built the schedule-change workflow — /schedule-change now opens a modal."""
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/schedule-change", "trigger_id": "TRIG789"})
    assert len(client.views_opened) == 1
    assert client.views_opened[0]["view"]["callback_id"] == "sir_schedule_change_modal"


# --- 10. Natural-language facilities capture still works ---

@pytest.mark.asyncio
async def test_natural_language_facilities_capture(rig):
    bot, client, store = rig
    event = {
        "type": "message",
        "text": "The projector in room 12 isn't working.",
        "channel": "DU111",
        "user": "U111",
        "ts": "1722000000.001",
        "channel_type": "im",
    }
    await bot.on_envelope("events_api", {"event": event})
    records = store.records_for_day("2026-07-30", teacher_id="t-ana")
    facilities = [r for r in records if r.category == "facilities"]
    assert len(facilities) >= 1


# --- 11. Request summary endpoint ---

def test_request_summary_counts(env):
    store, tmp_path = env
    from fastapi.testclient import TestClient
    from src.web import app
    client = TestClient(app)

    r1 = store.add_record(
        category="facilities", teacher_id="t-ana", date_for="2026-07-30",
        text_raw="ops", text_clean="ops",
        extra={"workflow": "sir_ops_request", "request_type": "facilities", "severity": "teaching_blocked"},
    )
    store.update_status(r1.id, "resolved")

    store.add_record(
        category="facilities", teacher_id="t-ben", date_for="2026-07-30",
        text_raw="ops", text_clean="ops",
        extra={"workflow": "sir_ops_request", "request_type": "it", "severity": "routine"},
    )

    store.add_record(
        category="facilities", teacher_id="t-ana", date_for="2026-07-30",
        text_raw="ops", text_clean="ops",
        extra={"workflow": "sir_ops_request", "request_type": "supplies", "severity": "same_day",
               "reopened_from": r1.id},
    )

    resp = client.get("/api/ops/request-summary?date=2026-07-30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 3
    assert data["by_type"] == {"facilities": 1, "it": 1, "supplies": 1}
    assert data["teaching_blocked"] == 1
    assert data["routine"] == 1
    assert data["same_day"] == 1
    assert data["resolved"] == 1
    assert data["reopened"] == 1
    assert data["unassigned"] == 2
