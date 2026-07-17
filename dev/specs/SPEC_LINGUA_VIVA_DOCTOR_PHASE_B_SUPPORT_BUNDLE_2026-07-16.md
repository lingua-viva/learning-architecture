# Lingua Viva Doctor Phase B Support Bundle Spec

**Status**: proposed build spec  
**Date**: 2026-07-16  
**Branch**: `LINGUA-VIVA-UPDATE`  
**Depends on**: Phase A Doctor MVP  
**Primary user surface**: Lingua Viva app Doctor result panel  

## 0. Goal

Add a local, redacted support bundle flow so a teacher can package useful diagnostic evidence after Doctor finds an issue, without uploading data and without exposing student/private content.

## 1. User Story

A teacher presses `Doctor` in the Lingua Viva app. Doctor returns `WARN`, `BLOCKED`, `FIXABLE`, or `PRIVATE_RISK`. The app offers:

```text
Create Support Bundle
```

The teacher confirms. The app creates a local redacted bundle, shows the local file path, and confirms:

```text
Support bundle created.
No student data was included.
No files were uploaded.
```

The teacher can send the bundle manually if needed.

## 2. Scope

Phase B adds:

- support bundle builder
- app button/action to create bundle after Doctor run
- CLI fallback for bundle creation
- redaction and exclusion rules
- bundle manifest
- bundle gauntlet/tests
- hardening report
- revision-log entry

Phase B does not add:

- upload
- repair
- update
- incident logging workflow
- improvement proposal loop
- curriculum/source edits
- `.docx` edits

## 3. Non-Negotiable Privacy Rules

The bundle must never include:

- raw student observations
- student names
- IEPs
- progress reports
- individual assessment records or scores
- parent communications
- raw `.docx` contents
- unpublished curriculum excerpts
- API keys, tokens, passwords, OAuth secrets
- private local databases
- screenshots unless explicitly requested and redacted

The bundle may include:

- file paths
- file existence status
- branch name
- git status for relevant paths
- Doctor check IDs and statuses
- redacted Doctor output
- gauntlet output
- YAML/NDJSON parse status
- support-loop version
- manifest of excluded files with reasons

## 4. App UX

### 4.1 Button Visibility

After Doctor completes, show `Create Support Bundle` when:

- status is `WARN`
- status is `FIXABLE`
- status is `BLOCKED`
- status is `PRIVATE_RISK`

Do not show by default when status is `OK`, though details may include an optional support bundle action for operator/debug mode.

### 4.2 Confirmation Dialog

Before creating:

```text
Create a local support bundle?

This will collect diagnostic status, failed checks, version information, and redacted logs.

It will not include student data, parent communications, raw observations, or the manual .docx contents.

Nothing will be uploaded.
```

Buttons:

- `Create Bundle`
- `Cancel`

### 4.3 Success State

```text
Support bundle created.

Path:
/home/.../.lv_support/bundles/lv-support-20260716T153000Z/

No student data was included.
No files were uploaded.
```

### 4.4 Failure State

```text
I could not create the support bundle safely.

Reason:
[safe, redacted reason]

No files were uploaded.
```

## 5. Command Surface

CLI fallback:

```bash
python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle
python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle --json
```

Optional:

```bash
python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle --doctor-json /path/to/doctor.json
```

The app should call a local endpoint, not shell out from browser code.

Proposed endpoint:

```text
POST /api/lingua-viva/support-bundle
```

Request body:

```json
{
  "include_screenshots": false
}
```

Response:

```json
{
  "status": "OK",
  "bundle_path": "/home/mical/fde/implementations/education/lingua-viva/.lv_support/bundles/lv-support-20260716T153000Z",
  "manifest_path": ".../MANIFEST.json",
  "summary": "Support bundle created. No student data was included. No files were uploaded.",
  "included_count": 8,
  "excluded_count": 4,
  "privacy_notes": [
    "Manual .docx contents excluded.",
    "Private paths excluded by rule."
  ],
  "external_calls": false
}
```

## 6. Bundle Structure

Bundle directory:

```text
.lv_support/bundles/lv-support-YYYYMMDDTHHMMSSZ/
  SUPPORT_SUMMARY.md
  DOCTOR_RESULT.json
  GAUNTLET_OUTPUT.txt
  STRUCTURED_PARSE.json
  GIT_STATUS.txt
  MANIFEST.json
  EXCLUDED_FILES.md
  REDACTION_REPORT.md
```

Do not create zip by default in Phase B. A directory is easier to inspect and less likely to hide accidental content. Zip can be Phase B.1 after review.

