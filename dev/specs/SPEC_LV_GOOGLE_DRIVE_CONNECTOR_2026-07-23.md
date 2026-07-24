# Lingua Viva Google Drive Connector

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** file-map, support bundle privacy exclusions, local extraction/import paths  
**Build order:** 4 of 5  
**Route:** local only, `MC_AGENT=1` for build/validation commands

## 1. Objective

Add Google Drive as an explicit import source alongside Slack while preserving
Lingua Viva's local-first privacy boundary.

This is not complete when a backend client exists. It is complete only when a
teacher/coordinator can open the real served app, see Google Drive status in
Settings, list mocked/authorized Drive files through a visible control, import
selected files into the local runtime cache, and see those imported files
available for assignment/extraction without using a terminal.

Google Drive is an input source. It must not become automatic cloud sync for
student lenses.

## 1.5 Execution Protocol

Build under the same governance discipline used for the observation write path:

1. Read `/home/mical/fde/mission-canvas/AGENTS.md`.
2. Read this repo's `CLAUDE.md` and `AGENTS.md`.
3. For any live Mission Canvas shell/pipeline/classification command used
   during implementation or validation, run:

   ```bash
   export MC_AGENT=1
   ```

4. Treat MC shell discipline as build governance only. Do not make Mission
   Canvas runtime the default Lingua Viva runtime.
5. No raw student file content, Drive token, client secret, refresh token, or
   imported student record may be sent to an external model during this build.

## 2. Product Contract

Teachers/coordinators must be able to:

- see whether Google Drive is configured
- enter a query or folder filter from the app UI
- list Drive files from approved Drive locations
- select one or more files explicitly
- import selected files into `~/.lingua-viva/runtime/drive_imports/`
- see an import result in the UI with local paths, MIME support status, and
  per-file errors
- assign imported files to a student or curriculum purpose through the same
  teacher-facing file-map assignment flow used for local files
- pass imported local files to the existing local extraction/import path when
  supported

They must not be able to:

- upload local student lenses to Drive
- auto-sync observations or support profiles to Drive
- run background Drive polling
- expose Drive credentials or raw imported content in logs, status endpoints,
  app HTML, support bundles, or test fixtures

## 3. UI Mounting Requirement

Mount this feature in `static/index.html` under **Settings**.

Required visible controls:

- a **Google Drive** panel in `renderSettings()`
- a status badge showing configured/unconfigured
- a query text input
- a folder/root filter input, optional but visible if supported by the backend
- a **List Drive Files** button
- a selectable result list with checkboxes
- a purpose selector:
  - `student_lens_source`
  - `curriculum_unit_source`
  - `teacher_artifact_source`
  - `unassigned`
- a student selector shown/enabled when purpose is `student_lens_source`
- an **Import Selected** button
- an import-result area showing local file paths and per-file status

Required UI call sites:

- `renderSettings()` must call `GET /api/google-drive/status`
- **List Drive Files** must call `POST /api/google-drive/list`
- **Import Selected** must call `POST /api/google-drive/import`
- imported file assignment must reuse or visibly bridge to the existing
  `/api/filemap/assign` semantics, either directly or through the import
  endpoint's assignment behavior

No new backend route in this spec may be considered shipped unless the route has
a call site in `static/index.html` or is explicitly listed in this spec as
backend-only. There are no backend-only Drive routes in the first build.

## 4. Module Layout

Add:

```text
src/lingua_viva/google_drive_integration.py
tests/test_google_drive_integration.py
tests/test_google_drive_app_integration.py
```

Modify:

```text
src/web.py
static/index.html
tests/test_teacher_ui_phase2.py
contracts/UI_CONTRACT.yaml
contracts/UI_CONTRACT.lock
```

Do not modify Slack modules except for shared navigation/layout code if needed.

## 5. Configuration

Read from local environment:

- `LV_GOOGLE_DRIVE_ENABLED`
- `LV_GOOGLE_CLIENT_ID`
- `LV_GOOGLE_CLIENT_SECRET`
- `LV_GOOGLE_REFRESH_TOKEN`
- `LV_GOOGLE_DRIVE_ROOT_ID` optional folder/shared-drive root

