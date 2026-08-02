"""Gap-signal audit — the read-back loop for memory/data/gap_signals.ndjson.

SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md. Ported lessons from Mission Canvas's
`mc improve --audit` V2 (longitudinal delta exit semantics), not its code:

- Delta-first exit: with a journaled baseline, exit 1 only on NEW drift.
  `--strict` or no baseline = absolute. An audit that WARNs forever on
  historical state is noise to the loop that reads its exit code.
- Exact vocabulary membership: a signal family is either in
  KNOWN_SIGNAL_FAMILIES or it is drift. Never prefix-tolerant.
- Fail-visible degradation: malformed journal lines are skipped AND counted;
  wrong-typed baseline fields read as "no data" so drift counts as NEW.
  Never crash, never fail-silent.
- Reports, never gates: firewall activity is informational only.

Read-only over runtime state. Writes only its own summary journal
(gap_audit_summaries.ndjson) and only when asked (--journal-write).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Env overrides mirror lv distill's seam (improvement_audit.py). Needed for
# the frozen (PyInstaller) binary, where __file__ resolves into the extracted
# bundle temp dir and the repo-relative defaults see empty stores.
DEFAULT_SIGNALS_FILE = Path(os.environ.get(
    "LV_GAP_SIGNALS_PATH", REPO_ROOT / "memory" / "data" / "gap_signals.ndjson"))
DEFAULT_SUMMARIES_FILE = Path(os.environ.get(
    "LV_GAP_AUDIT_SUMMARIES_PATH",
    REPO_ROOT / "memory" / "data" / "gap_audit_summaries.ndjson"))
DEFAULT_FIREWALL_FILE = Path(os.environ.get(
    "LV_FIREWALL_LOG_PATH", REPO_ROOT / "memory" / "data" / "firewall_log.ndjson"))

# Exact write-side emitter set: src/pipeline.py + src/context_builder.py.
# If an emitter is added or renamed, the audit flags it as drift until this
# set is updated — that friction is the point (measurement parity).
KNOWN_SIGNAL_FAMILIES = frozenset({
    "entry_gate_blocked",
    "sensitive",
    "education_execute",
    "low_classification_confidence",
    "skipped_research",
    "research_blocked_by_entry_gate",
    "research_skipped_by_intent",
    "research_blocked_by_governance",
    "malicious_response",
    "research_gap",
    "contradiction",
    "integrity",
    "weak_classification",
    "no_knowledge_at_node",
    "voice_loop_failure",
})

REPEAT_THRESHOLD = 3
AGING_HIT_THRESHOLD = 5
TOP_SHARE_WARN = 0.50
MIN_VOLUME_FOR_CONCENTRATION = 10  # tiny samples always look concentrated
SINGLETON_SHARE_WARN = 0.50
MIN_FAMILIES_FOR_FRAGMENTATION = 10


# --- Fail-visible coercers: wrong type reads as "no data", never a crash ---

def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _as_num(value, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _as_str(value) -> str:
    return value if isinstance(value, str) else ""


def signal_family(signal: str) -> str:
    """Family = token before the first ':' (whole signal when no ':')."""
    return _as_str(signal).split(":", 1)[0].strip()


# --- Loaders ---

def load_entries(path: Path = DEFAULT_SIGNALS_FILE, last: int | None = None) -> tuple[list[dict], int]:
    """Read gap-signal records. Returns (entries, malformed_line_count).

    Unlike memory/ndjson_adapter.py's reader, malformed lines never crash the
    audit — they are skipped and counted so corruption stays visible.
    """
    if not path.exists():
        return [], 0
    entries: list[dict] = []
    malformed = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(record, dict):
                entries.append(record)
            else:
                malformed += 1
    if last is not None:
        entries = entries[-last:]
    return entries, malformed


def _count_ndjson_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# --- Indicators ---

def _iter_occurrences(entries: list[dict]):
    """Yield (family, node) per signal occurrence."""
    for entry in entries:
        node = _as_str(_as_dict(entry).get("entry_node")) or "(unknown)"
        for signal in _as_list(_as_dict(entry).get("gap_signals")):
            family = signal_family(signal)
            if family:
                yield family, node


def audit_repeat_signals(entries: list[dict]) -> dict[str, int]:
    """(family, node) pairs recurring >= REPEAT_THRESHOLD, as 'family@node'."""
    counts: dict[str, int] = {}
    for family, node in _iter_occurrences(entries):
        key = f"{family}@{node}"
        counts[key] = counts.get(key, 0) + 1
    return {k: v for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v >= REPEAT_THRESHOLD}


def audit_family_distribution(entries: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for family, _node in _iter_occurrences(entries):
        counts[family] = counts.get(family, 0) + 1
    total = sum(counts.values())
    if not total:
        return {"total": 0, "distinct_families": 0, "top_family": None,
                "top_share": 0.0, "singleton_share": 0.0,
                "concentration_warn": False, "fragmentation_warn": False}
    top_family, top_count = max(counts.items(), key=lambda kv: kv[1])
    singletons = sum(1 for c in counts.values() if c == 1)
    singleton_share = singletons / len(counts)
    return {
        "total": total,
        "distinct_families": len(counts),
        "top_family": top_family,
        "top_share": round(top_count / total, 3),
        "singleton_share": round(singleton_share, 3),
        "concentration_warn": (total >= MIN_VOLUME_FOR_CONCENTRATION
                               and top_count / total >= TOP_SHARE_WARN),
        "fragmentation_warn": (len(counts) >= MIN_FAMILIES_FOR_FRAGMENTATION
                               and singleton_share >= SINGLETON_SHARE_WARN),
    }


def audit_vocabulary(entries: list[dict]) -> list[str]:
    """Families outside KNOWN_SIGNAL_FAMILIES. Exact membership, no prefixes."""
    seen = {family for family, _node in _iter_occurrences(entries)}
    return sorted(seen - KNOWN_SIGNAL_FAMILIES)


def audit_aging_candidates(proposals_dir: Path | None = None) -> dict:
    """Open candidates with hit_count >= AGING_HIT_THRESHOLD (receipt decay:
    the gap was acknowledged with a candidate, then nobody resolved it)."""
    try:
        from ontology.proposals.candidate import CandidateStore
        store = CandidateStore(proposals_dir)
        aging = []
        for path in sorted(store._dir.glob("CAND-*.yaml")):
            candidate = store.get(path.stem)
            if candidate is None:
                continue
            resolved = candidate.status in ("PROMOTED", "DISCARDED") or (
                candidate.resolution or "").startswith("discarded")
            if not resolved and _as_num(candidate.hit_count) >= AGING_HIT_THRESHOLD:
                aging.append({"id": candidate.candidate_id,
                              "hits": int(_as_num(candidate.hit_count)),
                              "status": candidate.status})
        return {"aging": aging, "unavailable": None}
    except Exception as exc:  # degrade, never crash the audit
        return {"aging": [], "unavailable": str(exc)[:120]}


# --- Report / summary / baseline / delta ---

def build_report(signals_file: Path = DEFAULT_SIGNALS_FILE,
                 firewall_file: Path = DEFAULT_FIREWALL_FILE,
                 proposals_dir: Path | None = None,
                 last: int | None = None) -> dict:
    entries, malformed = load_entries(signals_file, last=last)
    candidates = audit_aging_candidates(proposals_dir)
    return {
        "record_count": len(entries),
        "malformed_lines": malformed,
        "repeat_pairs": audit_repeat_signals(entries),
        "distribution": audit_family_distribution(entries),
        "oov_families": audit_vocabulary(entries),
        "aging_candidates": candidates["aging"],
        "candidates_unavailable": candidates["unavailable"],
        "firewall_count": _count_ndjson_lines(firewall_file),
        "routing": _routing_summary(),
    }


def _routing_summary() -> dict:
    """Routing-memory rollup (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01).

    Informational ONLY — like the firewall count, it never enters
    has_absolute_warn, the baseline summary, or delta/exit semantics.
    The full report (per-signal precision, proposals) lives in `lv distill`.
    """
    try:
        from src.lingua_viva.improvement_audit import build_routing_report
        from src.lingua_viva.routing_memory import read_memory

        rows, skipped = read_memory()
        routing = build_routing_report(rows, skipped)
        return {
            "decisions": sum(t["volume"] for t in routing["per_type"].values()),
            "corrections": sum(t["corrected"] for t in routing["per_type"].values()),
            "collapse_flags": len(routing["collapse_flags"]),
            "proposals": len(routing["proposals"]),
            "skipped_rows": skipped,
            "unavailable": "",
        }
    except Exception as exc:  # fail-visible, never fail-loud in an audit
        return {"decisions": 0, "corrections": 0, "collapse_flags": 0,
                "proposals": 0, "skipped_rows": 0, "unavailable": str(exc)}


def has_absolute_warn(report: dict) -> bool:
    dist = _as_dict(report.get("distribution"))
    return bool(
        report.get("repeat_pairs")
        or report.get("oov_families")
        or dist.get("concentration_warn")
        or dist.get("fragmentation_warn")
        or report.get("aging_candidates")
    )


def build_summary_record(report: dict, window: int | None = None) -> dict:
    dist = _as_dict(report.get("distribution"))
    return {
        "ts": time.time(),
        "window": window if window is not None else "full",
        "record_count": report.get("record_count", 0),
        "repeat_pairs": sorted(_as_dict(report.get("repeat_pairs"))),
        "oov_families": _as_list(report.get("oov_families")),
        "top_family": dist.get("top_family"),
        "top_share": _as_num(dist.get("top_share")),
        "concentration_warn": bool(dist.get("concentration_warn")),
        "fragmentation_warn": bool(dist.get("fragmentation_warn")),
        "aging_candidate_ids": [
            _as_str(_as_dict(c).get("id")) for c in _as_list(report.get("aging_candidates"))],
        "firewall_count": _as_num(report.get("firewall_count")),
    }


def find_baseline(summaries_file: Path = DEFAULT_SUMMARIES_FILE) -> dict | None:
    """Last full-window summary. Windowed summaries are never baselines —
    a --last N run under-reports and would poison delta semantics."""
    if not summaries_file.exists():
        return None
    baseline = None
    with open(summaries_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("window") == "full":
                baseline = record
    return baseline


def compute_delta(report: dict, baseline: dict) -> dict:
    """NEW drift vs baseline. Missing/corrupt baseline fields read as 'no
    data' via coercers, so present-day drift counts as NEW (fail-visible)."""
    baseline = _as_dict(baseline)
    dist = _as_dict(report.get("distribution"))

    base_pairs = {_as_str(p) for p in _as_list(baseline.get("repeat_pairs"))}
    new_pairs = sorted(set(_as_dict(report.get("repeat_pairs"))) - base_pairs)

    base_oov = {_as_str(f) for f in _as_list(baseline.get("oov_families"))}
    new_oov = sorted(set(_as_list(report.get("oov_families"))) - base_oov)

    concentration_worse = bool(dist.get("concentration_warn")) and (
        _as_num(dist.get("top_share")) > _as_num(baseline.get("top_share")))
    fragmentation_new = bool(dist.get("fragmentation_warn")) and not (
        baseline.get("fragmentation_warn") is True)

    base_aging = {_as_str(c) for c in _as_list(baseline.get("aging_candidate_ids"))}
    new_aging = sorted(
        {_as_str(_as_dict(c).get("id")) for c in _as_list(report.get("aging_candidates"))}
        - base_aging)

    ts = _as_num(baseline.get("ts"))
    days = round((time.time() - ts) / 86400, 1) if ts else None

    return {
        "new_repeat_pairs": new_pairs,
        "new_oov_families": new_oov,
        "concentration_worse": concentration_worse,
        "fragmentation_new": fragmentation_new,
        "new_aging_candidates": new_aging,
        "firewall_delta": _as_num(report.get("firewall_count")) - _as_num(baseline.get("firewall_count")),  # informational, never gates
        "days_since_baseline": days,
        "has_new_drift": bool(new_pairs or new_oov or concentration_worse
                              or fragmentation_new or new_aging),
    }


