"""
Tests for the test-corpus gate (spec §7) — runner + routes.

Runner (src/education/ops_corpus.py): relative-date expectations
resolved against an injected `today` (deterministic, never rot), pack
samples + admin sentences combined, fail-closed rules (empty corpus
never passes; unknown expectation keys fail their row), and a result
hash that is stable across reference days.

Routes (src/web.py):
  POST /api/ops/setup/corpus/run       — run + RECORD last_run (the
                                         go-live gate's evidence)
  POST /api/ops/setup/corpus/sentences — add admin sentence, clears the
                                         recorded run (stale)
  POST /api/ops/setup/rules/decide     — corpus-gated candidate
                                         approve / reject ceremony

Plus the PUT staleness guard: changing pack membership drops the
recorded run so go-live requires a fresh passing corpus run.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.education import ops_bot_spec, ops_corpus
from src.education.ops_bot_spec import (
    default_bot_spec_data,
    install_compiled_spec,
    load_compiled_spec,
    write_bot_spec,
)
from src.education.ops_classifier import classify_ops_message

client = TestClient(web.app)

TODAY = date(2026, 7, 28)  # a Tuesday


@pytest.fixture(autouse=True)
def _seams(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_OPS_BOT_SPEC_PATH", str(tmp_path / "bot_spec.yaml"))
    yield tmp_path / "bot_spec.yaml"
    install_compiled_spec(None)


def spec_with(data: dict) -> ops_bot_spec.CompiledBotSpec:
    return ops_bot_spec._compile_from_data(data)


# ------------------------------------------------------------------ runner


def test_parity_corpus_all_pack_samples_pass():
    result = ops_corpus.run_corpus(load_compiled_spec(), today=TODAY)
    assert result.total == 18  # 5 launch packs' shipped samples
    assert result.failed == 0
    assert result.passed is True
    assert {row.source for row in result.rows} == {
        "absence_coverage",
        "announcements",
        "facilities",
        "schedule_changes",
        "student_logistics",
    }


def test_relative_dates_resolve_against_injected_today():
    assert ops_corpus.resolve_expected_date("+0d", TODAY) == "2026-07-28"
    assert ops_corpus.resolve_expected_date("+1d", TODAY) == "2026-07-29"
    assert ops_corpus.resolve_expected_date("+7d", TODAY) == "2026-08-04"
    # Unresolvable tokens are None → the row fails explicitly, no crash.
    assert ops_corpus.resolve_expected_date("friday", TODAY) is None
    assert ops_corpus.resolve_expected_date("", TODAY) is None


def test_result_hash_stable_across_reference_days():
    spec = load_compiled_spec()
    run_a = ops_corpus.run_corpus(spec, today=date(2026, 7, 28))
    run_b = ops_corpus.run_corpus(spec, today=date(2026, 12, 3))
    assert run_a.passed and run_b.passed
    assert run_a.result_hash == run_b.result_hash


def test_admin_sentences_included_and_failures_counted():
    data = default_bot_spec_data()
    data["corpus"]["admin_sentences"] = [
        {"text": "Reminder: bring the permission slips.", "expect": {"category": "reminder"}},
        {"text": "Totally unrelated chatter.", "expect": {"category": "schedule_change"}},
    ]
    result = ops_corpus.run_corpus(spec_with(data), today=TODAY)
    assert result.total == 20
    assert result.failed == 1
    assert result.passed is False
    bad = next(row for row in result.rows if not row.ok)
    assert bad.source == "admin"
    assert "category" in bad.mismatches
    assert bad.actual["category"] == "other"


def test_unknown_expect_key_fails_that_row():
    data = default_bot_spec_data()
    data["corpus"]["admin_sentences"] = [
        {"text": "I'm sick today.", "expect": {"category": "absence", "catgory": "absence"}}
    ]
    result = ops_corpus.run_corpus(spec_with(data), today=TODAY)
    bad = next(row for row in result.rows if row.source == "admin")
    assert bad.ok is False
    assert "unknown expectation: catgory" in bad.mismatches


def test_expectation_missing_category_fails_row():
    data = default_bot_spec_data()
    data["corpus"]["admin_sentences"] = [
        {"text": "I'm sick today.", "expect": {"confidence": "high"}}
    ]
    result = ops_corpus.run_corpus(spec_with(data), today=TODAY)
    bad = next(row for row in result.rows if row.source == "admin")
    assert bad.ok is False
    assert "expectation missing category" in bad.mismatches


def test_empty_corpus_never_passes():
    data = default_bot_spec_data(enabled_pack_ids=[])
    result = ops_corpus.run_corpus(spec_with(data), today=TODAY)
    assert result.total == 0
    assert result.passed is False


def test_channel_directive_runs_sample_as_ops_post():
    # "Welcome back..." only classifies announcement POSITIONALLY (the
    # ops-channel default bucket) — proof the channel directive is honored.
    data = default_bot_spec_data()
    data["corpus"]["admin_sentences"] = [
        {
            "text": "Welcome back everyone, great first day!",
            "expect": {"category": "announcement", "channel": "ops"},
        }
    ]
    result = ops_corpus.run_corpus(spec_with(data), today=TODAY)
    admin_row = next(row for row in result.rows if row.source == "admin")
    assert admin_row.ok, admin_row.mismatches


# ------------------------------------------------------------- corpus routes


def test_corpus_run_route_requires_saved_bot_spec(_seams):
    response = client.post("/api/ops/setup/corpus/run", json={})
    assert response.status_code == 409
    assert "bot-spec" in response.json()["error"].lower()
    assert not _seams.exists()


def test_corpus_run_route_refuses_fallback_spec(_seams):
    _seams.write_bytes(b"[unclosed")
    response = client.post("/api/ops/setup/corpus/run", json={})
    assert response.status_code == 409
    assert _seams.read_bytes() == b"[unclosed"  # never overwritten


def test_corpus_run_records_last_run_and_unlocks_go_live(_seams):
    write_bot_spec(default_bot_spec_data())
    # Gate closed before any run.
    assert client.put("/api/ops/setup/bot-spec", json={"live": True}).status_code == 409
    response = client.post("/api/ops/setup/corpus/run", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["passed"] is True
    assert payload["run"]["total"] == 18
    assert len(payload["run"]["result_hash"]) == 64
    assert all(row["ok"] for row in payload["rows"])
    # Recorded on disk → the gate opens.
    on_disk = load_compiled_spec()
    assert on_disk.corpus_last_run["passed"] is True
    response = client.put("/api/ops/setup/bot-spec", json={"live": True})
    assert response.status_code == 200
    assert response.json()["live"] is True


def test_corpus_run_records_failing_run_and_gate_stays_closed(_seams):
    data = default_bot_spec_data()
    data["corpus"]["admin_sentences"] = [
        {"text": "Totally unrelated chatter.", "expect": {"category": "reminder"}}
    ]
    write_bot_spec(data)
    payload = client.post("/api/ops/setup/corpus/run", json={}).json()
    assert payload["run"]["passed"] is False
    assert payload["run"]["failed"] == 1
    assert client.put("/api/ops/setup/bot-spec", json={"live": True}).status_code == 409


def test_add_sentence_clears_recorded_run(_seams):
    data = default_bot_spec_data()
    data["corpus"]["last_run"] = {"at": "x", "passed": True, "result_hash": "abc"}
    write_bot_spec(data)
    response = client.post(
        "/api/ops/setup/corpus/sentences",
        json={"text": "Gym is closed for repairs.", "expect": {"category": "facilities"}},
    )
    assert response.status_code == 200
    state = response.json()
    assert len(state["corpus"]["admin_sentences"]) == 1
    assert state["corpus"]["last_run"] is None  # stale — must re-run
    assert client.put("/api/ops/setup/bot-spec", json={"live": True}).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"text": "", "expect": {"category": "reminder"}},
        {"text": "hi", "expect": {}},
        {"text": "hi", "expect": {"category": "not_a_category"}},
        {"text": "hi", "expect": {"category": "reminder", "catgory": "x"}},
    ],
)
def test_add_sentence_validation(_seams, body):
    write_bot_spec(default_bot_spec_data())
    response = client.post("/api/ops/setup/corpus/sentences", json=body)
    assert response.status_code == 400


def test_put_changing_packs_drops_recorded_run(_seams):
    data = default_bot_spec_data()
    data["corpus"]["last_run"] = {"at": "x", "passed": True, "result_hash": "abc"}
    write_bot_spec(data)
    response = client.put(
        "/api/ops/setup/bot-spec",
        json={"packs": {"enabled": ["absence_coverage", "announcements"]}},
    )
    assert response.status_code == 200
    assert response.json()["corpus"]["last_run"] is None
    # Routing changed since the recorded run → go-live closed again.
    assert client.put("/api/ops/setup/bot-spec", json={"live": True}).status_code == 409


def test_put_without_routing_change_keeps_recorded_run(_seams):
    data = default_bot_spec_data()
    data["corpus"]["last_run"] = {"at": "x", "passed": True, "result_hash": "abc"}
    write_bot_spec(data)
    response = client.put(
        "/api/ops/setup/bot-spec",
        json={"settings": {"briefing_hhmm": "06:45"}},
    )
    assert response.json()["corpus"]["last_run"]["result_hash"] == "abc"


# ------------------------------------------------------------ rule decisions


def candidate_spec_data(keyphrase: str, category: str) -> dict:
    data = default_bot_spec_data()
    rule = ops_bot_spec.new_candidate_rule(
        category=category, keyphrase=keyphrase, source_record_id="rec-1"
    )
    data["learned_rules"] = [rule]
    return data


def test_reject_candidate_records_decision_no_compile(_seams):
    data = candidate_spec_data("door duty", "student_logistics")
    rule_id = data["learned_rules"][0]["id"]
    write_bot_spec(data)
    response = client.post(
        "/api/ops/setup/rules/decide", json={"rule_id": rule_id, "action": "reject"}
    )
    assert response.status_code == 200
    state = response.json()
    assert state["decided_rule"]["status"] == "rejected"
    assert state["learned_rules"][0]["status"] == "rejected"
    # Rejected rules never compile in.
    ops_bot_spec.refresh_from_disk()
    assert (
        classify_ops_message("Door duty starts Monday.", today=TODAY).category
        == "other"
    )


def test_approve_candidate_corpus_pass_goes_live_in_classifier(_seams):
    data = candidate_spec_data("door duty", "student_logistics")
    rule_id = data["learned_rules"][0]["id"]
    write_bot_spec(data)
    ops_bot_spec.refresh_from_disk()
    # Candidate: NOT live before approval (spec §4).
    assert (
        classify_ops_message("Door duty starts Monday.", today=TODAY).category
        == "other"
    )
    response = client.post(
        "/api/ops/setup/rules/decide", json={"rule_id": rule_id, "action": "approve"}
    )
    assert response.status_code == 200
    state = response.json()
    assert state["decided_rule"]["status"] == "approved"
    # The passing run (which INCLUDED the rule) was recorded.
    assert state["corpus"]["last_run"]["passed"] is True
    assert state["corpus_run"]["run"]["total"] == 18
    # Approved → compiled in and live via the atomic swap.
    assert (
        classify_ops_message("Door duty starts Monday.", today=TODAY).category
        == "student_logistics"
    )


def test_approve_that_breaks_corpus_is_refused_atomically(_seams):
    # "out of paper" would reroute the shipped absence-pack sample
    # "I'm out of paper for the copier." (expected: other) → the gate
    # must refuse and change NOTHING (zero previously-passing samples
    # may change routing, spec §4/§7).
    data = candidate_spec_data("out of paper", "facilities")
    rule_id = data["learned_rules"][0]["id"]
    write_bot_spec(data)
    response = client.post(
        "/api/ops/setup/rules/decide", json={"rule_id": rule_id, "action": "approve"}
    )
    assert response.status_code == 409
    body = response.json()
    assert "corpus" in body["error"].lower()
    assert body["rows"] and not body["rows"][0]["ok"]
    # Nothing written: rule still candidate, no run recorded, not compiled.
    on_disk = load_compiled_spec()
    assert on_disk.learned_rules[0]["status"] == "candidate"
    assert on_disk.corpus_last_run is None
    ops_bot_spec.refresh_from_disk()
    assert (
        classify_ops_message("We are out of paper again.", today=TODAY).category
        == "other"
    )


def test_decide_guards(_seams):
    # No bot-spec at all.
    response = client.post(
        "/api/ops/setup/rules/decide", json={"rule_id": "lr-x", "action": "approve"}
    )
    assert response.status_code == 409
    # Unknown rule / bad action / non-candidate status.
    data = candidate_spec_data("door duty", "student_logistics")
    data["learned_rules"][0]["status"] = "approved"
    rule_id = data["learned_rules"][0]["id"]
    write_bot_spec(data)
    assert (
        client.post(
            "/api/ops/setup/rules/decide",
            json={"rule_id": "lr-nope", "action": "approve"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/ops/setup/rules/decide", json={"rule_id": rule_id, "action": "banish"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/ops/setup/rules/decide", json={"rule_id": rule_id, "action": "approve"}
        ).status_code
        == 409
    )
