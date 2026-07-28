# File Map — Current UX, As-Is (2026-07-27)

Descriptive only. No recommendations. Written as input for a UX review of the
file-scan system shipped in desktop-v0.2.10. Source references:
`static/index.html:1811-1823, 2296-2499`, `src/web.py:543-697, 776-816`,
`src/lingua_viva/filemap.py`, `src/lingua_viva/cli.py:291-305, 480-517`.

## 1. Where It Lives

- **Single UI location**: Settings view → third panel, titled **"Curriculum
  folders"** — below "My week" (schedule), above "Google Drive".
- **Secondary surface**: Profile view shows one read-only line: `File map:
  N roots, M directories` or `not configured` (`static/index.html:1652,1661`).
- **No presence anywhere else**: not in the first-launch setup wizard
  (Python/Ollama/server steps only), not on the home/brief view, no nudge,
  no empty-state call-to-action outside the Settings panel itself.

## 2. First-Launch / Empty State

On a fresh install the teacher who navigates to Settings sees:

- Heading "Curriculum folders"
- Text input **"Folder path"** with placeholder `~/Documents/Teaching`
- **"Depth"** dropdown: 2 / 3 / 4 (default 3) — no explanation of what depth means
- Buttons: **"Scan Folder"** (primary) and **"Clear Map"**
- Status line: badge `empty` + badge `0 student data zones excluded`
- Summary area:
  - "Scanned roots" → "No folders scanned yet."
  - "Detected domains" → badge `none` + caption "Confirm each curriculum
    source before it is used downstream."
  - "Domain folders" → "No domain-tagged folders found."
  - "Detected student-data zones" → "No student-data zones detected." with
    fixed caption "Lingua Viva stayed out during scanning. Nothing below is
    listed until you explicitly choose a zone."
  - "Exclusions" → "No exclusions set."

Nothing scans automatically, ever. All action is teacher-initiated.

## 3. Scan Flow

1. Teacher types a path (must be typed; **no native folder picker**, no
   autocomplete, no recent-paths memory). `~` is accepted and expanded.
2. Clicks **Scan Folder**.
   - Empty path → warn badge `choose a folder path`.
   - During scan → badge `scanning...` (no progress %, no cancel).
3. Backend walks the directory tree to the chosen depth using **metadata only
   (`os.stat`)** — file contents are never opened. Skipped silently:
   `.git`, `node_modules`, `__pycache__`, `.venv`, `.cache`, `.Trash`, etc.
   Symlinks are refused/skipped.
4. On success, status line shows two badges:
   `scanned N folders` (ok/green) + `M student data zones excluded` (warn/amber).
5. On failure (nonexistent path, permission error): the API 400 error text is
   rendered raw in the summary area or status badge (e.g. a Python OSError
   message).
6. Result is persisted to `~/.lingua-viva/file_map.yaml` (mode 0600) and
   re-rendered on every app load; scanning again **merges a new root** into
   the existing map (multiple roots supported).

## 4. Rendered Map (after scan)

Two-column grid, then three stacked sections:

- **Scanned roots**: each root path (displayed with `~` substituted for the
  home directory — absolute home paths never shown) + folder count.
- **Detected domains**: one badge per inferred domain with count, e.g.
  `curriculum 4` `assessment 2`. Domains are inferred from **folder-name
  keywords only** (English + Italian): curriculum, assessment, cefr,
  resources, reference, planning. No file contents, no semantic summary.
- **Domain folders**: each folder that got a domain tag, showing path, domain
  badge, file count, and a two-button confirm row:
  - **"Use for curriculum"** / **"Ignore"** (selected one turns primary,
    `aria-pressed`, plus badge `curriculum source` / `ignore`; unconfirmed
    shows badge `not confirmed`).
  - Caption above: "Confirm each curriculum source before it is used
    downstream." Confirmation state persists in the map.
- **Detected student-data zones**: folders whose names match student-data
  keywords (student/alunno, IEP/BES/PDP, pagella, parent/genitore,
  confidential/riservato, registro, ...). These are **excluded from the map's
  domain listing entirely**. Each zone row shows the path and a button:
  - **"Show what's inside"** → calls peek (below); after listing, the button
    relabels to "Refresh listing" and sets `aria-expanded`.
- **Exclusions**: list of manually excluded paths, each with a **Remove**
  button. (Adding an exclusion has **no UI affordance in this panel** — the
  add direction exists only via API/CLI; the UI can only remove.)

## 5. Student-Zone Peek + Assign

Clicking "Show what's inside":

- Interim text: "Listing names and metadata only..."
- Lists **one directory level**, metadata only: subdirectories render as
  `name/` + badge `folder — not opened`; files render name, size in bytes,
  and an ISO-8601 UTC modified timestamp (raw, e.g.
  `2026-07-21T14:03:22+00:00` — not humanized).
- Peek is server-gated: only paths the scan itself flagged as student zones
  can be peeked; symlinked zones are refused.
- Each **file** row gets an **"Assign to student"** dropdown populated from
  the current roster (display names), plus options "Not assigned" and
  **"New student"**.
  - Selecting a student → immediate save, inline text `Saved`.
  - "Not assigned" → `Assignment removed`.
  - "New student" → inline mini-form: "Student name" input + "Create and
    assign" button → creates the lens, assigns, shows
    `Created and assigned to <name>.`
  - Server validates the file is a direct child of a detected zone and the
    student exists in the roster; errors render as inline raw message text.
- Empty zone → "This zone is empty."

## 6. Clear

**"Clear Map"** deletes the entire map immediately — **no confirmation
dialog** — and re-renders the empty state. Domain confirmations, exclusions,
and student-file assignments are all part of the map and are lost with it.

## 7. Error/Edge Presentation

- All backend errors surface as raw API `error` strings (inline text or warn
  badge). No retry affordance, no error taxonomy, no help links.
- No loading skeletons; sections re-render wholesale after each action
  (`loadFileMap()` full refresh).
- No pagination/virtualization: very large scans render every folder row.

## 8. CLI Surface (parity)

`lv filemap scan <path> [--depth N]` · `lv filemap show` ·
`lv filemap exclude <path>` (the add direction missing from the UI) ·
`lv filemap clear`. Output is text/JSON summaries of the same map.

## 9. Privacy Behaviors Visible to the User

- Scan reads directory structure + `os.stat` metadata only; no file is ever
  opened; no content-derived summary exists anywhere in the system.
- Student-data zones are auto-detected by folder name and kept out of the
  map; the UI states this explicitly and requires an explicit per-zone action
  ("Show what's inside") before even file *names* are listed.
- All paths render with `~` substitution; absolute home paths never leave the
  backend.
- Map file stored locally at `~/.lingua-viva/file_map.yaml`, mode 0600.

## 10. What Does Not Exist Today (inventory, not critique)

- No folder picker / drag-a-folder; path must be typed.
- No scan step or mention of File Map in the first-launch setup wizard.
- No automatic or suggested initial scan; no onboarding nudge anywhere.
- No progress indication or cancel during scan; no rescan-this-root button
  (rescan = retype path + Scan Folder).
- No "add exclusion" control in the UI (remove only).
- No confirmation dialog on Clear Map.
- No file-content reading, indexing, or semantic summaries (by design).
- No visualization of the folder tree (flat lists only).
- No humanized dates/sizes; raw bytes + ISO timestamps.
- No connection from the map to the home/brief view; outside Settings the
  only trace is the one-line Profile count.
