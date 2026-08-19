# SPEC: Drive Out-of-the-Box — Roster → Lenses → Drive (2026-08-18)

**Status**: APPROVED (operator directive 2026-08-18, verbatim below) — build same day.
**Origin**: Claudia's first real test (2026-08-18). She could not import her students
from Drive; the app asked her to create profiles by hand and Drive sign-in was dead
on a fresh install.

## 0. The Teacher Contract (frozen — this is the whole product)

> "we need connect to drive, get all the student information automatically, all
> lenses created automatically, all lenses updatable via observe automatically,
> then all updated lenses uploaded back to drive automatically. only teacher
> actions are connect to drive where roster and student info is located...
> then observe when needed per student... NO OTHER ACTION CAN BE ASKED OF TEACHERS"

Exactly **two** teacher actions, ever:

1. **Connect** — sign in to Google Drive once, point at the roster file where
   student info lives.
2. **Observe** — per student, when needed.

Everything else is automatic. This must work for **hundreds of teachers out of
the box** — no API keys, no Google Cloud console, no folder configuration, no
per-student confirmation clicks. Same bar as the bundled research key.

The roster is **one messy file**: whatever the teacher already has (Doc, Sheet,
Word, text), no required structure. We fill in what we have, one lens per
student. Fields without evidence stay empty — nothing is invented.

**Out of scope (settled, do not touch):** the lens structure itself (studied at
length — unchanged); Perplexity key rotation (operator: "we will worry about the
key soon"); Chromebook build; the in-flight .deb packaging work (separate
session — its hunks must NOT be committed with this build).

## 1. What already exists (verified in code this session)

| Capability | Where | State |
|---|---|---|
| PKCE loopback Drive sign-in | `src/lingua_viva/google_drive_oauth.py` (`start_signin` :167, `can_signin` :105) | Built; **dead on fresh installs** because no OAuth client ships (`load_client_config()` finds nothing → "Google sign-in is not available on this build") |
| Client config candidates | `google_drive_oauth.py:50-55` — env vars, `lv_home()/config/oauth_client.json`, next to `sys.executable`, repo root (`parents[2]`) | Repo-root candidate resolves to `resources/app/oauth_client.json` in the packaged app |
| Roster ingest from Drive ref | `src/web.py:2485` `/api/students/ingest` accepts `{drive_ref}` | Endpoint built; `docpipe/drive.py fetch_file` is a **NotImplementedError stub** (frozen T1 seam) → honest failure message |
| Extraction → student detection → lens creation | `_run_ingest_job` (web.py:2415), `_create_lens_for_detected` (:2377) → `docpipe_lens.create_from_extraction` | Built. Tolerant fill: only fields with evidence populate (`fields_populated`). Local-model enrichment optional; deterministic offline |
| Auto-create policy | web.py:2444-2465 — auto-creates at confidence ≥ 0.7, **but any import with > 2 students forces per-name review** (`BULK_IMPORT_CONFIRMATION_THRESHOLD = 2`) | Blocks the contract for real rosters |
| Undo an import | `DELETE /api/students/ingest/{job_id}` (web.py:2714) — archives every created lens | Built, keep |
| Lens auto-upload after observation | `trigger_sync(student_id)` at web.py:3851 and :4483 → `drive_sync.sync_lens_to_drive` (:502) | Built. **Skips with `queued: student summaries folder is not configured`** on every fresh install — nothing ever configures the folder |
| Upload mechanics | `google_drive_integration.upload_text_to_folder` (:1038) — update-in-place by filename; `assert_safe_for_external_output` gate before upload | Built, keep |
| Queue drain | `retry_pending_syncs` (drive_sync.py:861), "Sync now" (`sync_lenses_to_drive`, web.py:3570) | Built; drain requires a teacher click today |
| Firewall allowlist | `oauth2.googleapis.com`, `www.googleapis.com` already allowed | No change |

**Diagnosis**: the whole cycle was built as capabilities, but two credentials/
configs were never packaged (OAuth client; sync folder) and two seams were left
as stubs/over-cautious policy (fetch_file; bulk-confirm). Same failure class as
the Perplexity key: *capability built, credential never packaged.*

## 2. Gaps and exact changes

### G1 — Ship the Google OAuth client in the installer (unblocks Connect)
- `.github/workflows/desktop-release.yml`: before `npm run dist:*`, write
  `oauth_client.json` at repo root from secrets `LV_GOOGLE_OAUTH_CLIENT_ID` /
  `LV_GOOGLE_OAUTH_CLIENT_SECRET` (all 3 platform jobs). Skip silently when
  secrets are absent (fork builds keep working; sign-in stays honestly
  unavailable).
- `desktop/package.json` `extraResources.filter`: add `"oauth_client.json"` so
  it lands at `resources/app/oauth_client.json` — the existing repo-root
  candidate path. No code change in `google_drive_oauth.py`.
