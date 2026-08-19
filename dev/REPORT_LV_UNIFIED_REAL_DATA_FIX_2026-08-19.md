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

## STEPs 8+10 COMBINED — Model governance + generation honesty — CODE COMPLETE

Per operator directive 08-19: STEP 8 (model governance) and STEP 10
(generation honesty) implemented back-to-back, then ONE combined
verification battery (three runs) instead of two separate ones.

### STEP 8 — model governance
- **Fail-closed detector:** `CLOUD_FALLBACK` deleted entirely.
  `detect_model()` returns `None` when no preferred local model is
  installed — never a `:cloud` name. Class-locked:
  `test_detect_model_never_returns_a_cloud_model_class_lock` asserts
  `":cloud"` does not appear in the function source AND a cloud-only
  installed list yields `None`.
- **Native Ollama leg:** local calls now use `/api/chat` (native shape:
  `stream: false`, `options.num_predict`, parse `message.content`,
  tokens = `prompt_eval_count + eval_count`). Payload shape follows the
  ENDPOINT, not externality — `:cloud` models are external for logging
  but dispatch through the local daemon, so `native =
  url.endswith("/api/chat")` decides shape in BOTH synchronized engine
  copies (`reasoning.py`, `pipeline.py`).
- **`"think": false`** sent for thinking models
  (`THINKING_MODEL_TAGS = ("glm", "nemotron", "qwen3")` →
  `config.is_thinking_model`). This is the fix for the audit's 35.3s +
  0-visible-chars nemotron calls. Locked:
  `test_local_leg_sends_think_false_for_thinking_models`.
- **Empty content = failure:** a 200 with no visible content returns
  `error="empty_model_response"`, confidence 0.0 — never a silent
  "success". Locked: `test_empty_content_with_no_error_is_a_failure_not_a_success`.
- **VRAM residency (C1):** in live-probe mode the detector reads
  `/api/tags` sizes and picks the first candidate fitting
  `0.9 × estimated GPU bytes` — prefers a resident smaller model over a
  larger offloaded one. Names-only callers keep pure preference order.
  Size lookup routes through `model_matches_installed` (no second
  `:latest` literal — STEP 7 class-lock preserved). Locked:
  `test_detect_model_prefers_resident_fit_over_larger_offloaded`.
- **Resolution order respected:** `LocalModelClient` no longer hard-codes
  `detect_model()` (which silently ignored `LV_REASON_MODEL`); it passes
  no model and lets the engine resolve (explicit → provider config →
  default → `LV_REASON_MODEL` → cached detect). `local_only=True` still
  guarantees provably-local. Locked:
  `test_local_model_client_respects_engine_resolution_order`.

### STEP 10 — generation honesty
- **`TierMaterial.generation_status`** (`"generated"` |
  `"template_fallback"`, mirrors `sync_status`). EVERY switch to
  `_deterministic_material_fields` pairs with the fallback status —
  source-level class lock counts both
  (`test_every_fallback_path_sets_the_status_signal_class_lock`).
- **Blank output = failed generation:** `_has_blank_output` (blank
  instructions OR blank exercise) triggers the fallback switch, so a
  parse that "succeeds" into emptiness is treated as failure.
- **Fallback is loud and never blank:** parametrized across
  empty_response / timeout / privacy_refusal / none_model /
  empty_no_error / blank_instructions — all three tiers report
  `template_fallback` with non-blank instructions, exercise, and
  scaffolding (foundational included).
- **On-surface signal:** the status rides `materials_as_dicts` into
  `/api/lesson-materials/generate`; `index.html` renders a warn badge
  "AI generation did not run — this is template text" on
  `template_fallback`. UI contract bumped **v163 → v164**.

### Combined verification battery (operator directive) — ALL THREE RUNS PASS

**Run 1 — happy path (governed auto-pick, real IB PDF):**
- Detector auto-pick = `ollama/nemotron-3.5-lightning` (never `:cloud`).
- Real PDF (`Lizard BrainWizard Brain`) extracted: 2,385 chars.
- Single-tier call: **13.3s**, `status=generated`, non-empty visible
  content. Full 3-tier: **36.0s** wall-clock, all tiers `generated`,
  content grounded in the source (lizard/wizard/instinct).
