# BUILD REPORT — LV Unified Real-Data Fix Wave

**Spec:** `dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` (binding order)
**Started:** 2026-08-19 · **Status:** IN PROGRESS
**Privacy:** this report carries COUNTS ONLY. Real student/teacher names never
appear here, in fixtures, in tests, or in any committed file.

---

## Phase 0A — Always-preview ingest (§2A) — CODE COMPLETE

Detection never writes. `/api/students/ingest` now stops at job status
`preview` (creates nothing, syncs nothing); creation runs only on explicit
`POST /api/students/ingest/approve`; `POST /api/students/ingest/cancel`
leaves zero trace. Zero detections finish `done` directly.

- Job machine: queued → extracting → identifying → **preview** → (approve)
  creating → done | (cancel) cancelled | failed.
- Class-lock test: store count before/after + monkeypatched sync spies
  (`enqueue_lens` / `ensure_lens_sync_folder` / `trigger_sync`) record zero
  calls on preview (`tests/test_students_ingest.py`, 45 tests green).
- Claudia-lens: raw confidence numbers never render — boolean
  `low_confidence` badge only, locked by `"student.confidence" not in HTML`.
- Contracts: UI_CONTRACT bumped to **v159**; ROUTE_REACHABILITY 170 routes
  classified (approve/cancel routes added with call sites).
- Default preview-on pending operator ruling §8-1 (currently: always preview
  when ≥1 student detected).

## Phase 0B — Measurement instrument (§2B) — CODE COMPLETE

### Real corpus (local only, NEVER committed)
- Location: `~/Downloads/LV-lenses-test/` with `corpus/labels.json` (v2,
  chmod 444) — hand-labelled from file STRUCTURE (openpyxl reads),
  independent of the detection code, before any fix.
- **Frozen + hashed:** corpus hash
  `41d21053f2db4cf2435826f92cb17843ba5b95bc80a13a69fcfac41a01e0e17b`
  (`corpus/FROZEN.json`, per-file sha256s, frozen 2026-08-19).
- **Holdout:** the K-5 per-class support file is `sealed: true` — the scorer
  skips it unless `--open-holdout`; opened exactly once at the end (§6).
- Note-row labelling: 12 genuine "1/2 groups…" scheduling rows excluded;
  nickname-parenthesis names retained (labeller v2 fix).

### Scorer (committed)
- `src/lingua_viva/docpipe/corpus_scorer.py` — runs the REAL extraction
  pipeline (deterministic core, `model_client=None`), reports PER FILE
  precision / recall / FP count — never "students detected" alone.
- CLI: `MC_AGENT=1 python3 -m src.lingua_viva.docpipe.corpus_scorer <dir>`
  (`--open-holdout`, `--show-names` for local/private use only).
- Tests: `tests/test_detection_corpus_scorer.py` — 11 tests locking the
  instrument (math incl. None-on-zero-denominator, sealed skip, labels
  fallback layout, counts-only report privacy, real-pipeline consistency
  over the synthetic corpus). Quality gates live in the STEP tests, not here.

### Synthetic mirror (committed, CI)
- Generator: `scripts/build_synthetic_corpus.py` (deterministic) →
  `tests/fixtures/docpipe/synthetic-corpus/` — 5 files, 4 structural shapes,
  synthetic names, 32 expected students, own `labels.json`.

### BASELINE — real corpus, before any fix (2026-08-19)

| file (shape) | exp | det | TP | FP | FN | prec | rec |
|---|---|---|---|---|---|---|---|
| curriculum_mapping | 0 | 144 | 0 | **144** | 0 | 0.00 | n/a |
| cycle_calendar | 0 | 86 | 0 | **86** | 0 | 0.00 | n/a |
| single_sheet_support (3V) | 6 | 0 | 0 | 0 | 6 | n/a | **0.00** |
| grade_sheet_class_list | 417 | 637 | 90 | **547** | 327 | 0.14 | 0.22 |
| per_class_sheet_support (K-5) | SEALED — holdout | | | | | | |

### BASELINE — synthetic mirror, before any fix (2026-08-19)