# --- CLI entry ---

def run_audit(last: int | None = None, journal_write: bool = False,
              strict: bool = False, json_out: bool = False,
              signals_file: Path = DEFAULT_SIGNALS_FILE,
              summaries_file: Path = DEFAULT_SUMMARIES_FILE,
              firewall_file: Path = DEFAULT_FIREWALL_FILE,
              proposals_dir: Path | None = None) -> int:
    if last is not None and last <= 0:
        print(f"lv audit: --last must be a positive integer (got {last})")
        return 2

    report = build_report(signals_file, firewall_file, proposals_dir, last=last)
    baseline = find_baseline(summaries_file)
    absolute_warn = has_absolute_warn(report)

    delta = compute_delta(report, baseline) if (baseline and not strict) else None
    if delta is not None:
        exit_code = 1 if delta["has_new_drift"] else 0
        exit_basis = "delta"
    else:
        exit_code = 1 if absolute_warn else 0
        exit_basis = "strict" if strict else "absolute"

    journaled = False
    if journal_write:
        summaries_file.parent.mkdir(parents=True, exist_ok=True)
        with open(summaries_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(build_summary_record(report, window=last)) + "\n")
        journaled = True

    if json_out:
        print(json.dumps({
            "report": report, "delta": delta, "exit_code": exit_code,
            "exit_basis": exit_basis, "journaled": journaled,
            "window": last if last is not None else "full",
        }, indent=2, ensure_ascii=True))
        return exit_code

    _print_human(report, delta, exit_code, exit_basis, absolute_warn, last, journaled)
    return exit_code


