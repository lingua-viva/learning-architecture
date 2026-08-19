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

_(pending — STEPs 4–8, 10, 11; STEP 9 gated on ruling §8-2; STEP 12 only if
time. Each entry: scorer before/after, per-STEP gate result, commits.)_

## Holdout opening (§6) — NOT YET OPENED

_(one-time, end of wave: `--open-holdout` run, result recorded here.)_