- Trace ledger: 4 lines `model_used=ollama/nemotron-3.5-lightning` at
  13343/15038/27955/35971 ms with 796/802/794/782 REAL tokens — vs the
  audit baseline of 35.3s + 0 visible chars (`"think": false` proven
  effective on the thinking model).

**Run 2 — forced failure (loud, non-blank, fail-closed):**
- Unavailable model (`LV_REASON_MODEL=ollama/model-that-does-not-exist`):
  all tiers `template_fallback` in 0.1s, `blank_fields=False` every tier.
- 1s timeout budget: honored at 1.0s wall-clock; all tiers
  `template_fallback`, instructions 57–71 ch, exercise 184–217 ch —
  foundational tier NOT blank.
- Detector fails closed: installed=`["tiny-custom"]` →
  `detect_model()=None`; student-data call through `LocalModelClient` →
  `model_used='none:local_only'`, `error='local_only_no_model'` — honest
  reason, never `:cloud`.

**Run 3 — override respected end-to-end:**
- `LV_REASON_MODEL=ollama/qwen2.5:7b` (different installed model).
- Leg A `LocalModelClient.complete` → `model_used='ollama/qwen2.5:7b'`,
  4.8s, valid JSON content (the STEP 8 fix target — it used to hard-code
  `detect_model()` and silently ignore the override).
- Leg B full 3-tier: 26.1s wall-clock, all tiers `status=generated`,
  non-blank (instr 41–52 ch, ex 75–177 ch).
- Trace ledger: 4 lines `model_used=ollama/qwen2.5:7b` at
  4754/10264/17402/26039 ms — override logged per call.

### Tests + scorer
- Targeted: **340 tests green** (config 35 / reasoning / extract /
  lesson_materials 36 / UI contract + consumers: students_ingest 62,
  pipeline consumers 71, others).
- Scorer re-run (unchanged lens side): **identical to STEP 4/7 baseline**
  — class list 1.00 prec / 0.80 rec (334 TP, 0 FP); 3V 1.00/1.00;
  curriculum/calendar 0 FP; holdout SEALED. STEPs 8+10 touch only the
  model/generation leg.

**Spec gate (§9, combined):** detector never returns cloud, fails closed
with honest reason ✓; think:false effective (real tokens + content within
budget) ✓; model-used logged every call ✓; empty-content-no-error is a
FAILURE ✓; fallback loud on-surface + never blank (foundational included)
✓; `LV_REASON_MODEL` respected end-to-end incl. `LocalModelClient` +
logged ✓; lens-side scorer unchanged ✓.

## STEP 9 — SKIPPED (gated on operator ruling §8-2, unruled when reached)

Per operator directive 08-19: "STEP 9 remains gated on operator ruling §8-2
— if unruled when you get there, skip it and continue to STEP 11; do not
stall." No ruling had arrived; skipped, continued to STEP 11.

## STEP 11 — Metadata detection from structure (C4) — CODE COMPLETE

Same root as the lens side: first-plausible-line vs document structure.
`parse_lesson_metadata` picked the letterhead as title and missed grade.

- **Title = structure:** in a labelled document, the title is the nearest
  non-label line immediately ABOVE the first metadata label
  (`Unit:`/`Author:`/…) — letterheads sit higher up. Markdown `#` headings
  still win; unlabelled documents keep the old first-plausible-line
  heuristic. If the nearest-above line is implausible, detection falls back
  rather than walking further up into the letterhead.
- **Grade from labelled structure:** `Grade:` and `Author:` values parsed
  for grade tokens (`_grade_from_text`: "Grade 3 …" → `G3`, "MYP2 English"
  → `MYP2`, bare "3" → `G3`) — normalized to the app's grade-band form so
  the Prepare pre-fill dropdown (exact-match on G1–G5) can actually match.
  `Subjects:`/`Subject:` → first listed subject. Existing `Class:` parse
  untouched.
