# SPEC: Sources View + File Map UX Redesign

**Date**: 2026-07-27
**Status**: APPROVED FOR BUILD 2026-07-27 — assigned to a separate build
window; this session performs the post-build review
**Driver**: UX review of `dev/UX_FILE_MAP_AS_IS_2026-07-27.md`. Verdict:
privacy mechanics are correct and must not change; the failure is that the
feature is "hidden and framed like configuration." Redesign the invitation,
language, and daily placement — not the scanner.
**Scope**: LV-only, all the way through. Port the pattern back to MC later
as a separate effort.

## Product Frame

File Map joins Slack and Drive as the third leg of a **source layer**:

| Source | Teacher question it answers |
|---|---|
| Slack | What changed today? |
| Google Drive | What shared documents should I bring in? |
| Local folders | Where do my local teaching materials live? |

Teacher-level mental model for File Map: "Help Lingua Viva understand where
my teaching materials live, without reading private student files."

## Invariants (unchanged, load-bearing)

- Stat-only scanning; file contents never opened; no semantic summaries.
- Student-zone auto-exclusion by folder name; explicit per-zone action
  before even file names are listed.
- `~` path substitution; map local-only at `~/.lingua-viva/file_map.yaml` (0600).
- `src/lingua_viva/filemap.py` scanning/inference logic untouched.
- No new API routes without same-commit UI call sites (route-reachability gate).

## Changes

### 1. New "Sources" view (nav item)

New top-level view `sources` in `static/index.html` nav, replacing the
Settings placement of Drive + Curriculum folders (Settings keeps schedule,
privacy, and app-level controls). Three sections:

- **Slack** — status card from `/api/slack/status` (connected/not
  configured), one line on what it contributes ("Daily updates and
  observations from your school workspace"), link to the existing Slack view.
  No Slack logic moves.
- **Google Drive** — the existing Drive panel moves here verbatim
  (markup + handlers relocated, same routes).
- **Local folders** — the redesigned File Map section (below).

Each section header shows: connected/not-connected badge, last-updated line
where available, "what it contributes" copy, and pending-review count
(Local folders: unconfirmed domain folders).

No new backend routes — this is UI relocation + existing endpoints, so the
route-reachability gate is satisfied by construction.

### 2. First-time flow (empty map, Sources visited)

If the map is empty and the teacher hasn't skipped (flag in
`localStorage.lv_sources_skip`), Local folders renders the invitation state:

> **Where do you keep your teaching materials?**

Buttons:
- **Choose a folder** — native picker on desktop (new Electron IPC
  `lv:pick-folder` → `dialog.showOpenDialog({properties:["openDirectory"]})`,
  exposed via preload as `lvDesktop.pickFolder()`); browser fallback = the
  typed-path input.
- **Use Documents/Teaching** — pre-filled `~/Documents/Teaching`. English
  only — operator ruling 2026-07-27: do NOT localize for Italian. If the
  folder doesn't exist, fall through to the friendly not-found error.
- **Skip for now** — collapses to a quiet "No folders connected" card with a
  "Connect a folder" affordance; sets the skip flag.

Pre-scan reassurance line (always visible above the scan action):

> Lingua Viva will look at folder names and file names only. It will not
> open or read your files during this scan.

Scan button label: **Scan folder names** (was "Scan Folder").

### 3. Post-scan result framing

Headline sentence, not badges-first:

> Lingua Viva found **N teaching folders** and **M folders that may contain
> student information**.

Then two sections:

- **Teaching materials** — domain folders grouped, each row with
  **Use for planning** / **Ignore** (renamed from "Use for curriculum";
  same `/api/filemap/confirm` purposes — `curriculum_source` value kept on
  the wire, label-only change).
- **Private student folders** (renamed from "Detected student-data zones")
  — caption: "Lingua Viva did not open these." Each row:
  **Leave closed** (default, no-op visual state) / **Show names only**
  (renamed from "Show what's inside"). Peek result header reinforces:
  "File names and basic details only. Lingua Viva will not open these files."

Scan ends with a next-action row: **Use for planning** (scrolls to teaching
materials) / **Review private folders** / **Done**.

### 4. Depth control hidden

Default depth 3, dropdown removed from the primary flow. An "Advanced"
disclosure offers: **Scan nearby folders only** (depth 2) / **Scan more
deeply** (depth 4). No bare numerals in the default UI.

