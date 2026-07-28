# EXECUTION PROMPT — Sources View + File Map UX Redesign (LV)

You are building in `/home/mical/learning-architecture` (Lingua Viva, public
repo). This prompt is self-contained but the spec is authoritative — read it
first and follow it exactly:

1. `dev/specs/SPEC_LV_SOURCES_VIEW_FILE_MAP_UX_2026-07-27.md` — the spec,
   APPROVED FOR BUILD, with operator rulings and the review checklist your
   work will be graded against.
2. `dev/UX_FILE_MAP_AS_IS_2026-07-27.md` — the as-is UX with exact code
   references for every surface you are changing.
3. `AGENTS.md` + `CLAUDE.md` + `publication-policy.md` — repo rules.

## What you are building

The File Map feature works but is "hidden and framed like configuration."
You are redesigning its surface — invitation, language, placement — WITHOUT
touching the scanner. New top-level **Sources** view unifying Slack (status
card), Google Drive (panel relocated), and Local folders (redesigned file
map UX). LV-only. No MC changes.

## Hard constraints (violating any of these fails the build)

- **Scanner untouched**: `src/lingua_viva/filemap.py` scan/inference/storage
  logic must remain byte-identical. The ONLY backend change allowed anywhere
  is adding a stable `code` field (`not_found` | `permission_denied` |
  `invalid_path`) to filemap error responses in `src/web.py`, derived from
  exception class/errno.
- **No new API routes.** This is UI relocation + existing endpoints. The
  route-reachability gate (`contracts/ROUTE_REACHABILITY.yaml`) must stay
  green — update call-site literals for moved markup.
- **Privacy copy is load-bearing.** These strings must appear verbatim:
  - "Lingua Viva will look at folder names and file names only. It will not
    open or read your files during this scan."
  - "Lingua Viva did not open these."
  - "File names and basic details only. Lingua Viva will not open these files."
  - Reset confirm: "This removes Lingua Viva's memory of your folder
    choices. It does not delete any files from your computer."
  - Link confirmation: "Linked to <name>. File contents were not read."
- **No school names, no colleague names** in any new copy (publication policy).
- **Do NOT commit.** Leave the working tree dirty for operator review. Do
  not push, tag, or touch releases. Another session reviews before commit.
- **The working tree already contains OTHER uncommitted work** (One-Button
  Update build: `src/lingua_viva/reconcile.py`, web.py startup wiring,
  Settings "Template Updates" panel, UI contract v35, ~44 new tests — see
  `dev/INDEX.md` row SPEC_ONE_BUTTON_UPDATE). Do not revert, stage, stash,
  or "clean up" anything you didn't write. Record `git status --porcelain`
  and `python3 -m pytest tests/ -q` BEFORE you start, and diff your final
  state against that baseline — the pass-count baseline in Verification
  below may be stale for the same reason; what matters is no NEW failures.
- **English only** for the suggested default folder (`~/Documents/Teaching`)
  — operator ruling: no Italian localization.

## Implementation map (current code locations)

All line refs verified 2026-07-27 on current main (`a944c3c`).

### static/index.html
- **Nav** (`~735-769`): `utilityNav` becomes `["slack"], ["sources"],
  ["why"], ["health"], ["privacy"], ["profile"], ["settings"], ["reflect"]`.
  Remove the `drive` entry; retire the standalone Drive view id; keep the
  Slack view untouched.
