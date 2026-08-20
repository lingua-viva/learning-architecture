# BUILD PROMPT — LV Unified Real-Data Fix (2026-08-19)

You are the fix agent for the Lingua Viva real-data pipeline wave. You are building, not
researching — the diagnosis is done and verified. Your job is to execute
`dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` in its binding order.

## Why this build, why now — current state and the stakes

**There is a live demo TOMORROW (2026-08-20), in front of the real teacher, on her real
school files.** The two workflows being demoed are exactly the two this build fixes:

1. **Lesson-content diversification** from a real IB coursework file (Prepare → 3 tiers).
2. **Student lens creation** from the real school file set — lenses ONLY for her class
   (20 students — her class COLUMN; the grade sheet holds 41 across two side-by-side
   class columns, and both-columns-as-one-class is a FAIL), enriched from the support
   files, ignoring the curriculum/calendar
   files entirely.

**Current state (measured 2026-08-19, desktop-v0.2.64 live):** both workflows fail on
real files while looking green. Content generation silently swaps in generic template
text (thinking-model auto-pick returns empty content, fallback fires with no signal —
the demo would show template filler as if it were AI output). Lens ingest on the five
real files would create ~940 mostly-fake student lenses synced toward her Drive, while
the one file that matters yields ZERO students and no lens gets class attribution or
enrichment. Demoing today's build as-is is not an option.

**Why this survived until now — read this so you don't repeat it.** Every prior pass
tested on idealized files and trusted the system's own reporting, and the system lies
about itself in five distinct ways:

- **Failures present as success.** Template fallback returns 200 with plausible text;
  empty thinking-model output carries `error: <none>`. Nothing red anywhere.
- **When it does report failure, it reports the wrong reason.** A privacy refusal
  surfaces as `invalid JSON after retry` — everyone debugged JSON, not the model gate.
- **Gates that report as working but cannot fail.** Flat 0.99 confidence makes the 0.7
  threshold dead code that looks like a functioning check.
- **Two normalizers that agreed on every test machine** until `:latest` tags made the
  picker and the gate disagree — enrichment has been silently dead on real hardware.
- **No denominator.** "Students detected: N" goes up when detection gets worse. Without
  ground truth per file, 637 false positives read as success.

The fix agent before you would have "fixed" these by testing the happy path and reading
the green output. You will not, because Phase 0 builds the instrument first and every
STEP verifies against labelled ground truth.

