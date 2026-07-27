"""
Tests for src/lingua_viva/improvement_audit.py (`lv distill`).

Spec: dev/specs/SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md.
Hermetic: all store paths go through env vars (LV_GAP_SIGNALS_PATH,
LV_REVISION_LOG_PATH, LV_AUDIT_SUMMARY_PATH) resolved lazily per call —
the conftest autouse fixture clears LV_*; each test sets its own tmp path.
"""

from __future__ import annotations

import json

import pytest

from ontology.proposals.candidate import CandidateRIU
from src.lingua_viva.improvement_audit import (
    audit_defect_concentration,
    audit_proxy_to_live,
    append_summary_record,
    build_audit_report,
    compute_delta,
    distill_gap_signals,
    previous_summary,
    read_gap_signals,
    reconcile_with_candidates,
    replay_candidates,
    summary_record,
    STRUCTURAL_FLOOR_WINDOW,
)


def _gap(node="LV-CUR-003", signal="skipped_research:self_sufficient",
         session="s1", ts=1784391026.0):
    return {"entry_node": node, "domain": "curriculum", "gap_signals": [signal],
            "timestamp": ts, "session_id": session}


def _cand(cid="CAND-AAAA0001", status="CREATED", fallback="CORE-RESEARCH",
          query="how do refugee schools teach languages", confidence=0.3):
    return CandidateRIU(
        candidate_id=cid, status=status, original_query=query,
        fallback_node=fallback, fallback_confidence=confidence,
    )


def _rev(defect_class="publication_wording", instrument="phase0_claim_audit",
         revision_id="lv-rev-x"):
    return {"defect_class": defect_class, "instrument_that_found_it": instrument,
            "revision_id": revision_id}


# --- distill_gap_signals ---

def test_breadth_counts_distinct_sessions_not_rows():
    # 5 rows from ONE session vs 3 rows from THREE sessions: the
    # three-session cluster ranks first (evidence breadth, MC A2 lesson).
    entries = [_gap(signal="loop_wall", session="s1") for _ in range(5)]
    entries += [_gap(node="CORE-PROTECT", signal="entry_gate_blocked:high",
                     session=s) for s in ("a", "b", "c")]
    clusters = distill_gap_signals(entries)
    assert clusters[0]["entry_node"] == "CORE-PROTECT"
    assert clusters[0]["breadth"] == 3
    assert clusters[0]["count"] == 3
    assert clusters[1]["breadth"] == 1
    assert clusters[1]["count"] == 5


def test_distill_timestamps_and_missing_session():
    entries = [
        _gap(session="", ts=1784391026.0),          # no session_id -> breadth still >= 1
        _gap(session="", ts=1785000000.0),
    ]
    (c,) = distill_gap_signals(entries)
    assert c["breadth"] == 1
    assert c["count"] == 2
    assert c["first_seen"] == "2026-07-18"
    assert c["last_seen"] == "2026-07-25"


def test_informational_signals_rank_after_walls():
    # skipped_research is working-as-designed telemetry (2026-07-27 finding:
    # a benign self-sufficiency cluster outranked every real wall) — it must
    # sort after ANY wall regardless of breadth.
    entries = [_gap(node="LV-CUR-003", signal="skipped_research:self_sufficient",
                    session=f"s{i}") for i in range(40)]
    entries += [_gap(node="CORE-PROTECT", signal="entry_gate_blocked:high",
                     session=s) for s in ("a", "b")]
    clusters = distill_gap_signals(entries)
    assert clusters[0]["entry_node"] == "CORE-PROTECT"
    assert not clusters[0]["informational"]
    assert clusters[1]["informational"]
    assert clusters[1]["breadth"] == 40


def test_suspected_burst_flags_machine_cadence_sessions():
    # 6 rows, 6 "distinct" sessions, 5s apart -> harness-minted UUIDs
    fast = [_gap(session=f"u{i}", ts=1784391000.0 + i * 5) for i in range(6)]
    (c,) = distill_gap_signals(fast)
    assert c["suspected_burst"]

    # same breadth spread over hours -> organic, no flag
    slow = [_gap(session=f"u{i}", ts=1784391000.0 + i * 3600) for i in range(6)]
    (c,) = distill_gap_signals(slow)
    assert not c["suspected_burst"]

    # below the row floor never flags, even at machine cadence
    few = [_gap(session=f"u{i}", ts=1784391000.0 + i * 5) for i in range(4)]
    (c,) = distill_gap_signals(few)
    assert not c["suspected_burst"]


