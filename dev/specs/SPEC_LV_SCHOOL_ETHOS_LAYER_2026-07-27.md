# SPEC: School Ethos Layer — ethos-as-data, lens-as-mechanism

**Date**: 2026-07-27
**Status**: BUILT same day (uncommitted — operator commit window)
**Driver**: First-customer request (Still I Rise pilot, MYP5 cohort, via the
ai-lingua-viva Slack channel): "build our 'ethos' into the canvas itself,
specifically our characteristics and traits that we are developing throughout
lessons and projects... teacher feedback recorded into these on student
profiles to use as evidence in students' reports." Plus profile-level
Academic Strengths / Personal Strengths sections alongside the 7 IEP-style
support categories (already shipped as student lens v2).

## Architecture Decision

**Ethos-as-data, lens-as-mechanism.** The generic mechanism ships in this
public repo; the school-specific trait content is local data, never
committed (publication-policy.md: no proprietary school documents).

- Taxonomy file: `~/.lingua-viva/ethos.yaml`, env seam `LV_ETHOS_PATH`
  (mirrors `LV_STUDENT_DB_PATH` — never `__file__`-relative, frozen-binary
  safe).
- Built-in seed: 3 generic core values (ambition/bravery/care) + 10 learner
  attributes paraphrased in our own words (IB learner profile shape,
  original descriptors — no copyrighted text). Real school docs swap in as
  data when the shared Drive folder link arrives; zero code change.

## Components (all built 2026-07-27)

1. **`src/education/ethos.py`** — taxonomy loader/validator/seed.
   `load_ethos()` (missing file → seed; invalid file → raises, never
   silently replaced), `save_ethos()`, `validate_ethos()` (id regex, dup
   detection, group ∈ value|learner_attribute, length caps),
   `match_traits()` (deterministic keyword match, suggestion-signal only),
   `format_traits_for_prompt()` (lens injection block).
2. **Student lens v2.1** (`src/education/student_lens.py`) — two new JSON
   columns with `ALTER TABLE` migration + normalize-with-warnings:
   - `strengths_profile`: profile-level `academic_strengths` /
     `personal_strengths` entry lists (`add_profile_strength`).
   - `ethos_profile`: `traits.{trait_id}.evidence[]` keyed by configurable
     taxonomy (`add_ethos_evidence` — trait membership validated against
     the active taxonomy or an injected `allowed_trait_ids`). Evidence
     items carry `confidence`; both writes bump `profile_version`.
3. **Capture wiring** (`src/education/observation_capture.py`) —
   `capture()` returns `ethos_trait_suggestions` (deterministic, no LLM,
   `model_suggested` / `pending_teacher_confirmation`); **never
   auto-written**. `confirm_ethos_suggestion()` is the only
   observation→ethos_profile path and writes `teacher_confirmed` with
   `source_observation_id`. Broken local taxonomy degrades to a
   `taxonomy_error` suggestion note — capture write path never breaks.
4. **Report export** (`StudentLensStore.export_ethos_report`) — report
   body includes only `REPORT_GRADE_CONFIDENCE`
   (`teacher_confirmed`/`imported_verified`) items;
   `include_unconfirmed=True` surfaces the rest in a separate
   `pending_review` section (teacher prep view, never report body). Label
   lookup degrades to trait ids if the taxonomy won't load — export is
   never blocked.
5. **`lenses/education/school-ethos.yaml`** — generic institutional lens,
   keyword-triggered (ethos/values/traits/report evidence...), enforces:
   taxonomy-only trait ids, behavior-cited evidence, suggestion-only model
   authority, developmental (non-deficit) framing.

## Invariant Under Test

Teacher review authority: nothing model-suggested is ever auto-written to
a profile or exported into a report body. This mirrors the trauma_flag
rule from the extraction write path (spec 5 of 5, 2026-07-23).

## Verification

- `tests/test_ethos.py`: 38 tests, all passing (taxonomy validation,
  v2.1 store methods, legacy-DB migration, corrupt-column normalization,
  suggestion-only capture, confirm path, report-grade filtering, lens
  activation).
- Existing suites unaffected: `test_student_lens.py` 32/32,
  `test_lenses.py` 9/9, observation/lens-related selection 100/100.

## Hardening Pass (same day, 15 iterations)

Adversarial probe → fix → verify, each locked in as a permanent test
(`TestHardening`, `tests/test_ethos.py` now 48 tests):

| # | Finding | Fix |
|---|---|---|
| 1 | **Measured false positives**: substring keyword matching fired 'care' on "scared"/"careless", 'goal' on "goalkeeper" | `match_traits` now word-boundary anchored (`(?<!\w)kw(?!\w)`, re.escape'd) |
| 2 | Seed phrase keywords missed inflections ("asked questions") | seed coverage extended |
| 3 | Report export was **fail-open**: evidence missing a `confidence` field defaulted to report-grade | fail-closed — missing confidence never reaches a report body |
| 4 | `OSError`/bad-encoding on ethos.yaml broke the capture write path (guard only caught `EthosValidationError`) | broad degrade-to-`taxonomy_error` guard; capture never breaks |
| 5 | `save_ethos` non-atomic — torn write would down the ethos layer (invalid file raises by design) | temp file + `os.replace` |
| 6 | **Measured crash**: non-dict items inside evidence/strength lists survived normalization → `AttributeError` in export | both normalizers drop non-object items with warnings |
| 7 | `confirm_ethos_suggestion` accepted forged/cross-student `observation_id` — evidence claiming a grounding that doesn't exist | source verified at write time (exists + belongs to student) or `ValueError` |
| 8 | No file-size boundary on teacher-owned taxonomy file | 1MB cap, refuse-to-parse |
| 9 | Signal keywords had no length cap | ≤100 chars each |
| 10 | Evidence/strength text stored unstripped | strip-on-store |
| 11 | Double-submit wrote duplicate evidence + spurious `profile_version` bumps | exact-duplicate (text+source) idempotency guard, no version bump |
| 12 | Unicode probe (Italian teacher notes) | word-boundary matching confirmed unicode-safe, tested |
| 13 | All probes encoded as permanent tests | `TestHardening`, 10 cases |
| 14 | Cross-surface regression | student_lens/lenses/observation suites 63/63, `lv preflight` 6/6 |
| 15 | Full-suite regression | green (see Verification) |

Known-and-accepted (documented, not fixed): read-modify-write profile
updates share the pre-existing single-connection pattern of
`add_support_entry` — multi-process write races are a structural property
of all profile writes and deserve their own spec, not a piecemeal fix
here. Lens keyword "trait" substring-matches "portrait" in the shared
LensEngine — cost is a harmless prompt modifier; false-negative cost of
removing the keyword is higher.

## Open (deferred, needs operator/UI lane)

- UI mount: suggestions chip in Observe review flow + ethos section in
  Students view + report export button (route-reachability gate applies —
  see ROOT_CAUSE_BUILT_NOT_MOUNTED §6 before adding routes).
- `src/web.py` routes for confirm/export (not built — no route without a
  same-commit UI call site, per the gate above).
- Real school ethos docs → `ethos.yaml` conversion once the shared Drive
  folder link is available (data-only swap).
