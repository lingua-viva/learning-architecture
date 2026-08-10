# Two-Week Plan, Phase 1 — Build Prompt (2026-08-06)

**Context you need (you have no memory of the meeting that produced this):** Still I Rise
is a real pilot school using Lingua Viva. On the 2026-08-06 bi-weekly sync, Olga (the
on-the-ground lead trying to pilot this with 2-3 teachers) reported 4 blocking problems
in the app's Slack channel. All 4 were traced to real code this session — no guessing.
Full plan + reasoning: `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md` — **read that first**, this
prompt only covers the "ready to build now" half of it (items #1-5). Items #6-11 in that
plan (confidential/CPS category, manifesto traits, trait mapping, rubric generator, Slack
bot) are explicitly **gated on input from the school** that hasn't arrived yet — do not
build them, do not scope them, they are out of bounds for this prompt.

**Deadline context:** next sync is 2026-08-20. Olga is actively blocked *today* on items
#1-#3 — she has real false student data in her instance right now and cannot re-upload
her class list safely until #1 ships. Prioritize in the order below, not alphabetically.

Read first: `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md` (full root-cause detail + file:line
citations for every item below — this prompt summarizes, that doc is the source of truth).

---

## How this was prioritized (added 2026-08-08, for the audit)

This section explains the classification method, not just the resulting order, so a
future prompt-writer can reuse or challenge the method rather than just the output.

1. **Root cause traced to code before anything got written.** Every item below cites
   actual file:line evidence gathered by reading the source, not inferred from the
   meeting notes alone. One correction happened mid-session: the first pass assumed
   Olga's upload complaint pointed at `/api/ingest` (the PDF-only curriculum path);
   grepping the real request flow showed the actual path is `/api/students/ingest`
   backed by `docpipe/extract.py`, and the plan was corrected before publishing.
2. **Primary split: ready-to-build-now vs. gated-on-external-input** — not by feature
   category or size. Items 1-5 (this prompt) needed no further input from the school.
   Items 6-11 in the parent build plan (confidential/CPS category, manifesto traits,
   trait-mapping tuning, rubric generator, Slack bot) each depend on something the
   school committed to sending but hadn't yet (Christianna's abuse-signs list, a
   concrete Slack use-case, rubric requirements) — building or even scoping those
   ahead of that input risks baking in wrong assumptions, so they were explicitly
   fenced out of this build window rather than half-built.
3. **Within the ready-now set, ordered by who is blocked today, not by size.** Olga
   has real, incorrectly-created student data in her live instance right now and
   cannot safely re-upload her class list until Item 1 ships — so Items 1-2 (format
   support + a bulk-undo escape hatch) lead. Item 3 (confirmation gate) is preventive
   rather than urgent — it stops the *next* bad import, not the current one — so it
   comes after the immediate unblock. Item 4 (grades 1-12) is small and isolated.
   Item 5 (Perplexity/Rime key persistence) comes last because neither broken
   integration blocks Olga's pilot workflow, even though both are fully broken.