def test_read_gap_signals_skips_torn_lines(tmp_path, monkeypatch):
    path = tmp_path / "gaps.ndjson"
    path.write_text(
        json.dumps(_gap()) + "\n" + '{"torn": "reco' + "\n" + json.dumps(_gap()) + "\n",
        encoding="utf-8")
    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(path))
    assert len(read_gap_signals()) == 2


def test_read_gap_signals_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(tmp_path / "nope.ndjson"))
    assert read_gap_signals() == []


# --- reconcile_with_candidates (latest-outcome-wins retirement) ---

def test_cluster_without_candidates_stays_active():
    active, retired = reconcile_with_candidates(
        distill_gap_signals([_gap()]), [])
    assert len(active) == 1 and retired == []
    assert active[0]["candidates"] == []


def test_cluster_with_open_candidate_stays_active_with_linkage():
    cand = _cand(status="ENRICHED", fallback="LV-CUR-003")
    active, retired = reconcile_with_candidates(
        distill_gap_signals([_gap(node="LV-CUR-003")]), [cand])
    assert len(active) == 1 and retired == []
    assert active[0]["candidates"] == [
        {"candidate_id": cand.candidate_id, "status": "ENRICHED"}]


def test_cluster_retired_only_when_all_candidates_resolved():
    resolved = [_cand("CAND-1", "PROMOTED", "LV-CUR-003"),
                _cand("CAND-2", "DISCARDED", "LV-CUR-003")]
    active, retired = reconcile_with_candidates(
        distill_gap_signals([_gap(node="LV-CUR-003")]), resolved)
    assert active == [] and len(retired) == 1

    mixed = resolved + [_cand("CAND-3", "CREATED", "LV-CUR-003")]
    active, retired = reconcile_with_candidates(
        distill_gap_signals([_gap(node="LV-CUR-003")]), mixed)
    assert len(active) == 1 and retired == []


# --- replay_candidates (already_shipped gate, LV edition) ---

def test_replay_skips_resolved_candidates():
    queue = replay_candidates(
        [_cand(status="PROMOTED"), _cand("CAND-2", status="DISCARDED")],
        classify_fn=lambda q: ("LV-NEW-001", 0.9))
    assert queue == []


def test_replay_flags_query_routing_to_different_node():
    (q,) = replay_candidates(
        [_cand(fallback="CORE-RESEARCH")],
        classify_fn=lambda _: ("LV-CUR-001", 0.4))
    assert q["reason"] == "routes_to_different_node"
    assert q["now_classifies_to"] == "LV-CUR-001"


def test_replay_flags_confidence_recovery_on_same_node():
    (q,) = replay_candidates(
        [_cand(fallback="CORE-RESEARCH", confidence=0.3)],
        classify_fn=lambda _: ("CORE-RESEARCH", 0.75))
    assert q["reason"] == "confidence_recovered"


def test_replay_does_not_flag_unchanged_gap():
    queue = replay_candidates(
        [_cand(fallback="CORE-RESEARCH")],
        classify_fn=lambda _: ("CORE-RESEARCH", 0.3))
    assert queue == []


# --- audit_defect_concentration ---

def test_concentration_empty():
    result = audit_defect_concentration([])
    assert result["total"] == 0 and not result["warn"]


def test_concentration_below_floor_never_warns():
    entries = [_rev("only_class") for _ in range(STRUCTURAL_FLOOR_WINDOW - 1)]
    result = audit_defect_concentration(entries)
    assert result["top_share"] == 1.0
    assert not result["meets_floor"] and not result["warn"]


def test_concentration_warn_over_floor():
    entries = [_rev("dominant") for _ in range(15)] + [_rev(f"c{i}") for i in range(6)]
    result = audit_defect_concentration(entries)  # 21 entries, top 15/21 = 71%
    assert result["meets_floor"]
    assert result["warn_concentration"] and result["warn"]


