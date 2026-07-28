"""
Tests for the v2 Bot Setup routes (spec §6) and the review-required
settings gate.

Routes under test (src/web.py):
  GET /api/ops/setup/catalog    — shipped pack catalog (read-only data)
  GET /api/ops/setup/bot-spec   — current bot-spec state (disk truth)
  PUT /api/ops/setup/bot-spec   — write + atomic swap; preserves
                                  teach-loop fields; go-live corpus gate
  GET /api/ops/setup/roster     — read-only roster (env source of truth)

Hard rules proven here: every payload is secret-free (no tokens, no ops
channel id); a PUT never touches a running transport; an invalid spec is
never written to disk; go-live is refused without a recorded passing
corpus run (spec §7 — a school never goes live on untested rules).
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.education import ops_bot_spec, ops_packs
from src.education.daily_file import DailyFileEngine
from src.education.ops_bot_spec import (
    default_bot_spec_data,
    install_compiled_spec,
    write_bot_spec,
)
from src.education.ops_records import OpsRecordStore
from src.education.slack_ops_bot import SlackOpsBot

client = TestClient(web.app)

TODAY = date(2026, 7, 28)  # a Tuesday
OPS_CHANNEL = "C0TESTOPS"

OPS_ENV = {
    "LV_SLACK_BOT_TOKEN": "xoxb-test-token",
    "LV_SLACK_APP_TOKEN": "xapp-test-token",
    "LV_SLACK_OPS_CHANNEL": OPS_CHANNEL,
    "LV_SLACK_TEACHER_MAP": json.dumps(
        {
            "U111": {"teacher_id": "t-ana", "display_name": "Ana Ruiz"},
            "U222": {"teacher_id": "t-ben", "display_name": "Ben Ali"},
        }
    ),
}


@pytest.fixture(autouse=True)
def _seams(monkeypatch, tmp_path):
    """Hermetic bot-spec path + seam reset after every test."""
    monkeypatch.setenv("LV_OPS_BOT_SPEC_PATH", str(tmp_path / "bot_spec.yaml"))
    yield tmp_path / "bot_spec.yaml"
    install_compiled_spec(None)


@pytest.fixture
def ops_env(monkeypatch):
    for key, value in OPS_ENV.items():
        monkeypatch.setenv(key, value)


def assert_secret_free(payload):
    body = json.dumps(payload)
    assert "xoxb-test-token" not in body
    assert "xapp-test-token" not in body
    assert OPS_CHANNEL not in body


# ---------------------------------------------------------------- catalog


def test_catalog_lists_launch_packs_secret_free(ops_env):
    data = client.get("/api/ops/setup/catalog").json()
    packs = {p["id"]: p for p in data["packs"]}
    assert set(packs) == {
        "absence_coverage",
        "announcements",
        "facilities",
        "schedule_changes",
        "student_logistics",
    }
    # Facilities: launch-enabled for v1 parity, unchecked for new schools.
    assert packs["facilities"]["enabled_by_default"] is True
    assert packs["facilities"]["default_for_new_schools"] is False
    # Announcement is positional: no vocabulary of its own.
    announcement = next(
        c for c in packs["announcements"]["categories"] if c["id"] == "announcement"
    )
    assert announcement["channel_default"] is True
    assert announcement["vocabulary_count"] == 0
    # Core `other` is not a pack and cannot be disabled.
    assert data["core"]["category"] == "other"
    assert_secret_free(data)


# ---------------------------------------------------------------- bot-spec GET


def test_bot_spec_get_no_file_reports_parity(ops_env):
    data = client.get("/api/ops/setup/bot-spec").json()
    assert data["exists"] is False
    assert data["live"] is False
    assert data["fallback"] is None
    assert data["settings"]["briefing_hhmm"] == ops_bot_spec.DEFAULT_BRIEFING_HHMM
    assert data["compiled"]["categories"] == list(
        ops_packs.default_rule_set().category_ids()
    )
    assert_secret_free(data)


def test_bot_spec_get_surfaces_fallback_warning(_seams):
    _seams.write_bytes(b"[unclosed")
    data = client.get("/api/ops/setup/bot-spec").json()
    assert data["exists"] is True
    assert data["fallback"]
    assert data["live"] is False
    # Fail-closed: compiled summary is v1 parity.
    assert data["compiled"]["categories"] == list(
        ops_packs.default_rule_set().category_ids()
    )


# ---------------------------------------------------------------- bot-spec PUT


def test_put_writes_swaps_and_never_touches_transport(ops_env, _seams):
    sentinel = object()
    web._ops_runtime["client"] = sentinel
    try:
        response = client.put(
            "/api/ops/setup/bot-spec",
            json={
                "packs": {
                    "enabled": [
                        "absence_coverage",
                        "announcements",
                        "schedule_changes",
                        "student_logistics",
                    ]
                },
                "settings": {
                    "briefing_hhmm": "08:00",
                    "eod_hhmm": "15:30",
                    "review_required": ["schedule_change"],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "facilities" not in data["compiled"]["categories"]
        assert data["settings"]["briefing_hhmm"] == "08:00"
        assert data["settings"]["review_required"] == ["schedule_change"]
        assert_secret_free(data)
        # Written to the hermetic path, atomic, generated header.
        assert _seams.exists()
        assert _seams.read_text(encoding="utf-8").startswith(
            ops_bot_spec.GENERATED_HEADER
        )
        # The live compile swapped: classifier seam no longer has facilities.
        assert "facilities" not in ops_packs.current_rule_set().category_ids()
        # The running transport was never touched.
        assert web._ops_runtime["client"] is sentinel
    finally:
        web._ops_runtime.clear()


def test_put_unknown_pack_rejected_nothing_written(ops_env, _seams):
    response = client.put(
        "/api/ops/setup/bot-spec",
        json={"packs": {"enabled": ["absence_coverage", "no_such_pack"]}},
    )
    assert response.status_code == 400
    assert "unknown packs" in response.json()["error"]
    assert not _seams.exists()  # a spec that does not compile is never written


def test_put_malformed_body_rejected(ops_env):
    response = client.put(
        "/api/ops/setup/bot-spec",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    response = client.put("/api/ops/setup/bot-spec", json=["a", "list"])
    assert response.status_code == 400


def test_put_preserves_teach_loop_fields(ops_env):
    # Teach loop owns learned_rules + corpus; the panel PUT must carry
    # them over from disk, never clobber them.
    data = default_bot_spec_data()
    data["learned_rules"] = [
        {
            "id": "lr-keepme00001",
            "category": "reminder",
            "keyphrase": "spirit week",
            "status": "approved",
        }
    ]
    data["corpus"] = {
        "admin_sentences": [{"text": "Spirit week!", "expect": {"category": "reminder"}}],
        "last_run": {"at": "2026-07-27T10:00:00+00:00", "passed": True, "result_hash": "abc"},
    }
    write_bot_spec(data)
    response = client.put(
        "/api/ops/setup/bot-spec",
        json={"settings": {"briefing_hhmm": "06:50"}},
    )
    assert response.status_code == 200
    state = response.json()
    assert [r["id"] for r in state["learned_rules"]] == ["lr-keepme00001"]
    assert state["corpus"]["last_run"]["result_hash"] == "abc"
    assert len(state["corpus"]["admin_sentences"]) == 1
    assert state["settings"]["briefing_hhmm"] == "06:50"


def test_put_go_live_requires_passing_corpus_run(ops_env, _seams):
    # No corpus run recorded → refuse to go live (spec §7).
    response = client.put("/api/ops/setup/bot-spec", json={"live": True})
    assert response.status_code == 409
    assert "corpus" in response.json()["error"].lower()
    assert not _seams.exists()
    # With a recorded passing run on disk, the same toggle succeeds.
    data = default_bot_spec_data()
    data["corpus"]["last_run"] = {
        "at": "2026-07-27T10:00:00+00:00",
        "passed": True,
        "result_hash": "abc",
    }
    write_bot_spec(data)
    response = client.put("/api/ops/setup/bot-spec", json={"live": True})
    assert response.status_code == 200
    assert response.json()["live"] is True


def test_put_failed_corpus_run_still_blocks_go_live(ops_env):
    data = default_bot_spec_data()
    data["corpus"]["last_run"] = {
        "at": "2026-07-27T10:00:00+00:00",
        "passed": False,
        "result_hash": "abc",
    }
    write_bot_spec(data)
    response = client.put("/api/ops/setup/bot-spec", json={"live": True})
    assert response.status_code == 409


# ---------------------------------------------------------------- roster


def test_roster_read_only_from_env_secret_free(ops_env):
    data = client.get("/api/ops/setup/roster").json()
    assert data["editable"] is False
    assert data["source"] == "LV_SLACK_TEACHER_MAP"
    assert data["count"] == 2
    assert data["teachers"][0] == {
        "slack_user_id": "U111",
        "teacher_id": "t-ana",
        "display_name": "Ana Ruiz",
    }
    assert_secret_free(data)


def test_roster_unconfigured_is_empty_not_error():
    data = client.get("/api/ops/setup/roster").json()
    assert data["count"] == 0
    assert data["teachers"] == []


# ------------------------------------------- review-required settings gate


class FakeClient:
    def __init__(self):
        self.posts = []

    async def post_message(self, channel, text, blocks=None, thread_ts=None):
        self.posts.append({"channel": channel, "text": text, "blocks": blocks})
        return {"ok": True, "ts": "1721990400.000001", "channel": channel}

    async def update_message(self, channel, ts, text, blocks=None):
        return {"ok": True, "ts": ts}

    async def open_dm(self, user_id):
        return f"D{user_id}"


async def test_review_required_gate_holds_confident_matches(monkeypatch, tmp_path):
    """Interview-chosen review-required categories land in To Review even
    at high confidence (spec §6) — and render there in the daily file."""
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops.db"))
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(tmp_path / "desktop"))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(tmp_path / "state.json"))
    rules = ops_packs.compile_rule_set(review_required={"schedule_change"})
    teacher_map = json.loads(OPS_ENV["LV_SLACK_TEACHER_MAP"])
    with OpsRecordStore() as store:
        daily = DailyFileEngine(store, teacher_map=teacher_map, rule_set=rules)
        bot = SlackOpsBot(
            store=store,
            daily=daily,
            client=FakeClient(),
            ops_channel=OPS_CHANNEL,
            teacher_map=teacher_map,
            today=lambda: TODAY,
            rule_set=rules,
        )
        await bot.on_envelope(
            "events_api",
            {
                "event": {
                    "type": "message",
                    "text": "Assembly moved to 10:30.",
                    "user": "U111",
                    "channel": OPS_CHANNEL,
                    "channel_type": "channel",
                    "ts": "1721990000.000001",
                }
            },
        )
        records = store.records_for_day(TODAY.isoformat())
        record = next(r for r in records if r.category == "schedule_change")
        assert record.needs_review is True
        markdown = daily.render_markdown("t-ben", "Ben Ali", TODAY.isoformat())
        assert "To Review" in markdown
        assert "Assembly moved to 10:30." in markdown


# --------------------------------------------------- teach loop (spec §4)


def _local_today() -> str:
    from datetime import datetime

    return datetime.now().astimezone().date().isoformat()


def _seed_review_record(category="other", text="Bikes go behind the gym now.",
                        teacher_id="t-ana", actor_name="Ana Ruiz"):
    with OpsRecordStore() as store:
        record = store.add_record(
            category=category,
            teacher_id=teacher_id,
            actor_name=actor_name,
            date_for=_local_today(),
            text_clean=text,
            needs_review=True,
            review_reason="not understood",
        )
    return record


def test_reclassify_fixes_record_and_audits_identifiers_only(ops_env):
    import os as _os
    from pathlib import Path as _Path

    record = _seed_review_record()
    response = client.post(
        "/api/ops/review/reclassify",
        json={"record_id": record.id, "category": "reminder"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["record"]["category"] == "reminder"
    assert data["record"]["needs_review"] is False
    assert data["record"]["status"] == "logged"
    assert data["candidate_rule"] is None
    with OpsRecordStore() as store:
        stored = store.get_record(record.id)
    assert stored.category == "reminder"
    assert stored.review_reason == ""
    # Audit entry: identifiers only, from->to visible, NO message text.
    log = _Path(_os.environ["LV_PRIVACY_LOG_PATH"]).read_text(encoding="utf-8")
    assert "ops_record_reclassified" in log
    assert "from=other" in log
    assert "Bikes go behind the gym" not in log


def test_reclassify_rerenders_old_and_new_placements(ops_env):
    # Wrongly-broadcast schedule_change -> student_logistics: the OTHER
    # teacher's daily file must lose the line (old placement re-rendered),
    # the record's own teacher keeps it under the corrected section.
    record = _seed_review_record(
        category="schedule_change", text="Marco leaves early for the dentist."
    )
    day = _local_today()
    teacher_map = json.loads(OPS_ENV["LV_SLACK_TEACHER_MAP"])
    with OpsRecordStore() as store:
        engine = DailyFileEngine(store, teacher_map=teacher_map)
        # Pre-state: broadcast reaches Ben too.
        assert "dentist" in engine.render_markdown("t-ben", "Ben Ali", day)
    response = client.post(
        "/api/ops/review/reclassify",
        json={"record_id": record.id, "category": "student_logistics"},
    )
    assert response.status_code == 200
    with OpsRecordStore() as store:
        engine = DailyFileEngine(store, teacher_map=teacher_map)
        assert "dentist" not in engine.render_markdown("t-ben", "Ben Ali", day)
        ana = engine.render_markdown("t-ana", "Ana Ruiz", day)
        assert "dentist" in ana and "Student Logistics" in ana
    # Desktop files were re-written for both placements.
    from pathlib import Path as _Path
    import os as _os

    desktop = _Path(_os.environ["LV_OPS_DESKTOP_DIR"])
    ben_file = engine.daily_file_path("Ben Ali")
    assert ben_file.exists() and "dentist" not in ben_file.read_text(encoding="utf-8")


def test_reclassify_with_keyphrase_files_candidate_not_live(ops_env):
    record = _seed_review_record(text="Bikes go behind the gym now.")
    response = client.post(
        "/api/ops/review/reclassify",
        json={
            "record_id": record.id,
            "category": "facilities",
            "keyphrase": "behind the gym",
        },
    )
    assert response.status_code == 200
    rule = response.json()["candidate_rule"]
    assert rule["status"] == "candidate"
    assert rule["keyphrase"] == "behind the gym"
    assert rule["provenance"]["source_record_id"] == record.id
    # Durable in the bot-spec…
    state = client.get("/api/ops/setup/bot-spec").json()
    assert [r["id"] for r in state["learned_rules"]] == [rule["id"]]
    # …and NEVER live: the swapped compile still routes the phrase to
    # facilities only via its shipped vocabulary, not the candidate. A
    # sentence matching ONLY the keyphrase stays `other`.
    from src.education.ops_classifier import classify_ops_message

    result = classify_ops_message(
        "Meet behind the gym.", today=TODAY, rule_set=ops_packs.current_rule_set()
    )
    assert result.category == "other"


def test_reclassify_coverage_target_clears_review_keeps_category(ops_env):
    record = _seed_review_record(text="Can anyone take my class Friday?")
    response = client.post(
        "/api/ops/review/reclassify",
        json={
            "record_id": record.id,
            "category": "coverage_request",
            "keyphrase": "take my class",
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Record does NOT enter the claim machine retroactively…
    assert data["record"]["category"] == "other"
    assert data["record"]["needs_review"] is False
    # …the candidate rule is how FUTURE messages get real coverage flow.
    assert data["candidate_rule"]["category"] == "coverage_request"


def test_reclassify_guards(ops_env):
    assert client.post(
        "/api/ops/review/reclassify",
        json={"record_id": "nope", "category": "reminder"},
    ).status_code == 404
    record = _seed_review_record()
    assert client.post(
        "/api/ops/review/reclassify",
        json={"record_id": record.id, "category": "not_a_category"},
    ).status_code == 400
    for target in ("other", "announcement", "coverage_claim"):
        response = client.post(
            "/api/ops/review/reclassify",
            json={"record_id": record.id, "category": target, "keyphrase": "x y"},
        )
        assert response.status_code == 400, target
    assert client.post(
        "/api/ops/review/reclassify", json={"record_id": record.id}
    ).status_code == 400


def test_reclassify_refuses_coverage_machine_records(ops_env):
    with OpsRecordStore() as store:
        record = store.add_record(
            category="coverage_request",
            teacher_id="t-ana",
            actor_name="Ana Ruiz",
            date_for=_local_today(),
            text_clean="Need coverage for period 2.",
            status="open",
        )
    response = client.post(
        "/api/ops/review/reclassify",
        json={"record_id": record.id, "category": "reminder"},
    )
    assert response.status_code == 400
    assert "machine" in response.json()["error"]


def test_reclassify_same_category_just_clears_review(ops_env):
    record = _seed_review_record(category="facilities", text="Projector bulb out.")
    response = client.post(
        "/api/ops/review/reclassify",
        json={"record_id": record.id, "category": "facilities"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["record"]["category"] == "facilities"
    assert data["record"]["needs_review"] is False