- **Verified against the real PDF locally (spec gate):** before →
  title = letterhead school-code line, no grade. After →
  `title='Lizard Brain/Wizard Brain - Instinct vs. Reason'` (the actual
  document title), `grade='G3'`, `subject='Social Emotional Learning'`,
  `unit='Diversity and emotions'`. Real file stays local; committed tests
  use a synthetic letterhead mirror (no institution name).
- Tests: 4 new in `test_docpipe_extract.py` (structural title vs
  letterhead, grade normalization incl. no-grade Author line, markdown +
  unlabelled + Class-label behavior preserved, implausible-line fallback
  does NOT walk up). 52 extract + 98 lesson_materials/students_ingest green.
- Scorer re-run: **identical to baseline** (class list 1.00/0.80 — 334 TP,
  0 FP; 3V 1.00/1.00; curriculum/calendar 0 FP; holdout SEALED) — title
  detection feeds `_build_structure`, student detection unaffected.
- No UI change → no contract bump (pre-fill consumes existing fields).

**Spec gate (§STEP 11):** title = the actual document title, grade
detected, not the letterhead — verified on the real PDF ✓.

_(pending — STEP 12 only if time.)_

## Holdout opening (§6) — OPENED 2026-08-19 (once) — HONEST FAIL

One-time `--open-holdout` scorer run (operator-authorized):

| file (shape) | exp | det | TP | FP | FN | prec | rec |
|---|---|---|---|---|---|---|---|
| K-5 support (per_class_sheet_support) | 230 | 1 | 0 | 1 | 230 | 0.00 | 0.00 |

**The per-class-sheet genre did not generalize.** Diagnosis (structure, no
names): 12 sheets named by class (class identity lives in the SHEET NAME);
the name column has NO header (every other column is a long descriptive
support header); names are "Firstname + initial" — a single-capital
surname the bigram fallback cannot match, and no labelled column or
first/last pair for the structural detector. The 1 FP is a bigram inside
a long free-text cell. Zero structural detections → zero enrichment from
this file.

**Measurement integrity:** this result stands as recorded. No fix was
built and re-scored against the opened holdout — a post-hoc fix scored on
the same file would be in-sample, not generalization evidence. Fixing the
genre (sheet-name class + unlabelled row-key column + first-name-initial)
needs an operator ruling and its own verification data.

## End-to-end assertion (§6) — PASS (isolated store, counts only)

All five real files imported through the real ingest API
(`/api/students/ingest` → preview → approve/cancel) into an isolated
store (`LV_STATE_HOME`/`LV_STUDENT_DB_PATH` in tmp):

- **Curriculum map:** 0 structural detections. The model-enrichment leg
  added 1 low-confidence candidate (7 on an earlier run — the leg is
  nondeterministic), `evidence=None`, visibly low-confidence in preview;
  the teacher declines → cancel → **0 lenses**. Calendar: 0 detections,
  job finishes `done` directly → **0 lenses**. Gate: zero lenses from
  curriculum/calendar ✓ (held by the Phase 0A always-preview gate).
- **Class list:** 334 found, 12 classes on the preview; approve scoped to
  the target teacher's class → **35 lenses created, 0 false positives**.
  (Spec's "~39" was a pre-labelling estimate; the class-list FN are
  entirely the grades 6–8 sheets — a different genre, recorded at STEP 4.
  Her K-5 class resolves fully, 0 FP.)
- **3V support:** 6 found; approve → 3 linked to existing lenses via
  identity review (enrichment, never duplicated) + 3 created for the
  other class; 35 → 38 lenses, no duplicate explosion ✓.
- **K-5 holdout:** 0 structural detections on this path too (consistent
  with the scorer) — preview shows 1 low-confidence model candidate; the
  teacher declines → 0 lenses. Known FAIL, recorded above.

**Findings for the next wave (recorded, not fixed):**
1. The model-enrichment leg can add ungrounded-EVIDENCE (span-grounded but
   structurally uncorroborated) "students" to previews of non-student
   documents — e.g. book authors in a curriculum map. Today the always-
   preview gate + low-confidence badge hold the line at zero lenses; the
   corpus scorer measures the structural leg only, so this leg is
   currently unmeasured.
2. The per-class-sheet support genre (holdout) needs its own detection
   rule + fresh verification data.
