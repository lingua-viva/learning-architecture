# Lingua Viva Session Memory — 5-Spec Build Sequence Complete

**Date:** 2026-07-23  
**Status:** COMPLETE, COMMITTED, MEMORY RECORDED  
**Repo:** `/home/mical/learning-architecture`  
**Core Build Commit:** `7ddf6bf` (`feat(lingua-viva): complete 5-spec build sequence`)  
**Current HEAD at memory write:** `0d464e6` (`docs(lingua-viva): record session memory and index entry for 5-spec build completion`)  
**Current origin/main at memory write:** `ff2401e` (`feat(ui): close LV-BLT-001 + LV-BLT-003 -- provider connect form and teaching artifact ingest`)  
**Lens:** Claudia Canu Fautré (`LENS-PERSON-002`)  
**Route:** Local (`MC_AGENT=1`)

---

## Executive Summary

All 5 specifications in the Lingua Viva Student Lens & Ingestion sequence have been implemented, UI-mounted, contract-locked (v28 during this build sequence), and empirically verified.

The build sequence was pushed through `7ddf6bf`. A later upstream commit, `ff2401e`, closes LV-BLT-001 and LV-BLT-003 for provider connect and teaching artifact ingest. The local branch currently has one additional documentation memory commit, `0d464e6`, ahead of `origin/main`.

---

## 5-Spec Sequence Inventory

| Spec # | Specification Document | Description | Key Modules Created / Updated | Verification Status |
|---|---|---|---|---|
| 1 | `dev/specs/SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23.md` | Student Lens JSON v2 Schema & SQLite Store | `src/education/student_lens.py` | `PASS` (Schema v2, SQLite auto-migrations, 8 canonical support categories) |
| 2 | `dev/specs/SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_WRITE_PATH_2026-07-23.md` | Observation IEP Classification & Write Path | `src/education/observation_capture.py`, `src/web.py` (`/api/observe/classify`, `/api/observe/capture`) | `PASS` (99/99 unit & integration tests) |
| 3 | `dev/specs/SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23.md` | Lens UI & API Contract | `src/web.py` (`/api/categories`, `/api/students/support-summary`), `static/index.html` | `PASS` (Served UI support profile summary & Gagné scaffolding) |
| 4 | `dev/specs/SPEC_LV_GOOGLE_DRIVE_CONNECTOR_2026-07-23.md` | Google Drive Explicit-Import Connector | `src/lingua_viva/google_drive_integration.py`, `src/web.py` (`/api/google-drive/*`), `static/index.html` | `PASS` (15-pass hardening, local cache isolation) |
| 5 | `dev/specs/SPEC_LV_INGESTION_EXTRACTION_MAPPING_V2_2026-07-23.md` | Ingestion and Extraction Mapping v2 | `src/lingua_viva/student_lens_writer.py`, `src/lingua_viva/extraction_engine.py`, `src/web.py` (`/api/extraction/*`), `static/index.html` | `PASS` (Extraction Sources, Run Extraction, Review modal, Write Confirmed to Lens) |

---

## Key Invariants Enforced

1. **Terminal-First Validation:** Every claim verified via `run_command` against live uvicorn process running on port 8799 under `MC_AGENT=1`.
2. **UI Contract Governance:** UI contract protected files (`static/index.html`, `static/sw.js`, `src/web.py`) re-locked at version **v28** in `contracts/UI_CONTRACT.yaml` and `contracts/UI_CONTRACT.lock`.
3. **Trauma Flag Safety Rule:** `trauma_flag` is hard-excluded from auto-verification and auto-writing. Requires explicit teacher check in UI review modal.
4. **Provenance & Source References:** Every imported support-profile entry requires non-empty `source_ref_ids` citing chunk IDs before it can be written to a student lens.
5. **Enrichment Isolation:** `advanced_enrichment` items are rendered in a distinct UI section and explicitly excluded from intervention/RTI tier calculations.

---

## Command Verification Log

- **UI Contract Check:** `python3 scripts/check_ui_contract.py` -> `[ui-contract] OK — contract v28, 3 files locked`
- **Focused verification before push:** `MC_AGENT=1 uv run pytest tests/test_lens_ui_api_contract.py tests/test_ingestion_extraction_mapping_v2.py tests/test_google_drive_integration.py tests/test_google_drive_app_integration.py tests/test_ui_contract.py tests/test_teacher_ui_phase2.py tests/test_support_bundle.py -q` -> `44 passed in 100.96s`
- **Previously reported full suite in memory commit:** `uv run pytest` -> `696 passed, 13 skipped in 293.89s (0:04:53)`
- **Git status at latest check:** clean working tree, `main` ahead of `origin/main` by 1 documentation commit (`0d464e6`).

---

## Commits in This Work Window

- `814961b` Implement student lens support profile v2
- `ea325d1` Harden student lens support profile v2
- `f3dc10a` Build observation support profile write path
- `7ddf6bf` Complete 5-spec build sequence: Google Drive connector, Lens UI/API contract, ingestion extraction mapping v2
- `ff2401e` Close LV-BLT-001 and LV-BLT-003: provider connect form and teaching artifact ingest
- `0d464e6` Record session memory and index entry for 5-spec build completion

---

## Next Hardening Recommendations

1. Replace duplicated `teacherNav` / `adminNav` / `utilityNav` / `renderView()` mappings in `static/index.html` with a single UI view registry so navigation and rendering are generated from one source of truth.
2. Make `/api/categories` the canonical source for support category labels/definitions in the UI, with a small offline fallback only.
3. Consider promoting Google Drive and extraction from Settings-only access into a first-class `Sources` / `Import` utility nav item or Home attention panel.
4. Add a route reachability manifest that maps every required backend route to a view, control id, handler, and live served-app verification.
5. Continue using live served-app verification as the standard for “built,” not only unit/API tests.
