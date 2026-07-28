# EXECUTION PROMPT — Ship the Sources Build Across the Line (LV)

You are working in `/home/mical/learning-architecture` (Lingua Viva, public
repo). The Sources View + File Map UX build (spec:
`dev/specs/SPEC_LV_SOURCES_VIEW_FILE_MAP_UX_2026-07-27.md`) is BUILT,
independently REVIEWED (PASS 8/8 against the Post-Build Review Checklist),
and sitting UNCOMMITTED in a working tree shared with three other completed
lanes. "Across the line" means the AGENTS.md definition of PUSHED:
**downloadable and working from linguaviva.art, right now** — verified by the
7-step checklist. Nothing less counts.

Read first: `AGENTS.md`, `CLAUDE.md`, `publication-policy.md`,
`dev/BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md`.

## Hard gates (do not proceed past a gate without the operator)

- **G1 — Commits are operator-window-only.** This repo has ONE dedicated
  commit window run with the operator present. Phases 0–2 are buildable
  solo; Phase 3 onward happens only in that window.
- **G2 — RESOLVED (operator ruling 2026-07-27): Phase 1 fixes ARE folded
  into this ship.** Build items 1a and 1b; item 2 stays deferred.
- **G3 — Verbatim privacy strings are frozen.** Never edit the five strings
  in the spec's "Privacy copy is load-bearing" list.
- **G4 — `src/lingua_viva/filemap.py` stays byte-identical.** All Phase 1
  work lives in `src/web.py` and `static/index.html` only.
- **G5 — Publication policy**: no school/colleague/student names in any new
  copy or commit message.

## Phase 0 — Freeze + baseline

1. Confirm all other agent windows in this repo have STOPPED writing:
   run `python3 scripts/check_ui_contract.py`, wait 10 minutes, run again —
   the contract version must not move (it drifted v39→v44 during the review
   because lanes were still active). If it moves, stop and find the window.
2. Record baseline: `git status --porcelain > /tmp/lv_ship_baseline.txt`,
   `python3 -m pytest tests/ -q` (expected as of review: **1120 passed,
   13 skipped**; the one `test_version_bumped_exactly_one_from_live` failure
   seen mid-review was a concurrent-lane race and passes in isolation —
   after freeze it must pass in the full run too).

## Phase 1 — Pre-ship fixes (approved per G2 ruling; no commits)

From `dev/BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md`. Build items 3 and 1.
Item 2 (map staleness nudge) is **DEFERRED** — it needs its own mini-spec;
do not build it here.

### 1a. Scan-button double-fire (backlog item 3)
`scanLocalFolder()` (`static/index.html:3136`; button wired at `:2850`)
fires concurrent POSTs to `/api/filemap/scan` on double-click. Fix: disable
the scan button and show the scanning state when the request starts;
re-enable in a `finally` after settle. Client-only, two lines plus state.

### 1b. Scan-root death path (backlog item 1)
A root renamed/deleted after scanning still renders "connected" from the
stored map. Fix, stat-only, **web.py only**:
- In `filemap_get` (`src/web.py:777-782`), post-process the `to_api()`
  result: for each scanned root add `"exists": os.path.isdir(
  os.path.expanduser(<stored root path>))`. Do NOT touch `filemap.py`.
- In the Sources view root rendering: when `exists` is false, show
  "This folder no longer exists at this location." with actions
  **Choose another folder** / **Scan folder names** (reuse the existing
  friendly-error affordances). No change when `exists` is true or absent.
- Tests: extend `tests/test_filemap.py` — root present → `exists: true`;
  root removed after scan → `exists: false`; API shape otherwise unchanged.

### 1c. Contract + reachability re-sync
Bump `contracts/UI_CONTRACT.yaml` (one bump for both fixes — never
drive-by), re-run:
```bash
python3 scripts/check_ui_contract.py
python3 scripts/check_route_reachability.py
python3 -m pytest tests/test_filemap.py tests/test_ui_contract.py -q
```

## Phase 2 — Manual verification (human, app running)

These were unverifiable headlessly in review and are the only unchecked
items. Launch the desktop build (`cd desktop && npm run build && npm start`
or the packaged app) and verify each:

- [ ] Invitation state renders on empty+unskipped map; three buttons work.
- [ ] **Choose a folder** opens the native directory picker (desktop) and
      the typed-path input still works in a plain browser.
- [ ] **Use Documents/Teaching** pre-fills `~/Documents/Teaching`; if the
      folder doesn't exist, the friendly not-found error renders.
- [ ] Scan → headline sentence → Teaching materials / Private student
      folders two-section split.
- [ ] **Show names only** peek: extension chips, human sizes, relative
      dates; header copy "File names and basic details only…".
- [ ] Link file to student → "Linked to <name>. File contents were not
      read."; removal → "Link removed."
- [ ] **Reset local folder map** inline confirm with the does-not-delete
      sentence; Cancel works.
- [ ] Friendly permission error: `mkdir /tmp/lv_perm_test && chmod 000
      /tmp/lv_perm_test`, scan it → teacher-language error + collapsed raw
      details. (`chmod 755` + remove after.)
- [ ] **Skip for now** persists across app restart; "Connect a folder"
      revives the flow.