4. **Two same-morning, unrelated-looking issues were folded into one item.** The
   Perplexity key failure (seen on the operator's own machine) and the Rime
   deprecation email share one actual root cause — neither key has a durable,
   Settings-backed storage location — so they became a single Item 5 instead of two
   separate asks. The Rime deprecation email specifically was downgraded to "confirm
   via one email to Rime support," not a code task, after checking the actual
   `RIME_MODEL_ID` in use (`mistv3`) against the model the deprecation notice names
   (`arcana`) — they don't match, so no migration code was scoped.
5. **A "what NOT to build" list was written proactively**, not reactively, to keep
   the gated items (rubric generator, Slack bot, auto daily Drive push, a 5th Drive
   category) from getting absorbed into this window by momentum. This repo has a
   documented pattern of build windows drifting past their stated scope (see
   `SPEC_LV_VOICE_SCOPE_NARROWED_2026-08-08.md`'s own operator ruling that "the last
   build round drifted toward full voice re-integration") — the explicit fence here
   was meant to pre-empt the same drift for this window.

---

## Item 1 (Day 1-2, do first) — Class-list upload accepts real school formats

**Root cause:** `/api/students/ingest` (`src/web.py:2365`) → `docpipe/extract.py:_normalize()`
(`src/lingua_viva/docpipe/extract.py:104-116`) only accepts `.md`/`.txt`/`.csv`/`.pdf`.
Real class lists are `.xlsx`/`.docx`. Anything else raises `ValueError("unsupported format
for extraction...")`, surfaced to the teacher as `job["error"] = f"Could not read this
document: {error}"` (`src/web.py:2360-2362`).

**Fix:**
- Add `.xlsx`/`.docx` text extraction to `_normalize()` — `openpyxl` for xlsx (read all
  cell text per sheet, join rows), `python-docx` for docx (paragraph + table text). Follow
  the exact pattern already used for PDF (`_pdf_text()`, same file, lines 128-144): missing
  library → clear `ValueError`, never a silent empty result.
- Add both new extensions to `TEXT_EXTS`/a new `SPREADSHEET_EXTS`/`DOCX_MIMES` set as
  appropriate, and to whatever MIME-sniffing the upload path relies on.
- Add both libraries to the desktop bootstrap's Python dependency list (wherever
  `faster-whisper`/`pdfplumber` etc. are declared) so this doesn't work in dev and fail in
  the packaged app — check `desktop/electron/bootstrap.ts`.
- Update the client file input hint at `static/index.html:2167` ("Point at a class list,
  roster, or lesson plan...") to name the actually-supported formats.

**Acceptance:**
- Upload a real `.xlsx` class list (build a small fixture: 5-10 First Last rows plus a
  header row) → job completes, names detected.
- Upload a `.docx` with the same content in a table → same result.
- Upload an unsupported format (e.g. `.pptx`) → same honest `ValueError` message pattern
  as today, not a crash.
- Existing `.csv`/`.txt`/`.md`/`.pdf` ingest tests still pass unchanged.

---

## Item 2 (Day 1-2, do alongside Item 1) — Bulk undo for a bad import

**Root cause:** `_run_ingest_job` (`src/web.py:2310-2350`) can create many students in one
job (one per detected name at confidence ≥ 0.7 — see Item 3 below for why that's basically
always). Today, undoing a bad import means archiving each student one at a time via
`DELETE /api/students/{student_id}` (`src/web.py:4239`, soft-delete/tombstone). There is no
"undo this whole import" action.

**Fix:**
- New endpoint, e.g. `DELETE /api/students/ingest/{job_id}` (or `/by-source/{source_id}`):
  looks up the job's `students_created` list (already tracked per-job, see
  `job["students_created"].append(created)` at `src/web.py:2343`) and archives every one of
  those student_ids using the existing soft-delete path — same tombstone semantics as
  `archive_student`, just applied in bulk. Persist enough job state to survive a page reload
  (jobs may already be persisted — check `_ingest_job`/`_new_ingest_job` for where job state
  lives before deciding whether this needs new storage or just a new read+loop).
- Surface this in the UI: after an import completes, show "Undo this import" alongside the
  created-students list, for some reasonable window (at minimum: for the lifetime of the
  job record).
- This does NOT need to be undo-after-undo-proof or support re-doing — a straightforward
  bulk-archive of exactly the students this job created is sufficient.

**Acceptance:**
- Import a 5-name fixture, confirm 5 students created, call bulk-undo, confirm all 5 are
  archived (same state as calling `DELETE /api/students/{id}` on each individually).
- Undo does not touch students that existed before the import or were created by a
  different job.
- Test with the existing archive/soft-delete test patterns as a reference
  (`tests/` — search for `archive_student` tests).

---

## Item 3 (Day 3-4) — Require confirmation before a bulk roster import creates students

**Root cause:** `_detect_students()` (`docpipe/extract.py:322-351`) gives every capitalized
First-Last bigram `VERBATIM_STUDENT_CONFIDENCE = 0.99` — always above the
`INGEST_CONFIDENCE_THRESHOLD = 0.7` gate at `src/web.py:2341`. So a class list — which is
by definition a list of names — auto-creates a real, permanent student profile per name
with **zero teacher confirmation**. Low-confidence names already get a review step
(`job["needs_confirmation"]`, `src/web.py:2344-2350` + the existing
`/api/students/ingest/confirm` endpoint at `static/index.html:2259` / find its `src/web.py`
counterpart) — this item extends that same review gate to the high-confidence bulk case.

**Fix:**
- When a single import job detects **more than N students** (suggest N=2 — a single
  work-sample document naming one or two students is a different case from a roster
  naming a whole class), route ALL detected names through the existing
  `needs_confirmation` / confirm-endpoint path instead of auto-creating — regardless of
  confidence score. Single or dual detections in an otherwise-prose document (the T9 use
  case this pipeline was originally built for — see `dev/SPEC_T9_INGEST_UI_2026-08-04.md`)
  can keep today's auto-create behavior; that distinction is what makes this safe without
  breaking the existing single-student-observation flow.
- Confirm UI: show the full detected-name list with checkboxes (default-checked), "Create
  N students" button — mirrors what a bulk roster import should have looked like from the
  start.
- Make sure this composes correctly with Item 2 — a confirmed bulk-create should still be
  trackable as one job for bulk-undo purposes.

**Acceptance:**
- Import the 5-name fixture from Item 1/2 → job status shows `needs_confirmation` with 5
  entries, **zero** students created yet.
- Confirming all 5 creates exactly 5 students.
- Confirming a subset (e.g. 3 of 5) creates exactly those 3.
- Import a single-student work-sample fixture (1-2 names, prose document) → unchanged
  auto-create behavior (regression check — do not require confirmation for the case this
  pipeline was built for).

---

## Item 4 (Day 3-4) — Grades 1-12, decoupled from curriculum content

**Root cause:** `create_student` (`src/web.py:4204-4223`) validates `grade_level` against
`CurriculumService().get_overview()["grade_bands"]` — i.e. against which grades currently
have curriculum *content* loaded, not against a real list of valid school grades. Today
that's effectively G1-G5.

**Fix:**
- Define a canonical, independent grade list (G1-G12, or add PYP/MYP/DP labels if that's
  what this school actually uses — check `dev/ADD_STUDENT_FORM_DECISION_2026-08-04.md`,
  Decision 1, referenced in the docstring at `src/web.py:4193-4198`, for the reasoning
  behind the current dropdown before changing its shape).
- Change the validation in `create_student` to check against this new canonical list
  instead of `CurriculumService().get_overview()["grade_bands"]`. Curriculum-content
  coverage becomes irrelevant to whether a grade is a *valid student grade* — a student in
  G9 should be creatable even if no G9 curriculum units exist yet.
- Update the Add Student dropdown in `static/index.html` to the new full list.
- `CurriculumService._normalize_grade()` (`src/lingua_viva/curriculum.py:107-113`) can stay
  as-is — it's just string normalization ("Grade 3" → "G3"), not the bug.

**Acceptance:**
- `POST /api/students` with `grade_level: "G9"` succeeds even with no G9 curriculum
  content loaded.
- `POST /api/students` with an invalid grade (e.g. `"G13"`, `"3rd grade"`) still returns
  400 with the valid grade list in the error body — same error *shape* as today, just a
  bigger valid set.
- Existing grade-validation tests updated to the new canonical list, not deleted.

---

## Item 5 (Day 3-4) — Perplexity + Rime keys: real Settings persistence

**Root cause:**
- `_perplexity_api_key()` (`src/web.py:1962-1969`) checks `provider_api_key("perplexity")`
  (reads `providers.json` via `src/lingua_viva/config.py:159-164`) then
  `PERPLEXITY_API_KEY` env var. Nothing in the app ever *writes* a `perplexity` entry to
  `providers.json` — the only connect flow (`/api/provider/connect`, `src/web.py:6106`,
  backed by `SUPPORTED_PROVIDERS` in `src/provider_config.py`) is scoped to reasoning-model
  providers (Ollama/OpenAI/Groq/Mistral). So Perplexity is env-var-only in practice.
- `_rime_api_key()` (`src/web.py:1909-1910`) is env-var-only, full stop — no
  `providers.json` fallback exists.
- The desktop Electron bootstrap never sets either env var for a packaged install — check
  `desktop/electron/bootstrap.ts` and `main.ts` to confirm (this session did not find a
  match there for either key name).

**Fix:**
- Extend `providers.json`'s schema (or add a small sibling config file if that's cleaner —
  your call, but keep it inside `lv_home()` / config dir, same pattern as
  `provider_config_path()`) to hold `perplexity_api_key` and `rime_api_key` as flat,
  independently-settable values — these are NOT "reasoning providers" and don't need a
  `default_provider`/model shape, just a key each.
