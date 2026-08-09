# Report — Unattributed Review Queue — 2026-08-08

## Status

Built, tested, and committed locally. Not pushed, not tagged, not released.

## What Shipped In This Window

- Persisted Drive class-folder unattributed documents to `runtime_data_dir("ingest_review") / "unattributed.ndjson"` with append-only events, `0o600`, last-event-wins state, and duplicate-open suppression by Drive file.
- Added `source_id` to unattributed ingest response entries.
- Extracted the automatic attribution branch into `attribute_extraction_to_student()` and reused it for manual assignment.
- Added routes:
  - `GET /api/students/ingest/unattributed`
  - `POST /api/students/ingest/attribute`
- Added UI controls in Drive ingest results and a persistent Students → Needs review panel with roster dropdown, Assign, and Dismiss actions.
- Classified routes and bumped UI contract to v129 after hardening.

## Hardening Loop

The requested 7-10 pass review found two real defects after the initial commit:

1. Current queue state was keyed by `drive_id|source_id`, but re-ingesting the same Drive file creates a new `source_id`. Fixed by collapsing current state by `drive_id`, so dismiss/re-ingest reopens exactly one current item.
2. Manual assignment could still write lens evidence for a stale/dismissed item. Fixed by requiring the current item to be open and source-matched before any vault or lens write.

## Acceptance

1. Queue survives navigation/restart: covered by `tests/test_unattributed_review_queue.py`.
2. Assign updates student lens/evidence and removes item: covered, with `manual_teacher`, `1.0`, and `teacher_confirmed`.
3. Dismiss removes item without lens writes: covered.
4. Off-roster assignment returns 422 with zero writes: covered.
5. Duplicate re-ingest does not create duplicate open items: covered.
6. Dismiss then re-ingest reopens one current item: covered.
7. Assignment of a stale/dismissed item returns 409 with zero writes: covered.

## Verification

- `pytest -q tests/test_class_folder_ingest.py tests/test_unattributed_review_queue.py` → 9 passed
- `pytest -q tests/test_students_ingest.py tests/test_class_folder_ingest.py tests/test_unattributed_review_queue.py tests/test_runtime_write_locations.py tests/test_ui_contract.py tests/test_route_reachability.py` → 50 passed
- `python3 scripts/check_ui_contract.py` → OK, contract v129
- `python3 scripts/check_route_reachability.py` → OK, 157 routes classified
- First full suite exposed stale contract expectations, then fixed.
- Final `pytest -q tests/` → 2050 passed, 13 skipped in 1018.72s
- Hardening subset after fixes: `pytest -q tests/test_students_ingest.py tests/test_class_folder_ingest.py tests/test_unattributed_review_queue.py tests/test_google_drive_app_integration.py tests/test_lens_ui_api_contract.py tests/test_teacher_ui_phase2.py tests/test_lv_preflight.py tests/test_ui_contract.py tests/test_route_reachability.py tests/test_runtime_write_locations.py` → 85 passed
- `python3 -m src.lingua_viva.cli preflight` → 6/6

## Manual

Live Drive spot check remains operator-run: connect a real folder, ingest a mixed class folder, assign and dismiss queue items from the Students panel, and confirm the selected lens reflects the assigned teacher-confirmed evidence.

## Commit

Final commit SHA: see `git log -1 --oneline` for this report's containing commit.