## 7. Manifest Schema

```json
{
  "bundle_id": "lv-support-20260716T153000Z",
  "created_at": "2026-07-16T15:30:00Z",
  "created_by": "lv_support_phase_b",
  "repo_root": "/home/mical/fde",
  "lingua_viva_root": "/home/mical/fde/implementations/education/lingua-viva",
  "external_calls": false,
  "included": [
    {
      "path": "SUPPORT_SUMMARY.md",
      "source": "generated",
      "privacy_class": "redacted_diagnostic"
    }
  ],
  "excluded": [
    {
      "path": "Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx",
      "reason": "authoritative private-source manual; contents excluded"
    }
  ],
  "redactions": [
    {
      "type": "email",
      "count": 2
    }
  ],
  "checks": {
    "student_data_included": false,
    "docx_content_included": false,
    "external_upload": false
  }
}
```

## 8. Included Files

### 8.1 `SUPPORT_SUMMARY.md`

Human-readable summary:

- Doctor status
- top failed/warn checks
- next recommended action
- branch
- timestamp
- privacy statement
- list of excluded private files

### 8.2 `DOCTOR_RESULT.json`

Doctor result object with all details redacted.

Must preserve:

- check IDs
- statuses
- messages
- safe details
- next steps

Must redact:

- email
- phone
- secrets
- private context terms
- any matched private path details beyond path basename where needed

### 8.3 `GAUNTLET_OUTPUT.txt`

Output of:

```bash
python3 dev/lv_artifact_gauntlet.py
```

Redacted before writing.

### 8.4 `STRUCTURED_PARSE.json`

Machine-readable parse status:

```json
{
  "yaml": {
    "artifacts/inventory.yaml": "pass",
    "claims/evidence_register.yaml": "pass"
  },
  "ndjson": {
    "dev/lv_revision_log.ndjson": "pass"
  }
}
```

No raw file contents.

### 8.5 `GIT_STATUS.txt`

Output of safe git status commands only:

```bash
git branch --show-current
git status --short -- implementations/education/lingua-viva
```

Redacted.

### 8.6 `EXCLUDED_FILES.md`

List excluded paths and reasons.

Example:

```text
- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx
  Reason: authoritative private-source manual; contents excluded.
- .lv_support/
  Reason: support state directory; avoid recursive bundle inclusion.
```

### 8.7 `REDACTION_REPORT.md`

Counts only:

```text
Redactions applied:
- email: 2
- phone: 0
- secret: 0
- private context phrase: 1
```

No original values.

## 9. Exclusion Rules

Always exclude contents for:

```text
**/*.docx
**/student_lens*.db
**/still_i_rise.db
**/observations*
**/parent_reports*
**/progress_reports*
**/IEP*
**/private*
**/.lv_support/**
```

The bundle may list these paths with reasons but must not read or copy contents.

## 10. Redaction Rules

Redact from any included text:

- API keys
- tokens
- passwords
- secrets
- emails
- phone numbers
- parent report phrase
- progress report phrase
- student observation phrase
- IEP phrase
- obvious private context markers

Redaction output examples:

```text
[REDACTED_EMAIL]
[REDACTED_PHONE]
[REDACTED_SECRET]
[REDACTED_PRIVATE_CONTEXT]
```

## 11. Engine Design

Add modules:

```text
dev/support_loop/bundle.py
dev/support_loop/redaction.py    # optional if privacy.py grows too large
```

Suggested functions:

```python
def create_support_bundle(include_screenshots: bool = False) -> dict:
    ...

def build_manifest(bundle_dir: Path, included: list, excluded: list, redactions: dict) -> dict:
    ...

def write_support_summary(bundle_dir: Path, doctor_result: dict, manifest: dict) -> None:
    ...
```

The existing `privacy.py` may be extended for counted redactions, but keep the Phase A redactor behavior stable.

## 12. Endpoint Design

Add:

```python
@app.post("/api/lingua-viva/support-bundle")
async def lingua_viva_support_bundle(payload: dict | None = None):
    ...
```

Endpoint rules:

- local only
- no upload
- no repair
- no update
- generic app-safe error detail
- return JSON result
- call support-loop bundle engine

## 13. App UI Design

Add button inside Doctor result card when status is not `OK`:

```html
<button onclick="createSupportBundle()">Create Support Bundle</button>
```

Add JS function:

```javascript
async function createSupportBundle() {
  if (!confirm(...)) return;
  const res = await fetch('/api/lingua-viva/support-bundle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({include_screenshots: false})
  });
  ...
}
```