**Build for the teacher, never for the demo (operator STANDING rule, 2026-08-19).**
The demo sets the *clock*, never the *target*: nothing you build may only work under
demo conditions (registered accounts, operator credentials, idealized files, hidden
dev-machine state). Acceptance is always "works for any teacher with zero special
access." The spec's stop points (§9) set the priority under the clock: Phase 0 →
STEP 4 (real lens creation scoped to one class, no garbage) plus STEP 8 + STEP 10
(content generation that either genuinely works or says honestly that it didn't) is
the minimum coherent product. STEPs 5–7, 9, 11–12 follow. Do not gold-plate an early
STEP at the cost of that set. Do not skip Phase 0 to save time — an unpreviewed
misfire into a real teacher's Drive is the one strictly unacceptable outcome.

## Read first, in this order

1. `dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` — the spec. Its build order is
   BINDING. Its prohibitions (§5) are absolute.
2. `dev/FINDINGS_REAL_DATA_PIPELINE_AUDIT_2026-08-19.md` — the sixteen findings (C1–C5,
   L1–L10) with exact file:line references, plus the verified-good list so you do not
   re-litigate what already works.
3. `~/Downloads/NEXT_STEPS_REAL_DATA_PIPELINE_2026-08-19.md` — the sequencing rationale
   and [MC] precedents (local file; if missing, the spec restates everything binding).
4. `AGENTS.md` — the definition of PUSH and the 7-step verification checklist.
5. `dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` §6 — required checklist before any
   new backend route.
6. `dev/SPEC_LV_DRIVE_PER_FILE_ACCESS_2026-08-19.md` — Drive is now `drive.file`
   (per-file access, NEVER widen the scope — a class-lock test enforces this).
   Credentials are done. Pre-existing school files come in by direct upload, not Drive
   link — which is this build's ingest path anyway.

## The one-line diagnosis you are fixing

The pipeline destroys the structure that contains the answer, then tries to recover the
answer by guessing at text. Structure preservation (STEP 1) is the keystone; three P0s
sit on top of it. Do not fix in filed priority order.

## Hard constraints — violating any of these ends the run

- **Phase 0 first.** No fix code runs against the real files at `~/Downloads/` until the
  preview/dry-run path (spec §2A) is merged with its preview-never-writes lock test
  green, AND the labelled corpus + scorer + sealed holdout (§2B) exist. One misfire
  creates hundreds of lenses in a real teacher's Drive.
- **Privacy.** Never commit real student/colleague/school names. The labelled corpus and
  the real files stay local. Committed fixtures use synthetic names replicating the four
  structural shapes (spec §2B.4). Check `publication-policy.md` before any commit.
- **The holdout stays sealed** until every planned STEP is done. Opened exactly once.
- **`MC_AGENT=1`** on every run you execute.
- **Do not touch the uncommitted .deb WIP files** in the working tree. Hunk-isolate your
  commits; commit only what you changed.
- **Do not extend the name blocklist.** Positive structural conditions only.
- **One normalizer** (STEP 7): extract the canonical model-name normalizer; never patch
  `:latest` handling on one side. Add the test that fails if a second path appears.
- **No new hardcoded confidence.** Either derive it and prove discrimination on the
  corpus, or delete the dead gate (STEP 3).
- **STEP 9 (medical category) is gated** on operator ruling §8-2 — skip it unless the
  ruling is in the conversation.
- Rulings §8-1/§8-3 defaults until told otherwise: always-preview; identity always
  queues, never auto-merges.

## Build order (spec §2–§4; stoppable at spec §9 stop points)

Phase 0A (preview/dry-run) → Phase 0B (corpus + scorer + holdout) → STEP 1 (structure
preservation) → STEP 2 (structural detection) → STEP 3 (confidence discriminates or gate
deleted) → STEP 4 (class membership + "my class" scope) → STEP 5 (identity resolution +
unresolved queue) → STEP 6 (enrichment veto) → STEP 7 (one normalizer + honest failure
reporting) → STEP 8 (model governance: never cloud from local detector, `LV_REASON_MODEL`
override everywhere, per-call model logging, `"think": false` for thinking models,
empty-content-with-no-error = failure, VRAM residency in auto-pick) → [STEP 9 if ruled]
→ STEP 10 (generation honesty: loud template fallback + non-empty foundational tier) →
STEP 11 (metadata from structure) → STEP 12 (excerpt budget, only if time permits).

Each STEP ends with: its scorer run (synthetic corpus in tests, real corpus locally),
its class-lock test(s) green, and a short evidence note in the report. Do not start the
next STEP with a red scorer regression.

## Key code anchors (verified 08-19; re-verify line numbers before editing)

- Ingest job + bulk threshold: `src/web.py:2501` (`_run_ingest_job`), `:2378`
  (`BULK_IMPORT_CONFIRMATION_THRESHOLD`), `:2377` (dead `INGEST_CONFIDENCE_THRESHOLD`)
- Detection: `src/lingua_viva/docpipe/extract.py:646` (`_NAME_BIGRAM`), `:649`
  (`_detect_students`), `:40` (`VERBATIM_STUDENT_CONFIDENCE`), `:46` (blocklist)
- Structured xlsx path: `extract.py:273` (`_xlsx_support_extract`), `:79`
  (`_SHEET_FIELD_MAP`) — sheet-TITLE matching is the only structured entry; real files
  use class-named sheets with category COLUMNS
- Enrichment (additive-only): `extract.py:692` (`_model_enrich_students`)
- Profile fields: `src/lingua_viva/docpipe/lens.py:14` (`PROFILE_FIELDS`, 10 categories,
  no medical)
- Model plumbing: `src/lingua_viva/docpipe/model.py:59-66` (hard-coded
  `detect_model()` + `local_only=True`), `src/lingua_viva/config.py:29,468`
  (`CLOUD_FALLBACK` returned by the "local" detector), `:18`
  (`LOCAL_MODEL_PREFERENCE[0]` = thinking model), `model_gate.py:93`
  (`is_provably_local_model`, no `:latest` strip)
- Reasoning: `src/lingua_viva/reasoning.py:52-192` (`reason()`; note :160 — model only
  called when `system_prompt` present), timeout `:250-254`
- Lesson generation: `src/lingua_viva/lesson_materials.py:~529`
  (`_generate_tier_material` silent fallback), `:509` (`_source_excerpt`, 1500 cap),
  `:929` (`parse_lesson_file_metadata`)
- Existing patterns to reuse: unattributed-review queue
  (`/api/students/ingest/unattributed`, `class_folder_ingest.py`), `sync_status`
  (Drive leg — mirror for generation status), `teacher_roster` table (08-19 build).

## Verification and shipping

- Binding acceptance gates: spec §6 — the per-file scorer table, the single end-to-end
  assertion (20 attributed + enriched lenses — count never grows on enrichment — zero
  from curriculum/calendar), the
  content-side check (real PDF → grounded 3 tiers with honest status on the governed
  auto-pick), then the holdout, once.
- Full test suite green (`pytest -q tests/`), `lv preflight` green, UI contract bumped
  for any UI/route change, route-reachability classified.
- Mandatory Claudia-lens UX audit before push.
- Write the report: `dev/REPORT_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` — per-STEP
  evidence, corpus hash, scorer before/after tables, holdout result, found-not-fixed
  list. Update the `dev/INDEX.md` status row in the same commit as any status change.
- PUSH means live and downloadable NOW per AGENTS.md. Do not claim it otherwise. If the
  operator has not asked you to push, stop at committed + report and say so plainly.
