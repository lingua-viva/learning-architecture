# SPEC: LV Measurement Distillation — `lv distill`

**Date**: 2026-07-26
**Status**: DRAFT → BUILT same session (see §8)
**Origin**: Direct port of Mission Canvas's measurement-integrity hardening
(mission-canvas `dev/SPEC_EXTERNAL_DISTILL_AUDIT_HARDENING_2026-07-26.md`,
commit `c890516e`, plus the `mc improve --audit` V1/V2 instruments), applied
to Lingua Viva's existing-but-unanalyzed measurement stores.

**Sibling spec / naming**: a concurrent window built
`SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md` (`lv audit`,
`src/lingua_viva/gap_audit.py`) the same evening — a drift GATE with
delta-based exit codes (repeat pairs, OOV vocabulary drift, aging
candidates, firewall delta). This build was renamed `lv distill` (operator
ruling 2026-07-26) to compose rather than collide: `audit` answers "did
anything drift since baseline? (exit code)", `distill` answers "what should
a human look at, ranked? (report)". Complementary capabilities unique to
this spec: evidence-breadth ranking by distinct sessions, candidate
retirement via latest-outcome-wins, candidate replay through today's
engine, revision-log defect-class concentration, proxy→live transitions.

---

## 1. Problem

LV *records* measurement data in three places but *analyzes* none of it:

| Store | State today | Consequence |
|---|---|---|
| `memory/data/gap_signals.ndjson` (61 rows) | Written by `context_builder.py` + `memory/ndjson_adapter.py:55`, read by nothing | Classification gaps accumulate invisibly; nobody knows LV-CUR-003 has been emitting `skipped_research:self_sufficient` across dozens of sessions |
| `ontology/proposals/CAND-*.yaml` (10 files) | `lv candidates` is a read-only list in file order | No ranking by evidence breadth; no staleness check — a candidate whose gap the ontology has since closed sits in the active list forever |
| `dev/lv_revision_log.ndjson` (9 rows) | Schema-enforced by doctor, aggregated by nothing | `defect_class` and `instrument_that_found_it` fields exist precisely so concentration and proxy→live transitions can be measured — and never are |

This is the same defect class MC closed on 2026-07-26: **append-only stores
with no reconciliation are honest but blind**. MC's fixes (latest-outcome-wins
reconciliation, evidence-breadth counting, proxy→live tracking, fragmentation
metrics, longitudinal deltas) port directly because LV's revision log already
copied MC's journal vocabulary (`instrument_that_found_it`,
`instrument_touched`, `independent_cross_check`).

Verified NOT a problem for THIS spec: `scripts/mc_push.py::_verify_live()`
in the working tree already compares served pins to the just-cut tag and
curls the download URLs — the 2026-07-25 site-pin trap is closed. NOTE:
that fix is the concurrent window's UNCOMMITTED work (plus its
`tests/test_mc_push_verify.py`), not committed history — it must land via
that lane's commit.

## 2. What ports, and the LV analog of each MC lesson