| file (shape) | exp | det | TP | FP | FN | prec | rec |
|---|---|---|---|---|---|---|---|
| synthetic_class_list | 19 | 25 | 0 | 25 | 19 | 0.00 | 0.00 |
| synthetic_support_3v | 6 | 0 | 0 | 0 | 6 | n/a | 0.00 |
| synthetic_support_k5 | 7 | 12 | 2 | 10 | 5 | 0.17 | 0.29 |
| synthetic_curriculum | 0 | 18 | 0 | 18 | 0 | 0.00 | n/a |
| synthetic_calendar | 0 | 12 | 0 | 12 | 0 | 0.00 | n/a |

The mirror reproduces every failure class of the real baseline: Last/First
columns never joined (0 TP on class list), abbreviated support names missed
(recall 0), staff detected as students (K-5 FPs), capitalized non-English
bigrams detected as names (zero-student files). A fix that moves the real
numbers must move these; CI holds the line.

---

## STEP evidence (filled as each STEP lands)

### STEP 1 — Preserve structure at extraction (L9) — DONE

`_xlsx_row_spans` in `docpipe/extract.py`: generic xlsx now yields ONE SPAN
PER ROW with additive metadata (`sheet`, `row_index`, `cells` with real
column letters) — same additive pattern as the support path's `field_hint`,
so spans stay byte-exact slices and the grounding gate holds by
construction. Support path untouched; flat `_xlsx_text` retained for lesson
materials. `EXTRACTOR_VERSION` 1.0 → 1.1.

- **Gate (spec):** 3V-shaped fixture yields one span per row (7 = header +
  6 students), not 1 — locked in `tests/test_docpipe_extract.py`.
- **Latent bug found + fixed (failure-class chokepoint):** the extraction
  schema (`extraction.schema.json`) had `additionalProperties: false` on
  spans and no `student_support` in the `document_type` enum — so the
  2026-08-18 support-xlsx fix produced extractions the VAULT REFUSED
  ("Could not read this document") on every real support-file ingest.
  Schema now declares the additive span keys + the enum value; class locked
  by `test_xlsx_extractions_survive_the_vault_schema_gate` (real vault
  write for both xlsx paths).

Scorer movement from structure alone (no detection change yet):

| real corpus | before | after STEP 1 |
|---|---|---|
| curriculum FP | 144 | 125 |
| calendar FP | 86 | 86 |
| 3V recall | 0.00 | 0.00 (needs STEP 2) |
| class list prec / rec | 0.14 / 0.22 | **0.30 / 0.41** (TP 90→171, FP 547→404) |

Synthetic mirror: K-5 file went 0.17/0.29 → **1.00/1.00** (per-row spans
kill the cross-row false bigrams that glued staff names together); class
list/3V/zero-student files move to STEP 2's account.

### STEP 2 — Detect from structure, not text shape (L1, L3) — DONE

Structured documents (row spans with column identity) now use POSITIONAL
evidence only: a student is a value in a column whose header IS a
student-name label (exact label match — EN + IT: Student/Name/First/Last/
Nome/Cognome/Alunno/Studente...; "nome" resolves to first-name when paired
with a cognome column). A structured document with no student-name column
yields ZERO students. The bigram regex survives ONLY for unstructured
documents. Every detection now carries an `evidence` class
(`student_column` | `bigram_fallback` | `model`) — schema extended.

- First cut used SUBSTRING concept matching and failed on the real corpus:
  prose mentioning students ("...per studenti...", "Gli studenti sono...")
  and label-like non-name columns ("Student Support Plan") became name
  columns (curriculum 35 FP, 3V +5 FP). Fixed with the exact-label rule —
  a header is a label EQUAL to the concept, never prose containing it.
  Locked by `test_prose_mentioning_students_is_not_a_name_column`.
- No blocklist additions (§5 honored); the old blocklist now only serves
  the unstructured fallback. No new hardcoded confidence — the evidence
  class is the discrimination axis (STEP 3 settles the numbers).

**Gate results (real corpus):**

| real corpus | baseline | after STEP 2 | spec gate |
|---|---|---|---|
| curriculum FP | 144 | **0** | 0 ✓ |
| calendar FP | 86 | **0** | 0 ✓ |
| 3V recall / FP | 0.00 / 0 | **1.00 (6/6) / 0** | 6 ✓ |
| class list | 0.14/0.22 | 0 detections | (intermediate — STEP 4 reads the class-pair structure) |

Synthetic mirror: identical picture (3V 1.00/1.00, K-5 1.00/1.00,
curriculum+calendar 0 det, class list 0 pending STEP 4).

### STEP 3 — Confidence discriminates, or the gate is deleted (L1) — DONE