The status endpoint must report booleans only. It must never return:

- client secret
- refresh token
- access token
- OAuth authorization header
- student file contents
- Drive file IDs outside explicit list/import responses
- folder names outside explicit list responses

Initial implementation may use refresh-token based OAuth configuration rather
than a browser OAuth ceremony, provided the UI says setup is required and the
status route stays secret-free.

## 6. API Contract

### `GET /api/google-drive/status`

Returns:

```json
{
  "configured": false,
  "mode": "explicit_import",
  "enabled": false,
  "client_id_set": false,
  "client_secret_set": false,
  "refresh_token_set": false,
  "root_id_set": false,
  "can_list": false,
  "can_download": false,
  "can_upload": false,
  "local_only_after_import": true,
  "setup_message": "Google Drive import is not configured on this machine."
}
```

### `POST /api/google-drive/list`

Body:

```json
{
  "query": "optional",
  "folder_id": "optional",
  "page_token": "optional"
}
```

Returns secret-free file metadata:

```json
{
  "files": [
    {
      "id": "opaque-drive-id",
      "name": "filename.pdf",
      "mime_type": "application/pdf",
      "modified_time": "ISO-8601",
      "size": 12345,
      "supported_for_import": true,
      "supported_for_extraction": true
    }
  ],
  "next_page_token": null
}
```

### `POST /api/google-drive/import`

Body:

```json
{
  "file_ids": ["opaque-drive-id"],
  "purpose": "student_lens_source | curriculum_unit_source | teacher_artifact_source | unassigned",
  "assigned_student_id": "optional"
}
```

Behavior:

1. Validate configuration.
2. Validate `file_ids` is a non-empty list of opaque IDs.
3. Validate purpose.
4. If purpose is `student_lens_source`, validate `assigned_student_id` exists
   before downloading.
5. Download each selected file to `~/.lingua-viva/runtime/drive_imports/`.
6. Sanitize filenames so Drive names cannot write outside the import cache.
7. Record source metadata in a local import manifest without raw file content.
8. If assigned to a student, call the same file-map assignment path used for
   local files.
9. Return local file paths suitable for downstream extraction/import UI.
10. Return per-file errors instead of crashing the whole batch.

Response:

```json
{
  "imported": [
    {
      "drive_id": "opaque-drive-id",
      "name": "filename.pdf",
      "local_path": "/home/user/.lingua-viva/runtime/drive_imports/filename.pdf",
      "purpose": "student_lens_source",
      "assigned_student_id": "student-123",
      "supported_for_extraction": true,
      "status": "imported"
    }
  ],
  "failed": [
    {
      "drive_id": "opaque-drive-id-2",
      "status": "unsupported_for_import",
      "message": "This file type is not supported yet."
    }
  ],
  "local_only_after_import": true
}
```

## 7. Supported Formats

First build:

- PDF
- plain text
- Markdown
- Google Docs exported as `.docx` or `.txt` if supported by the downloader

If `.docx` parsing is not supported by the existing extraction engine at build
time, import may download it but must report `supported_for_extraction: false`
or `unsupported_for_extraction`.

Unsupported MIME types must be reported per file and must not crash the batch.

## 8. Local Manifest

Write a local manifest under:

```text
~/.lingua-viva/runtime/drive_imports/import_manifest.json
```

Each entry may include:

- import timestamp
- Drive file ID
- Drive file name
- MIME type
- modified time
- local path
- purpose
- assigned student ID, if teacher-selected
- supported/import status

The manifest must not include:

- raw file content
- access tokens
- refresh tokens
- client secrets
- authorization headers

## 9. Privacy and Governance

- Read/list/download only in first build.
- No automatic background sync.
- No upload/export to Drive in first build.
- No student lens database upload.
- Imported files remain local after download.
- Logs may include operation type, status, and counts; they must not include
  raw student text.
- Support bundles must exclude Drive tokens and imported student files.
- Drive status must be secret-free.
- Drive file names may appear only after an explicit list/import action.
- Imported student files are treated as student data zones by support bundle
  and file-map privacy logic.

