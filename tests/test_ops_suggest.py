"""
Phase 6 stretch tests: backlog packs + shadow suggester (spec §5 packs
6-7, §8).

Backlog packs prove the pack promise: a new pack is vocabulary + section
DATA only — no flow code changed anywhere. Neither pack is in the
v1-parity compile; the golden ops suite never sees them.

Shadow suggester: weekly would-have-matched counts of unmatched traffic
(`other` from DMs, positional `announcement` from the ops channel)
against DISABLED packs' vocabularies. Suggestion only; payload carries
counts and pack names, never record text.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.education import ops_bot_spec, ops_corpus, ops_packs, ops_suggest
from src.education.ops_bot_spec import default_bot_spec_data, install_compiled_spec
from src.education.ops_classifier import classify_ops_message
from src.education.ops_records import OpsRecordStore

client = TestClient(web.app)

TODAY = date(2026, 7, 28)  # a Tuesday


@pytest.fixture(autouse=True)
def _seams(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_OPS_BOT_SPEC_PATH", str(tmp_path / "bot_spec.yaml"))
    yield tmp_path / "bot_spec.yaml"
    install_compiled_spec(None)


# ------------------------------------------------------------- backlog packs


def test_backlog_packs_ship_but_stay_out_of_parity_compile():
    packs = ops_packs.load_packs()
    for pack_id in ("bus_transport", "dismissal_changes"):
        assert pack_id in packs
        assert packs[pack_id].enabled_by_default is False
        assert packs[pack_id].default_for_new_schools is False
        # Vocabulary/section only — no capability, no flow code (spec §5).
        assert all(entry.capability is None for entry in packs[pack_id].categories)
    assert "bus_transport" not in ops_packs.default_rule_set().enabled_pack_ids
    # Parity routing untouched: a bus message stays positional/other.
    assert (
        classify_ops_message(
            "Bus 7 is running about 15 minutes late.",
            today=TODAY,
            rule_set=ops_packs.default_rule_set(),
        ).category
        == "other"
    )


def test_enabled_backlog_packs_route_and_pass_corpus():
    data = default_bot_spec_data()
    data["packs"]["enabled"] = sorted(
        set(data["packs"]["enabled"]) | {"bus_transport", "dismissal_changes"}
    )
    spec = ops_bot_spec._compile_from_data(data)
    assert (
        classify_ops_message(
            "Bus 7 is running about 15 minutes late.",
            today=TODAY,
            rule_set=spec.rule_set,
        ).category
        == "bus_transport"
    )
    assert (
        classify_ops_message(
            "Marco goes home with his grandmother today.",
            today=TODAY,
            rule_set=spec.rule_set,
        ).category
        == "dismissal_change"
    )
    # Launch-pack triggers still win their priority slots.
    assert (
        classify_ops_message(
            "Dismissal moved to 2:30.", today=TODAY, rule_set=spec.rule_set
        ).category
        == "schedule_change"
    )
    result = ops_corpus.run_corpus(spec, today=TODAY)
    assert result.total == 23  # 17 launch + 3 bus + 3 dismissal
    assert result.passed, [r.mismatches for r in result.rows if not r.ok]
    # Sections render after the launch sections, before To Review.
    order = list(spec.rule_set.section_order)
    assert order.index("Bus & Transport") < order.index("To Review")
    assert order.index("Announcements") < order.index("Bus & Transport")


# ---------------------------------------------------------------- suggester


class FakeRecord:
    def __init__(self, text):
        self.text_clean = text
        self.text_raw = text


BUS_TEXTS = [
    "Bus 7 is running about 15 minutes late.",
    "The late bus is full today.",
    "Bus duty rotation starts this afternoon.",
]


def test_suggester_counts_disabled_pack_matches():
    records = [FakeRecord(t) for t in BUS_TEXTS] + [
        FakeRecord("Totally unrelated chatter.")
    ]
    suggestions = ops_suggest.shadow_suggestions(
        records, rule_set=ops_packs.default_rule_set()
    )
    assert [s["pack_id"] for s in suggestions] == ["bus_transport"]
    assert suggestions[0]["count"] == 3
    assert "Bus / Transport" in suggestions[0]["message"]
    # Counts and names only — never record text.
    assert "late bus" not in json.dumps(suggestions).lower()


def test_suggester_below_threshold_stays_silent():
    records = [FakeRecord(t) for t in BUS_TEXTS[:2]]
    assert (
        ops_suggest.shadow_suggestions(records, rule_set=ops_packs.default_rule_set())
        == []
    )


def test_suggester_never_suggests_enabled_packs():
    data = default_bot_spec_data()
    data["packs"]["enabled"] = sorted(
        set(data["packs"]["enabled"]) | {"bus_transport"}
    )
    spec = ops_bot_spec._compile_from_data(data)
    records = [FakeRecord(t) for t in BUS_TEXTS]
    assert ops_suggest.shadow_suggestions(records, rule_set=spec.rule_set) == []


# ------------------------------------------------------------------- route


def test_suggestions_route_scans_weekly_unmatched_traffic():
    now = datetime.now(timezone.utc)
    with OpsRecordStore() as store:
        # Three ops-channel bus messages this week — positionally filed
        # as announcement (the unmatched ops-channel bucket).
        for index, text in enumerate(BUS_TEXTS):
            store.add_record(
                category="announcement",
                status="logged",
                text_raw=text,
                text_clean=text,
                source_channel="C0TESTOPS",
                source_ts=f"1234.000{index}",
            )
        # An old bus message outside the 7-day window must not count.
        old = store.add_record(
            category="announcement",
            status="logged",
            text_raw="Bus riders wait in the gym.",
            text_clean="Bus riders wait in the gym.",
            source_channel="C0TESTOPS",
            source_ts="1000.0001",
        )
        stale = (now - timedelta(days=30)).isoformat()
        store._conn.execute(
            "UPDATE ops_records SET created_at = ? WHERE id = ?", (stale, old.id)
        )
        store._conn.commit()
    data = client.get("/api/ops/setup/suggestions").json()
    assert data["window_days"] == 7
    assert data["threshold"] == 3
    assert [s["pack_id"] for s in data["suggestions"]] == ["bus_transport"]
    assert data["suggestions"][0]["count"] == 3
    body = json.dumps(data)
    assert "running about 15 minutes late" not in body  # no record text
    assert "C0TESTOPS" not in body  # no identifiers


def test_suggestions_route_empty_store_is_quiet():
    data = client.get("/api/ops/setup/suggestions").json()
    assert data["suggestions"] == []