- [ ] Home nudge shows once on empty+unskipped; dismiss sets the flag;
      click routes to Sources.
- [ ] Slack status card + relocated Drive panel function in Sources;
      Settings no longer shows Curriculum folders or Drive.
- [ ] If Phase 1 ran: double-click scan fires once; a renamed root shows
      the no-longer-exists row.

Record pass/fail per item. Any FAIL → fix (respecting gates) before Phase 3.

## Phase 3 — Commit plan (operator window ONLY, gate G1)

The tree holds ~65 dirty files across four lanes plus shared hot files.
Commit lane-by-lane; shared files last. Suggested sequence (verify each
file's ownership with `git diff <file>` before staging — anything you can't
attribute, STOP and ask the operator; do not stash, revert, or "clean up"):

1. **Slack ops lane** — `src/education/{slack_ops_bot,ops_classifier,
   ops_records,daily_file}.py`, `src/lingua_viva/slack_socket.py`,
   `tests/test_slack*`, `tests/test_ops*`, `tests/test_daily_file.py`,
   Slack docs/specs.
   `feat(engine): add Slack ops assistant (Socket Mode) with daily file`
2. **Drive lane** — `src/lingua_viva/google_drive_integration.py`,
   `google_drive_oauth.py`, `tests/test_google_drive*`, Drive specs.
   `feat(engine): Drive round-trip upload/share-back + self-service OAuth`
3. **One-Button Update lane** — `src/lingua_viva/reconcile.py`,
   `tests/test_reconcile.py`, `tests/test_update_conflict_surface.py`,
   `doctor/support_loop/doctor.py` (verify hunk ownership), OBU
   spec/report/research docs.
   `feat(engine): one-button update reconcile + conflict surface`
4. **Sources/File Map lane** — `desktop/electron/{main,preload}.ts`,
   `tests/test_filemap.py`, `dev/UX_FILE_MAP_AS_IS…`, `dev/specs/SPEC_LV_
   SOURCES_VIEW…`, `dev/EXECUTION_PROMPT_LV_SOURCES_VIEW…`, backlog file.
   `feat(engine): Sources view + file map UX redesign (spec + IPC + tests)`
5. **Shared integration commit** — `static/index.html`, `src/web.py`,
   `contracts/*`, `dev/INDEX.md`, `tests/test_ui_contract.py`,
   `tests/conftest.py`, remaining attributed files (lens YAMLs,
   `student_lens.py`, `curriculum/lingua_viva_matrix.yaml`,
   `privacy_log.py`, `__init__.py` — attribute first; ethos-evidence work
   is a known candidate owner for the lens/student_lens edits).
   `feat(engine): integrate Sources view, update wiring, and UI contract vNN`

After each commit: `python3 -m pytest tests/ -q` must stay green. Never
`git add -A`. Pre-commit publication sweep on every staged diff:
`git diff --cached | grep '^+' | grep -iE '<school/colleague/student name
patterns from publication-policy.md>'` must be clean.

## Phase 4 — Release desktop-v0.2.11

This tag bundles: Sources build, One-Button Update, Drive round-trip,
Slack ops (server-side, rides along), and the DMG notarize/staple workflow
fix (already on main at `a944c3c`, rides the next tag by construction).

1. Push main: `git push origin main` (remote alias per repo config; SSH key
   `~/.ssh/lingua-viva`).
2. Run `python3 scripts/mc_push.py` — lingua-viva context is manual
   tag-cut: it rebuilds desktop, bumps `desktop/package.json`
   0.2.10→0.2.11 AND the `docs/index.html` site pins in the same commit
   (site-pin staleness trap: desktop releases are prerelease-only, so
   `/releases/latest` never serves them — pins are literal tags), tags
   `desktop-v0.2.11`, pushes, polls CI, verifies live pins + download URLs.
3. If CI fails: read the failing job log, fix forward, new tag. Never
   retag or force-push.
4. Drive env creds: being configured by the operator in parallel
   (2026-07-27). Before Phase 5 sign-off, confirm with the operator that
   creds are in place; if not yet, the panel degrades to not-connected and
   the ship may still proceed — note it in the report.

## Phase 5 — Definition-of-Pushed verification (all 7, in order)

Per `AGENTS.md`:
1. `main` local == `origin/main`.
2. Tag `desktop-v0.2.11` exists, CI run for it fully green.
3. Release assets present and signature/notarization check passes
   (this is the first tag with the DMG staple fix — verify
   `xcrun stapler validate` step succeeded in CI logs).
4. `docs/index.html` pins == `desktop-v0.2.11` on the live site (curl the
   live page, not the local file).
5. GitHub Pages deploy for the pin commit completed.
6. Download URLs return 200 (mac + win).
7. Exactly one version live — no mixed pins.

Operator-account item (cannot be done from this machine — pretendhome
token has no lingua-viva org write access): delete superseded prereleases
desktop-v0.2.7/8/9.

## Report format

Report: Phase 0 baseline vs final diff; Phase 1 built-or-skipped (with G2
ruling); Phase 2 checklist pass/fail per item; commit SHAs per lane; tag +
CI run URL; all 7 checklist outcomes with evidence (curl output, asset
list); anything deviating from this prompt, flagged not silently judged.
Only after step 7 passes may you use the word "pushed."