Spec outcome taken: **the gate is deleted** — and replaced by the evidence
class, which the corpus proved DOES discriminate. `VERBATIM_STUDENT_
CONFIDENCE = 0.99` flat made `INGEST_CONFIDENCE_THRESHOLD = 0.7` a check
that could never fire; it reported as a working gate on every import.

**Measured discrimination (the STEP 3 evidence), same real files:**

| evidence class | precision | source |
|---|---|---|
| `student_column` (STEP 2) | **1.00** (6/6 on 3V, 0 FP everywhere) | current scorer run |
| `bigram_fallback` (baseline) | **0.14 / 0.00 / 0.00** | frozen baseline tables above |

The evidence class predicts correctness; the number never did. So:

- `INGEST_CONFIDENCE_THRESHOLD` deleted (web.py). No replacement number —
  `_trusted_detection(student)` = `evidence == "student_column"`; missing
  evidence (older extractions) is untrusted (§5: no new hardcoded
  confidence).
- Preview `low_confidence` badge, small-import `needs_confirmation`, and
  roster warning flags all derive from the evidence class. Prose documents
  (bigram fallback, measured precision 0.14) now always require per-name
  confirmation on small imports — a high number can no longer buy trust.
- Class lock: `test_gate_rides_on_evidence_class_not_confidence_number` —
  bigram detection with confidence 0.99 still needs confirmation; detection
  with no evidence class is untrusted; the dead constant stays deleted
  (`not hasattr(web, "INGEST_CONFIDENCE_THRESHOLD")`).
- Real-corpus scorer re-run after the change: identical to STEP 2 (gate
  change, not a detection change).
- UI_CONTRACT bumped v159 → **v160** (server-side only; the boolean badge
  contract from v157 is unchanged — raw numbers still never render).

### STEP 4 — Class membership and "my class" (L4) — DONE

Grade-sheet class lists carry NO header labels — the SHAPE is the
evidence. `_sheet_class_pairs` (extract.py) recognizes the pair genre:
row 1 = class name above each Last|First column pair, row 2 = teacher,
roster rows fill BOTH columns of a pair. Detections carry `class`,
`grade` (sheet title), `teacher_attribution`; teachers are attribution,
never students (position, not text). Fail-closed guards, both earned on
the real corpus (see below): ≥2 pairs required, first two non-empty rows
must fill the same columns, no adjacent heading cells, and any row
filling a column outside the pairs is table data. The label-header rule
(STEP 2) wins per sheet; a lone "class"/"classe" column is scoping
metadata, never a name header — and on label sheets it now attaches
`class` to each detection (3V: her 3 of 6).

- **Regression the synthetic mirror missed, the real corpus caught:**
  first cut of the pair rule turned title+subtitle-over-a-grid sheets
  into a false (A,B) pair — real curriculum +217 FP, calendar +35 FP.
  Fixed with the ≥2-pairs and allowed-columns guards; class locked by
  `test_title_and_subtitle_over_a_grid_is_not_a_class_pair` (+ a same-
  shape synthetic guard test), so the mirror now holds this line in CI.
- **Scope option ("only my class"):** preview rows carry the class
  metadata + jobs list `preview_classes`; approve accepts `classes`
  (unknown class = 422, never a silent no-op; out-of-scope names skipped
  with an honest count warning). UI: scope picker on the preview panel,
  per-row class badges, button says exactly how many it will create.
  Roster attribution rides the existing `teacher_roster` wiring
  (`_register_roster`, add_to_roster source='ingest') — the approving
  teacher's roster gets exactly the class she scoped to.
- Locks: 8 new extract tests (membership, teacher exclusion, note rows,
  grid fail-closed ×2, label-wins + class scoping, lone-class column,
  vault schema gate for the new keys) + 5 new ingest tests (preview
  metadata, scoped approve, unscoped approve, unknown-class 422 then
  correct approve, UI wiring). Schema: `class`/`grade`/
  `teacher_attribution` added to students_detected (additive).
- UI_CONTRACT bumped v160 → **v161** (web.py + index.html).

**Gate results (real corpus):**

| real corpus | baseline | after STEP 4 | spec gate |
|---|---|---|---|
| class list prec / rec | 0.14 / 0.22 (FP 547) | **1.00 / 0.80 (334 TP, 0 FP)** | roster attributed to the correct teacher, teachers not in the student set ✓ |
| curriculum / calendar FP | 144 / 86 | **0 / 0** (held through the pair rule) | 0 ✓ |
| 3V | 1.00 / 1.00 | 1.00 / 1.00 + class metadata ("V"/"A") | unchanged ✓ |

