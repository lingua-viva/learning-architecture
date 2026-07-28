# EXECUTION PROMPT — File Map Final: §A + §B Pre-Ship Fixes (LV)

You are the builder in `/home/mical/learning-architecture` (Lingua Viva,
public repo). Build **§A and §B only** of
`dev/specs/SPEC_LV_FILE_MAP_FINAL_2026-07-27.md` (APPROVED per the G2
ruling). §C (freshness) is DEFERRED — do not build it, do not "while I'm
here" it. This work is Phase 1 of
`dev/EXECUTION_PROMPT_LV_SOURCES_SHIP_2026-07-27.md`; Phases 3+ (commits,
release) remain operator-window-only.

Read first if not already in context: the spec above, `AGENTS.md`,
`publication-policy.md`, `dev/BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md`.

## Gate 0 — Freeze (BLOCKING; known-unmet as of writing)

At 20:35:40 the contract checked OK at v44; at **20:38:02 it FAILED** —
`static/index.html` drifted from the v44 lock (locked `8745c563…`, actual
`f8f81e35…`). Another window was still writing.

Do NOT start until ALL of:
1. Operator confirms every other window (Drive, Slack ops, One-Button
   Update) has stopped.
2. The drifted index.html edits are claimed: the owning lane takes its own
   re-seal bump (v45), OR the operator rules them abandoned. **Never bump
   over unclaimed drift** — that is the v38 trap and it already happened
   once today.
3. `python3 scripts/check_ui_contract.py` passes twice, ≥10 minutes apart,
   same version both times.
4. Record baseline: `git status --porcelain > /tmp/lv_fmfinal_baseline.txt`
   and `python3 -m pytest tests/test_filemap.py tests/test_ui_contract.py -q`
   (full-suite baseline already exists from the ship prompt's Phase 0 —
   don't re-run 11 minutes of tests for a 2-file fix; the ship window owns
   the full-suite gate).

## Invariants (violating any fails the build)

- `src/lingua_viva/filemap.py` **byte-identical** (`git diff` on it = 0
  lines at report time).
- The five verbatim privacy strings untouched.
- No new routes; reachability checker stays green with **zero** YAML edits
  (nothing here adds call sites).
- Stat-only: nothing opens or reads file contents.
- **One** contract bump for §A+§B together, taken only after Gate 0.
- No school/colleague/student names anywhere.
- Do not touch other lanes' files. Do not commit, stage, stash, or revert
  anything.

## §A — Scan-button double-fire (static/index.html only)

In `scanLocalFolder()` (~:3136 at v44 — re-locate by searching
`async function scanLocalFolder`, line numbers will have drifted):
1. First statement after the empty-path early-return: look up the scan
   button (it lives in the same form markup as `#filemap-path`; give it
   `id="filemap-scan-btn"` in `localFolderScanForm()` if it doesn't have
   one) and set `disabled = true`.
2. Wrap the existing `try { await api(...) }`/`catch` in `finally`:
   re-enable the button. Success path re-renders the whole section (button
   is rebuilt enabled), so the `finally` matters for the error path — keep
   it anyway for both.
3. No copy changes. Keep the existing "scanning folder names..." badge.

## §B — Scan-root death path (src/web.py + static/index.html)

Backend — `filemap_get` (`src/web.py` ~:777–782, re-locate by route):
1. Post-process the `to_api()` dict before returning: for each entry in the
   scanned-roots list, add
   `"exists": os.path.isdir(os.path.expanduser(<stored root path>))`.
   Stored paths are `~`-substituted — `expanduser` is mandatory. Check the
   actual key name for roots in `to_api()` output before writing code; do
   not guess.
2. Touch nothing else in the response. `os` and the error-code helper are
   already imported/nearby.

UI — scanned-roots rendering inside `renderLocalFoldersSection()`:
3. Where root rows render: if `root.exists === false`, add to that row the
   line **"This folder no longer exists at this location."** plus two
   buttons reusing existing affordances: **Choose another folder** →
   `chooseLocalFolder()`; **Scan folder names** → focus/scroll to the scan
   form (pre-fill the input with the dead root's path so one click rescans
   or replaces it).
4. `exists === true` or `exists` absent → render exactly as today
   (fail-open for old maps/degraded backend).

Tests — `tests/test_filemap.py` (append; follow the existing API-test
style with the app client + tmp map):
5. Root present after scan → response root entry has `exists: true`.
6. Root directory removed (`shutil.rmtree`) after scan → `exists: false`.
7. Response shape otherwise unchanged (assert the pre-existing keys
   survive on the same entry).

## Ceremony (after §A+§B, one pass)

```bash
python3 scripts/check_ui_contract.py --bump   # expect v(N+1) over the settled tree
# add bump-log line to contracts/UI_CONTRACT.yaml + tests/test_ui_contract.py,
# update EXPECTED_VERSION — same commit-unit as the bump, per file header rules
python3 scripts/check_ui_contract.py
python3 scripts/check_route_reachability.py
python3 -m pytest tests/test_filemap.py tests/test_ui_contract.py -q
node --check on the extracted inline <script>   # same method as the v39 build
git diff src/lingua_viva/filemap.py             # must be empty
git status --porcelain | diff /tmp/lv_fmfinal_baseline.txt -   # only intended deltas
```

## Report format

Report: Gate-0 evidence (two timestamped contract checks + who claimed the
drift); files changed with one-liners; test counts before/after; each
ceremony command's output; the new contract version; any deviation from
this prompt or the spec, flagged explicitly — including anything you could
not verify headlessly (the double-click and dead-root rows go to the ship
prompt's Phase 2 manual checklist, items already listed there). Do not use
the word "done" for anything beyond Phase 1 — the ship prompt owns
"pushed."
