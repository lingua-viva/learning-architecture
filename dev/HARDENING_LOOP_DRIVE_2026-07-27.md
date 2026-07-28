# Hardening Loop — Google Drive Surface (2026-07-27)

15-iteration probe→fix→verify loop over the Drive round-trip + workspace built
earlier tonight (SPEC_LV_DRIVE_WORKSPACE_2026-07-27, UI contract v34→v39).
Pattern: each iteration probes one weakness class; fixes are verified with
targeted tests; full suite + contract re-seal at the end. No commits (operator
commit window).

## Scorecard

| # | Probe | Verdict | What happened |
|---|-------|---------|---------------|
| 1 | Drive `q`-expression injection via `folder_id` | **FIXED** | Raw folder_id was interpolated into the quoted `q` filter; a crafted ID could break out and list files outside the intended folder. `BARE_FOLDER_ID` guard in `list_files` + ValueError→400 at the route. 3 tests. |
| 2 | Folder registry write safety | **FIXED** | `drive_folders.json` was written non-atomically with a world-readable window (chmod after write). Now 0600-from-birth temp + `os.replace`. |
| 3 | Privacy-event transparency | **FIXED** | Connect/disconnect/import made no privacy-log entries. Added `drive_folder_connected` / `drive_folder_disconnected` / `drive_files_imported` event types (generic details, hashed query_text), wired fail-open into all three routes. |
| 4 | Import guardrails (purpose/roster) | **VERIFIED-OK** | Backend enforces purpose whitelist; `student_lens_source` requires `assigned_student_id` present AND in the roster. |
| 5 | XSS / escaping in Drive UI | **VERIFIED-OK** | All interpolation sites in the Drive section route external data through `escapeHtml` (covers `&<>"'`) inside helpers, or are internal constants. |
| 6 | `page_token` injection | **VERIFIED-OK** | Token passes through `parse.urlencode`; invalid tokens fail as `DriveAuthError` with clean route mapping. |
| 7 | Registry read-modify-write race | **FIXED** | connect / disconnect / `mark_folder_checked` all RMW the registry from `asyncio.to_thread` workers — the list route's `last_checked` stamp could silently drop a concurrent connect (last-writer-wins). Added `_FOLDERS_LOCK`; `mark_folder_checked` no longer writes when nothing matched. 12-thread stress test. |
| 8 | "Review now" → extraction preselect flow after Sources-lane (v39) restructure | **VERIFIED-OK** | Import-result handler still sets `state.pendingExtractionFile` and navigates to Settings; `renderExtractionControls` still consumes it. |
| 9 | Upload egress guard (symlink/`..`) + destination ID | **FIXED + VERIFIED** | `.resolve(strict=True)` defeats symlink/`..` escapes (pinned by new test). Gap: destination folder ID wasn't format-checked — malformed IDs failed downstream as opaque `upload_failed`. Same `BARE_FOLDER_ID` guard as iteration 1, fails fast with a clear 400. |
| 10 | Import/export manifest write safety | **FIXED** | Both manifests (they carry student-linked data) were non-atomic RMW with a world-readable window. Extracted shared `_atomic_write_private_json` (0600-from-birth + `os.replace`) + `_MANIFEST_LOCK`; refactored the folder-registry writer onto the same helper. Permission/temp-residue test. |
| 11 | `parse_folder_link` real-world URL variants | **VERIFIED-OK** | Trailing slash, `#fragment`, `/u/0/`, mobile, `resourcekey`, padded, bare-ID all parse; doc/file links rejected (plus live mimeType verify). 6 new pinned parametrize cases. |
| 12 | UI unconfigured/degraded state | **VERIFIED-OK** | `ready=false` disables all action buttons, plain-language setup panel renders, folders-fetch failure swallowed, every element the controls binder touches exists in both branches. |
| 13 | Import route payload validation | **FIXED** | `file_ids: []` passed despite the "non-empty" error copy, and non-string items (`[123]`) reached `.strip()` → unhandled 500. Route now 400s both. |
| 14 | Hermeticity: demo-file fallback (PRE-EXISTING) | **FIXED** | `extraction_sources`' demo fallback wrote into the operator's REAL `~/.lingua-viva/imports/` under tests (conftest deliberately doesn't force `LV_CONFIG_HOME`). New `LV_LOCAL_IMPORTS_DIR` seam in web.py + conftest override — same pattern as `LV_SANITIZER_DATA_DIR`. |
| 15 | Secret leakage across all persisted artifacts | **VERIFIED-OK** | Live probe of full connect→import→upload→log flow: every artifact 0600; no client secret / refresh token / access token anywhere on disk; privacy log holds only hashes + generic details (teacher-typed folder names never reach it). |

**Totals: 8 FIXED (1 pre-existing), 7 VERIFIED-OK.**

## Files touched

- `src/lingua_viva/google_drive_integration.py` — injection guards (list +
  upload destination), `_FOLDERS_LOCK`/`_MANIFEST_LOCK`,
  `_atomic_write_private_json`, all three persisted-JSON writers atomic + 0600.
- `src/web.py` (PROTECTED) — ValueError→400 on list, 3 privacy-event wirings,
  import payload validation, `LV_LOCAL_IMPORTS_DIR` seam.
- `src/lingua_viva/privacy_log.py` — 3 new Drive event types in `_generic_detail`.
- `tests/conftest.py` — `LV_LOCAL_IMPORTS_DIR` hermeticity override.
- `tests/test_google_drive_integration.py` — +11 tests (46 total).
- `tests/test_google_drive_app_integration.py` — +2 tests (19 total).

## Ceremony

- UI contract re-seal required for the `src/web.py` edits: v39 → v40
  (`check_ui_contract.py --bump` is the only mechanism; no UI features in this
  bump — hardening-only re-seal).
- No commits made (operator commit window).
