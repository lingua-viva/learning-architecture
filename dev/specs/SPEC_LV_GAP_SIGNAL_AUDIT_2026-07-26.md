# SPEC: Gap-Signal Audit (`lv audit`) — MC Lagging-Indicator Lessons Port

**Date**: 2026-07-26
**Status**: BUILT same day (see §7)
**Origin**: Mission Canvas `mc improve --audit` V1+V2 (SPEC_IMPROVE_AUDIT_V2_LONGITUDINAL_2026-07-26,
two 15-pass hardening loops). This spec ports the *lessons*, not the code — LV has no
improvement journal/verdict vocabulary; its closest analog is `memory/data/gap_signals.ndjson`,
which today is write-only: `memory/store.py:60` appends, nothing ever reads it back for
trend analysis. Signals accumulate forever with zero loop-visible feedback.

## 1. Problem

LV emits 14 gap-signal families across `src/pipeline.py` and `src/context_builder.py`
(`entry_gate_blocked`, `sensitive`, `education_execute`, `low_classification_confidence`,
`skipped_research`, `research_blocked_by_entry_gate`, `research_skipped_by_intent`,
`research_blocked_by_governance`, `malicious_response`, `research_gap`, `contradiction`,
`integrity`, `weak_classification`, `no_knowledge_at_node`). Nothing detects:
- the same gap recurring at the same node forever (repeat blindness),
- signal volume concentrating on one family (systemic weakness) or fragmenting into
  unclassifiable one-offs,
- a signal family appearing that no emitter is known to produce (vocabulary drift —
  emitter renamed/added without the measurement side knowing),
- candidates (`ontology/proposals/`) that keep accumulating hits while stuck open —
  the gap was *acknowledged* (receipt written) but never *resolved* (receipt decay).

The MC meta-lesson: an audit whose exit code WARNs forever on historical state is noise.
Exit semantics must be **delta-based from day one** (MC learned this the hard way — V1
shipped absolute-only and needed a same-day V2).

## 2. Scope

- New read-only module `src/lingua_viva/gap_audit.py` + `lv audit` subcommand.
- Touches NO runtime pipeline code. No write-time gate in `pipeline.py` (hot path,
  teachers start 2026-07-27; MC's `blocked_deferred` near-miss shows write gates can
  break live loops — read-side OOV detection only; a write gate is a future operator ruling).
- Audit summaries journal to a NEW file `memory/data/gap_audit_summaries.ndjson`
  (never mixes with the signal stream it measures).

## 3. Indicators

1. **Repeat signals** — `(family, entry_node)` pairs with ≥3 occurrences. WARN axis.
2. **Family concentration/fragmentation** — top family share ≥50% of occurrences with
   ≥10 total occurrences (min-volume guard: tiny samples always look concentrated —
   MC min-n lesson), or singleton families ≥50% of distinct families with ≥10 families
   (WARN: fragmentation).
3. **Vocabulary drift** — signal family (token before first `:`; whole signal when no `:`)
   not in `KNOWN_SIGNAL_FAMILIES` (exact membership, mirrors emitter set — MC pass-10
   lesson: exact set, never prefix-tolerant; prefix tolerance hid 5 live drift strings). WARN.
4. **Aging candidates** — open candidates (status not PROMOTED/DISCARDED, no `discarded*`
   resolution) with `hit_count ≥ 5`. The receipt-decay analog. WARN.
5. **Firewall activity** — `memory/data/firewall_log.ndjson` record count delta since
   baseline. INFORMATIONAL ONLY — reported, never gates (MC "reports, never gates" fence
   for anything not yet calibrated).

## 4. Exit semantics (delta-first, the V2 lesson)

- `--journal-write` appends a summary record `{ts, window, record_count, repeat_pairs,
  oov_families, top_family, top_share, singleton_share, aging_candidate_ids,
  firewall_count}` to `gap_audit_summaries.ndjson`.
- Baseline = last summary with `window == "full"` (windowed summaries are never
  baselines — MC baseline-poisoning fix).
- With baseline: exit 1 **only on NEW drift** — new repeat pair, new OOV family,
  `top_share` worsened past threshold, new aging candidate. Known drift → exit 0 with
  explicit `EXIT 0 — no NEW drift since baseline (absolute report above still WARNs)` line.
- `--strict`: absolute (any WARN → exit 1). No baseline on record: absolute.
- `--last N` (positive int, validated): audit only the last N journal records; windowed
  delta is conservative — may under-report vs baseline, never false-alarms; windowed
  summaries carry `window: N` and are skipped by baseline selection.
- `--json`: machine-readable `{report, delta, exit_code, exit_basis, journaled, window}`
  — the loop-visible surface.

## 5. Robustness (fail-visible, never crash)

- Malformed NDJSON lines: skipped and **counted** (`malformed_lines` in report — the
  existing `memory/ndjson_adapter.py:88` reader crashes on them; the audit must not).
- Wrong-typed fields in journal or baseline: coerced via `_as_dict/_as_num/_as_str/_as_list`
  → treated as "no data", which makes drift count as NEW (fail-visible, never fail-silent).
- Missing files (`gap_signals.ndjson`, candidates dir, firewall log): empty report, exit 0,
  explicit "no data" line — a fresh install must not fail its first audit.
- Candidate store read failures degrade to indicator-level `unavailable` note, not a crash.

## 6. Out of scope / deferred (operator rulings)

- Write-time signal-family gate in `pipeline.py` (see §2).
- Wiring `lv audit` into `lv health --full` (adds journal reads to a teacher-facing
  command the week of launch — defer).
- First baseline write is operator opt-in: `lv audit --journal-write`. Until then exit
  semantics are absolute.
- NEVER committed by the agent — operator's single commit window
  (feedback_lv_commit_window.md).

## 7. Build record

- `src/lingua_viva/gap_audit.py` (module), CLI wiring in `src/lingua_viva/cli.py`,
  `tests/test_gap_audit.py`. All uncommitted at close.
