# SPEC — Student Lens Full Circle (Drive → Lens → Observations → Drive) — 2026-08-08

**Priority: P0 — must work this week.** Customer commitments from the 2026-08-06 Still I Rise
sync (transcript on operator's machine; recap actions restated below) plus the operator's
ruling: "producing an actual student profile all the way through."

## Goal statement

A teacher connects a Google Drive folder containing **unstructured** student documentation,
the app creates **one lens per student**, teacher observations **update that lens**, and the
updated lens is **automatically written back** to a specific Drive folder — with different
folders per category, **some private/restricted**. The whole circle runs without the
operator in the loop and without any raw narration or PII leaving the machine.

## What already exists (build on it, do not rebuild)

| Piece | Where | State |
|---|---|---|
| Drive list/download/upload | `src/lingua_viva/google_drive_integration.py` (`list_folder_files`, `download_file_text`, `import_files`, `upload_text_to_folder`) | WORKS |
| OAuth | `src/lingua_viva/google_drive_oauth.py` | WORKS |
| Lens push + whitewash boundary | `src/lingua_viva/drive_sync.py` (`sync_lens_to_drive`, `format_lens_markdown`; raw narration excluded at lines ~237-250) | WORKS, single-folder |
| Lens store + observations | `src/education/student_lens.py` (`StudentLensStore`, `Observation`, `append_observation`, `update_profile`, `list_lenses_for_teacher`) | WORKS, append-only |
| Lens scaffold from documents | `src/lingua_viva/docpipe/lens.py` (T4, `SPEC_T4_LENS_ENGINE_2026-08-04`) | WORKS, single-doc oriented |
| PII gate | `src/lingua_viva/privacy.py` (`assert_safe_for_external_output`, `redact_runtime_text`) | WORKS |
| Folder categories | Sources UI: student evidence / teacher artifacts / general / assigned | WORKS, 4 categories |
| Students bulk ingest endpoint | `src/web.py` `students_ingest` + undo + `bulk_review_required` gating; xlsx/docx/pdf extraction in `docpipe/extract.py` (commit `303b7cc`, 08-06) | WORKS — G1 builds ON this endpoint, not beside it |
| SIR traits taxonomy | `src/education/ethos.py` `still_i_rise_seed` rewrite + absence signal (commit `f164359`, 08-06) | PARTIAL G5 — audit which of the nine keys/evidence-mapping already exist; close gaps, don't rebuild |

## The five gaps this spec closes

### G1 — Batch ingest: unstructured class folder → N lenses
- New: `ingest_class_folder(folder_id, teacher_id)` — walks a connected Drive folder
  (recursively, bounded by the existing 100MB/H2 caps), downloads text, and **partitions
  documents by student** before scaffolding.
- Student attribution is the hard part of unstructured input. Strategy, in order:
  filename match against existing roster names → in-document name match (first page /
  header scan) → UNATTRIBUTED bucket surfaced to the teacher for manual assignment.
  **Never guess silently**: every attribution carries `attribution_method` +
  `attribution_confidence` in the lens's evidence ledger; UNATTRIBUTED docs block nothing
  — they wait in a review list.
- For each student: create lens via the T4 scaffold path if none exists; if a lens exists,
  ingest as new evidence (append), never overwrite.
- Class size target: 15 per class. One run must handle a full class folder.

### G2 — Observations actually update the lens
- Today `append_observation()` appends to SQLite and stops; `update_profile()` is a
  separate manual call. Close the seam: after each saved observation, run a
  **lens-refresh step** that recomputes the affected profile fields from the append-only
  log (snapshot pattern already implied by the store — make it real and automatic).
- The refresh must be deterministic where possible (counts, dates, CEFR/RTI fields) and
  model-assisted only for narrative synthesis fields. Model-assisted output lands as
  DRAFT until the nightly/next export, never blocks the save.

### G3 — Category-routed write-back, including PRIVATE folders
- Extend `drive_sync.py` from one `sync_folder_id` to a **folder map**:
  `{category → folder_id}` with categories = the existing four + a new fifth
  **personal/confidential** category (final name pending Christianna — default to
  `"Personal"` in code, display-name configurable; she found "confidential" unwelcoming).
- Routing rule: the shared lens markdown goes to the general/student-summaries folder;
  any observation tagged personal/confidential is **excluded from the shared lens
  entirely** and its (whitewashed-per-policy) record goes ONLY to the personal folder.
- **Permission model is Drive-native and stays that way** (operator's own words in the
  sync: "I don't own the permissions... you just control who accesses it"): the app
  writes with the connected account's OAuth; if the account can't reach a folder, the
  write fails visibly and is queued, never rerouted to a less-private folder.
  **Fail-closed: a personal-category item with no reachable personal folder is never
  written anywhere else.**
- CPS/abuse-sign auto-flagging is **out of scope this week** (Christianna owes the
  category list). Leave the hook: observations carry a `category` field; a future
  classifier can set it. Do not build the classifier now.

### G4 — Scheduled auto-sync (the "once a day" promise)
- A daily (configurable) background sync that re-exports every dirty lens to its mapped
  folders + a manual "Sync now" per student and per class. Reuse the existing
  fire-and-forget `sync_lens_to_drive` shape; add a sync ledger (per-student last-synced,
  last-attempt, failure reason) surfaced in the UI. Preview-before-share stays: first
  export of a new lens requires one-time teacher approval; subsequent daily updates of an
  approved lens auto-push.

### G5 — Nine manifesto keys on the profile
- Add to the lens schema, as a section **separate from** the T4 learning-needs fields:
  traits `self_worth`, `self_discipline`; characteristics `critical_thinking`,
  `emotional_intelligence`, `self_organization`, `grit`, `social_intelligence`,
  `entrepreneurship`, `integrity`. Each key = evidence list (append-only, dated,
  teacher-attributed — same pattern as `SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01`).
- Mapping observations → keys, per the sync agreement: **optional dropdown + model
  best-guess inference** with a general fallback. Nothing obligatory for the teacher.
  Inference uses the manifesto definitions doc as the matching framework (operator will
  place the five-page manifesto from Slack into the repo/config; builder: FLAG if absent
  and implement against the nine names + a definitions-file interface).
  Every inferred mapping is marked `inferred` and is teacher-correctable; corrections are
  the tuning data. Accuracy is explicitly trial-and-error with the customer — ship the
  simple version.
- Rename the parent-facing summary to **"Student Summaries"** everywhere it is surfaced
  (UI label + export title; keep internal identifiers stable if renaming is invasive).

## Privacy law (unchanged, restated because this build touches the boundary)
- Raw transcripts / teacher-edited narration / Personal Context NEVER leave the machine
  (`SPEC_LENS_PRIMITIVE_2026-08-04` DOES boundary; `drive_sync.py` whitewash section).
- Every new egress path (G3, G4) calls `assert_safe_for_external_output` before upload.
- Personal-category content never appears in any shared artifact, ever, including sync
  ledgers and error messages.

## Non-goals (this week)
- CPS alerting / abuse-sign classifier (G3 hook only). Slack bot. Rubric generator.
  Voice expansion (see `SPEC_LV_VOICE_SCOPE_NARROWED_2026-08-08.md`). Any change to the
  observation capture UI beyond the optional key dropdown.

## Acceptance (all must pass on the operator's machine, real Drive account)
1. Point at an unstructured folder with ≥10 students' mixed documents → ≥10 lenses
   created, UNATTRIBUTED list correct, zero silent misattributions on spot-check.
2. Record an observation → lens profile visibly updated without a manual second step.
3. Observation tagged personal → absent from shared lens export; present only in the
   personal folder; with the personal folder unmapped, it is written NOWHERE and the
   failure is visible.
4. Daily sync (run manually in test) re-exports dirty lenses to correct per-category
   folders; sync ledger accurate.
5. Nine keys visible on the profile; a "grit"-worded observation lands under grit via
   inference; correction UI works.
6. `assert_safe_for_external_output` exercised by a test on every new egress call site.
7. Full regression suite green; released through the (now-working) auto-release chain;
   7-step push verification from `AGENTS.md`.