- Add a Settings UI section (Ask / Voice, wherever those currently render in
  `static/index.html` — check the existing Settings → Sync/Voice sections referenced in
  `dev/PROMPT_CHIP_QA_0.2.42_2026-08-06.md` checks #10/#19) with a field + save button for
  each key. Save via a new small endpoint (e.g. `POST /api/settings/keys`), read back via
  `/api/provider` or a new status field so Settings can show "configured" vs not without
  ever echoing the key value back.
- Update `_perplexity_api_key()` to read the new config location instead of/in addition to
  `provider_api_key("perplexity")` (that call was reading a key that could never get
  written — either repurpose it correctly or replace it, don't leave dead code that looks
  functional).
- Update `_rime_api_key()` to check the new config location first, env var as fallback
  (keeps manual/dev override working).
- **Do not touch the Rime model_id ("mistv3", `src/web.py:2588`) or attempt any
  Arcana→Coda migration** — this integration doesn't use the Arcana model line, so the
  Aug 15 2026 deprecation email likely doesn't apply here. That's a one-line email to Rime
  support to confirm, not a code change. Leave a `# confirmed 2026-08-xx: mistv3 unaffected
  by Arcana deprecation` comment once that email is answered, not before.

**Acceptance:**
- A key entered in Settings persists across app restart and is used by `/api/query`
  (Perplexity, via Ask) and `/api/voice/tts` (Rime) without any env var set.
- An env var still works if set (back-compat, no regression for the current
  dev/QA-harness workflow that exports these manually).
- Settings never echoes back a previously-saved key's plaintext value (show "configured"/
  masked, same UX convention as any existing secret field in this app, if one exists —
  check before inventing a new pattern).
