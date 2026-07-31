"""
`lv audit` — gap-signal lagging-indicator audit
(SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md, MC lessons port).

Contract highlights under test:
- read-only over gap_signals.ndjson; writes only its own summary journal
  and only with --journal-write
- delta-first exit: baseline present -> exit 1 only on NEW drift
- exact vocabulary membership (no prefix tolerance)
- fail-visible degradation: malformed lines counted, corrupt baseline
  fields read as "no data" (drift counts as NEW), never a crash
- windowed runs are conservative and never become baselines
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.lingua_viva import gap_audit
from src.lingua_viva.gap_audit import (
    AGING_HIT_THRESHOLD,
    KNOWN_SIGNAL_FAMILIES,
    REPEAT_THRESHOLD,
    audit_family_distribution,
    audit_repeat_signals,
    audit_vocabulary,
    build_report,
    build_summary_record,
    compute_delta,
    find_baseline,
    has_absolute_warn,
    load_entries,
    run_audit,
    signal_family,
)


def _write_signals(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _entry(node: str, signals: list[str]) -> dict:
    return {"entry_node": node, "domain": "core", "gap_signals": signals,
            "timestamp": time.time(), "session_id": "s"}


@pytest.fixture
def files(tmp_path):
    return {
        "signals": tmp_path / "gap_signals.ndjson",
        "summaries": tmp_path / "gap_audit_summaries.ndjson",
        "firewall": tmp_path / "firewall_log.ndjson",
        "proposals": tmp_path / "proposals",
    }


def _run(files, **kwargs) -> int:
    return run_audit(
        signals_file=files["signals"],
        summaries_file=files["summaries"],
        firewall_file=files["firewall"],
        proposals_dir=files["proposals"],
        **kwargs,
    )


# --- primitives ---

def test_signal_family_splits_on_first_colon():
    assert signal_family("sensitive:child_name:high") == "sensitive"
    assert signal_family("research_blocked_by_entry_gate") == "research_blocked_by_entry_gate"
    assert signal_family("") == ""
    assert signal_family(None) == ""  # wrong type degrades, never crashes


def test_load_entries_counts_malformed_lines_never_crashes(files):
    files["signals"].write_text(
        json.dumps(_entry("N1", ["integrity:x"])) + "\n"
        + "{not json\n"
        + json.dumps(["a", "list", "not", "a", "dict"]) + "\n"
        + json.dumps(_entry("N2", ["contradiction:y"])) + "\n",
        encoding="utf-8",
    )
    entries, malformed = load_entries(files["signals"])
    assert len(entries) == 2
    assert malformed == 2


def test_load_entries_missing_file_is_empty(files):
    assert load_entries(files["signals"]) == ([], 0)


# --- indicators ---

def test_repeat_signals_threshold_per_family_node_pair():
    entries = ([_entry("LV-CUR-003", ["skipped_research:self_sufficient"])] * REPEAT_THRESHOLD
               + [_entry("OTHER", ["skipped_research:self_sufficient"])] * (REPEAT_THRESHOLD - 1))
    repeats = audit_repeat_signals(entries)
    assert repeats == {"skipped_research@LV-CUR-003": REPEAT_THRESHOLD}


def test_distribution_concentration_and_fragmentation():
    concentrated = [_entry("N", ["integrity:a"])] * 6 + [_entry("N", ["contradiction:b"])] * 4
    dist = audit_family_distribution(concentrated)
    assert dist["top_family"] == "integrity"
    assert dist["concentration_warn"] is True
    assert dist["fragmentation_warn"] is False

    fragmented = [_entry("N", [f"fam_{i}:x"]) for i in range(12)]
    dist = audit_family_distribution(fragmented)
    assert dist["fragmentation_warn"] is True

    assert audit_family_distribution([])["total"] == 0


def test_vocabulary_exact_membership_no_prefix_tolerance():
    # MC pass-10 lesson: 'integrity_extended' shares a prefix with a known
    # family but is NOT in the emitter set — it must be flagged as drift.
    entries = [_entry("N", ["integrity_extended:x", "integrity:ok", "voice_loop_failure:stt_mismatch", "brand_new_family"])]
    assert audit_vocabulary(entries) == ["brand_new_family", "integrity_extended"]
    assert "integrity" in KNOWN_SIGNAL_FAMILIES
    assert "voice_loop_failure" in KNOWN_SIGNAL_FAMILIES


def test_aging_candidates_and_unavailable_degradation(files, tmp_path):
    from ontology.proposals.candidate import CandidateStore

    store = CandidateStore(files["proposals"])
    cand = store.create(query="q", query_hash="h", fallback_node="F",
                        fallback_confidence=0.2, signals=["s"], domain="core")
    cand.hit_count = AGING_HIT_THRESHOLD
    store._save(cand)
    report = build_report(files["signals"], files["firewall"], files["proposals"])
    assert [c["id"] for c in report["aging_candidates"]] == [cand.candidate_id]

    # resolved candidates never age
    cand.status = "DISCARDED"
    store._save(cand)
    report = build_report(files["signals"], files["firewall"], files["proposals"])
    assert report["aging_candidates"] == []


# --- exit semantics ---

def test_no_data_exits_zero(files, capsys):
    assert _run(files) == 0
    assert "No gap-signal data" in capsys.readouterr().out


def test_absolute_warn_without_baseline_exits_one(files, capsys):
    _write_signals(files["signals"],
                   [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD)
    assert _run(files) == 1
    out = capsys.readouterr().out
    assert "VERDICT: WARN" in out
    assert "--journal-write" in out  # tells the operator how to set a baseline


def test_baseline_makes_known_drift_exit_zero(files, capsys):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    assert _run(files, journal_write=True) == 1  # first run: absolute, journals baseline
    capsys.readouterr()
    assert _run(files) == 0  # same drift, now known
    out = capsys.readouterr().out
    assert "EXIT 0 — no NEW drift" in out
    assert "VERDICT: WARN" in out  # absolute report still visible


def test_new_drift_after_baseline_exits_one(files, capsys):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    assert _run(files, journal_write=True) == 1
    _write_signals(files["signals"],
                   rows + [_entry("M", ["never_seen_family:z"])])
    capsys.readouterr()
    assert _run(files) == 1
    assert "NEW drift since baseline: never_seen_family" in capsys.readouterr().out


def test_strict_ignores_baseline(files):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    assert _run(files, journal_write=True) == 1
    assert _run(files) == 0
    assert _run(files, strict=True) == 1


def test_corrupt_baseline_degrades_drift_counts_as_new(files):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    files["summaries"].write_text(
        json.dumps({"window": "full", "repeat_pairs": "not-a-list",
                    "oov_families": 42, "top_share": "high",
                    "aging_candidate_ids": None, "ts": "yesterday"}) + "\n",
        encoding="utf-8",
    )
    # baseline exists but its fields are garbage -> read as no data -> NEW drift
    assert _run(files) == 1


def test_windowed_summary_never_becomes_baseline(files):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    assert _run(files, journal_write=True, last=2) == 0  # window hides the repeat
    # windowed summary journaled but must not serve as baseline
    assert find_baseline(files["summaries"]) is None
    assert _run(files) == 1  # still absolute semantics


def test_last_rejects_non_positive(files, capsys):
    assert _run(files, last=0) == 2
    assert _run(files, last=-3) == 2


def test_windowed_delta_conservative_never_false_alarms(files):
    rows = [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD
    _write_signals(files["signals"], rows)
    assert _run(files, journal_write=True) == 1  # full baseline
    _write_signals(files["signals"], rows + [_entry("Q", ["integrity:ok"])])
    assert _run(files, last=1) == 0  # window sees no repeat -> no NEW drift


def test_journal_write_only_touches_summaries(files):
    rows = [_entry("N", ["integrity:ok"])]
    _write_signals(files["signals"], rows)
    before = files["signals"].read_text(encoding="utf-8")
    _run(files)
    assert not files["summaries"].exists()  # no write without the flag
    _run(files, journal_write=True)
    assert files["summaries"].exists()
    assert files["signals"].read_text(encoding="utf-8") == before  # read-only


def test_summary_record_shape(files):
    _write_signals(files["signals"], [_entry("N", ["integrity:ok"])])
    report = build_report(files["signals"], files["firewall"], files["proposals"])
    record = build_summary_record(report)
    assert record["window"] == "full"
    assert set(record) >= {"ts", "record_count", "repeat_pairs", "oov_families",
                           "top_share", "aging_candidate_ids", "firewall_count"}


def test_firewall_is_informational_never_gates(files):
    _write_signals(files["signals"], [_entry("N", ["integrity:ok"])])
    files["firewall"].write_text("{}\n" * 50, encoding="utf-8")
    assert _run(files) == 0  # firewall volume alone never exits 1
    report = build_report(files["signals"], files["firewall"], files["proposals"])
    baseline = build_summary_record(report)
    files["firewall"].write_text("{}\n" * 80, encoding="utf-8")
    report2 = build_report(files["signals"], files["firewall"], files["proposals"])
    delta = compute_delta(report2, baseline)
    assert delta["firewall_delta"] == 30
    assert delta["has_new_drift"] is False


def test_json_output_machine_readable(files, capsys):
    _write_signals(files["signals"],
                   [_entry("N", ["skipped_research:x"])] * REPEAT_THRESHOLD)
    code = _run(files, json_out=True)
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == code == 1
    assert payload["exit_basis"] == "absolute"
    assert payload["window"] == "full"
    assert payload["report"]["repeat_pairs"] == {"skipped_research@N": REPEAT_THRESHOLD}
    assert payload["journaled"] is False


def test_has_absolute_warn_axes():
    assert has_absolute_warn({"repeat_pairs": {"a@b": 3}}) is True
    assert has_absolute_warn({"oov_families": ["x"]}) is True
    assert has_absolute_warn({"distribution": {"concentration_warn": True}}) is True
    assert has_absolute_warn({"aging_candidates": [{"id": "CAND-1"}]}) is True
    assert has_absolute_warn({"repeat_pairs": {}, "oov_families": [],
                              "distribution": {}, "aging_candidates": []}) is False


# --- CLI wiring ---

def test_cli_audit_dispatch(files, monkeypatch, capsys):
    from src.lingua_viva.cli import main

    monkeypatch.setattr(gap_audit, "DEFAULT_SIGNALS_FILE", files["signals"])
    captured = {}

    def fake_run_audit(last=None, journal_write=False, strict=False, json_out=False, **_):
        captured.update(last=last, journal_write=journal_write,
                        strict=strict, json_out=json_out)
        return 0

    monkeypatch.setattr(gap_audit, "run_audit", fake_run_audit)
    assert main(["audit", "--last", "5", "--strict", "--json"]) == 0
    assert captured == {"last": 5, "journal_write": False,
                        "strict": True, "json_out": True}