## 10. Error Handling

- Missing config returns `503` for list/import and configured false for status.
- Google auth failure returns `401` or `503` with a generic message.
- File download failure returns per-file failure, not total crash.
- Unsupported MIME type is reported per file.
- Network unavailable degrades cleanly.
- Empty selection returns `400`.
- Invalid purpose returns `400`.
- Missing/unknown assigned student for `student_lens_source` returns `400`
  before any download.
- Path traversal in file names is neutralized.

## 11. Tests

Use mocked HTTP responses. Do not call live Google APIs in tests.

Add integration tests for:

- status is secret-free
- missing config returns configured false
- list route requires configuration
- list builds a Drive files query without leaking tokens
- list returns only secret-free file metadata
- import writes to local cache
- imported filename cannot escape the cache
- import manifest excludes raw file content and credentials
- unsupported MIME type is reported per file
- partial download failure does not crash whole batch
- assigned student must exist before file-map assignment
- assigned student import records file-map assignment or equivalent bridge
- support bundle excludes Drive credentials/imported student files
- no upload route exists

Add UI/reachability tests for:

- Settings HTML includes "Google Drive"
- Settings HTML includes `/api/google-drive/status`
- Settings HTML includes `/api/google-drive/list`
- Settings HTML includes `/api/google-drive/import`
- Settings HTML includes `List Drive Files`
- Settings HTML includes `Import Selected`
- Settings HTML includes a purpose selector with `student_lens_source` and
  `curriculum_unit_source`

Update protected UI contract:

- bump `contracts/UI_CONTRACT.yaml`
- re-lock `contracts/UI_CONTRACT.lock`
- update the pinned expected version in `tests/test_ui_contract.py`

## 12. Live Served-App Verification

Before reporting PASS, run a served-app verification against the real FastAPI
app and real `static/index.html`, using mocked Drive transport where needed.

Minimum verification:

1. Start the app with isolated state:

   ```bash
   export MC_AGENT=1
   LV_HOME=/tmp/lv-drive-live \
   LV_STUDENT_DB_PATH=/tmp/lv-drive-live/student_lenses.db \
   uv run uvicorn src.web:app --host 127.0.0.1 --port 8799
   ```

2. Fetch `/` and confirm the served HTML contains:
   - `Google Drive`
   - `/api/google-drive/status`
   - `/api/google-drive/list`
   - `/api/google-drive/import`

3. Call `GET /api/google-drive/status` and confirm no secrets are present.
4. With mocked Drive transport/config, call `POST /api/google-drive/list` and
   confirm file metadata returns.
5. Create or use a local test student.
6. Call `POST /api/google-drive/import` with one mocked file assigned to that
   student.
7. Read back the file-map/import manifest state and confirm:
   - local file exists under the Drive import cache
   - no raw content appears in the manifest
   - assigned student linkage is recorded
   - no upload path was used

If browser automation is available, also click the Settings UI flow. If it is
not available, state that limitation and include the served HTML + public HTTP
route verification above.

## 13. Acceptance Criteria

- A teacher can reach Google Drive import from the real Settings view.
- The Settings view has visible controls for status, list, select, purpose,
  and import.
- Every new Drive route is called by the real app UI.
- App can show Google Drive configured/unconfigured status.
- App can list mocked Drive files through the public route.
- App can import selected mocked files into the local runtime cache.
- Imported files can be assigned to a student or curriculum purpose.
- Imported files can be passed to existing local extraction/import inputs when
  supported.
- No upload route exists.
- No secret is returned by status/list/import responses.
- Support bundle excludes credentials and imported student files.
- UI contract passes after deliberate bump/re-lock.
- Full test suite passes without live Google credentials.
- Build report distinguishes:
  - direct route/function verification
  - served-app UI reachability verification

## 14. Explicit Non-Goals

- No Drive upload/export.
- No background sync.
- No automatic student-lens sharing.
- No browser OAuth ceremony unless explicitly pulled into scope.
- No live Google API calls in tests.
- No external model use with raw imported student content.