def test_fragmentation_warn_and_singleton_share():
    # 20 entries, 8 distinct classes (> 25% of 20), 6 singletons -> 75%
    entries = ([_rev("a") for _ in range(8)] + [_rev("b") for _ in range(6)]
               + [_rev(f"solo{i}") for i in range(6)])
    result = audit_defect_concentration(entries)
    assert result["distinct_classes"] == 8
    assert result["warn_fragmentation"]
    assert result["singleton_share"] == pytest.approx(6 / 8)
    assert not result["warn_concentration"]  # 8/20 = 40% < 50%


# --- audit_proxy_to_live ---

def test_proxy_to_live_transition_detected():
    entries = [_rev("publication_wording", "phase0_claim_audit", "lv-rev-001"),
               _rev("publication_wording", "doctor_readme_pattern_check", "lv-rev-005")]
    (t,) = audit_proxy_to_live(entries)
    assert t["proxy"] == "phase0_claim_audit"
    assert t["live"] == "doctor_readme_pattern_check"
    assert t["transitioned_at"] == "lv-rev-005"


def test_proxy_to_live_requires_proxy_first():
    # live-only, proxy-only, and live-then-proxy are all NOT transitions
    assert audit_proxy_to_live([_rev("a", "reflect_view")]) == []
    assert audit_proxy_to_live([_rev("b", "phase0_claim_audit")]) == []
    assert audit_proxy_to_live(
        [_rev("c", "reflect_view"), _rev("c", "phase0_claim_audit")]) == []


def test_proxy_to_live_first_transition_only():
    entries = [_rev("x", "manual_review", "r1"),
               _rev("x", "live_gate_a", "r2"),
               _rev("x", "live_gate_b", "r3")]
    (t,) = audit_proxy_to_live(entries)
    assert t["live"] == "live_gate_a" and t["transitioned_at"] == "r2"


# --- report / longitudinal ---

@pytest.fixture
def distill_env(tmp_path, monkeypatch):
    gaps = tmp_path / "gaps.ndjson"
    rev = tmp_path / "rev.ndjson"
    summary = tmp_path / "summary.ndjson"
    gaps.write_text("", encoding="utf-8")
    rev.write_text("", encoding="utf-8")
    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(gaps))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(rev))
    monkeypatch.setenv("LV_AUDIT_SUMMARY_PATH", str(summary))
    return {"gaps": gaps, "rev": rev, "summary": summary}


def test_build_report_end_to_end(distill_env):
    distill_env["gaps"].write_text(
        json.dumps(_gap(node="CORE-RESEARCH", session="s1")) + "\n"
        + json.dumps(_gap(node="LV-CUR-003", session="s2")) + "\n",
        encoding="utf-8")
    distill_env["rev"].write_text(json.dumps(_rev()) + "\n", encoding="utf-8")
    cands = [_cand("CAND-1", "PROMOTED", "LV-CUR-003"),
             _cand("CAND-2", "ENRICHED", "CORE-RESEARCH")]
    report = build_audit_report(
        classify_fn=lambda _: ("LV-NEW-009", 0.8), candidates=cands)
    assert len(report["active_clusters"]) == 1
    assert report["active_clusters"][0]["entry_node"] == "CORE-RESEARCH"
    assert len(report["retired_clusters"]) == 1
    assert [q["candidate_id"] for q in report["needs_review"]] == ["CAND-2"]
    assert report["defect_concentration"]["total"] == 1
    assert report["proxy_to_live"] == []


def test_report_without_classifier_marks_replay_skipped(distill_env):
    report = build_audit_report(classify_fn=None, candidates=[])
    assert report["needs_review"] is None


def test_summary_append_previous_delta_roundtrip(distill_env):
    report = build_audit_report(classify_fn=None, candidates=[])
    assert previous_summary() is None
    first = append_summary_record(report)
    assert previous_summary() == first

    distill_env["gaps"].write_text(
        json.dumps(_gap(session="s9")) + "\n", encoding="utf-8")
    second = summary_record(build_audit_report(classify_fn=None, candidates=[]))
    delta = compute_delta(first, second)
    assert delta == ["active gap clusters: 0 -> 1 ↑"]
    # equal runs produce no delta lines; None fields never produce lines
    assert compute_delta(first, dict(first)) == []
    assert compute_delta({"needs_review": None}, {"needs_review": 3}) == []
