# REPORT: Lingua Viva Google Drive Connector

Date: 2026-07-23
Spec: `dev/specs/SPEC_LV_GOOGLE_DRIVE_CONNECTOR_2026-07-23.md`
Status: SHIPPED locally, not pushed

## Scope Built

- Added `src/lingua_viva/google_drive_integration.py`.
- Added secret-free Drive status, explicit list, and explicit import routes:
  - `GET /api/google-drive/status`
  - `POST /api/google-drive/list`
  - `POST /api/google-drive/import`
- Mounted Google Drive in the real Settings view in `static/index.html`.
- Added status, query, folder filter, selectable results, purpose selector, student selector, and import result UI.
- Added local fixture transport via `LV_GOOGLE_DRIVE_MOCK_FIXTURE` for served-app verification without live Google calls.
- Imported files write under `~/.lingua-viva/runtime/drive_imports/` by default.
- Import manifest records metadata only, not raw file content or credentials.
- File-map extraction inputs now include imported student, curriculum, and teacher artifact sources.
- Support bundles explicitly exclude `drive_imports`.
- UI contract was bumped and relocked for the mounted UI change. Google Drive
  first mounted at v23; after hardening and concurrent protected-file fixes,
  the current contract lock is v27.

## Privacy Boundary

- No Drive upload/export route was added.
- No background sync was added.
- Status/list/import responses do not return client secret, refresh token, access token, or authorization headers.
- Tests use mocked/fixture Drive transport only.
- Imported local files are treated as possible student/curriculum source material and excluded from support bundles.

## Direct Route And Function Verification

- `python3 -m py_compile src/lingua_viva/google_drive_integration.py src/lingua_viva/filemap.py src/lingua_viva/support_bundle.py src/web.py`
- `python3 -m pytest tests/test_google_drive_integration.py tests/test_google_drive_app_integration.py tests/test_support_bundle.py tests/test_teacher_ui_phase2.py -q`
  - Result: 22 passed
- `python3 -m pytest tests/test_ui_contract.py tests/test_google_drive_integration.py tests/test_google_drive_app_integration.py tests/test_support_bundle.py tests/test_teacher_ui_phase2.py -q`
  - Result: 27 passed
- Broader targeted regression:
  - `python3 -m pytest tests/test_google_drive_integration.py tests/test_google_drive_app_integration.py tests/test_filemap.py tests/test_support_bundle.py tests/test_teacher_ui_phase2.py tests/test_ui_contract.py tests/test_pwa_routes.py tests/test_document_ingest_endpoint.py -q`
  - Result after hardening: 88 passed

## 15-Pass Hardening Ledger

1. Baseline connector/app tests: PASS.
2. Config truthiness audit: FIXED whitespace-only credential env values counting as configured.
3. Drive ID URL encoding audit: FIXED `/` in opaque Drive IDs not being escaped in metadata/download URLs.
4. Google Docs export suffix audit: FIXED exported Docs keeping an incompatible original suffix while marked extraction-ready.
5. Error-order audit: FIXED invalid import payloads returning `503` before the spec-required `400`.
6. Secret-response scan: PASS, no credential/token value returned by status/list/import.
7. No-upload route probe: PASS, `/api/google-drive/upload` remains absent.
8. Support-bundle privacy audit: PASS, `drive_imports` and import manifests excluded.
9. Route-mount audit: PASS, all three Drive routes appear in `static/index.html`.
10. UI contract audit: PASS, protected files locked; current lock v27.
11. JavaScript parse audit: FIXED pre-existing support-profile summary syntax error that would have broken the served app script before Settings could work.
12. JS regression pin: ADDED `test_static_inline_javascript_syntax_is_valid`.
13. Served-app re-verification: PASS on `127.0.0.1:8799` with fixture Drive transport.
14. Targeted regression: PASS.
15. Full suite: PASS, 689 passed / 13 skipped.

## Served-App UI Reachability Verification

Verified against a real FastAPI process on `http://127.0.0.1:8799` with isolated state:

- Served `/` contained:
  - `Google Drive`
  - `/api/google-drive/status`
  - `/api/google-drive/list`
  - `/api/google-drive/import`
- `GET /api/google-drive/status` returned configured status without secrets.
- `POST /api/google-drive/list` returned mocked Drive metadata.
- `POST /api/students` created a local test student.
- `POST /api/google-drive/import` imported a mocked PDF into `/tmp/lv-drive-live/runtime/drive_imports/`.
- Import manifest contained metadata only, not raw fixture PDF content.
- `GET /api/filemap` showed the imported file assigned to the created student.

Served-app verification result: PASS before and after the 15-pass hardening fixes.

## Remaining Non-Goals

- No browser OAuth ceremony.
- No live Google API verification.
- No Drive upload/export.
- No background polling/sync.
- No automatic student-lens sharing.
