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

_(pending — STEPs 1–8, 10, 11; STEP 9 gated on ruling §8-2; STEP 12 only if
time. Each entry: scorer before/after, per-STEP gate result, commits.)_

## Holdout opening (§6) — NOT YET OPENED

_(one-time, end of wave: `--open-holdout` run, result recorded here.)_