- Existing `tests/test_ask_perplexity.py` and voice TTS tests still pass.

---

## Rules for this build window

- Stay inside Items 1-5. Everything else in `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md` is
  gated on input from the school that has not arrived — do not build ahead of it, and flag
  clearly in your final report if it arrives mid-window (don't silently absorb new scope).
- Every fix above traces to a specific, cited root cause — if what you find in the code
  doesn't match the citation (line numbers drift fast in this repo), trust what you read
  over what's written here, but say so rather than silently building around a mismatch.
- Run the full suite (`pytest -q tests/`) before considering any item done — this repo's
  own recent history has a live pytest-mutates-real-files hazard
  (`unset LV_STATE_HOME LV_DESKTOP` first, then `git status --short` before and after).
- Commit each item separately, scoped to files it actually touches. Suggested messages:
  - `fix: accept .xlsx/.docx class-list uploads (item 1)`
  - `feat: bulk undo for a roster import (item 2)`
  - `fix: require confirmation before bulk roster import creates students (item 3)`
  - `feat: decouple grade validation from curriculum coverage, support G1-G12 (item 4)`
  - `feat: persist Perplexity/Rime keys via Settings (item 5)`
- **Never commit or push** without the operator's explicit go-ahead in this session — this
  repo's standing rule is one dedicated commit window, not autonomous commits mid-build.

---

## Status audit — added 2026-08-08

What was actually being worked on, and what happened after, verified against `git log`
and `git show` rather than assumed from this doc's own claims:

- **Items 1-5 (this prompt's entire scope): SHIPPED the same day**, commit `303b7cc feat:
  build Still I Rise phase 1 fixes` (2026-08-06). Confirmed by diff, not just the commit
  message: `STUDENT_GRADE_LEVELS` (G1-G12) added for Item 4; `_xlsx_text()`/`_docx_text()`
  added mirroring the existing `_pdf_text()` error pattern for Item 1; `_ingest_jobs_dir()`
  / `_save_ingest_job()` + a new `students_ingest_undo` endpoint for Item 2;
  `BULK_IMPORT_CONFIRMATION_THRESHOLD` + `bulk_review_required` gating for Item 3; a new
  `settings_keys` endpoint for Item 5. All match this prompt's suggested fixes closely,
  including several suggested constant names.
- **Gated items moved faster than this prompt assumed.** `f164359 feat: add SIR traits and
  absence signal` and `88c9e4b fix: harden SIR summaries and voice dedup` also landed
  2026-08-06, i.e. inside the same window this prompt tried to fence to Items 1-5 only.
  `f164359` rewrites `ethos_seed()` into a "still_i_rise_seed" taxonomy — substantial
  progress on the parent plan's Item 7 (nine manifesto traits), apparently unblocked
  because the manifesto doc was already available in Slack, matching this doc's own note
  that Item 7 was "not blocked, just sequenced." `88c9e4b` plausibly covers Item 9
  (parent-summary rename/hardening) and part of Item 6 (personal-context wiring) — this
  was not independently re-verified line-by-line and should be treated as likely, not
  confirmed, if it matters for future work.
- **A further slice shipped 2026-08-08**, `2ffdcba feat: add printable packets and
  readable lens exports` (per `dev/HANDOFF_CODEX_LINGUA_VIVA_WINDOW_2026-08-08.md`), built
  by treating this prompt as the designated tie-breaker source. It added a teacher-facing
  printable-packet preview/approve flow and converted Drive student-lens export from
  JSON-shaped output to privacy-checked Markdown. Full suite `2009 passed, 13 skipped`
  before push; prod is now at `f31657d chore(release): pin desktop-v0.2.45`.
- **Also 2026-08-08: the remaining gated items got superseded by new specs, not carried
  forward as-is.** `SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md` and
  `SPEC_LV_TIERED_MATERIALS_FULL_CIRCLE_2026-08-08.md` (both `dev/INDEX.md`-listed as
  `DRAFT — P0 this week, not yet built`) reframe Items 6/7/8 (confidential category,
  trait mapping, manifesto keys) and the lesson-materials/tiering work as one end-to-end
  Drive-to-lens-to-Drive loop and one end-to-end Drive-to-library-to-tiers-to-Drive loop,
  respectively, rather than isolated features. `SPEC_LV_VOICE_SCOPE_NARROWED_2026-08-08.md`
  separately froze voice scope to two surfaces after an operator ruling that a prior
  window had drifted. Anyone resuming work after this prompt should treat those three
  specs as the current frontier, not the original Items 8/10/11 in the parent build plan
  — rubric generator and Slack bot specifically remain unscoped; no evidence either has
  moved since this prompt was written.
- **One item outside this prompt's original scope surfaced as unresolved and still open**:
  the Codex handoff reports the app's `/api/health` endpoint returning `PRIVATE_RISK` on
  a normal local launch (`127.0.0.1:8788`) — cause not yet identified. Worth a fast
  follow-up even though it was never part of Items 1-5.