Render:

- success message
- local bundle path
- privacy statement
- no upload statement
- app-safe failure message

## 14. Tests

### 14.1 Unit Tests

Add tests for:

- bundle directory creation
- manifest schema
- excluded `.docx`
- excluded private paths
- redaction counts
- no original secret/email in bundle files
- doctor result included and redacted
- gauntlet output included and redacted
- git status included and redacted

### 14.2 Endpoint Tests

Add tests for:

- `POST /api/lingua-viva/support-bundle` returns 200
- response has `external_calls: false`
- response has local `bundle_path`
- response does not expose raw exception detail on failure
- bundle manifest exists

### 14.3 App Tests

Add tests for:

- Doctor card contains `Create Support Bundle` action for non-OK status
- JS function calls `/api/lingua-viva/support-bundle`
- UI states no upload

### 14.4 Adversarial Redaction Tests

Fixtures:

- fake email
- fake phone
- fake API key
- fake parent report text
- fake IEP filename
- fake `.docx` path
- fake student observation line

Expected:

- original sensitive strings absent from bundle
- redaction tokens present
- excluded files listed by path/reason only

## 15. Validation Commands

Run:

```bash
python3 implementations/education/lingua-viva/dev/lv_support.py doctor
python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle
python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle --json
python3 implementations/education/lingua-viva/dev/lv_artifact_gauntlet.py
pytest -q implementations/education/lingua-viva/dev/support_loop/tests
pytest -q mission-canvas/tests/test_pwa_assets.py mission-canvas/tests/test_pwa_routes.py
python3 -m py_compile mission-canvas/src/web.py implementations/education/lingua-viva/dev/lv_support.py implementations/education/lingua-viva/dev/support_loop/*.py
```

Also verify:

```bash
git -C /home/mical/fde branch --show-current
git -C /home/mical/fde status --short -- implementations/education/lingua-viva/Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx
```

Branch must be `LINGUA-VIVA-UPDATE`. `.docx` must have no status output.

## 16. Hardening Sweep

Create:

```text
dev/LV_DOCTOR_PHASE_B_SUPPORT_BUNDLE_HARDENING_REPORT_2026-07-16.md
```

Run and record 15 gates:

1. branch is `LINGUA-VIVA-UPDATE`
2. Doctor CLI passes
3. support-bundle CLI creates bundle
4. support-bundle JSON parses
5. endpoint returns 200
6. manifest exists and parses
7. `.docx` excluded from bundle contents
8. fake secret redacted
9. fake email redacted
10. fake private path excluded
11. app button/static test passes
12. PWA route test passes
13. support-loop tests pass
14. `.docx` no-diff
15. final git status visibility

## 17. Revision Log

Append to:

```text
dev/lv_revision_log.ndjson
```

Required entry fields:

```json
{
  "timestamp": "2026-07-16T00:00:00-07:00",
  "revision_id": "lv-rev-009",
  "artifact_id": "lv-artifact-support-bundle-phase-b",
  "artifact_path": "dev/support_loop/bundle.py; ../../../../mission-canvas/src/web.py; ../../../../mission-canvas/static/index.html",
  "defect_class": "privacy_exposure",
  "origin": "agent_implementation",
  "instrument_that_found_it": "doctor_phase_b_support_bundle_spec",
  "instrument_touched": true,
  "independent_cross_check": "phase_b_redaction_hardening_sweep",
  "decision": "Add local redacted support bundle creation from the Doctor app flow.",
  "proof": "Bundle creation, manifest, redaction, exclusion, endpoint, app UI, tests, and .docx no-diff passed.",
  "reviewer": "codex_agent",
  "teacher_contribution_involved": false,
  "privacy_review": "passed"
}
```

Use the next actual revision ID if `lv-rev-009` is no longer available.

## 18. Acceptance Criteria

Phase B is done when:

- app offers `Create Support Bundle` after non-OK Doctor results
- bundle creation is local only
- bundle path is shown in app
- no upload occurs
- `.docx` contents are excluded
- private paths are excluded
- redaction tests pass
- support-loop tests pass
- app endpoint tests pass
- hardening report exists
- revision log entry exists
- `.docx` remains unmodified
- branch remains `LINGUA-VIVA-UPDATE`

## 19. Deferred After Phase B

- zip export
- optional upload after operator approval
- screenshots with redaction
- safe repair
- safe update
- incident logging
- recursive support improvement proposal loop

## 20. Final Rule

If a support bundle is not safe, do not create it. Return `BLOCKED` with an app-safe reason and no raw diagnostic detail.
