# SPEC: GIR v2 — Claim-Level Observation Linkage (`claim_support_v2_linkage`)

**Date**: 2026-08-03
**Status**: BUILT — uncommitted; tone recalibration held back
**Lens**: measurement (primary), product truth, protection
**Depends on**:
- `dev/SPEC_LV_TEACHER_READINESS_HARNESS_2026-08-03.md` (its invention probe is this spec's acceptance instrument)
- `dev/SPEC_LV_GIR_VOICE_HARDENING_LOOP_2026-07-30.md` (existing calibration harness; SHIPPED `247ade8`)
- `src/lingua_viva/grounding/build.py`, `src/lingua_viva/grounding/schema.py` (v1 lives here)

**Priority rationale**: AGENTS.md already labels this honestly as the v2 gap ("Ask answers
don't check `source_observation_ids` linkage the way parent reports do"). What's new as of
2026-08-03 is *hard evidence of how bad the v1 blindness is*: an internal Mission Canvas
evaluation run demonstrated that the structurally identical `claim_support_v1_heuristic`
scored an answer containing outright fabrications at a perfect 1.000 (because sources were
present), while docking an honest, hedged answer for its hedging. The metric as built
penalizes honesty and misses fabrication — and LV couples it to voice tone, so a fabricated
high-GIR answer is *spoken confidently* to a teacher. (MC evidence is a pointer only; results
are local to the MC repo and must not be copied into this public repo.)

---

## 1. The defect, in LV's own code

`src/lingua_viva/grounding/build.py:144–152` (verified 2026-08-03):

- Line 151: `unsupported_claims = max(total_claims - uncertainty_claims, 0) if total_claims
  and not grounded else 0` — the moment `grounded` is True (any one relevant source record
  or knowledge citation, lines 145/124–141), **every unhedged claim in the answer counts as
  supported**, including claims about observations that do not exist. One relevant source
  whitewashes unlimited fabrication.
- Lines 18/52/152: `_UNCERTAINTY_MARKERS` ("might", "may", "possibly"…) are counted and
  subtracted from the score **unconditionally** — an honest "I don't have enough
  observations; Marco *may* need listening practice" scores *worse* than a confident
  fabrication.
- Downstream coupling makes it teacher-facing: `src/pipeline.py:950` feeds `gir.score`
  straight into `resolve_voice_tone` (`src/lingua_viva/voice_tone.py:16–17`, plain ≥0.8 /
  clarify ≥0.4 / hedge <0.4). Fabricated-but-grounded ⇒ 1.0 ⇒ plain confident voice.
  Honest hedging ⇒ lower score ⇒ the system *audibly* second-guesses its most honest answers.

This is a metric-inversion failure class, not a tuning bug. Fix the class at the chokepoint
(`build_grounding_result`), and lock it with tests that encode the inversion directly.

## 2. Design — `claim_support_v2_linkage`

Versioned method string (schema already carries it: `grounding/schema.py:69`). Three changes,
in priority order:

### 2.1 Identifier-level linkage (the fabrication catcher)

Extract identifier-shaped citations from the answer content: `OBS-*` observation IDs,
`source_record_id` values, knowledge citation strings, and student names. Each must resolve:

- observation IDs → exist in the observation ledger AND belong to the student in scope
  (same rule parent reports already enforce via `_source_ids` —
  `src/education/help_artifacts.py:280,323`);
- source record IDs → exist in `sources/ledger`;
- student names → match the student(s) actually in the query/session scope (synthetic-name
  set; never log the names themselves into grounding records beyond what v1 already stores).

Any non-resolving identifier ⇒ `unsupported_claims += 1` **regardless of the grounded flag**,
and a new `fabricated_identifiers: list[str]` field on `GIR` (schema addition) records them
verbatim for the harness/report.

### 2.2 Per-claim support instead of blanket amnesty

Replace the `if not grounded else 0` branch: an unhedged claim fragment counts as supported
only if it has token overlap with at least one used source/citation (reuse the existing
`_tokens`/`_record_relevant` machinery, applied per-fragment instead of per-answer). Grounded
status stops being a global pardon and becomes per-claim evidence. Keep the existing lexical
guard behavior for relevance (from the 07-30 hardening loop) — this narrows it, doesn't
replace it.

### 2.3 Stop penalizing honest hedging

Uncertainty markers stop counting against the score when `tier_used == "none"` or when the
hedged fragment has no source support — hedging about absent evidence is the *correct*
behavior and must not be scored as a grounding failure. Hedging on a claim that HAS solid
source support may still count (over-hedging is a real, lesser signal). This directly
removes the inversion.

### 2.4 Transition mechanics

- Compute **both** v1 and v2 during a shadow window; store v2 as the live `gir` (method
  `claim_support_v2_linkage`), log the v1 score + delta into the hardening report via
  `scripts/run_lv_voice_gir_hardening.py`. Expect the proxy→live pattern: honest scores will
  DROP when the blind proxy is replaced — a drop is the fix working, not a regression.
  Report the delta; do not chase the old number.
- Voice-tone thresholds (`voice_tone.py:16–17`) were inherited, and the file itself says so.
  After the shadow window, recalibrate plain/clarify/hedge cut-points against the observed
  v2 distribution on the golden + teacher-readiness corpora. Threshold changes are a
  separate, operator-visible commit.

## 3. Acceptance criteria (the inversion tests — these lock the class)

1. **Fabrication test**: an answer citing a non-existent `OBS-` ID with one relevant source
   present scores < 0.5 and receives hedge/clarify tone. Under v1 this scores 1.0 — the test
   must assert the v2 behavior and document the v1 value as the regression sentinel.
2. **Honesty test**: "I don't have observations for Marco yet — he *may* benefit from X" with
   zero sources must score ≥ the fabrication test's answer. (The inversion, encoded.)
3. **Wrong-student test**: an Ask answer citing Nora's real observation ID in Marco's scope
   is flagged (fabricated_identifiers non-empty).
4. Teacher-readiness harness invention probe (companion spec §2.5) passes: seeded invented
   identifiers are caught and listed.
5. No regression on `lv eval golden`, `run_lv_voice_gir_hardening.py` checks
   (`gir_out_of_range`, `tone_mismatch_high_gir` re-baselined to v2), full suite green.

## 4. Kill / narrow criteria

- If per-fragment support (§2.2) proves too noisy on real teacher phrasing (false unsupported
  > ~20% on the golden corpus), narrow to §2.1 + §2.3 only and ship those — identifier
  linkage and de-penalized hedging are each independently correct and each independently
  removes a failure class. Do not hold the fabrication catcher hostage to claim-matching
  calibration.

## 5. Files touched (expected)

- EDIT `src/lingua_viva/grounding/build.py` (v2 logic), `src/lingua_viva/grounding/schema.py`
  (method string, `fabricated_identifiers`), `src/lingua_viva/voice_tone.py` (recalibration,
  separate commit), `scripts/run_lv_voice_gir_hardening.py` (shadow delta reporting)
- EDIT `tests/test_grounding_result.py`, `tests/test_voice_hardening_harness.py`; NEW
  inversion tests per §3
- EDIT `dev/INDEX.md` (status line)
