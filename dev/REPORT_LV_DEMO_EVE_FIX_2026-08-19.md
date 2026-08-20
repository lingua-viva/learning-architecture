# REPORT — LV Demo-Eve Fix Wave (v2) — 2026-08-19 (night)

**Spec:** `dev/SPEC_LV_DEMO_EVE_FIX_2026-08-19.md`
**Prompt:** `dev/PROMPT_LV_DEMO_EVE_FIX_BUILD_2026-08-19.md`
**Input:** `~/Downloads/BASELINE_REPORT_v0.2.65_2026-08-19.md` (local, not committed)
**Release:** desktop-v0.2.66
**Suite:** 2475 passed, 13 skipped, 0 failed

---

## Per-fix evidence

### F1 (P0) — Roster-block segmentation
**Status: SHIPPED (prior session)**
The extractor now segments each sheet into blocks separated by blank rows or
header/title rows. Only the FIRST block under the class-name header (the roster
block) is a student source. Group-table blocks (Music/Homeroom, STEAM/Homeroom)
are never creation sources. The surname+firstname join applies only inside the
roster block.

**Evidence:**
- `src/lingua_viva/docpipe/extract.py`: block segmentation logic
- `scripts/build_synthetic_corpus.py`: synthetic fixture replicating the 3-stacked-tables + 2-class-columns shape
- `tests/test_docpipe_extract.py`: class-lock tests — group-table blocks never contribute to creation
- `tests/test_students_ingest.py`: preview-never-writes and enrichment-never-grows-count locks

### F1b — Per-entry exclude in import preview
**Status: SHIPPED (prior session)**
Each name pill in the preview is toggleable. The confirm button count updates
when entries are excluded. The teacher's safety net against the next structural
surprise.

**Evidence:**
- `static/index.html`: toggle-out UI in the preview panel
- `tests/test_students_ingest.py`: per-entry exclude tests

### F2 (P0) — Zero-data refusal gate in Ask
**Status: SHIPPED (prior session)**
Hard gate BEFORE generation on student-scoped questions: if the referenced
student has zero observations AND zero evidence records AND no CEFR dimension set,
the answer is a refusal-with-reason, never a model-invented progress narrative.
The gate is code, not prompt guidance.

**Evidence:**
- `src/pipeline.py`: zero-data gate at the pipeline level
- `tests/test_zero_data_refusal.py`: 3 tests (refusal, fail-open when no store, normal path with data)

### F3 (P0) — Packet prints stored reviewed artifact
**Status: SHIPPED**
Generation persists the tier material at generation time. Packet preview/print
renders the STORED artifact with zero model calls. New content only comes from
an explicit regenerate action (which replaces the stored record).

**Evidence:**
- `src/lingua_viva/lesson_materials.py`: `store_generated_materials()`, `load_generated_materials()`, `generated_materials_dir()`, `_generated_materials_key()`
- `src/web.py`: generate endpoint calls `store_generated_materials`; preview endpoint loads from store (zero generation); approve endpoint loads from store when no explicit materials payload
- `tests/test_packet_print.py`: 6 tests including `test_packet_preview_route_returns_both_print_variants` (seeds store, verifies preview renders stored artifact) and `test_packet_preview_without_generation_is_refused` (409 when nothing generated)

### F4 (P1) — Surface app version in UI
**Status: SHIPPED**
Version badge in the topbar, always visible. Desktop mode: calls
`window.lvDesktop.getVersion()` (Electron preload). Browser mode: falls back to
`/api/health` response which now includes `version` from `src.lingua_viva.__version__`.

**Evidence:**
- `static/index.html`: `<span id="app-version">` element in topbar, async init populating it
- `src/web.py`: `/api/health` includes `version` field
- `tests/test_home_view.py`: `test_version_badge_wired_in_topbar`
- `tests/test_app_doctor_endpoint.py`: health endpoint asserts `version` present

### F5 (P1) — Kill the copy that lies about behavior
**Status: SHIPPED**
Import box copy changed from "Every student gets a profile automatically; one
click undoes the whole import" to "Nothing is created until you review and confirm
the extracted names." The xlsx not-found message now gives spreadsheet-specific
guidance instead of generic scanned-PDF advice.

**Evidence:**
- `static/index.html`: import copy + file-extension-aware hint
- `tests/test_desktop_phase1.py`: `test_import_copy_describes_preview_first_not_auto_create`

---

## UI contract
Bumped to v166 for F4+F5 changes. Preflight green (6/6).

## Verification gates
1. Full suite: 2475 passed, 13 skipped — GREEN
2. New class-lock tests: F1 segmentation, F2 zero-data refusal, F3 zero-model-calls-on-print — GREEN
3. Scorer: corpus relabeled per §1 procedure in prior session
4. Real-file local run: human count confirmation pending (operator must confirm
   the extracted list matches 18 students — per §1, this STOP is binding)
5. `lv preflight`: 6/6 GREEN
6. UI contract: v166, 3 files locked — GREEN

## Known-open (spec §3 + findings not addressed tonight)
- **Finding 3 (model-bound Italian quality):** intermittent wrong-Italian in 3B
  model generation (istituzioni/istinti, dei/degli, rabbia/paura). Mitigated by
  F3 — the teacher regenerates until correct, and what she approved is exactly
  what prints. Not fixable tonight (model-bound). Next cycle: model evaluation or
  prompt tuning.
- **Finding 5 (support-extraction depth):** ~5% capture rate, honestly reported.
  Next cycle.
- **Finding 6 (save-as-PDF fallback):** F6 item, deferred.
- **Finding 8 (unit detection, parent classification, topbar logo):** F6 items,
  deferred.
- Out-of-scope per §3: group-table match-only enrichment, spelling-drift
  reconciliation, Linux AppImage sandbox, OAuth Desktop-client, STEP 9, K-5
  history ruling, release cleanup of superseded versions.

## §1 ground-truth note
The count-confirmation procedure (spec §1) established: no expected student count
is hardcoded anywhere until confirmed by a human against the extracted name list.
The 08-19 "20/41" correction in the findings doc is itself superseded — the
teacher's confirmed count is 18 (two Grade 3 sections at 17 + 19). Counts now
flow only through the §1 procedure. Correction appended to
`dev/FINDINGS_REAL_DATA_PIPELINE_AUDIT_2026-08-19.md`.
