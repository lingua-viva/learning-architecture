"""
Tests for src/education/ops_bot_spec.py (v2 Phase 2 — bot-spec compile +
atomic swap) and the web-startup wiring that consumes it.

Spec: dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md §3.2,
§3.3, §4.

Families:
  1. LOAD/COMPILE — no file ⇒ exact v1 parity (exists=False); a valid
     spec compiles enabled packs, times, review-required, aliases;
     anything malformed/oversized/alias-bombed fails CLOSED to parity
     with a fallback reason (never crash, never half-apply).
  2. LEARNED RULES — only status=approved compiles in; candidates never
     affect live classification; keyphrase → pattern derivation is
     literal (escaped, word-bounded), never generalized.
  3. WRITE — atomic, generated header, refuses Slack-token shapes
     (secrets stay in env; spec §3.2 hard rule).
  4. SWAP SEAM + BACKWARD COMPAT (spec §3.3 — Claudia is LIVE):
     env-only + no bot-spec = v1 daily file byte-for-byte; bot-spec with
     live:false = startup gate keeps the transport off; installing a new
     compile never touches a running bot's transport.

Hermetic: conftest clears LV_* and redirects ops paths; every test here
sets LV_OPS_BOT_SPEC_PATH into tmp_path so the operator's real
lv_home()/ops/bot_spec.yaml is never read or written.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
import yaml
from fastapi.testclient import TestClient

import src.web as web
from src.education import ops_bot_spec, ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_bot_spec import (
    DEFAULT_BRIEFING_HHMM,
    DEFAULT_EOD_HHMM,
    GENERATED_HEADER,
    CompiledBotSpec,
    bot_spec_path,
    default_bot_spec_data,
    install_compiled_spec,
    keyphrase_pattern,
    load_compiled_spec,
    new_candidate_rule,
    normalize_keyphrase,
    refresh_from_disk,
    write_bot_spec,
)
from src.education.ops_classifier import classify_ops_message
from src.education.ops_records import OpsRecordStore

DAY = "2026-07-28"
TODAY = date(2026, 7, 27)  # a Monday


def classify(text, **kwargs):
    kwargs.setdefault("today", TODAY)
    return classify_ops_message(text, **kwargs)

OPS_ENV = {
    "LV_SLACK_BOT_TOKEN": "xoxb-test-token",
    "LV_SLACK_APP_TOKEN": "xapp-test-token",
    "LV_SLACK_OPS_CHANNEL": "C0TESTOPS",
    "LV_SLACK_TEACHER_MAP": json.dumps(
        {"U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"}}
    ),
}


@pytest.fixture(autouse=True)
def _reset_seams():
    """Both swap seams are module globals — never leak between tests."""
    yield
    install_compiled_spec(None)


@pytest.fixture
def spec_path(monkeypatch, tmp_path):
    path = tmp_path / "ops" / "bot_spec.yaml"
    monkeypatch.setenv("LV_OPS_BOT_SPEC_PATH", str(path))
    return path


def valid_data(**overrides):
    data = default_bot_spec_data()
    data.update(overrides)
    return data


# ---------------------------------------------------------------- load/compile


def test_no_file_is_exact_v1_parity(spec_path):
    spec = load_compiled_spec()
    assert spec.exists is False
    assert spec.live is False
    assert spec.fallback is None
    assert spec.briefing_hhmm == DEFAULT_BRIEFING_HHMM
    assert spec.eod_hhmm == DEFAULT_EOD_HHMM
    parity = ops_packs.default_rule_set()
    assert spec.rule_set.category_ids() == parity.category_ids()
    assert spec.rule_set.broadcast_categories == parity.broadcast_categories
    assert spec.rule_set.section_order == parity.section_order


def test_bot_spec_path_honors_env_override(spec_path):
    assert bot_spec_path() == spec_path


def test_valid_spec_compiles_packs_times_and_settings(spec_path):
    data = valid_data(live=True)
    data["packs"]["enabled"] = [
        "absence_coverage",
        "announcements",
        "schedule_changes",
        "student_logistics",
    ]  # facilities off
    data["settings"].update(
        {
            "briefing_hhmm": "08:00",
            "eod_hhmm": "15:15",
            "review_required": ["schedule_change"],
            "period_aliases": [r"\bblock\s+([a-h])\b"],
        }
    )
    write_bot_spec(data)
    spec = load_compiled_spec()
    assert spec.exists is True and spec.live is True and spec.fallback is None
    assert spec.enabled_pack_ids == tuple(data["packs"]["enabled"])
    assert spec.briefing_hhmm == "08:00" and spec.eod_hhmm == "15:15"
    assert "facilities" not in spec.rule_set.category_ids()
    assert spec.rule_set.review_required == frozenset({"schedule_change"})
    assert len(spec.rule_set.period_alias_patterns) == 1
    # Settings-fed alias reaches the classifier's period extraction.
    result = classify("Block B moved to the gym.", rule_set=spec.rule_set)
    assert result.category == "schedule_change"
    assert list(result.periods) == [2]


def test_invalid_hhmm_falls_back_to_defaults(spec_path):
    data = valid_data()
    data["settings"].update({"briefing_hhmm": "25:99", "eod_hhmm": "4pm"})
    write_bot_spec(data)
    spec = load_compiled_spec()
    assert spec.fallback is None  # bad times are soft — spec still compiles
    assert spec.briefing_hhmm == DEFAULT_BRIEFING_HHMM
    assert spec.eod_hhmm == DEFAULT_EOD_HHMM


@pytest.mark.parametrize(
    "raw, reason_hint",
    [
        (b"[unclosed", "parse"),
        (b"- just\n- a\n- list\n", "mapping"),
        (b"schema_version: 99\npacks:\n  enabled: []\n", "schema_version"),
        (
            b"schema_version: 1\npacks:\n  enabled: [no_such_pack]\n",
            "unknown packs",
        ),
        (
            b"schema_version: 1\npacks:\n  enabled: [absence_coverage]\n"
            b"learned_rules:\n  - {category: absence, keyphrase: x, status: wild}\n",
            "status",
        ),
        (b"a: &b [1, 2]\nc: *b\n", "alias"),
    ],
)
def test_malformed_spec_fails_closed_to_parity(spec_path, raw, reason_hint):
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_bytes(raw)
    spec = load_compiled_spec()
    assert spec.exists is True
    assert spec.fallback  # health WARN surface
    assert spec.live is False  # fail closed: never live on a broken spec
    parity = ops_packs.default_rule_set()
    assert spec.rule_set.category_ids() == parity.category_ids()


def test_oversized_spec_fails_closed(spec_path):
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_bytes(
        b"schema_version: 1\n# " + b"x" * (ops_bot_spec.MAX_BOT_SPEC_BYTES + 1)
    )
    spec = load_compiled_spec()
    assert spec.fallback  # health WARN surface, size-capped before parse
    assert spec.rule_set.category_ids() == ops_packs.default_rule_set().category_ids()


# ---------------------------------------------------------------- learned rules


def test_only_approved_rules_compile_in(spec_path):
    data = valid_data()
    data["learned_rules"] = [
        {
            "id": "lr-approved01",
            "category": "schedule_change",
            "keyphrase": "door duty",
            "status": "approved",
        },
        {
            "id": "lr-candidate1",
            "category": "facilities",
            "keyphrase": "lunch swap",
            "status": "candidate",
        },
    ]
    write_bot_spec(data)
    spec = load_compiled_spec()
    assert [r["id"] for r in spec.approved_rules()] == ["lr-approved01"]
    assert [r["id"] for r in spec.candidate_rules()] == ["lr-candidate1"]
    # Approved rule classifies; candidate NEVER affects live classification.
    hit = classify("Door duty list is posted.", rule_set=spec.rule_set)
    assert hit.category == "schedule_change"
    miss = classify("Lunch swap anyone?", rule_set=spec.rule_set)
    assert miss.category == "other"


def test_learned_rule_never_reorders_priority(spec_path):
    # An approved reminder-keyphrase that also contains absence vocabulary:
    # absence (priority 10) must still win over reminder (priority 70).
    data = valid_data()
    data["learned_rules"] = [
        {
            "id": "lr-reminder01",
            "category": "reminder",
            "keyphrase": "out sick protocol",
            "status": "approved",
        }
    ]
    write_bot_spec(data)
    spec = load_compiled_spec()
    result = classify(
        "I'm out sick protocol says to tell you.", rule_set=spec.rule_set
    )
    assert result.category == "absence"


def test_keyphrase_normalization_and_literal_pattern():
    assert normalize_keyphrase("  Door \t DUTY ") == "door duty"
    pattern = keyphrase_pattern("Door   Duty")
    assert re.search(pattern, "door\tduty roster", re.IGNORECASE)
    assert not re.search(pattern, "doorduty", re.IGNORECASE)
    # Literal, not generalized: regex metacharacters are escaped.
    assert re.search(keyphrase_pattern("room 3 (annex)"), "in room 3 (annex) now", re.I)
    assert keyphrase_pattern("   ") == ""


def test_new_candidate_rule_has_provenance():
    rule = new_candidate_rule(
        category="reminder", keyphrase="  Spirit  WEEK ", source_record_id="rec-9"
    )
    assert rule["id"].startswith("lr-")
    assert rule["status"] == "candidate"
    assert rule["keyphrase"] == "spirit week"
    assert rule["provenance"]["source_record_id"] == "rec-9"
    assert rule["provenance"]["created_at"]


# ---------------------------------------------------------------------- write


def test_write_bot_spec_is_atomic_with_generated_header(spec_path):
    write_bot_spec(valid_data())
    text = spec_path.read_text(encoding="utf-8")
    assert text.startswith(GENERATED_HEADER)
    parsed = yaml.safe_load(text)
    assert parsed["schema_version"] == ops_bot_spec.SCHEMA_VERSION
    assert parsed["updated_at"]
    leftovers = [p for p in spec_path.parent.iterdir() if p.name != spec_path.name]
    assert leftovers == []  # no temp files left behind


def test_write_bot_spec_refuses_slack_tokens(spec_path):
    data = valid_data()
    data["settings"]["note"] = "token is xoxb-123-abc"
    with pytest.raises(ValueError, match="never contain Slack tokens"):
        write_bot_spec(data)
    assert not spec_path.exists()


# ------------------------------------------------- swap seam + backward compat


def test_refresh_from_disk_swaps_rule_set_atomically(spec_path):
    data = valid_data()
    data["packs"]["enabled"] = ["absence_coverage", "announcements"]
    write_bot_spec(data)
    spec = refresh_from_disk()
    assert ops_bot_spec.current_spec() is spec
    assert ops_packs.current_rule_set() is spec.rule_set
    # Disabled facilities: falls through to core `other`, never dropped.
    result = classify("The projector is broken in room 12.")
    assert result.category == "other"
    # Reset restores parity for both seams.
    install_compiled_spec(None)
    assert (
        ops_packs.current_rule_set().category_ids()
        == ops_packs.default_rule_set().category_ids()
    )


def test_installing_a_compile_never_touches_bot_transport(spec_path):
    sentinel = object()
    web._ops_runtime["client"] = sentinel
    try:
        write_bot_spec(valid_data())
        refresh_from_disk()
        assert web._ops_runtime["client"] is sentinel  # transport untouched
    finally:
        web._ops_runtime.clear()


def test_env_only_no_bot_spec_daily_file_is_v1_byte_for_byte(spec_path):
    """Spec §3.3: no bot-spec + env configured ⇒ exact v1 behavior."""
    refresh_from_disk()  # no file → parity compile installed
    teacher_map = json.loads(OPS_ENV["LV_SLACK_TEACHER_MAP"])
    with OpsRecordStore() as store:
        store.add_record(
            category="schedule_change", date_for=DAY, text_clean="Assembly at 10:30."
        )
        store.add_record(
            category="absence",
            teacher_id="t-ana",
            actor_name="Ana Ruiz",
            date_for=DAY,
            text_clean="Out sick today.",
        )
        via_seam = DailyFileEngine(store, teacher_map=teacher_map).render_markdown(
            "t-ana", "Ana Ruiz", DAY
        )
        explicit_v1 = DailyFileEngine(
            store, teacher_map=teacher_map, rule_set=ops_packs.default_rule_set()
        ).render_markdown("t-ana", "Ana Ruiz", DAY)
    assert via_seam == explicit_v1


def test_startup_gate_live_false_keeps_bot_off(monkeypatch, spec_path):
    """Go-live gate (spec §3.3): bot-spec exists but live:false ⇒ the
    transport never starts, even with full env config present."""
    for key, value in OPS_ENV.items():
        monkeypatch.setenv(key, value)
    write_bot_spec(valid_data(live=False))
    with TestClient(web.app) as started:
        data = started.get("/api/slack/ops/status").json()
        assert data["configured"] is True
        assert data["connected"] is False
        assert web._ops_runtime == {}
    assert web._ops_runtime == {}


def test_startup_no_bot_spec_env_only_reaches_transport_build(monkeypatch, spec_path):
    """Env-only setups (Claudia today) must NOT be gated: startup proceeds
    past the gate to the transport build. We stub the transport class so
    no network is touched, and prove run_schedules got the spec times."""
    for key, value in OPS_ENV.items():
        monkeypatch.setenv(key, value)

    import src.lingua_viva.slack_socket as slack_socket

    built = {}

    class StubClient:
        def __init__(self, config, on_envelope):
            built["config"] = config

        def start(self):
            built["started"] = True

        async def stop(self):
            built["stopped"] = True

    monkeypatch.setattr(slack_socket, "SlackSocketClient", StubClient)
    with TestClient(web.app):
        assert built.get("started") is True
        assert web._ops_runtime.get("client") is not None
    assert built.get("stopped") is True
    assert web._ops_runtime == {}


def test_startup_schedule_times_come_from_bot_spec(monkeypatch, spec_path):
    for key, value in OPS_ENV.items():
        monkeypatch.setenv(key, value)
    data = valid_data(live=True)
    data["settings"].update({"briefing_hhmm": "06:45", "eod_hhmm": "17:05"})
    write_bot_spec(data)

    import src.lingua_viva.slack_socket as slack_socket
    from src.education.slack_ops_bot import SlackOpsBot

    class StubClient:
        def __init__(self, config, on_envelope):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    captured = {}
    real_run_schedules = SlackOpsBot.run_schedules

    async def capture_run_schedules(self, **kwargs):
        captured.update(kwargs)
        return await real_run_schedules(self, **kwargs)

    monkeypatch.setattr(slack_socket, "SlackSocketClient", StubClient)
    monkeypatch.setattr(SlackOpsBot, "run_schedules", capture_run_schedules)
    with TestClient(web.app):
        pass
    assert captured.get("briefing_hhmm") == "06:45"
    assert captured.get("eod_hhmm") == "17:05"
