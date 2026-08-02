# Build Prompt — Routing Memory Loop (Collect + Audit, No Adaptation)

You are implementing `dev/SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01.md`.
**Preconditions**: Spec 1 (category suggestions) and Spec 4 (detection log with
`lv_route_mem_v1` schema) built. If Spec 4's log helper exists, extend it into the new
module rather than duplicating.

Read first:

```text
dev/SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01.md   (especially §Inherited Constraints — they are hard rules)
src/lingua_viva/improvement_audit.py            (full — distill_gap_signals, build_audit_report, reconcile_with_candidates, path helpers 90-103)
src/lingua_viva/cli.py                          (_audit 329-343, _distill 346-393)
src/lingua_viva/voice_intent.py                 (signal-list key structure — your signals_matched values reference these)
src/web.py                                      (voice/act handler; observe capture/classify; find every endpoint where a teacher edits template_type, confirms a category, or re-assigns a student — these are your correction hooks)
tests/test_voice_intent.py                      (_isolate pattern)
```

## Objective

Append-only routing-decision memory + invisible teacher-correction capture + an `lv audit`
routing section that turns the memory into ranked signal-list proposals. **This spec changes
zero routing behavior.** It is instrumentation and reporting only.

## Hard Rules

1. **If your diff touches a threshold constant or a signal list, you have failed the spec.**
   Run `git diff src/lingua_viva/voice_intent.py` at the end — only additive `signals_matched`
   plumbing (exposing which keys fired) is acceptable there.
2. **Content-free records.** No transcript, no names, no free text in any row. Signal keys and
   ids only. Enforced by a key-set test.
3. **Append-only.** Corrections are new rows referencing `decision_id` — never a rewrite.
   Schema field `"lv_route_mem_v1"` in every row; unknown-schema rows skipped with a counted
   warning on read.
4. **Fire-and-forget everywhere.** A full disk or read-only path must never surface in any
   teacher-facing response. Wrap every append in the same swallow-and-log pattern the privacy
   log uses.
5. **Safety gates emit nothing.** Do not instrument `check_publication_safety`, the TTS privacy
   gate, exit-gate code, or the never-guess clarification rule. They are outside the loop by
   design — adding "just one metric" there is how the loop eventually eats them.
6. Hermetic tests. No commits. No UI changes → **no UI contract bump needed** (verify: if you
   touched static/index.html for any reason, reconsider — this spec shouldn't).

## Build Order

### Step 1 — `src/lingua_viva/routing_memory.py`
- `routing_memory_path()` — `LV_ROUTING_MEMORY_PATH` env, default
  `memory/data/routing_memory_v1.ndjson` (mirror `_gap_signals_path()` style)
- `record_decision(decision, outcome, confidence, signals_matched, subject_ref, trace_id) -> decision_id`
- `record_correction(decision_id, corrected: dict)`
- `read_memory() -> (rows, skipped_count)` with schema validation
- Module-level `ALLOWED_KEYS` frozenset; `record_*` strips anything else defensively

### Step 2 — Decision emission
- Intent: in the voice/act handler after `classify_intent` — outcome = chosen intent,
  signals_matched = which signal-list keys fired (expose from classify_intent additively if
  not already returned)
- Student detect: migrate/extend Spec 4's emission into this module
- Category: in `suggest_support_categories` call sites — one row per suggestion set (top
  suggestion + confidence), not per category
- Thread `decision_id`s into the response payloads ONLY where the correction hooks need them
  (e.g., observation save response carries `routing_decision_ids` so a later edit can
  reference them). Additive fields only.

### Step 3 — Correction hooks (the careful part)
Inventory first, then wire — report in your build notes exactly which endpoints you found:
1. Observation `template_type` edit path → intent correction
2. Category confirm-tap (Spec 1) → positive; recategorize/dismiss → negative + teacher's choice
3. Student re-assignment on an observation → detection correction
4. Clarification resolution in voice/act (the merged-pending re-send that resolves a student) →
   resolution row
Each hook: look up `routing_decision_ids` from the stored observation (persist them on the
observation row — add a JSON column via guarded migration, ids only), append correction,
swallow failures. If a hook's decision_id is missing (old observation, pre-feature) → skip
silently, no error.

### Step 4 — Audit integration
In `improvement_audit.py`:
- `build_routing_report(rows) -> dict`: per-decision-type {volume, correction_rate,
  corrected-vs-uncorrected confidence summary}; per-signal-key precision proxy
  (fired-count, corrected-count, worst offenders ranked); collapse flags
  (>90% single intent over the window; category with 0 fires across ≥50 category-corrected
  observations)
- Fold into `build_audit_report()` output under `"routing"`; render in `format_report`;
  include in `compute_delta` so week-over-week correction-rate movement shows in `lv audit`
- Proposals: each worst-offender signal gets a one-line proposal string citing counts —
  reuse the existing cluster/proposal formatting so `reconcile_with_candidates` treats them
  uniformly

### Step 5 — Tests (`tests/test_routing_memory.py`)
The spec's 7-point plan, plus:
- End-to-end: voice/act call (test client) → decision rows appear; simulated template edit →
  correction row pairs correctly
- Byte-stability: capture file bytes, append correction, assert prefix unchanged
- `LV_ROUTING_MEMORY_PATH` pointed at an unwritable dir → endpoints still 200
- Synthetic 100-row memory → audit numbers verified by hand-computed fixture

### Step 6 — Verify
```bash
python3 -m pytest tests/test_routing_memory.py tests/test_voice_intent.py -q
python3 -m src.lingua_viva.cli audit          # routing section renders on real (empty) memory
python3 -m src.lingua_viva.cli preflight
python3 -m pytest -q tests/
git diff --stat                                # confirm: no signal-list/threshold lines changed
```

## Definition of Done

- [ ] All three decision types + four correction paths captured, content-free, append-only
- [ ] `lv audit` shows routing volume, correction rates, per-signal precision, collapse flags,
      and concrete proposals
- [ ] Provably zero routing-behavior change (diff inspection + byte-identical classifier tests)
- [ ] Failure-proof appends; unknown schemas skipped; full suite green