### 5. Reset confirmation

"Clear Map" → **Reset local folder map**, with an inline confirm step:

> This removes Lingua Viva's memory of your folder choices. It does not
> delete any files from your computer.

Buttons: **Cancel** / **Reset folder map**. (The does-not-delete-files
sentence is mandatory copy.)

### 6. Link-file language

"Assign to student" → **Link file name to student**. Save confirmation:
"Linked to <name>. File contents were not read." Removal: "Link removed."
Same `/api/filemap/assign` route and payloads.

### 7. Humanized metadata

In peek listings: extension chip (PDF/DOCX/…), human size (2.4 MB), relative
dates ("Updated yesterday", falling back to date for >7 days). Raw values
remain in the API; formatting is client-side only.

### 8. Friendly errors

Client-side mapping of filemap API errors to teacher language + actions:

- Permission/not-found class →
  > Lingua Viva could not open this folder location. You may not have
  > permission, or the folder may have moved.
  Actions: **Choose another folder** / **Try again**.
- Anything unmapped → generic "Something didn't work reading that folder"
  + Try again. Raw error retained in a collapsed details element for support.

Backend addition (small, no new route): filemap error responses gain a
stable `code` field (`not_found` / `permission_denied` / `invalid_path`)
derived from the exception class/errno, so the client mapping isn't
string-matching English.

### 9. Onboarding surface (first launch)

No setup-wizard change (wizard is pre-server, stays Python/Ollama/server).
Instead: the home/brief view shows a one-time nudge card when the map is
empty and unskipped — "Connect your teaching folders" → routes to Sources.
Dismiss = same skip flag.

## Out of Scope (explicitly)

- Any change to scanning, zone detection, domain inference, or map storage.
- Slack/Drive functional changes (placement + status card only).
- Content reading / semantic summaries (permanently out per operator ruling).
- MC port (follow-on effort once LV pattern validates with the pilot).
- UI "add exclusion" affordance — deferred; CLI/API parity gap noted in the
  as-is doc but not requested by the UX review.

## Verification

- Existing `tests/test_filemap.py` 43/43 unchanged (backend untouched except
  error `code` field — extend tests for the codes).
- `contracts/ROUTE_REACHABILITY.yaml` — call-site literals updated for moved
  markup; `lv preflight` green.
- UI contract check (`scripts/check_ui_contract.py`) updated for the new
  view id + renamed controls.
- Manual pass on the desktop build: picker IPC, first-run invitation, reset
  confirm, friendly errors (permission-denied fixture folder).

## Operator Rulings (2026-07-27)

1. **Nav position**: Sources replaces the "Drive" entry in `utilityNav`
   (`static/index.html:760-769`) — utility nav becomes Slack, **Sources**,
   Why, Health, Privacy, Profile, Settings, Reflect. The Drive view id is
   retired; its panel renders inside Sources. Slack keeps its own view;
   Sources shows its status card with a link. (Default proposed to operator
   with the daily-row alternative explained; adopt this unless overridden.)
2. **No Italian localization** of the default folder suggestion.
3. **Build assignment**: a separate agent window builds this spec; the
   authoring session reviews the build afterward (spec-compliance +
   invariants + tests + reachability).

## Post-Build Review Checklist (for the reviewing session)

- [ ] Scanner untouched: `git diff src/lingua_viva/filemap.py` limited to
      error-`code` plumbing at most; scan/inference logic byte-identical.
- [ ] No new API routes; `contracts/ROUTE_REACHABILITY.yaml` call-site
      literals updated for moved markup; `lv preflight` green.
- [ ] Privacy invariants intact: stat-only, zone peek gated + renamed copy
      present ("Show names only", "did not open these", "File contents were
      not read"), `~` substitution everywhere.
- [ ] Reset confirm includes the "does not delete any files from your
      computer" sentence verbatim.
- [ ] Depth dropdown absent from default flow; Advanced disclosure works.
- [ ] Electron `lv:pick-folder` IPC: openDirectory only, no file dialogs;
      browser fallback still functional.
- [ ] `tests/test_filemap.py` green incl. new error-code cases; full suite
      no regressions; UI contract check updated.
- [ ] Publication policy: no school/colleague names in new copy.
