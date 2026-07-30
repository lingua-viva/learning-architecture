"""
Tests for Still I Rise /absence + coverage MVP.

Spec: dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md

Covers: /absence slash command opens modal, modal submission creates records,
private note not in public card, unrostered user rejected, coordinator
confirmation flow, partial claim, staffing summary endpoint, and existing
DM absence flow unchanged.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.education.daily_file import DailyFileEngine
from src.education import ops_packs
from src.education.ops_records import OpsRecordStore
from src.education.slack_ops_bot import (
    MSG_ABSENCE_MODAL_RECEIPT,
    MSG_COVERAGE_ALREADY,
    MSG_COVERAGE_CLAIMED_PENDING,
    MSG_COVERAGE_CONFIRMED,
    MSG_UNKNOWN_USER,
    SIR_ABSENCE_MODAL_CALLBACK_ID,
    SlackOpsBot,
)

OPS_CHANNEL = "C0PS"
TODAY = date(2026, 7, 30)
TEACHER_MAP = {
    "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
    "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
    "U333": {"teacher_id": "t-coordinator", "display_name": "Clara Diaz"},
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
        ts = f"1721990400.{self._counter:06d}"
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
        store=store,
        daily=daily,
        client=client,
        ops_channel=OPS_CHANNEL,
        teacher_map=TEACHER_MAP,
        today=lambda: TODAY,
        now=lambda: 1_000_000.0,
        rule_set=rule_set,
    )
    return bot, client, store


def _absence_modal_payload(user_id="U111", **overrides):
    """Build a view_submission payload for the absence modal."""
    vals = {
        "campus": {"campus": {"type": "plain_text_input", "value": "Nairobi"}},
        "date_for": {"date_for": {"type": "datepicker", "selected_date": "2026-07-30"}},
        "periods": {"periods": {"type": "static_select", "selected_option": {"value": "Full day"}}},
        "grade_class": {"grade_class": {"type": "plain_text_input", "value": "Grade 7"}},
        "subject": {"subject": {"type": "plain_text_input", "value": "Mathematics"}},
        "absence_type": {"absence_type": {"type": "static_select", "selected_option": {"value": "illness"}}},
        "coverage_needed": {"coverage_needed": {"type": "radio_buttons", "selected_option": {"value": "Yes"}}},
        "handover_link": {"handover_link": {"type": "plain_text_input", "value": ""}},
        "emergency_plan": {"emergency_plan": {"type": "radio_buttons", "selected_option": {"value": "Yes"}}},
        "contact_teacher": {"contact_teacher": {"type": "radio_buttons", "selected_option": {"value": "No"}}},
        "private_note": {"private_note": {"type": "plain_text_input", "value": ""}},
    }
    for k, v in overrides.items():
        if k in vals:
            # Update the inner action value
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
            "callback_id": SIR_ABSENCE_MODAL_CALLBACK_ID,
            "state": {"values": vals},
        },
    }


# --- 1. /absence slash command opens modal ---


@pytest.mark.asyncio
async def test_absence_command_opens_modal(rig):
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/absence", "trigger_id": "TRIG123"})
    assert len(client.views_opened) == 1
    view = client.views_opened[0]["view"]
    assert view["callback_id"] == SIR_ABSENCE_MODAL_CALLBACK_ID
    assert view["type"] == "modal"
    block_ids = [b.get("block_id") for b in view["blocks"]]
    assert "campus" in block_ids
    assert "date_for" in block_ids
    assert "absence_type" in block_ids
    assert "coverage_needed" in block_ids
    assert "private_note" in block_ids


@pytest.mark.asyncio
async def test_unknown_slash_command_is_ignored(rig):
    bot, client, store = rig
    await bot.on_envelope("slash_commands", {"command": "/unknown"})
    assert len(client.views_opened) == 0
    assert len(client.posts) == 0


# --- 2. Modal submission creates records ---


@pytest.mark.asyncio
async def test_modal_submission_creates_absence_record(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="No")
    await bot.on_envelope("interactive", payload)
    records = store.records_for_day("2026-07-30", teacher_id="t-ana")
    absences = [r for r in records if r.category == "absence"]
    assert len(absences) == 1
    assert absences[0].extra["campus"] == "Nairobi"
    assert absences[0].extra["absence_type"] == "illness"


@pytest.mark.asyncio
async def test_modal_submission_with_coverage_creates_both_records(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    records = store.records_for_day("2026-07-30", teacher_id="t-ana")
    absences = [r for r in records if r.category == "absence"]
    coverage = [r for r in records if r.category == "coverage_request"]
    assert len(absences) == 1
    assert len(coverage) == 1
    assert coverage[0].status == "open"


@pytest.mark.asyncio
async def test_modal_submission_posts_coverage_card(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    ops_posts = [p for p in client.posts if p["channel"] == OPS_CHANNEL]
    assert len(ops_posts) == 1
    assert "Coverage needed" in ops_posts[0]["text"]
    # Card should have Claim all + Claim part buttons
    blocks = ops_posts[0].get("blocks") or []
    actions_block = [b for b in blocks if b.get("type") == "actions"]
    assert actions_block
    elements = actions_block[0].get("elements", [])
    action_ids = [e.get("action_id") for e in elements]
    assert "ops_coverage_claim" in action_ids
    assert "ops_coverage_claim_part" in action_ids


@pytest.mark.asyncio
async def test_modal_submission_dms_receipt(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    dm_posts = [p for p in client.posts if p["channel"].startswith("D")]
    assert any("recorded" in p["text"] for p in dm_posts)


# --- 3. Private note not in public messages ---


@pytest.mark.asyncio
async def test_private_note_not_in_public_coverage_card(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(
        coverage_needed="Yes",
        private_note="I have a medical appointment — doctor's note to follow",
    )
    await bot.on_envelope("interactive", payload)
    ops_posts = [p for p in client.posts if p["channel"] == OPS_CHANNEL]
    for post in ops_posts:
        assert "medical" not in post["text"].lower()
        assert "doctor" not in post["text"].lower()
    # But it IS stored in the record extra
    records = store.records_for_day("2026-07-30", teacher_id="t-ana")
    absences = [r for r in records if r.category == "absence"]
    assert absences[0].extra.get("private_note_present") is True
    assert absences[0].extra.get("private_note") == "I have a medical appointment — doctor's note to follow"


# --- 4. Unrostered user rejected ---


@pytest.mark.asyncio
async def test_unrostered_user_gets_rejection(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(user_id="U999")
    await bot.on_envelope("interactive", payload)
    records = store.records_for_day("2026-07-30")
    assert len(records) == 0
    dm_posts = [p for p in client.posts if p["channel"].startswith("D")]
    assert any(MSG_UNKNOWN_USER in p["text"] for p in dm_posts)


# --- 5. Coverage claim stays claimed until coordinator confirms ---


@pytest.mark.asyncio
async def test_claim_stays_claimed_pending_coordinator(rig):
    bot, client, store = rig
    # Create a coverage request
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    coverage = [r for r in store.records_for_day("2026-07-30") if r.category == "coverage_request"]
    assert len(coverage) == 1
    record_id = coverage[0].id
    card_ts = coverage[0].extra.get("card_ts", "")

    # Claim via the coordinator-confirmed path
    await bot._claim_coverage_with_confirmation(
        record_id, claimer="Ben Ali", claimer_user_id="U222",
        card_channel=OPS_CHANNEL, card_ts=card_ts,
    )
    record = store.get_record(record_id)
    assert record.status == "claimed"
    assert record.extra.get("coordinator_pending") is True
    # Card should be updated to show pending
    assert any("Awaiting coordinator" in u["text"] for u in client.updates)


# --- 6. Confirm action moves claimed -> confirmed ---


@pytest.mark.asyncio
async def test_coordinator_confirm_moves_to_confirmed(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    coverage = [r for r in store.records_for_day("2026-07-30") if r.category == "coverage_request"]
    record_id = coverage[0].id
    card_ts = coverage[0].extra.get("card_ts", "")

    await bot._claim_coverage_with_confirmation(
        record_id, claimer="Ben Ali", claimer_user_id="U222",
        card_channel=OPS_CHANNEL, card_ts=card_ts,
    )
    # Coordinator confirms
    await bot._confirm_coverage(
        record_id, confirmed_by="Clara Diaz",
        card_channel=OPS_CHANNEL, card_ts=card_ts,
    )
    record = store.get_record(record_id)
    assert record.status == "confirmed"
    assert record.extra.get("coordinator_confirmed_by") == "Clara Diaz"
    assert record.extra.get("coordinator_pending") is False


# --- 7. Double-claim / stale buttons degrade ---


@pytest.mark.asyncio
async def test_double_claim_is_rejected(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    coverage = [r for r in store.records_for_day("2026-07-30") if r.category == "coverage_request"]
    record_id = coverage[0].id

    # First claim (v1 auto-confirm)
    await bot._claim_coverage(
        record_id, claimer="Ben Ali", card_channel=OPS_CHANNEL, card_ts="ts1"
    )
    # Second claim
    await bot._claim_coverage(
        record_id, claimer="Clara Diaz", card_channel=OPS_CHANNEL, card_ts="ts1"
    )
    assert any(MSG_COVERAGE_ALREADY in p["text"] for p in client.posts)


# --- 8. Staffing summary endpoint ---


def test_staffing_summary_reports_correct_counts(env):
    store, tmp_path = env
    from fastapi.testclient import TestClient
    from src.web import app
    client = TestClient(app)

    # Create some records
    store.add_record(
        category="absence", teacher_id="t-ana", date_for="2026-07-30",
        text_raw="out", text_clean="out",
    )
    store.add_record(
        category="absence", teacher_id="t-ben", date_for="2026-07-30",
        text_raw="out", text_clean="out",
    )
    cov = store.add_record(
        category="coverage_request", teacher_id="t-ana", date_for="2026-07-30",
        text_raw="cover", text_clean="cover",
    )
    store.update_status(cov.id, "claimed", claim_by="Ben Ali")
    store.update_status(cov.id, "confirmed")

    cov2 = store.add_record(
        category="coverage_request", teacher_id="t-ben", date_for="2026-07-30",
        text_raw="cover", text_clean="cover",
    )
    # cov2 stays open

    resp = client.get("/api/ops/staffing-summary?date=2026-07-30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reported_absences"] == 2
    assert data["coverage_requests"] == 2
    assert data["fully_covered"] == 1
    assert data["awaiting_coverage"] == 1
    assert data["claimed_awaiting_confirmation"] == 0
    assert data["critical_unfilled"] == 1


# --- 9. Coordinator rejection reverts to open ---


@pytest.mark.asyncio
async def test_coordinator_reject_reverts_to_open(rig):
    bot, client, store = rig
    payload = _absence_modal_payload(coverage_needed="Yes")
    await bot.on_envelope("interactive", payload)
    coverage = [r for r in store.records_for_day("2026-07-30") if r.category == "coverage_request"]
    record_id = coverage[0].id
    card_ts = coverage[0].extra.get("card_ts", "")

    await bot._claim_coverage_with_confirmation(
        record_id, claimer="Ben Ali", claimer_user_id="U222",
        card_channel=OPS_CHANNEL, card_ts=card_ts,
    )
    assert store.get_record(record_id).status == "claimed"

    await bot._reject_coverage_claim(record_id, card_channel=OPS_CHANNEL, card_ts=card_ts)
    record = store.get_record(record_id)
    assert record.status == "open"
    assert record.extra.get("coordinator_pending") is False


# --- 10. Existing DM absence flow still works ---


@pytest.mark.asyncio
async def test_existing_dm_absence_flow_unchanged(rig):
    bot, client, store = rig
    event = {
        "type": "message",
        "text": "I'm out tomorrow",
        "channel": "DU111",
        "user": "U111",
        "ts": "1721990400.001",
        "channel_type": "im",
    }
    await bot.on_envelope("events_api", {"event": event})
    # TODAY is 2026-07-30, so "tomorrow" = 2026-07-31
    records = store.records_for_day("2026-07-31", teacher_id="t-ana")
    # The DM flow should still create records
    assert len(records) >= 1
