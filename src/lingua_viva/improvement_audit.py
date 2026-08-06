"""
LV Measurement Distillation — the analysis half of LV's measurement stores.

Port of Mission Canvas's 2026-07-26 measurement-integrity hardening
(mission-canvas dev/SPEC_EXTERNAL_DISTILL_AUDIT_HARDENING_2026-07-26.md,
commit c890516e there) onto Lingua Viva's recorded-but-never-analyzed
stores. Spec: dev/specs/SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md.

Three append-only stores exist in this repo; before this module, nothing
read them for insight:

  memory/data/gap_signals.ndjson   — classification gaps per session
  ontology/proposals/CAND-*.yaml   — candidate nodes grown from those gaps
  dev/lv_revision_log.ndjson       — curated audit trail of shipped fixes

The MC lessons applied here:
  * evidence breadth: rank gap clusters by DISTINCT sessions, not raw rows
    (40 rows from one looping session is one wall, not forty)
  * latest-outcome-wins: a cluster whose candidates are all resolved
    (PROMOTED/DISCARDED) is retired from the active ranking — the
    append-only store is never rewritten
  * already_shipped gate: replay each active candidate's original query
    through today's engine; if the ontology has grown past the gap, flag
    it "possibly resolved" for HUMAN review (never auto-discard — the
    system proposes, the human disposes)
  * fragmentation/concentration metrics over revision-log defect classes,
    with structural floors reported honestly instead of faking a signal
  * proxy->live instrument transitions per defect class — informational,
    NEVER a WARN (a live instrument replacing a manual sweep is the goal)
  * longitudinal deltas via an opt-in summary record per run

All paths are resolved lazily per call (never module constants) — the
module-constant pattern broke test hermeticity twice before in this repo
(sanitizer/client.py SANITIZER_URL, 2026-07-20).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

def _state_home() -> Path:
    """Writable state directory — never inside the signed bundle (F6/P1-1)."""
    return Path(os.environ.get("LV_STATE_HOME", str(Path.home() / ".lingua-viva")))

# Instruments that are human sweeps / one-off audits rather than wired-in
# checks. A defect class first found by one of these and later found by a
# live instrument has "transitioned" — the lagging indicator MC calls #6.
PROXY_INSTRUMENTS = frozenset({
    "phase0_claim_audit",
    "manual_review",
    "operator_requested_whole_build_hardening",
})

# Floors identical to MC's improvement_audit so numbers are comparable
# across the two repos.
STRUCTURAL_FLOOR_WINDOW = 20   # min entries before concentration/fragmentation can WARN
CONCENTRATION_RATIO = 0.50     # one class over half the window -> systemic
FRAGMENTATION_RATIO = 0.25     # more distinct classes than 25% of window -> taxonomy churn

# A replayed candidate query classified at/above this confidence (or to a
# different node than its recorded fallback) suggests the ontology has
# grown past the gap. It is a prompt to review, not a verdict.
RESOLVED_CONFIDENCE = 0.6

# Signal families that record the system WORKING AS DESIGNED (research
# intentionally skipped), not a wall a user hit. First live run 2026-07-27
# ranked skipped_research:self_sufficient #1 with "43 sessions" — pipeline
# correctly serving CEFR queries from 4 tier-1/2 KL entries. Informational
# clusters are ranked after real walls, never above them.
INFORMATIONAL_SIGNAL_FAMILIES = frozenset({
    "skipped_research",
    "research_skipped_by_intent",
})

# Machine-cadence burst detection: eval harnesses that omit session_id get
# a fresh UUID per call (src/pipeline.py:540), which inflates breadth —
# the exact failure mode the A2 breadth lesson guards against, one level
# up. Rows arriving mostly < BURST_GAP_SECONDS apart across "distinct"
# sessions are flagged suspected_burst (a caveat on breadth, not a filter).
BURST_GAP_SECONDS = 30.0
BURST_MIN_ROWS = 5
BURST_FRACTION = 0.5


# --- Path resolution (lazy, env-overridable — hermetic under conftest) ---

def _gap_signals_path() -> Path:
    return Path(os.environ.get(
        "LV_GAP_SIGNALS_PATH", _state_home() / "gap_signals.ndjson"))


def _revision_log_path() -> Path:
    # Same env var src/web.py:_revision_log_path() already honors.
    return Path(os.environ.get(
        "LV_REVISION_LOG_PATH", _state_home() / "lv_revision_log.ndjson"))


def _summary_path() -> Path:
    return Path(os.environ.get(
        "LV_AUDIT_SUMMARY_PATH", _state_home() / "audit_summary.ndjson"))


def _read_ndjson(path: Path) -> list[dict]:
    """Read an append-only ndjson file, skipping torn/malformed lines.

    Append-only files can legitimately carry a torn final line (crash
    mid-write); one bad line must not take the whole instrument down.
    """
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            entries.append(record)
    return entries


def read_gap_signals() -> list[dict]:
    return _read_ndjson(_gap_signals_path())


def read_revision_log() -> list[dict]:
    return _read_ndjson(_revision_log_path())


# --- [1] Gap-signal distillation ---

def _iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


def distill_gap_signals(entries: list[dict]) -> list[dict]:
    """Aggregate raw gap-signal rows into clusters keyed (entry_node, signal).

    Breadth = distinct session_ids (evidence breadth, the MC A2 lesson);
    a single session looping on the same wall inflates `count` but not
    `breadth`, and breadth is what ranks.

    Two honesty caveats learned from the first live run (2026-07-27):
    `informational` marks working-as-designed signal families (ranked after
    real walls); `suspected_burst` marks machine-cadence rows whose
    "distinct" sessions were likely harness-minted UUIDs.
    """
    clusters: dict[tuple[str, str], dict] = {}
    for e in entries:
        node = str(e.get("entry_node") or "")
        session = str(e.get("session_id") or "")
        ts = e.get("timestamp") or 0.0
        for sig in e.get("gap_signals") or []:
            key = (node, str(sig))
            c = clusters.setdefault(key, {
                "entry_node": node, "signal": str(sig),
                "count": 0, "_sessions": set(), "_ts": [],
            })
            c["count"] += 1
            if session:
                c["_sessions"].add(session)
            try:
                tsf = float(ts)
            except (TypeError, ValueError):
                tsf = 0.0
            if tsf:
                c["_ts"].append(tsf)
    out = []
    for c in clusters.values():
        c["breadth"] = max(1, len(c.pop("_sessions")))
        ts_sorted = sorted(c.pop("_ts"))
        c["first_seen"] = _iso(ts_sorted[0]) if ts_sorted else ""
        c["last_seen"] = _iso(ts_sorted[-1]) if ts_sorted else ""
        gaps = [b - a for a, b in zip(ts_sorted, ts_sorted[1:])]
        fast = sum(1 for g in gaps if g < BURST_GAP_SECONDS)
        c["suspected_burst"] = bool(
            c["count"] >= BURST_MIN_ROWS and gaps and fast / len(gaps) > BURST_FRACTION)
        c["informational"] = (
            c["signal"].split(":", 1)[0] in INFORMATIONAL_SIGNAL_FAMILIES)
        out.append(c)
    out.sort(key=lambda c: (
        c["informational"], -c["breadth"], -c["count"], c["entry_node"], c["signal"]))
    return out


def reconcile_with_candidates(
    clusters: list[dict], candidates: list,
) -> tuple[list[dict], list[dict]]:
    """Split clusters into (active, retired) using candidate dispositions.

    Join key: cluster.entry_node == candidate.fallback_node (candidates are
    created exactly when a query falls back to that node). Latest-outcome-
    wins: a cluster is retired only when it has at least one matching
    candidate and ALL matching candidates are resolved (PROMOTED/DISCARDED)
    — the gap has been disposed. Any open candidate keeps it active.
    """
    by_node: dict[str, list] = {}
    for cand in candidates:
        by_node.setdefault(getattr(cand, "fallback_node", ""), []).append(cand)

    active: list[dict] = []
    retired: list[dict] = []
    for c in clusters:
        matches = by_node.get(c["entry_node"], [])
        c = dict(c)
        c["candidates"] = [
            {"candidate_id": m.candidate_id, "status": m.status} for m in matches
        ]
        resolved = [m for m in matches if m.status in ("PROMOTED", "DISCARDED")]
        if matches and len(resolved) == len(matches):
            retired.append(c)
        else:
            active.append(c)
    return active, retired


# --- [2] Candidate replay (the already_shipped gate, LV edition) ---

def replay_candidates(
    candidates: list,
    classify_fn: Callable[[str], tuple[str, float]],
) -> list[dict]:
    """Replay each unresolved candidate's original query through today's
    engine. Returns a NEEDS REVIEW queue of candidates whose gap the
    ontology may have grown past — a prompt to review, never a verdict,
    and never an automatic discard.
    """
    queue: list[dict] = []
    for cand in candidates:
        if getattr(cand, "status", "") in ("PROMOTED", "DISCARDED"):
            continue
        query = getattr(cand, "original_query", "") or ""
        if not query:
            continue
        riu_id, confidence = classify_fn(query)
        moved = bool(riu_id) and riu_id != cand.fallback_node
        confident = confidence >= RESOLVED_CONFIDENCE
        if moved or confident:
            queue.append({
                "candidate_id": cand.candidate_id,
                "status": cand.status,
                "fallback_node": cand.fallback_node,
                "fallback_confidence": cand.fallback_confidence,
                "now_classifies_to": riu_id,
                "now_confidence": round(confidence, 3),
                "reason": "routes_to_different_node" if moved else "confidence_recovered",
            })
    queue.sort(key=lambda q: q["candidate_id"])
    return queue


# --- [3] Revision-log defect-class concentration / fragmentation ---

def audit_defect_concentration(entries: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for e in entries:
        cls = str(e.get("defect_class") or "").strip()
        if cls:
            counts[cls] = counts.get(cls, 0) + 1
    total = sum(counts.values())
    top_class, top_n = ("", 0)
    if counts:
        top_class, top_n = max(counts.items(), key=lambda kv: kv[1])
    distinct_classes = len(counts)
    singletons = sum(1 for n in counts.values() if n == 1)
    singleton_share = (singletons / distinct_classes) if distinct_classes else 0.0
    meets_floor = total >= STRUCTURAL_FLOOR_WINDOW
    warn_concentration = meets_floor and top_n > total * CONCENTRATION_RATIO
    warn_fragmentation = meets_floor and distinct_classes > total * FRAGMENTATION_RATIO
    return {
        "total": total,
        "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "top_class": top_class,
        "top_share": (top_n / total) if total else 0.0,
        "distinct_classes": distinct_classes,
        "singleton_share": singleton_share,
        "meets_floor": meets_floor,
        "warn_concentration": warn_concentration,
        "warn_fragmentation": warn_fragmentation,
        "warn": warn_concentration or warn_fragmentation,
    }


# --- [4] Proxy -> live instrument transitions (lagging indicator) ---

def audit_proxy_to_live(entries: list[dict]) -> list[dict]:
    """First proxy->live transition per defect class, in log order.

    Informational and celebrated, NEVER a WARN: it means a manual sweep's
    job got taken over by a wired-in instrument.
    """
    seen_proxy: dict[str, str] = {}
    transitions: dict[str, dict] = {}
    for e in entries:
        cls = str(e.get("defect_class") or "").strip()
        inst = str(e.get("instrument_that_found_it") or "").strip()
        if not cls or not inst:
            continue
        if inst in PROXY_INSTRUMENTS:
            seen_proxy.setdefault(cls, inst)
        elif cls in seen_proxy and cls not in transitions:
            transitions[cls] = {
                "defect_class": cls,
                "proxy": seen_proxy[cls],
                "live": inst,
                "transitioned_at": str(e.get("timestamp") or e.get("revision_id") or ""),
            }
    return sorted(transitions.values(), key=lambda t: t["defect_class"])


# --- [5] Routing-memory report (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01) ---
#
# Consumption half of src/lingua_viva/routing_memory.py — the part the
# routing-loop doc says everyone skips ("nothing reads and acts on them").
# Reports and proposals ONLY: no threshold or signal list changes here or
# anywhere downstream; the operator disposes.

ROUTING_COLLAPSE_INTENT_SHARE = 0.90   # >90% one intent -> blind-spot flag
ROUTING_COLLAPSE_MIN_VOLUME = 10       # collapse needs a real window first
ROUTING_CATEGORY_CORRECTED_FLOOR = 50  # category-corrected obs before "never fires" means anything
ROUTING_PROPOSAL_MIN_FIRED = 5         # a signal must fire this often before
ROUTING_PROPOSAL_MIN_RATE = 0.5        # ... a >=50% correction rate proposes review


def _mean(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def build_routing_report(rows: list[dict], skipped: int = 0) -> dict:
    """Aggregate routing-memory rows into correction rates, per-signal
    precision proxies, collapse flags, and ranked human-readable proposals.

    Corrections with positive=True are confirmations (the suggestion was
    right) — they count toward volume, never toward correction_rate.
    Fitness = teacher correction, not "no error".
    """
    from src.lingua_viva.routing_memory import is_correction

    corrections_by_id: dict[str, list[dict]] = {}
    for row in rows:
        if is_correction(row):
            corrections_by_id.setdefault(
                str(row.get("decision_id") or ""), []).append(row["corrected"])

    per_type: dict[str, dict] = {}
    per_signal: dict[tuple[str, str], dict] = {}
    intent_outcomes: dict[str, int] = {}
    category_outcomes: set[str] = set()
    category_corrected_obs = 0
    decision_ids_seen: set[str] = set()

    for d in rows:
        if is_correction(d):
            continue
        decision_ids_seen.add(str(d.get("decision_id") or ""))
        dtype = str(d.get("decision") or "unknown")
        outcome = str(d.get("outcome") or "")
        try:
            conf = float(d.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        paired = corrections_by_id.get(str(d.get("decision_id") or ""), [])
        negatives = [c for c in paired if c.get("positive") is not True]
        confirmations = [c for c in paired if c.get("positive") is True]

        t = per_type.setdefault(dtype, {
            "volume": 0, "corrected": 0, "confirmed": 0,
            "_conf_corrected": [], "_conf_uncorrected": [],
        })
        t["volume"] += 1
        if negatives:
            t["corrected"] += 1
            t["_conf_corrected"].append(conf)
        else:
            t["_conf_uncorrected"].append(conf)
        if confirmations:
            t["confirmed"] += 1

        for key in d.get("signals_matched") or []:
            s = per_signal.setdefault((dtype, str(key)), {
                "decision": dtype, "signal": str(key), "fired": 0, "corrected": 0,
            })
            s["fired"] += 1
            if negatives:
                s["corrected"] += 1

        if dtype == "intent":
            intent_outcomes[outcome] = intent_outcomes.get(outcome, 0) + 1
        elif dtype == "category_suggest":
            if outcome:
                category_outcomes.add(outcome)
            if negatives:
                category_corrected_obs += 1

    for t in per_type.values():
        t["correction_rate"] = round(t["corrected"] / t["volume"], 3) if t["volume"] else 0.0
        t["confidence_corrected"] = _mean(t.pop("_conf_corrected"))
        t["confidence_uncorrected"] = _mean(t.pop("_conf_uncorrected"))

    signals = []
    for s in per_signal.values():
        s["precision_gap"] = round(s["corrected"] / s["fired"], 3) if s["fired"] else 0.0
        signals.append(s)
    signals.sort(key=lambda s: (-s["corrected"], -s["precision_gap"], s["decision"], s["signal"]))

    flags: list[dict] = []
    intent_total = sum(intent_outcomes.values())
    if intent_total >= ROUTING_COLLAPSE_MIN_VOLUME:
        top_intent, top_n = max(intent_outcomes.items(), key=lambda kv: kv[1])
        if top_n / intent_total > ROUTING_COLLAPSE_INTENT_SHARE:
            flags.append({
                "type": "intent_collapse", "outcome": top_intent,
                "share": round(top_n / intent_total, 3), "volume": intent_total,
            })
    if category_corrected_obs >= ROUTING_CATEGORY_CORRECTED_FLOOR:
        try:
            from src.education.observation_capture import CATEGORY_SIGNALS
            for cat in sorted(set(CATEGORY_SIGNALS) - category_outcomes):
                flags.append({
                    "type": "category_never_fires", "category_id": cat,
                    "category_corrected_observations": category_corrected_obs,
                })
        except Exception:  # shipped list unavailable — report without the flag
            pass

    proposals: list[str] = []
    for f in flags:
        if f["type"] == "intent_collapse":
            proposals.append(
                f"intent routing collapsed: {f['share']:.0%} of {f['volume']} decisions"
                f" landed on '{f['outcome']}' — the other signal lists have a blind"
                " spot (coverage gap, not a weight problem)")
        else:
            proposals.append(
                f"category '{f['category_id']}' never fired across"
                f" {f['category_corrected_observations']} category-corrected"
                " observations — its signal list may not match how teachers talk")
    for s in signals:
        if (s["fired"] >= ROUTING_PROPOSAL_MIN_FIRED
                and s["precision_gap"] >= ROUTING_PROPOSAL_MIN_RATE):
            proposals.append(
                f"signal {s['signal']!r} ({s['decision']}): fired {s['fired']}x,"
                f" corrected {s['corrected']}x ({s['precision_gap']:.0%}) — review"
                " this line in the shipped signal list")

    # Corrections referencing no known decision row (harmless by design —
    # record_decision returns an id even when its append fails — but a
    # rising count means a hook is threading the wrong id).
    dangling = sum(
        len(v) for k, v in corrections_by_id.items()
        if k not in decision_ids_seen)

    return {
        "total_rows": len(rows),
        "skipped_rows": skipped,
        "dangling_corrections": dangling,
        "per_type": dict(sorted(per_type.items())),
        "per_signal": signals,
        "collapse_flags": flags,
        "proposals": proposals,
    }


# --- Report assembly / longitudinal ---

def build_audit_report(
    classify_fn: Optional[Callable[[str], tuple[str, float]]] = None,
    candidates: Optional[list] = None,
) -> dict:
    if candidates is None:
        from ontology.proposals.candidate import CandidateStore
        store = CandidateStore()
        candidates = [
            c for c in (store.get(p.stem) for p in sorted(store._dir.glob("CAND-*.yaml")))
            if c is not None
        ]
    clusters = distill_gap_signals(read_gap_signals())
    active, retired = reconcile_with_candidates(clusters, candidates)
    revision_entries = read_revision_log()
    from src.lingua_viva.routing_memory import read_memory
    routing_rows, routing_skipped = read_memory()
    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "active_clusters": active,
        "retired_clusters": retired,
        "needs_review": (
            replay_candidates(candidates, classify_fn) if classify_fn else None
        ),
        "defect_concentration": audit_defect_concentration(revision_entries),
        "proxy_to_live": audit_proxy_to_live(revision_entries),
        "routing": build_routing_report(routing_rows, routing_skipped),
    }
    return report


def summary_record(report: dict) -> dict:
    conc = report["defect_concentration"]
    return {
        "timestamp": time.time(),
        "generated_at": report["generated_at"],
        "active_clusters": len(report["active_clusters"]),
        "retired_clusters": len(report["retired_clusters"]),
        "needs_review": (
            len(report["needs_review"]) if report["needs_review"] is not None else None
        ),
        "top_cluster": (
            {k: report["active_clusters"][0][k]
             for k in ("entry_node", "signal", "breadth", "count")}
            if report["active_clusters"] else None
        ),
        "revision_entries": conc["total"],
        "distinct_defect_classes": conc["distinct_classes"],
        "proxy_to_live_transitions": len(report["proxy_to_live"]),
        "routing_decisions": sum(
            t["volume"] for t in report.get("routing", {}).get("per_type", {}).values()),
        "routing_corrections": sum(
            t["corrected"] for t in report.get("routing", {}).get("per_type", {}).values()),
        "routing_collapse_flags": len(report.get("routing", {}).get("collapse_flags", [])),
    }


def append_summary_record(report: dict) -> dict:
    record = summary_record(report)
    path = _summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def previous_summary() -> Optional[dict]:
    records = _read_ndjson(_summary_path())
    return records[-1] if records else None


def compute_delta(prev: dict, cur: dict) -> list[str]:
    lines: list[str] = []
    for key, label in (
        ("active_clusters", "active gap clusters"),
        ("retired_clusters", "retired gap clusters"),
        ("needs_review", "candidates needing review"),
        ("proxy_to_live_transitions", "proxy->live transitions"),
        ("distinct_defect_classes", "distinct defect classes"),
        ("routing_decisions", "routing decisions"),
        ("routing_corrections", "routing corrections"),
        ("routing_collapse_flags", "routing collapse flags"),
    ):
        a, b = prev.get(key), cur.get(key)
        if a is None or b is None or a == b:
            continue
        arrow = "↓" if b < a else "↑"
        lines.append(f"{label}: {a} -> {b} {arrow}")
    return lines


def format_report(report: dict) -> str:
    lines: list[str] = []
    out = lines.append

    def _cluster_line(c: dict) -> str:
        cand = ""
        open_cands = [x for x in c["candidates"] if x["status"] not in ("PROMOTED", "DISCARDED")]
        if open_cands:
            cand = "  candidates: " + ", ".join(
                f"{x['candidate_id']}({x['status']})" for x in open_cands)
        burst = "  [burst? sessions likely harness-minted]" if c.get("suspected_burst") else ""
        return (f"  {c['entry_node']:<16} {c['signal']:<40} breadth={c['breadth']:>3}"
                f" count={c['count']:>4}  {c['first_seen']}..{c['last_seen']}{cand}{burst}")

    walls = [c for c in report["active_clusters"] if not c.get("informational")]
    info = [c for c in report["active_clusters"] if c.get("informational")]

    out("[1] GAP-SIGNAL CLUSTERS (breadth = distinct sessions — ranks; count = raw rows)")
    if not walls:
        out("  none — no unresolved classification walls on record")
    for c in walls:
        out(_cluster_line(c))
    if info:
        out("  -- informational (system worked as designed: research intentionally skipped) --")
        for c in info:
            out(_cluster_line(c))

    out("")
    out("[2] RETIRED CLUSTERS (all matching candidates disposed — latest outcome wins)")
    if not report["retired_clusters"]:
        out("  none")
    for c in report["retired_clusters"]:
        via = ", ".join(f"{x['candidate_id']}({x['status']})" for x in c["candidates"])
        out(f"  {c['entry_node']:<16} {c['signal']:<40} via {via}")

    out("")
    out("[3] CANDIDATES NEEDING REVIEW (ontology may have grown past the gap —")
    out("    a prompt to review by hand, not a verdict; nothing is auto-discarded)")
    if report["needs_review"] is None:
        out("  skipped (no classifier available this run)")
    elif not report["needs_review"]:
        out("  none — every open candidate still reproduces its gap")
    else:
        for q in report["needs_review"]:
            out(f"  {q['candidate_id']} ({q['status']}): fell back to"
                f" {q['fallback_node']}@{q['fallback_confidence']:.2f}, now"
                f" {q['now_classifies_to']}@{q['now_confidence']:.2f}"
                f" [{q['reason']}]")

    conc = report["defect_concentration"]
    out("")
    out("[4] REVISION-LOG DEFECT CONCENTRATION")
    if not conc["total"]:
        out("  no revision entries")
    else:
        for cls, n in conc["counts"].items():
            out(f"  {cls:<28} {n}")
        out(f"  total={conc['total']} distinct={conc['distinct_classes']}"
            f" top={conc['top_class']}({conc['top_share']:.0%})"
            f" singleton_share={conc['singleton_share']:.0%}")
        if not conc["meets_floor"]:
            out(f"  below structural floor ({conc['total']} < {STRUCTURAL_FLOOR_WINDOW})"
                " — concentration/fragmentation not yet meaningful, reported without WARN")
        if conc["warn_concentration"]:
            out(f"  WARN: {conc['top_class']} exceeds {CONCENTRATION_RATIO:.0%} of entries"
                " — systemic defect class")
        if conc["warn_fragmentation"]:
            out(f"  WARN: {conc['distinct_classes']} distinct classes over"
                f" {conc['total']} entries — taxonomy fragmenting")

    out("")
    out("[5] PROXY->LIVE INSTRUMENT TRANSITIONS (goal state — never a warning)")
    if not report["proxy_to_live"]:
        out("  none yet — defect classes are still found by manual sweeps only")
    for t in report["proxy_to_live"]:
        out(f"  {t['defect_class']}: {t['proxy']} -> {t['live']} ({t['transitioned_at']})")

    routing = report.get("routing") or {}
    out("")
    out("[6] ROUTING DECISIONS (append-only memory — reports and proposals only;")
    out("    no threshold or signal list is ever adjusted by this section)")
    if not routing.get("per_type"):
        out("  no routing memory on record")
    else:
        for dtype, t in routing["per_type"].items():
            conf_c = ("-" if t["confidence_corrected"] is None
                      else f"{t['confidence_corrected']:.2f}")
            conf_u = ("-" if t["confidence_uncorrected"] is None
                      else f"{t['confidence_uncorrected']:.2f}")
            out(f"  {dtype:<16} volume={t['volume']:>4}"
                f" corrected={t['corrected']:>3} ({t['correction_rate']:.0%})"
                f" confirmed={t['confirmed']:>3}"
                f"  conf corrected/uncorrected={conf_c}/{conf_u}")
        offenders = [s for s in routing["per_signal"] if s["corrected"]]
        if offenders:
            out("  worst signals (precision gap = share of firings later corrected):")
            for s in offenders[:8]:
                out(f"    {s['signal']:<44} ({s['decision']})"
                    f" fired={s['fired']:>3} corrected={s['corrected']:>3}"
                    f" ({s['precision_gap']:.0%})")
        if routing.get("collapse_flags"):
            out("  collapse flags:")
            for f in routing["collapse_flags"]:
                out(f"    {f}")
        if routing.get("proposals"):
            out("  proposals (the system proposes, the operator disposes):")
            for p in routing["proposals"]:
                out(f"    - {p}")
        if routing.get("skipped_rows"):
            out(f"  skipped rows: {routing['skipped_rows']} (unknown schema/malformed)")
        if routing.get("dangling_corrections"):
            out(f"  dangling corrections: {routing['dangling_corrections']}"
                " (reference no recorded decision — check hook id threading)")

    return "\n".join(lines)