The 83 FN are entirely the grades 6–8 sheets — a DIFFERENT genre
(full-name columns, r1≠r2 column sets), not the K–5 pair shape. Honest
deferral: no rule was tuned to reach them (§5), they are recorded here
as the known gap. The teacher's own requirement ("her ~39, not 400") is
met — every K–5 class roster resolves with zero false positives.
Synthetic mirror after STEP 4: **1.00/1.00 on all five files.**

### STEP 5 — Identity resolution + unresolved queue (L8) — DONE

`student_id = slug(display_name)` made identity BE the spelling: "Marco
B-R" in a support file next to "Marco Bianchi" on the class list silently
became two children. New module `docpipe/identity.py`: each child is a
canonical id plus observed SURFACE FORMS; every lens creation from ingest
(roster path, small trusted path, confirm path — all three
`_create_lens_for_detected` call sites) first resolves the spelling
against the approving teacher's roster (~39 names, snapshotted once per
approve; never the whole school):

- **exact** — the spelling IS a roster student or a surface form a human
  already ruled on → merge into the canonical lens (deterministic replay,
  not a guess).
- **queue** — plausible match (first name exact + abbreviated-initial
  compatibility) → the unresolved queue. Ruling §8-3 default honored:
  ALWAYS queue, NEVER auto-merge — confidence measures nothing (STEP 3).
- **new** — no plausible match → a genuinely new student.

The queue is the same NDJSON event-log pattern as ingest_review.py
(last-event-wins, chmod 600, junk-line tolerant). An "assigned" event is
the `same_person_as` relation of the MC lens precedent
(DESIGN_LENS_SCHEMA_MC_LENS_V1_2026-08-10): a relation between a spelling
and an existing canonical record — never a new entity type, never a
coercive merge — and it doubles as the surface-form registry future
imports replay. Lens schema untouched (docpipe.lens.v1 stays frozen).

- Routes: `GET /api/students/ingest/identity` (open items) +
  `POST /api/students/ingest/identity/resolve` (assign → evidence merged
  into the CANONICAL lens + surface form recorded; create → new lens;
  dismiss → closed; 400/404/409 on bad name, ghost student, non-open
  item). Both in ROUTE_REACHABILITY.
- UI: identity-review-panel on Students (mirrors the unattributed
  pattern) — per spelling: candidate picker, **Same child** / **New
  student** / **Dismiss**; done-job notice when names were held back;
  copy says "Nothing is merged or created until you decide."
- Locks: 17 unit tests (test_docpipe_identity.py — normalization,
  abbreviation compatibility, resolve exact/queue/new, roster scoping,
  surface-form replay, corrected-ruling last-event-wins, teacher filter,
  junk-line tolerance) + 8 ingest gate tests (the L8 scenario itself:
  "Marco B-R" after "Marco Bianchi" queues with the right candidate and
  store count stays at 3 — zero silent duplicates; exact respelling
  merges into the canonical lens; assign merges evidence + replays on a
  third import; create mints; dismiss creates nothing; bad-request
  refusals keep the item open; confirm path runs the same gate; UI
  wiring).
- Scorer not re-run: detection surface untouched (identity runs AFTER
  detection, at the creation chokepoint) — extract.py has no diff in
  this STEP.
- UI_CONTRACT bumped v161 → **v162** (web.py + index.html).

**Spec gate (§STEP 5 verify):** abbreviated support-file names resolve to
class-list students or land in the queue; zero silent duplicate lenses ✓
(locked by `test_abbreviated_spelling_queues_never_duplicates`,
`test_assign_ruling_merges_evidence_and_replays_forever`).

### STEP 6 — Enrichment veto (L7) — DONE

`_model_enrich_students` was additive-only — a pipeline that can only add
cannot converge on truth. The model may now DISPUTE a detection via a
`not_students` channel, but **a veto never deletes**: it sets
`removal_proposed` (additive schema field) and the teacher rules.

- **Grounding is symmetric with additions:** a veto claim must name a
  current detection (matched through `identity.normalize_name` — the ONE
  normalizer, §5), cite a real span, that span must contain the name, and
  give a reason. Ungrounded vetoes are DROPPED with
  `grounding_dropped:model_veto:` warnings — same mechanical severity as
  hallucinated additions. The current detections ride along in the prompt
  (the model can only dispute what it can see).
