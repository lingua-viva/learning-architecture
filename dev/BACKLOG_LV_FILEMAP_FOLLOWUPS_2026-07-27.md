# Backlog — File Map / Sources follow-ups (queued 2026-07-27)

**Status:** QUEUED — no build until the operator's deep-dive review of the
Sources View + File Map UX build (UI contract v39) completes. All three items
came out of cross-reviewing `SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27.md`
against the just-finished build.

**Shared constraints when built:**
- `src/lingua_viva/filemap.py` scan/inference logic stays untouched unless a
  new spec explicitly rules otherwise; items 1–2 are stat-only by design.
- Any `static/index.html` edit forces a UI-contract bump (v40+) — batch these
  with the next index.html window, never as drive-by edits.
- Verbatim privacy strings from SPEC_LV_SOURCES_VIEW_FILE_MAP_UX are frozen.

## 1. Scan-root death path (render-time, not just action-time)

If a scanned root is renamed/moved/deleted after scanning, the Sources view
still renders "connected" from the stored map; the teacher only finds out when
an action fails. Add a render-time existence signal for scanned roots
("This folder no longer exists at this location") with a re-scan/choose-again
path. Vanished *zones* at action time are already handled (friendly
`invalid_path` error, tested) — this closes the status-time half.

## 2. Map freshness ("your map may be stale")

The file map is a one-shot snapshot with a "Last scanned" date and no decay
signal. Mirror the Drive spec §B pattern: a stat-only mtime check of scanned
roots vs `last_scanned` — same privacy class as the original scan (folder
names and dates only, nothing opened) — powering a "Folders may have changed —
rescan?" nudge. Likely warrants a small spec (copy + threat-model sentence)
rather than a drive-by build.

## 3. Scan button double-fire

`scanLocalFolder()` (static/index.html:3059 at v39) never disables the button
during a scan; a double-click fires two concurrent POSTs to
`/api/filemap/scan` against the same map file. Low severity (single local
user) but wrong: disable button + show scanning state until settle. Two-line
fix — fold into the next index.html window with its contract bump.