- Google's own model for installed apps: the desktop client secret is
  officially non-confidential; bundling is the standard pattern.
- **Operator dependency (blocking A1, not the build):** create a Google Cloud
  OAuth client (type: Desktop) and add the two GitHub secrets. For >100 users
  on Drive scope, start Google app verification (until then: "unverified app"
  screen, still functional).

### G2 — Implement Drive fetch + roster picker (unblocks the roster)
- Implement `docpipe/drive.py fetch_file(file_ref)` by delegating to
  `google_drive_integration` (existing `_access_token`/transport/metadata
  helpers): Google Docs/Sheets export to text/CSV, binary files via
  `alt=media`, bounded read, return the existing `SourceBytes` contract.
  Accept a raw file ID or a pasted Drive file URL (add `parse_file_link`
  beside `parse_folder_link`).
- Students view: replace the file-picker-only import form with
  **"Import roster from Drive"**: if not signed in → existing PKCE start/poll
  flow (same as Settings); then a single input — paste the roster's Drive link
  → `POST /api/students/ingest {drive_ref}` → existing job progress UI.
  Local-file import stays as the fallback path.
- Remove the "Drive folder import arrives with the Drive connector" copy
  (static/index.html:2529) — it arrives now.

### G3 — Auto-create ALL roster students (kills the per-name confirms)
- In `_run_ingest_job`: for **roster-style imports** (the current
  `bulk_review_required` branch), auto-create every detected student instead
  of queuing per-name confirmation. Low-confidence detections are still
  created but carried in `job["warnings"]` ("check these names") — the teacher
  reviews by *undoing*, not by *approving*: `Undo this import` (one click,
  archives all) remains the safety, and archiving is reversible (soft delete).
  This converts a hundred confirm-clicks into zero clicks + one visible undo.
- Small imports (≤ 2 students, e.g. a single student doc) keep the existing
  confidence-gated behavior — unchanged.

### G4 — Tolerant fetch-and-fill from messy data (verify + lock, not rebuild)
- The tolerant fill already exists (`create_from_extraction`: fields populate
  only with evidence). Do NOT redesign. Add one regression fixture: a messy
  roster (mixed columns, prose notes, missing fields, inconsistent naming) →
  N lenses created, `fields_populated` non-empty where the data exists, empty
  where it doesn't, zero invented values. Lock the class.

### G5 — Auto-provision the sync-back folder (closes the loop to Drive)
- Add `create_folder(name, parent_id=None)` to `google_drive_integration`
  (Drive `files.create` with folder mimeType; reuse-if-exists by name query,
  same pattern as `upload_text_to_folder`'s update-in-place).
- On first successful roster import with Drive connected (and whenever
  `get_sync_folder_map()` lacks `student_summaries`): auto-create
  **"Lingua Viva – Student Lenses"** in the teacher's Drive and
  `set_sync_folder_map({student_summaries: <id>})`. Zero teacher action.
- Drain automatically: call `retry_pending_syncs()` on backend startup (when
  Drive is configured) and right after the folder is auto-provisioned — the
  "Sync now" button stays but is no longer required.
- Unchanged invariants: only lens markdown (+ provisioned-teacher ledgers)
  goes back to Drive; `assert_safe_for_external_output` gates every upload;
  offline observations queue and drain (existing `_record_pending_sync`).

### G6 — Contract + suite discipline
- `contracts/UI_CONTRACT.yaml` → v154 **in the same commit as**
  `tests/test_ui_contract.py` EXPECTED_VERSION + bump-log line (this morning's
  failure class).
- Full `python3 -m pytest tests/ -q` green before push.

## 3. The resulting teacher experience (acceptance)

- **A1** Fresh packaged install (secrets present at build): Students →
  "Import roster from Drive" → Google sign-in works first try. *(Blocked on
  operator creating the OAuth client + secrets; everything else ships now.)*
- **A2** Paste roster link → every student appears automatically, zero
  per-name confirmations; "Undo this import" archives all of them.
- **A3** Messy-roster fixture: fields filled where evidence exists, empty
  where not, nothing invented.
- **A4** Teacher saves an observation → the student's lens markdown appears/
  updates in "Lingua Viva – Student Lenses" in their Drive with no further
  action.
- **A5** Offline observation → queued; drains automatically on next launch.
- **A6** UI contract v154 + EXPECTED_VERSION in one commit; suite green.
- **A7** Pushed per AGENTS.md definition: auto-release green, linguaviva.art
  pin updated, download resolves, superseded release deleted. Only this
  build's hunks committed — the .deb WIP stays uncommitted.

## 4. Build order

G2 backend (fetch_file) → G3 (auto-create-all) → G5 (create_folder +
auto-provision + startup drain) → G2 UI (Students import flow) → G4 fixture →
G1 (workflow + packaging filter) → G6 (contract bump + suite) → push.