- **Review-gated at ingest, never auto-applied:** small imports hold a
  flagged name behind confirm with the model's reason ("The AI thinks
  this may not be a student: …"); roster imports keep the G3 zero-click
  contract — everyone is created, but the veto is surfaced loudly by name
  in warnings and the one-click Remove is the mechanism. Preview rows
  carry the flag ("may not be a student — reason" badge).
- Urgency note honored: after STEP 2 the false positives largely stopped
  existing (structural detection), which is why this landed as STEP 6 —
  the veto now guards the residual (bigram/model-added names, staff rows
  in unseen genres).
- Locks: 3 extract tests (grounded veto flags + survives the vault schema
  gate + never deletes; 4-way ungrounded drop; case-variant match through
  the one normalizer) + 3 ingest tests (small import gated behind confirm
  then teacher overrules; roster import creates-but-warns by name; UI
  wiring).
- Scorer re-run after the change: **identical to STEP 4** (class list
  1.00/0.80, curriculum/calendar 0 FP, 3V 1.00/1.00) — the veto only
  activates with a model client; deterministic detection untouched.
- UI_CONTRACT bumped v162 → **v163** (extract.py + web.py + index.html).

**Spec gate (§STEP 6):** enrichment may propose removal, gated by review ✓
— proposal grounded like additions, applied only by a human, never silent
in either direction.

### STEP 7 — One canonical model normalizer + honest failure reporting (L6) — DONE

Two installed-model matchers disagreed on `:latest`: `config._model_installed`
(handled `:latest` + tagless) vs `model_gate.is_provably_local_model` (exact
membership only). `detect_model()` could pick `ollama/X` when Ollama had
`X:latest` installed; the privacy gate then refused its own detector's pick,
every student-data call died as `none:local_only` — and that refusal carried
`error=""`, so enrichment misreported it as
`model_enrichment_discarded:invalid JSON after retry`. L6 stayed invisible
because the system lied about why it failed.

- **ONE normalizer (§5):** `config.model_matches_installed()` is now the
  single installed-match function — case-insensitive (detect_model's set was
  unlowered, model_gate's lowered: a second divergence closed by the same
  move), `:latest`, tagless-vs-any-tag. `detect_model()` and
  `is_provably_local_model()` both route through it (model_gate already
  imports config; the circular-import constraint puts the canonical function
  in config).
- **Class-lock:** `test_one_model_normalizer_class_lock` — the `:latest`
  literal may exist ONLY inside `model_matches_installed` (source-level
  count), zero occurrences in model_gate, and model_gate's source must
  reference the canonical function. A second normalization path fails the
  suite.
- **The regression itself:** `test_detector_pick_always_passes_the_privacy_gate`
  — whatever detect_model picks from `["nemotron-3.5-lightning:latest", …]`,
  the gate must accept (property holds on any hardware tier).
- **Honest failure reporting:** the `none:local_only` refusal now carries
  `error="local_only_no_model"` in BOTH synchronized engine copies
  (`reasoning.py`, `pipeline.py`); enrichment additionally treats any
  `none*` model_used as unavailability (belt) — the warning is
  `model_enrichment_unavailable:local_only_no_model`, never "invalid JSON".
  Locked by `test_privacy_refusal_reports_true_reason_not_invalid_json` +
  `test_none_model_without_error_still_reports_unavailable`.
- Targeted: 95 (config/extract/failure-honesty/reasoning/stays-local) + 78
  (all other refusal-shape consumers) — all green.
- Scorer re-run: **identical to STEP 4** (class list 1.00/0.80 — 334 TP,
  0 FP; 3V 1.00/1.00; curriculum/calendar 0 FP; holdout SEALED) — STEP 7
  touches only the model leg.
- No UI change → no contract bump.

**Spec gate (§STEP 7):** one normalizer, class-locked; a privacy refusal
reports its true reason ✓.

_(pending — STEPs 8+10 (combined verification battery per operator directive
08-19), 11; STEP 9 gated on ruling §8-2 — skipped if unruled when reached;
STEP 12 only if time. Each entry: scorer before/after, per-STEP gate result,
commits.)_

## Holdout opening (§6) — NOT YET OPENED

_(one-time, end of wave: `--open-holdout` run, result recorded here.)_
