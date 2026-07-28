"""
Tests for src/education/ops_packs.py (v2 Phase 1 — packs as data).

Spec: dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md §3, §3.4.

Two families:
  1. PARITY — the v1-parity default compile must reproduce v1's hardcoded
     values exactly: category set, priority order, section mapping,
     broadcast set (spec §3.3). The 168-test v1 ops suite pins regex
     behavior; this file pins the registry shape.
  2. DISABLED-PACK semantics (spec §3.4) — a message whose only matching
     category belongs to a disabled pack falls through to core `other` →
     To Review, never dropped; the section list, broadcast set, and
     priority chain shrink to enabled packs only. One test per launch pack.

Plus loader guards (YAML alias bomb / size cap / malformed pack fail
closed) and registry invariants.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.education import ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_classifier import classify_ops_message
from src.education.ops_packs import (
    MAX_PACK_BYTES,
    PackLoadError,
    compile_rule_set,
    current_rule_set,
    default_rule_set,
    install_rule_set,
    known_categories,
    load_packs,
    load_yaml_guarded,
)
from src.education.ops_records import OpsRecordStore

TODAY = date(2026, 7, 27)  # a Monday

LAUNCH_PACKS = (
    "absence_coverage",
    "announcements",
    "facilities",
    "schedule_changes",
    "student_logistics",
)


def classify(text, rule_set, **kwargs):
    kwargs.setdefault("today", TODAY)
    return classify_ops_message(text, rule_set=rule_set, **kwargs)


def compile_without(pack_id):
    enabled = [p for p in LAUNCH_PACKS if p != pack_id]
    return compile_rule_set(enabled)


# ---------------------------------------------------------------------------
# 1. Parity — the default compile equals v1's hardcoded values exactly
# ---------------------------------------------------------------------------


def test_parity_priority_order_equals_v1_dispatch_chain():
    # v1 classify() evaluation order (ops_classifier v1): absence →
    # coverage_claim → coverage_request → schedule_change →
    # student_logistics → facilities → reminder → positional announcement.
    assert default_rule_set().category_ids() == (
        "absence",
        "coverage_claim",
        "coverage_request",
        "schedule_change",
        "student_logistics",
        "facilities",
        "reminder",
        "announcement",
    )


def test_parity_category_set_equals_v1_categories():
    # v1 ops_records.CATEGORIES, order-insensitive (the priority order is
    # asserted separately above). The record CATALOG additionally carries
    # the shipped backlog packs' categories (spec §5 packs 6-7) so their
    # records stay loadable — but neither is in the v1-parity COMPILE
    # (test_parity_priority_order_equals_v1_dispatch_chain pins that).
    assert set(known_categories()) == {
        "absence",
        "coverage_request",
        "coverage_claim",
        "schedule_change",
        "announcement",
        "student_logistics",
        "facilities",
        "reminder",
        "other",
    } | {"bus_transport", "dismissal_change"}


def test_parity_section_mapping_equals_v1_category_sections():
    # v1 daily_file._CATEGORY_SECTIONS, verbatim.
    assert default_rule_set().category_sections == {
        "schedule_change": "Schedule Changes",
        "student_logistics": "Student Logistics",
        "coverage_request": "Coverage",
        "coverage_claim": "Coverage",
        "absence": "Coverage",
        "announcement": "Announcements",
        "reminder": "Announcements",
        "facilities": "Announcements",
        "other": "Announcements",
    }


def test_parity_section_order_equals_v1_section_order():
    assert default_rule_set().section_order == (
        "Schedule Changes",
        "Student Logistics",
        "Coverage",
        "Announcements",
        "To Review",
    )


def test_parity_broadcast_set_equals_v1_broadcast_categories():
    assert default_rule_set().broadcast_categories == frozenset(
        {"announcement", "schedule_change", "reminder"}
    )


def test_parity_announcement_is_positional_channel_default():
    rules = default_rule_set()
    assert rules.channel_default_category == "announcement"
    entry = rules.entry_for("announcement")
    assert entry.channel_default is True
    assert entry.patterns == ()  # never keyword-triggered (spec §3.1)


def test_parity_coverage_always_renders():
    assert default_rule_set().always_render == {
        "Coverage": "- No coverage assigned to you today."
    }


def test_parity_capability_ids():
    rules = default_rule_set()
    assert rules.capability_for("absence") == "absence_flow"
    assert rules.capability_for("coverage_request") == "coverage_machine"
    assert rules.capability_for("coverage_claim") == "text_claim"
    for capture_only in ("schedule_change", "announcement", "reminder",
                         "student_logistics", "facilities"):
        assert rules.capability_for(capture_only) is None


def test_parity_default_compile_enables_all_launch_packs():
    # Facilities is ON in the v1-parity set (spec §3.1: v1 captures it);
    # its off-by-default-for-new-schools stance is a setup-panel hint.
    assert set(default_rule_set().enabled_pack_ids) == set(LAUNCH_PACKS)


def test_parity_out_of_thing_lookahead_lives_in_pack_data():
    # Hardening pass 11 moved into absence pack vocabulary intact.
    rules = default_rule_set()
    assert rules.match_category("i'm out of paper for the copier") is None
    assert rules.match_category("i'm out of town on friday") == "absence"
    assert rules.match_category("i'm out tomorrow") == "absence"


# ---------------------------------------------------------------------------
# 2. Disabled-pack semantics (spec §3.4) — one per launch pack
# ---------------------------------------------------------------------------


def test_disabled_absence_coverage_falls_through_to_other():
    rules = compile_without("absence_coverage")
    msg = classify("I'm out tomorrow. Need coverage for 2nd period.", rules, is_dm=True)
    assert msg.category == "other"          # never dropped
    assert msg.confidence == "low"          # → To Review via clarification
    assert msg.clarification
    # Section list shrinks; Coverage always-render rule off.
    assert "Coverage" not in rules.section_order
    assert "Coverage" not in rules.always_render
    # Priority chain no longer contains the pack's categories.
    for gone in ("absence", "coverage_request", "coverage_claim"):
        assert rules.entry_for(gone) is None


def test_disabled_announcements_removes_channel_default_and_reminder():
    rules = compile_without("announcements")
    assert rules.channel_default_category is None
    # An ops-channel post no category claims now lands in `other` (low)
    # instead of the announcement bucket — still never dropped.
    msg = classify("Spirit week starts next week!", rules, is_ops_channel=True)
    assert msg.category == "other"
    assert msg.confidence == "low"
    msg = classify("Reminder: forms are due Friday.", rules, is_dm=True)
    assert msg.category == "other"
    assert "reminder" not in rules.broadcast_categories
    assert "announcement" not in rules.broadcast_categories


def test_disabled_schedule_changes_falls_through():
    rules = compile_without("schedule_changes")
    msg = classify("Assembly moved to 10:30.", rules, is_dm=True)
    assert msg.category == "other"
    assert msg.confidence == "low"
    assert "schedule_change" not in rules.broadcast_categories
    assert "Schedule Changes" not in rules.section_order


def test_disabled_student_logistics_falls_through():
    rules = compile_without("student_logistics")
    msg = classify("Sofia has an early pickup at 1:45.", rules, is_dm=True)
    assert msg.category == "other"
    assert msg.confidence == "low"
    assert "Student Logistics" not in rules.section_order


def test_disabled_facilities_falls_through():
    rules = compile_without("facilities")
    msg = classify("The projector in room 12 isn't working.", rules, is_dm=True)
    assert msg.category == "other"
    assert msg.confidence == "low"
    # Announcements section survives (core owns it for `other`).
    assert "Announcements" in rules.section_order


def test_disabled_pack_item_renders_in_to_review_not_dropped(tmp_path, monkeypatch):
    # End-to-end §3.4: with absence_coverage disabled, the fallen-through
    # record renders under To Review and Coverage is gone from the file.
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops.db"))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    rules = compile_without("absence_coverage")
    with OpsRecordStore() as store:
        store.add_record(
            category="other",
            teacher_id="t-ana",
            date_for="2026-07-28",
            text_clean="I'm out tomorrow",
            needs_review=True,
            review_reason="unclassified",
        )
        engine = DailyFileEngine(
            store, desktop_dir=tmp_path / "desk", rule_set=rules
        )
        markdown = engine.render_markdown("t-ana", "Ana", "2026-07-28")
    assert "## To Review" in markdown
    assert "I'm out tomorrow" in markdown
    assert "## Coverage" not in markdown


# ---------------------------------------------------------------------------
# Loader guards (fail closed — house YAML rules)
# ---------------------------------------------------------------------------


def test_yaml_alias_bomb_is_refused():
    bomb = b"a: &a [x, x]\nb: [*a, *a]\n"
    with pytest.raises(PackLoadError):
        load_yaml_guarded(bomb)


def test_yaml_size_cap_is_enforced():
    with pytest.raises(PackLoadError):
        load_yaml_guarded(b"x" * (MAX_PACK_BYTES + 1))


def test_malformed_pack_file_is_skipped_not_fatal(tmp_path):
    (tmp_path / "bad.yaml").write_text("categories: [", encoding="utf-8")
    (tmp_path / "good.yaml").write_text(
        "id: good\nname: Good\ncategories:\n"
        "  - id: goodcat\n    priority: 10\n    section: Announcements\n"
        "    vocabulary: ['\\bgood\\b']\n",
        encoding="utf-8",
    )
    packs = load_packs(tmp_path)
    assert list(packs) == ["good"]


def test_pack_cannot_define_core_other(tmp_path):
    (tmp_path / "evil.yaml").write_text(
        "id: evil\nname: Evil\ncategories:\n"
        "  - id: other\n    priority: 1\n    section: Announcements\n",
        encoding="utf-8",
    )
    assert load_packs(tmp_path) == {}


def test_channel_default_category_must_not_carry_vocabulary(tmp_path):
    (tmp_path / "mixed.yaml").write_text(
        "id: mixed\nname: Mixed\ncategories:\n"
        "  - id: mixedcat\n    priority: 1\n    section: Announcements\n"
        "    channel_default: true\n    vocabulary: ['\\bx\\b']\n",
        encoding="utf-8",
    )
    assert load_packs(tmp_path) == {}


# ---------------------------------------------------------------------------
# Learned-rule precedence (spec §4, compile-side enforcement)
# ---------------------------------------------------------------------------


def test_learned_rule_ors_into_existing_priority_slot():
    rules = compile_rule_set(
        list(LAUNCH_PACKS),
        learned_rules=[
            {"category": "schedule_change", "pattern": r"\bswitcheroo\b"}
        ],
    )
    # New phrase now routes to its target category…
    assert rules.match_category("big switcheroo for friday") == "schedule_change"
    # …but priorities did not reorder: absence still wins first.
    assert rules.category_ids() == default_rule_set().category_ids()
    msg = classify("I'm out tomorrow, total switcheroo", rules, is_dm=True)
    assert msg.category == "absence"


def test_learned_rule_cannot_target_core_other():
    rules = compile_rule_set(
        list(LAUNCH_PACKS),
        learned_rules=[{"category": "other", "pattern": r"\bmystery\b"}],
    )
    assert rules.match_category("a mystery message") is None


def test_learned_rule_for_disabled_category_is_ignored():
    rules = compile_rule_set(
        [p for p in LAUNCH_PACKS if p != "facilities"],
        learned_rules=[{"category": "facilities", "pattern": r"\bboiler\b"}],
    )
    assert rules.match_category("the boiler is acting up") is None


# ---------------------------------------------------------------------------
# Current-compile swap seam (spec §3.2)
# ---------------------------------------------------------------------------


def test_install_rule_set_swaps_and_resets():
    try:
        shrunk = compile_without("facilities")
        install_rule_set(shrunk)
        assert current_rule_set() is shrunk
        # The classifier default now reads the swapped compile.
        msg = classify_ops_message(
            "The projector isn't working.", today=TODAY, is_dm=True
        )
        assert msg.category == "other"
    finally:
        install_rule_set(None)
    assert current_rule_set() is default_rule_set()
    msg = classify_ops_message(
        "The projector isn't working.", today=TODAY, is_dm=True
    )
    assert msg.category == "facilities"