- **New `sources` view** with three sections:
  1. Slack — status card from `/api/slack/status` (connected/not
     configured), contribution line ("Daily updates and observations from
     your school workspace"), link that navigates to the existing Slack view.
  2. Google Drive — move the existing Drive panel + its JS handlers here
     verbatim (currently in Settings, panel starts `~1824`). Same routes,
     same behavior.
  3. Local folders — the redesigned file map (below).
- **Remove** the "Curriculum folders" panel from Settings (`1811-1823`) and
  the Drive panel from Settings. Settings keeps schedule/privacy/app controls.
- **Local folders UX** (rework of JS at `2296-2499`):
  - Empty + unskipped (`localStorage.lv_sources_skip` absent) → invitation:
    heading "Where do you keep your teaching materials?", buttons
    **Choose a folder** (native picker on desktop via `lvDesktop.pickFolder()`,
    fall back to the typed-path input in browser), **Use Documents/Teaching**
    (pre-fills `~/Documents/Teaching`), **Skip for now** (sets skip flag,
    collapses to "No folders connected" + "Connect a folder").
  - Pre-scan reassurance line (verbatim string above) always visible; scan
    button labeled **Scan folder names**.
  - Depth dropdown REMOVED from default flow. Default depth 3. "Advanced"
    disclosure with **Scan nearby folders only** (2) / **Scan more deeply** (4).
  - Post-scan headline: "Lingua Viva found N teaching folders and M folders
    that may contain student information." Then two sections:
    **Teaching materials** (domain folders; buttons renamed
    **Use for planning** / **Ignore** — keep `curriculum_source` on the wire,
    label-only change) and **Private student folders** (renamed from
    "Detected student-data zones"; per row **Leave closed** default state /
    **Show names only** (was "Show what's inside")).
  - Scan ends with next-action row: **Use for planning** /
    **Review private folders** / **Done**.
  - Peek listing: humanize client-side — extension chip (PDF/DOCX/…), human
    size (2.4 MB), relative dates ("Updated yesterday", date beyond 7 days).
    API payloads unchanged.
  - "Assign to student" → **Link file name to student**; save text "Linked
    to <name>. File contents were not read."; removal "Link removed." Same
    `/api/filemap/assign` payloads.
  - "Clear Map" → **Reset local folder map** with inline Cancel/confirm step
    using the verbatim reset copy above.
  - Friendly errors: map the new `code` field to teacher language
    (permission/not-found → "Lingua Viva could not open this folder
    location. You may not have permission, or the folder may have moved."
    with **Choose another folder** / **Try again**); unmapped → generic +
    Try again; raw error in a collapsed `<details>` for support.
- **Home/brief nudge**: one-time card when map empty + unskipped — "Connect
  your teaching folders" → navigates to Sources; dismiss sets the same flag.
- **Profile line** (`1652`, `1661`): keep, unchanged.

### src/web.py
- Filemap error responses (`/api/filemap/scan`, `confirm`, `peek`, `assign`,
  `exclude` — handlers at `543-697`, `776-816`): add `code` alongside the
  existing `error` string. Do not change status codes or the `error` field.

### desktop/electron/main.ts + preload.ts
- New IPC `lv:pick-folder`: `dialog.showOpenDialog({properties:
  ["openDirectory"]})`, return the selected path or null. Expose as
  `lvDesktop.pickFolder()` in preload (`contextBridge` block at
  `preload.ts:6`, handler registration pattern at `main.ts:439-459`).
  Directory-only — no file dialogs. Rebuild desktop after (`npm run build`
  in `desktop/`).

### contracts/ROUTE_REACHABILITY.yaml
- Filemap + Drive routes (`~83-97` for filemap): update `call-site` literals
  to match the moved/renamed markup so the reachability check still finds them.

### Tests
- `tests/test_filemap.py` (43 passing): extend with error-`code` assertions
  (not_found, permission_denied, invalid_path). Do not weaken existing tests.
- Update `scripts/check_ui_contract.py` expectations if it pins view ids or
  control labels you renamed.

## Build order

1. `src/web.py` error codes + tests (smallest, isolates backend risk).
2. Electron IPC picker (+ desktop rebuild).
3. Sources view markup + nav change + Drive relocation.
4. Local folders UX rework (invitation → scan → results → peek/link → reset).
5. Home nudge.
6. Reachability contract + UI contract updates.
7. Full verification pass.

## Verification (all must pass before you report done)

```bash
python3 -m pytest tests/test_filemap.py -q          # green incl. new cases
python3 -m pytest tests/ -q                          # no regressions (849+13 baseline)
python3 scripts/check_route_reachability.py          # green
python3 scripts/check_ui_contract.py                 # green
lv preflight                                         # 6/6
cd desktop && npm run build                          # compiles clean
```

Manual: launch the app, verify — invitation state, picker (desktop),
typed-path fallback, scan → headline → two-section split, Show names only,
link-file flow, reset confirm, friendly permission error (use a chmod-000
fixture dir), Skip for now persistence, home nudge, Slack/Drive cards.

## Report format

When done, report: files changed (paths + one-line what), test counts
(before/after), the verification command outputs, any spec deviation with
reasoning (deviations require flagging, not silent judgment calls), and
anything from the spec's "Post-Build Review Checklist" you know is not met.
The reviewing session will run that checklist against your diff.
