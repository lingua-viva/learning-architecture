# T1 — Google Drive Ingest Connector (Wave 2, after T0)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/CONTRACTS_V1_2026-08-04.md` (frozen — conform to the `drive.*`
interfaces exactly), `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/docpipe/drive.py` + its tests. Nothing else.

**Before speccing:** search the repo for existing Google Drive connector code —
LV inherited Drive OAuth work from the MC integration port (check `src/` for
drive/oauth modules and the egress allowlist for `oauth2.googleapis.com` /
`www.googleapis.com`). REUSE the existing auth if present; do not build a second
OAuth flow.

## Phase 1 — Spec prompt

Spec the Drive ingest connector. Output `dev/SPEC_T1_DRIVE_2026-08-04.md`, no code.
Cover:
- Auth flow and token storage location (under `~/.lingua-viva`, never the bundle).
  Teachers authenticate once; specify the failure UX when the token expires
  mid-session.
- `list_folder`: metadata returned, folder recursion, accepted file types and what
  is skipped (say which and why).
- `fetch_file`: Google-native formats (Docs/Sheets/Slides) need an export step —
  specify the export MIME per type. Binary formats download directly.
- Idempotency: sha256 of content decides re-fetch. A file already in the vault
  with a matching hash must not re-import.
- Rate limits, retry/backoff policy.
- Offline behavior: every operation degrades to "queue it" rather than throw.
  Teachers are on classroom wifi.

## Phase 2 — Implementation prompt

Implement your spec against the frozen interfaces. Scope: **INGEST ONLY** —
`drive.push_file` is T6's job, leave the stub.

Requirements:
- `drive.list_folder` and `drive.fetch_file` fully working.
- `fetch_file` writes through `vault.put_source` — it never touches disk directly.
  (Until T2 lands, write against the vault stub + T0 fixtures; switch when T2
  announces real reads.)
- Google-native export handled for Docs, Sheets, Slides.
- Hash-based skip on re-import.
- Every network failure returns a structured result, never an exception.
- Unit tests mocked; one integration test against a real Drive folder (skippable
  when no credentials — mark it clearly).

Do not parse or interpret document content — you move bytes and metadata.
Commit ONLY owned files by explicit path, message `docpipe: drive ingest (T1)`.
Report: what existing auth you reused, and the accepted-type list.