def _print_human(report: dict, delta: dict | None, exit_code: int,
                 exit_basis: str, absolute_warn: bool, last: int | None,
                 journaled: bool) -> None:
    scope = f"last {last} records" if last is not None else "full journal"
    print(f"Gap-signal audit ({scope}): {report['record_count']} records"
          + (f", {report['malformed_lines']} malformed lines skipped" if report["malformed_lines"] else ""))
    if not report["record_count"]:
        print("No gap-signal data on record.")

    pairs = report["repeat_pairs"]
    print(f"[1] Repeat signals (>={REPEAT_THRESHOLD}x at one node): "
          + (", ".join(f"{k} x{v}" for k, v in list(pairs.items())[:8]) or "none"))
    dist = report["distribution"]
    frag = " FRAGMENTED" if dist["fragmentation_warn"] else ""
    conc = " WARN" if dist["concentration_warn"] else ""
    print(f"[2] Families: {dist['distinct_families']} distinct / {dist['total']} occurrences; "
          f"top {dist['top_family']} at {dist['top_share']:.0%}{conc}; "
          f"singleton share {dist['singleton_share']:.0%}{frag}")
    print("[3] Vocabulary drift: "
          + (", ".join(report["oov_families"]) or "none (all families known)"))
    if report["candidates_unavailable"]:
        print(f"[4] Aging candidates: unavailable ({report['candidates_unavailable']})")
    else:
        aging = report["aging_candidates"]
        print(f"[4] Aging candidates (open, >={AGING_HIT_THRESHOLD} hits): "
              + (", ".join(f"{c['id']} x{c['hits']}" for c in aging[:8]) or "none"))
    print(f"[i] Firewall records: {report['firewall_count']} (informational, never gates)")
    routing = _as_dict(report.get("routing"))
    if routing.get("unavailable"):
        print("[i] Routing memory: unavailable (informational, never gates)")
    else:
        print(f"[i] Routing memory: {routing.get('decisions', 0)} decisions,"
              f" {routing.get('corrections', 0)} corrections,"
              f" {routing.get('collapse_flags', 0)} collapse flags,"
              f" {routing.get('proposals', 0)} proposals"
              " (informational, never gates — full report: lv distill)")

    verdict = "WARN" if absolute_warn else "OK"
    print(f"VERDICT: {verdict}")
    if delta is not None:
        if delta["days_since_baseline"] is not None:
            print(f"Baseline: {delta['days_since_baseline']} days old")
        if exit_code == 0 and absolute_warn:
            print("EXIT 0 — no NEW drift since baseline (absolute report above still WARNs)")
        elif exit_code == 1:
            new_bits = (delta["new_repeat_pairs"] + delta["new_oov_families"]
                        + delta["new_aging_candidates"]
                        + (["concentration_worse"] if delta["concentration_worse"] else [])
                        + (["fragmentation_new"] if delta["fragmentation_new"] else []))
            print(f"EXIT 1 — NEW drift since baseline: {', '.join(new_bits[:6])}")
    elif exit_basis == "absolute" and absolute_warn:
        print("No baseline on record — exit is absolute. Write one with: lv audit --journal-write")
    if journaled:
        print("Summary journaled to memory/data/gap_audit_summaries.ndjson")
