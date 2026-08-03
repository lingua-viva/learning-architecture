# BUILD PROMPT: GIR v2 — Claim-Level Observation Linkage — Track 3

**Spec**: `dev/SPEC_LV_GIR_V2_OBSERVATION_LINKAGE_2026-08-03.md` (authoritative — read it in full first)
**Date**: 2026-08-03
**Role**: builder agent, Lingua Viva repo (`~/learning-architecture`)

## Context you don't have

LV's grounding score (`claim_support_v1_heuristic`) has a proven metric inversion: once ANY one
relevant source is found, `src/lingua_viva/grounding/build.py:151` grants blanket
`unsupported_claims = 0` — unlimited fabrication scores 1.0 — while honest hedging is penalized
unconditionally (lines 18/52/152). The score drives spoken tone (`src/pipeline.py:950` →
`src/lingua_viva/voice_tone.py:16-17`), so fabrication is delivered in a confident voice and
honesty in a hesitant one, to live teachers. You are Track 3 of three parallel tracks; Track 1
fixes pipeline model-failure honesty, Track 2 builds the readiness harness whose invention probe
is your final acceptance instrument.

## Read first (in order)

1. The spec — §1 (the defect, with verified line numbers), §2 (design), §3 (the inversion tests)
2. `src/lingua_viva/grounding/build.py` + `grounding/schema.py` — v1 lives here; you are versioning, not patching
3. `src/education/help_artifacts.py:280,323` — the linkage rule parent reports already enforce (`_source_ids`); Ask answers must reach parity
4. `scripts/run_lv_voice_gir_hardening.py` + `tests/test_grounding_result.py` + `tests/test_voice_hardening_harness.py` — existing calibration harness you extend
5. `dev/SPEC_LV_GIR_VOICE_HARDENING_LOOP_2026-07-30.md` — the lexical-relevance guard you must narrow, not replace

## Ground rules (non-negotiable)

- **NEVER commit or push in this repo.** Operator owns the commit window. Build, test, leave
  dirty, report.
- **Synthetic data only** (Marco Bianchi / Nora Rossi) in every fixture and test.
- **Only touch your owned surface**: `src/lingua_viva/grounding/build.py`,
  `grounding/schema.py`, `scripts/run_lv_voice_gir_hardening.py`, your test files,
  `dev/INDEX.md` (your row only). Track 1 owns `src/pipeline.py` and
  `src/lingua_viva/reasoning.py` — do NOT edit them. Your coupling point (`pipeline.py:950`)
  already passes `gir.score`; v2 changes what the score MEANS, not the call site.
- **HOLD BACK §2.4 tone recalibration**: `voice_tone.py` thresholds are NOT yours to change in
  this build. Recalibration is a separate, operator-visible commit AFTER (a) Track 1 ships the
  `none:deterministic_only` sentinel and (b) the v1/v2 shadow window has data. Build the shadow
  delta reporting; do not move the thresholds.
- Expect scores to DROP when v2 replaces the blind proxy. **A drop is the fix working.** Report
  the delta honestly; never tune v2 to reproduce v1's flattering numbers.

## Build scope

1. **§2.1 identifier-level linkage** (the fabrication catcher): extract identifier-shaped
   citations (`OBS-*`, source_record_ids, knowledge citations, in-scope student names) from
   answer content; each must resolve against the ledgers and belong to the student in scope.
   Non-resolving identifier ⇒ unsupported claim regardless of the grounded flag + recorded in
   a new `fabricated_identifiers: list[str]` field on `GIR` (schema addition, method string
   `claim_support_v2_linkage` at `schema.py:69`).
2. **§2.2 per-claim support**: replace the `if not grounded else 0` amnesty with per-fragment
   token-overlap support, reusing `_tokens`/`_record_relevant`.
3. **§2.3 hedging de-penalized** when `tier_used == "none"` or the hedged fragment has no
   source support; over-hedging on well-supported claims may still count.
4. **§2.4a shadow window plumbing only**: compute v1 and v2 both; v2 is live `gir`; log v1 +
   delta through `run_lv_voice_gir_hardening.py`. No threshold changes.

## Definition of done

1. The three inversion tests from spec §3 pass, each documenting the v1 value as a regression
   sentinel in an assertion message or comment:
   - fabricated `OBS-` ID + one relevant source ⇒ score < 0.5, hedge/clarify tone (v1: 1.0)
   - honest zero-source hedged answer scores ≥ the fabricated answer
   - wrong-student citation ⇒ `fabricated_identifiers` non-empty
2. Narrow-path check (spec §4): measure false-unsupported rate on the golden corpus; if > ~20%,
   ship §2.1 + §2.3 only, mark §2.2 DEFERRED in your report and INDEX row — do not hold the
   fabrication catcher hostage to calibration.
3. `python3 -m pytest tests/ -q` zero failures; `lv preflight` green; `lv eval golden` green;
   `run_lv_voice_gir_hardening.py` checks (`gir_out_of_range`, `tone_mismatch_high_gir`)
   re-baselined to v2 and green; `python3 -m src.lingua_viva.spec_status` shows no NEW
   fail-severity findings.
4. `dev/INDEX.md` row updated (BUILT — uncommitted; note §2.4 recalibration explicitly as the
   remaining sequential step).
5. Build report: files changed, v1→v2 score deltas on the golden corpus, false-unsupported
   rate, narrow-path decision if taken, and the explicit statement that final acceptance
   (Track 2's invention probe) is pending the harness Phase 3.
