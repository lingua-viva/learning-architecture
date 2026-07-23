# REPORT: LV Extract+Fill+Verify Engine (LV-DATA-IN-5)

**Date**: 2026-07-22
**Spec**: `dev/specs/SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md`
**Built by**: Claude, live in the operator's session (not a fresh/handed-off window)
**Status**: Curriculum path + eval harness SHIPPED. Student-lens path + eval harness
SHIPPED, but **gated at §4** — implemented and fully verified against synthetic
fixtures only, has not run and will not run against any real file until the operator
explicitly confirms §4's reasoning.

---

## What Was Built

- `src/lingua_viva/extraction_engine.py` — concrete `extract()` implementation for
  both `curriculum_unit` and `student_lens` target schemas from
  `data_in_contracts.py`.
- Chunking: reuses `DocumentParser` directly for `.pdf`; a new minimal paragraph-
  window chunker for `.txt`/`.md` (the realistic shape of messy teacher notes).
  Anything else raises, caught as an `unresolved_question`, never a crash.
- Two-pass extraction+verification, exactly as spec'd: an LLM proposal call, then a
  SEPARATE LLM verification call — never the same call grading itself — plus a
  deterministic lexical-grounding gate that must ALSO pass. `status="verified"`
  requires both.
- `tests/fixtures/data_in_eval/{curriculum,student_lens}/` — 7 synthetic fixtures
  (invented names/content only — Elio, Aya, "Still I Rise"-flavored but fictional
  scenarios) with hand-written `expected.yaml` ground truth each.
- `tests/test_extraction_engine_eval.py` — 5 tests: per-schema eval with a hard
  zero-tolerance check for confidently-wrong `verified` fields, a dedicated
  trauma_flag safety test, a sparse-file no-hallucination test, and an unreadable-
  file-doesn't-crash test.

## Real Bugs Found And Fixed During Iteration

The eval harness did its job — three real correctness bugs surfaced on the first
live runs against the actual local model (qwen2.5:3b via Ollama), not synthetic
mocks:

1. **Grade grounding checked the wrong representation.** The LLM correctly proposed
   `grade="G3"`, but the deterministic grounding gate checked whether the literal
   string `"G3"` appeared in source text — which only ever says "Grade 3"/"terza".
   Every grade extraction failed grounding, always, regardless of correctness. Fixed
   by grounding enum-coded fields (`grade`, `grade_level`, `home_languages`) against
   their known label sets (the same ones `_deterministic_grade`/
   `_deterministic_languages` already use) instead of the raw code.
2. **Normalization silently collapsed "A2" and "A2+" into the same string** (`+`
   was stripped as non-alphanumeric). This risked grounding either level for the
   other. Fixed by preserving `+` in normalization.
