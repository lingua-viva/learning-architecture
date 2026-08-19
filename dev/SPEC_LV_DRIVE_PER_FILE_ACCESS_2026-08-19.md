# SPEC_LV_DRIVE_PER_FILE_ACCESS — 2026-08-19 (BUILT same day)

**Status: BUILT.** Scope changed to `drive.file`, honest degradation landed, class-lock
tests green. Remaining: ship in a desktop release → operator publishes the OAuth app to
production (2 clicks, no verification) → acceptance test = a teacher on NO list signs in.

## The ruling (operator, 2026-08-19 — STANDING)

**Build for teachers and students, never for the demo.** The acceptance test for any
user-facing capability: does it work for any teacher with NO special access, NO
registration, NO admin privileges, NO operator-side setup? Test-user lists, admin
allowlists, and per-school IT setup are **non-starters** — schools will not maintain
staff email lists outside their org, and the first testers are unknown admin staff the
operator never meets.

## What this forces

Google's OAuth model gives exactly one path that satisfies the ruling:

| Model | Works for any teacher? | Why rejected/chosen |
|---|---|---|
| Testing mode + test users | ✗ hard `access_denied` for non-listed users | per-user email registration — non-starter |
| Production + restricted `drive` scope, unverified | ✗ scary interstitial + 100-user cap | trust poison + CASA verification (weeks, annual cost) |
| Workspace admin allowlist | ✗ requires school IT action | admin privileges — non-starter |
| **Production + `drive.file` (non-sensitive)** | **✓ any Google account, no warnings, no lists, no verification** | **chosen** |

`drive.file` = per-file access: the app sees ONLY files/folders it created (by any user
of the app — shared app-created files remain visible across teachers).

## Code changes (this build)

- `google_drive_oauth.py` — `SCOPES` → `.../auth/drive.file`, with a NEVER-widen comment.
- `google_drive_integration.py` — `PER_FILE_ACCESS_HINT` + `_is_access_denied()`; 403/404
  on `connect_folder` / `download_file_text` / `list_files` / `list_folder_files` now
  says what works (direct upload in the app), never "check it is shared with the
  connected account" (a sharing fix cannot work under per-file access — that message was
  actively misleading).
- `docpipe/drive.py` — same honest hint on metadata/download 403/404.
- `web.py` class-folder route — passes the DriveAuthError message through instead of the
  generic "could not be reached safely".
- `tests/test_google_drive_oauth.py` — **class-lock**: scope must contain `drive.file`
  and must NOT contain restricted `drive`/`drive.readonly`; 403/404 must surface the
  per-file hint with upload guidance.

## What survives vs. degrades under drive.file

**Survives (all app-created content):** in-app sign-in; lens/lesson sync-back to Drive;
`ensure_lens_sync_folder`; `pull_shared_ledgers` (colleagues' ledgers are app-created →
visible when shared); safeguarding/HR share-to-folder; the whole collaborative loop.

**Degrades honestly (pre-existing school files by pasted link):** folder connect,
class-folder crawl ingest, roster-import-by-link, lesson-coursework-from-folder. Each
returns the per-file hint directing to direct upload — which is the ingest path the
real-data fix wave (SPEC_LV_UNIFIED_REAL_DATA_FIX) is built on, and explicit file
selection is the safety model that wave's audit demands (the crawl path is what produced
the 940-fake-lens scenario).

**Future (optional UX slice):** Google Picker lets a teacher grant specific existing
files/folders through a native Drive dialog under drive.file — restores "point at your
file in Drive" without the restricted scope. Not required for correctness.

## Operator steps remaining

1. Ship this in the next desktop release (OAuth client already staged via GitHub
   secrets, set 2026-08-19).
2. Google console → Audience → **Publish app** (to production). With only non-sensitive
   scopes requested, there is no verification step and no warning screen; refresh tokens
   stop expiring (Testing-mode tokens die after ~7 days — the cause of the "it worked
   when I tested it" confusion).
3. Acceptance: Claudia — on no list — signs in from her machine. If it does not work for
   her, it does not work.

## Never do again (defect class)

- Any scaffold that only works because the tester was pre-registered or the dev machine
  has hidden state (`~/.lingua-viva/config/oauth_client.json` existed locally since
  Aug 1 while shipped builds had no credentials at all — "works here" said nothing).
- Widening the Drive scope. The class-lock test fails the suite if it comes back.
