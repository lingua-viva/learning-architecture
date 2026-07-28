# SPEC — File Map Final (pre-ship fixes + deferred freshness)

**Date:** 2026-07-27
**Status:** §A + §B **APPROVED FOR BUILD** (operator G2 ruling 2026-07-27,
folded into `dev/EXECUTION_PROMPT_LV_SOURCES_SHIP_2026-07-27.md` Phase 1,
target `desktop-v0.2.11`). §C **DEFERRED — DRAFT**, own window + ruling.
**Owner:** the Sources-build session owns this through Definition-of-Pushed.
**Relates to:** `dev/specs/SPEC_LV_SOURCES_VIEW_FILE_MAP_UX_2026-07-27.md`
(built, independently reviewed **PASS 8/8**),
`dev/BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md` (source of items),
`dev/EXECUTION_PROMPT_LV_SOURCES_SHIP_2026-07-27.md` (ship vehicle).

## 0. Where the build stands

Sources View + File Map UX is BUILT and reviewed PASS 8/8 (scanner
byte-identical, no new routes, privacy strings verbatim, contract ceremony
clean, publication policy clean). The tree is uncommitted, shared with three
other finished lanes; the UI contract drifted v39→v44 during review because
lanes were still writing. What remains for the file map specifically is two
approved pre-ship fixes (§A, §B), one deferred item (§C), then the ship
prompt's Phases 0–5.

## Invariants (inherited, non-negotiable)

- I1. `src/lingua_viva/filemap.py` stays **byte-identical**. All work lives in
  `src/web.py` and `static/index.html`.
- I2. The five verbatim privacy strings are frozen.
- I3. No new API routes; route-reachability stays green.
- I4. Stat-only forever: nothing in this spec opens or reads file contents.
- I5. One UI-contract bump covers §A+§B together (never drive-by), taken only
  after all other lanes have stopped (v38 lesson).
- I6. No school/colleague/student names in copy or commit messages.

## §A — Scan-button double-fire (APPROVED)

`scanLocalFolder()` (`static/index.html:3136` at v44; button wired at
`:2850`) fires concurrent POSTs to `/api/filemap/scan` on double-click.

- Disable the scan button the moment the request starts; keep the existing
  "scanning folder names..." badge; re-enable in `finally` after settle
  (success re-render replaces the section anyway; the `finally` covers the
  error path).
- Client-only. No backend change. No new copy.
- Test: none automatable beyond `node --check` (behavioral, single client);
  covered by ship-prompt Phase 2 manual item "double-click scan fires once."

## §B — Scan-root death path (APPROVED)

A root renamed/moved/deleted after scanning still renders "connected" from
the stored map; the teacher only learns via a later action failure.

**Backend (`src/web.py` only, in `filemap_get` at ~:777–782):** post-process
the existing `to_api()` result — for each scanned root add
`"exists": os.path.isdir(os.path.expanduser(<stored root path>))`. Stored
paths are `~`-substituted, so `expanduser` is required. API shape otherwise
unchanged; no route added.

- Known edge (accepted): `os.path.isdir` also returns `False` when a parent
  directory is unreadable — the folder exists but LV can't see it. The row
  copy below is written to be truthful in both cases ("no longer exists **at
  this location**" — from LV's view it doesn't). Not worth an errno branch.

**UI (Sources view, scanned-roots rendering):** when `exists === false`, show
on that root's row: **"This folder no longer exists at this location."** with
actions **Choose another folder** (existing `chooseLocalFolder()` affordance)
and **Scan folder names** (existing scan path). No change when `exists` is
`true` or absent (older stored maps / degraded backend — render as today,
fail-open).

**Tests (`tests/test_filemap.py`):** root present → `exists: true`; root
removed after scan → `exists: false`; API response otherwise unchanged
(shape assertion). Scanner file untouched (I1 — the reviewer re-checks
`git diff src/lingua_viva/filemap.py` = 0).

## §C — Map freshness / staleness nudge (DEFERRED — DRAFT, not in 0.2.11)

The map is a one-shot snapshot with a "Last scanned" date and no decay
signal. Proposal for its own window, mirroring the Drive §B
metadata-vs-import split:

- In the same `filemap_get` post-processing seam as §B, add per-root
  `"changed_since_scan": <bool>` — `os.stat(root).st_mtime` (and optionally
  one level of child-dir mtimes, still stat-only) newer than the stored
  `scanned_at`. Fail-open: any stat error → field absent.
- UI: a quiet line on the root row — "Folders may have changed since your
  last scan." + **Scan folder names** reuse. No badge nag, no auto-rescan,
  no background cadence.
- Privacy class identical to the original scan (names/dates, nothing
  opened); one added sentence to the scan reassurance copy if the operator
  wants it surfaced at all.
- **Not built until ruled**: copy sign-off + whether child-dir mtimes are in
  scope (root-only mtime misses most real changes; one-level stat of already
  -mapped child folders is the honest minimum that works).

## Verification & ship path

§A+§B ride the ship prompt exactly as written:
- Phase 0 freeze (contract version stable across a 10-minute double-check;
  baseline `git status` + full suite, expected 1120 passed / 13 skipped
  post-freeze).
- Phase 1 = §A + §B + single contract bump + `check_ui_contract` +
  `check_route_reachability` + `pytest tests/test_filemap.py
  tests/test_ui_contract.py -q`.
- Phase 2 manual checklist (includes the two new items: double-click fires
  once; renamed root shows the no-longer-exists row).
- Phases 3–5 (commit window, `desktop-v0.2.11`, 7-step Definition-of-Pushed)
  are operator-gated per G1 — the word "pushed" is earned at step 7 only.

## Open questions

None for §A/§B (approved as specified). §C needs: build window assignment,
copy sign-off, and the child-mtime scope ruling.