| MC lesson (Jul 26) | LV application |
|---|---|
| **A1 latest-outcome-wins**: a later `already_shipped` record retires a `verified_gap` from ranking; append-only log preserved | A gap-signal cluster whose matching candidate is `PROMOTED`/`DISCARDED` is retired from the active ranking (shown separately). The ndjson is never rewritten. |
| **A2 evidence breadth**: count distinct sources, not raw records | Rank gap clusters by **distinct `session_id`s**, not row count — 40 rows from one looping session ≠ 40 sessions hitting the same wall |
| **already_shipped verification gate** | Candidate replay: re-run each active candidate's `original_query` through today's `OntologyEngine.classify()`. If it no longer lands on the recorded `fallback_node`, flag `possibly_resolved` — the ontology grew past it |
| **A4 NEEDS RESEARCH queue** | `possibly_resolved` candidates go to a NEEDS REVIEW queue. The system proposes, the human disposes — we never auto-discard (preserves `lv candidates`' read-only covenant, cli.py:311) |
| **B1 proxy→live transitions** (lagging indicator #6) | Per `defect_class`, detect the first transition from a proxy instrument (`phase0_claim_audit`, manual/operator-requested sweeps) to a live one (doctor check, route gate, reflect_view). Informational, never a WARN — transitions are the goal |
| **B2 fragmentation**: distinct classes, singleton share, structural floor | Same metric over revision-log `defect_class`, floor 20 / ratio 0.25 (floors identical to MC so numbers are comparable across repos) |
| **V2 longitudinal delta** | Optional summary record per run (`memory/data/audit_summary.ndjson`, env-overridable); next run prints the delta vs. previous |
| **Module-constant hermeticity trap** (`sanitizer/client.py`, 2026-07-20) | All paths resolved by lazy functions reading env vars per call (`LV_GAP_SIGNALS_PATH`, `LV_REVISION_LOG_PATH` — the latter already exists at web.py:332, reuse it), never module constants |

## 3. Deliverables

1. **`src/lingua_viva/improvement_audit.py`** (new) — pure functions, no
   side effects except the opt-in summary append:
   - `read_gap_signals()`, `read_revision_log()` — lazy env-resolved paths,
     malformed lines skipped (append-only files can carry a torn write)
   - `distill_gap_signals(entries)` → clusters keyed `(entry_node, signal)`
     with `breadth` (distinct sessions), `count` (raw rows), `first_seen` /
     `last_seen`; sorted by breadth desc, then count desc
   - `reconcile_with_candidates(clusters, candidates)` → annotates each
     cluster with `candidate_id`/`candidate_status` on signal overlap;
     splits active vs retired (retired = matching candidate PROMOTED or
     DISCARDED — latest-outcome-wins)
   - `replay_candidates(candidates, classify_fn)` → NEEDS REVIEW queue of
     `possibly_resolved` candidates (classify_fn injected for testability;
     CLI wires the real engine)
   - `audit_defect_concentration(entries)` → top-class share + concentration
     WARN (>50% over floor) + fragmentation WARN (distinct > 25% over floor)
     + `singleton_share`
   - `audit_proxy_to_live(entries)` → first proxy→live transition per
     defect_class; `PROXY_INSTRUMENTS` explicit frozenset
   - `build_audit_report()` / `format_report()` / `append_summary_record()`
     / `compute_delta(prev, cur)`
2. **`lv distill` CLI command** (`src/lingua_viva/cli.py`) — `--json`,
   `--no-replay`, `--write-summary` (default is read-only: zero side
   effects unless asked, matching `lv candidates`' covenant). NOT added to
   preflight (engine replay is too slow for the <5s budget; this is an
   operator instrument like `lv health --full`).
3. **`tests/test_improvement_audit.py`** (new) — hermetic per conftest
   pattern; every function covered incl. torn-write lines, breadth-vs-count
   divergence, retirement, replay flag, floor boundaries, never-warn on
   proxy→live, delta.
4. **`dev/lv_revision_log.ndjson`** +1 entry (`lv-rev-009-distill`,
   `instrument_touched: true`, doctor-schema-valid).
5. **`dev/INDEX.md`** row for this spec.

## 4. Explicitly out of scope

- Auto-promotion/auto-discard of candidates (human disposes).
- Wiring into `lv preflight` (speed budget) or `lv health --full` (can be a
  later one-line add once the instrument has operator trust).
- Any rewrite/compaction of the ndjson stores (append-only is load-bearing).
- The skipped Layer 1–5 eval architecture (separate spec, blocked on
  interfaces not yet built).
- Fixing the 4 specs missing from `dev/INDEX.md` (flagged to operator; not
  this build's diff).

## 5. Verification plan

- Scoped: new test file + `test_cli_candidates.py` + `test_lv_cli.py` +
  `test_lv_preflight.py` green.
- Live: run `lv distill` against the real 61-row/10-candidate/9-row stores;
  confirm output matches hand-computed values for at least the top cluster
  and the candidate replay verdicts.
- `lv preflight` 6/6 and `lv doctor` non-BLOCKED after the revision-log
  append (doctor schema-validates the new row).
- NO COMMIT — operator's dedicated commit window handles all commits in
  this repo (`feedback_lv_commit_window`). Deliver commit-readiness report.

## 6. Risks

- Engine replay verdicts depend on current ontology tuning; a
  `possibly_resolved` flag is a *prompt to review*, not a verdict — wording
  in output must say so (evidence-over-reassurance, per Claudia lens).
- 9 revision-log rows are below every structural floor — sections [4]/[5]
  will mostly report "insufficient volume" today. That is correct behavior
  (MC lesson: report the floor, don't fake a signal).

## 7. Why now

Teachers open the tool Monday 2026-07-27. The gap-signal store is the only
place real teacher classification failures will accumulate; today nothing
reads it. This instrument is how week-one field pain becomes a ranked list
instead of an invisible ndjson.

## 8. Build record

Built same session (2026-07-26), uncommitted per commit-window rule.

**2026-07-27 first-live-run correction (teachers-arrive day).** The
instrument's #1-ranked finding — `LV-CUR-003 skipped_research:self_sufficient`
"across 43 distinct sessions" — was investigated and found to be a double
false positive: (a) the signal records the pipeline WORKING AS DESIGNED
(pipeline.py:675 self-sufficiency check; KL genuinely holds 4 tier-1/2 CEFR
entries at confidence ≥0.80 — skipping Perplexity is correct), and (b) 42/43
rows were machine-cadence bursts on 2026-07-18 (5–20s apart) from an eval
harness that omitted `session_id`, so pipeline.py:540 minted a fresh UUID per
call — inflating "distinct sessions" and defeating the A2 breadth lesson one
level up. Fixes shipped to `improvement_audit.py` + tests (60 green):
`INFORMATIONAL_SIGNAL_FAMILIES` (skipped_research, research_skipped_by_intent)
rank after real walls in their own report subsection, and `suspected_burst`
(≥5 rows, >50% of inter-row gaps <30s) annotates clusters whose breadth is
likely harness-minted — a caveat, never a filter. Post-fix ranking: the only
organic signals on record are CORE-RESEARCH weak classifications (Jul 20-21,
4 rows). Root-cause recommendation for the operator (NOT built — touches the
shared pipeline on ship day): eval harnesses should pass a stable
`session_id`, or gap-signal writes should carry an origin tag.