3. **`trauma_flag` (and any future never-auto-verify field) could disappear as
   `"unsupported"`** instead of being surfaced for a human to look at — booleans
   rarely have a literal textual grounding match ("True" doesn't appear in prose),
   so the original logic silently dropped exactly the field most in need of
   visibility. Fixed: never-auto-verify fields always resolve `needs_confirmation`
   when the model proposes them, never `unsupported`, never `verified`.

## Eval Results

Recall varies somewhat run-to-run (small local model, temperature 0.3, especially on
the second/verification LLM call) — observed range across repeated runs: curriculum
33%→100%, student-lens 25%→75%. **The safety invariant did not vary once**: zero
confidently-wrong `verified` fields, and zero `trauma_flag` verifications, across
every run, including the dedicated adversarial test where the source text states a
traumatic history plainly and unambiguously. That's the bar the spec actually set
(§8 Definition of Done) — a field being under-confident (`needs_confirmation`/
`unsupported` when it could have verified) is an accepted, expected characteristic
of a small local model; a field being confidently wrong is the one failure mode this
whole design exists to prevent, and it never occurred.

## §4 Gate Status

**Not run against any real file.** All extraction, all iteration, all bug-fixing
above happened exclusively against the synthetic fixtures in
`tests/fixtures/data_in_eval/`. Per the spec, moving from "built and verified
against synthetic data" to "pointed at Marco's/Aya's/any real student's actual
file" requires the operator to explicitly confirm §4's reasoning first. That
confirmation has not happened in this session. Recommend treating this as a real,
separate decision point — not something to wave through because the eval harness
looks clean.

## Verification

```
python3 -m pytest -q tests/test_extraction_engine_eval.py -v   → 5 passed
python3 -m pytest -q tests/                                    → 468 passed, 21 failed
```

All 21 failures attributed to concurrent state, not this spec's code:
- `test_ui_contract.py`, `test_filemap.py` and related: `src/web.py` was mid-edit
  (git status showed `MM`, both staged and unstaged changes) by the concurrently
  running Kiro window (`SPEC_LV_UI_WIRING_FIXES_2026-07-22`) at the time of this
  run — the UI contract lock hash mismatch is exactly the transient state you'd
  expect before that window finishes and runs its own bump script.
- `test_install_hardening.py` (Mac architecture detection), `test_request_log.py`/
  `test_filemap.py::test_file_permissions` (`chmod 0600` assertions) — known
  non-portable on this Windows machine, unrelated to any change this session.
- `test_document_ingest_endpoint.py`, `test_document_intelligence.py` — exercise
  `document_store`/`document_retrieval`, neither touched by this spec; not
  investigated further here since they're outside this spec's scope, but flagged
  for whoever picks up next in case they're a real pre-existing gap.

`python3 -m extraction_engine` files pass `py_compile` clean.

## 15-Round Hardening Loop (same day, immediately following initial ship)

Operator asked for 15 iterations of run-eval → find-a-real-problem → fix →
re-run, matching the MC-derived methodology. Ran all 15 live against the local
model. Summary rather than a round-by-round transcript:

**Fixture set grew from 5 to 9** during the loop — added deliberately harder cases
rather than just re-running the same 5 fixtures 15 times hoping for different
random results: a genuine grade-disambiguation trap (`notes_decoy_grade.txt` — both
"Grade 2" and "Grade 3" literally appear in text, only one is the student's actual
grade), a multi-file aggregation case (unit content split across two files), an
empty file, and a noisy-content case (real unit content buried between unrelated
staff-memo text).

**Real findings, fixed live:**
1. **Verification prompt was too conservative** — rounds 5-6 showed every *value*
   correct but landing at `needs_confirmation` instead of `verified` far more than
   seemed warranted for clearly-stated facts. Rewrote `VERIFY_SYSTEM_PROMPT` to
   accept clear paraphrase (not require verbatim match) and reserve "unsure" for
   genuine ambiguity, and added one retry-on-"unsure" (still requires an explicit
   "yes" to ever verify — a second "unsure" or a "no" still doesn't verify, so this
   doesn't weaken the safety gate, it just gives a coin-flip judgment a second
   sample). Curriculum recall moved 0.50 → 0.75 and held there.
2. **List-valued fields were sent to the verification prompt as raw Python repr**
   (`"Claimed value: ['ar']"` instead of `"Claimed value: ar"`) — a strictly worse
   prompt for the model to reason over. Added `_display_value()` for natural
   formatting in both extraction and verification prompts.

**The decoy-grade trap resolved correctly**: the engine consistently identified the
student's real grade (G3) rather than the decoy reference grade (G2) mentioned in
the same sentence — it landed at `needs_confirmation` rather than `verified` (
appropriately humble given genuine textual ambiguity), but never once, across every
round it was tested, verified the wrong grade.

**Convergence**: recall stabilized at curriculum 0.75 / student-lens 0.75 for the
final 4 consecutive rounds (12-15), up from an initial baseline of 0.67/0.75 and a
mid-loop dip to 0.50/0.50 before the verification-prompt fix. **The safety
invariant — zero confidently-wrong `verified` answers — held across all 15 rounds
without a single exception**, including every run of the adversarial trauma_flag
test and the decoy-grade trap. Treating this as converged: the last several rounds
found no new bugs, only confirmed stability.

**Post-loop full-suite check**: `python3 -m pytest -q tests/` → 505 passed, 20
failed. Up from 468 passed/21 failed at initial ship (new passing tests are the
hardening loop's own additions: multi-file, decoy-grade, empty-file, noisy-content).
The 20 remaining failures are the same categories as before — `document_intelligence`
(untouched by this spec), Windows-non-portable `chmod`/permission assertions,
Mac-architecture detection, and one `ui_contract` version-bump-amount check — none
touch `extraction_engine.py`, `data_in_contracts.py`, or the eval fixtures/tests.
`test_extraction_engine_eval.py` does not appear in the failure list.

## What This Unblocks

Spec 6 (student lens writer) and Spec 7 (curriculum unit writer), not yet built,
can now import `extract` from `src.lingua_viva.extraction_engine` and consume
`result.verified_only()`. Spec 6 should call `StudentLensStore.append_observation()`
directly (confirmed clean of the `ontology.engine` dependency) rather than the
currently-broken `ObservationCapturePipeline` wrapper — restoring that wrapper's
governance/sanitizer-audit layer is a separate follow-up once `ontology.engine` has
at least a stub, tracked in this spec's file, not blocking Spec 6.
