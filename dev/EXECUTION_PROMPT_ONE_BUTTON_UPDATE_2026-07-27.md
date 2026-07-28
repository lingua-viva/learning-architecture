# EXECUTION PROMPT — One-Button Update: Build SPEC_ONE_BUTTON_UPDATE_2026-07-27

Copy everything below the line into a fresh agent window in `~/learning-architecture`.

---

You are building `dev/specs/SPEC_ONE_BUTTON_UPDATE_2026-07-27.md` in `~/learning-architecture` (Lingua Viva). Read that spec FIRST, in full, plus its research grounding `dev/RESEARCH_UPDATE_PRESERVATION_2026-07-27.md` (top-10 pitfalls section is your failure-mode checklist). This prompt adds build order, guardrails, and session context the spec doesn't carry.

## Hard rules (violating any of these is a failed build)

1. **NEVER commit or push.** The operator holds the single commit window for this repo. Leave all work uncommitted. Do not `git stash`, `git checkout --`, or revert ANYTHING you didn't write.
2. **Concurrent-session hazard**: the working tree already contains uncommitted work from parallel lanes — at minimum `docs/index.html` (SmartScreen note), `.github/workflows/desktop-release.yml` (DMG staple), possibly Drive round-trip and school-ethos files. Run `git status` at start, note what's there, touch none of it. Your diff must be isolatable from theirs.
3. **Privacy rules per `CLAUDE.md`**: no student data, no institution names, honest maturity labels.
4. **Route-reachability gate**: any new `src/web.py` route must either have a verified UI call site or be classified in `contracts/ROUTE_REACHABILITY.yaml` with a reason. `lv preflight` enforces this (check #6).
5. **UI contract**: if you touch served UI, bump `contracts/UI_CONTRACT.yaml` per its own conventions (it was at v34 as of 2026-07-27 — check current).
6. **The app must NEVER write into `LV_ROOT`** (the bundle/repo). Everything mutable goes through `lv_home()` (`src/lingua_viva/config.py`). You are building the system that enforces this; do not add new violations while doing it.

## Build order (stop-points between phases; verify each before the next)

### P0 — Reflection-log rescue (do this first; it must be shippable even if you build nothing else)
- `src/web.py:332` `_revision_log_path()`: default → `lv_home() / "dev" / "lv_revision_log.ndjson"`. Keep the `LV_REVISION_LOG_PATH` env override exactly as-is.
- One-time idempotent migration at backend startup: if legacy `LV_ROOT/dev/lv_revision_log.ndjson` exists and is readable, append its entries to the new path exactly once (sentinel or in-file marker; document your choice). Never write the legacy path again. Teachers on desktop 0.2.9/0.2.10 may already have reflections there — this migration is the only rescue window.
- Tests: desktop-mode (`LV_DESKTOP=1`) reflection POST writes only under `lv_home()`; migration idempotent (run twice, no duplicates); legacy-absent case clean.

### Phase 1 — Manifest + seed/live layers (`src/lingua_viva/reconcile.py`, NEW — sole manifest writer)
- Manifest at `~/.lingua-viva/update_manifest.json`: per managed artifact {relative path, canonicalized-content hash as shipped, shipped-in version, schema_version}; plus `last_run_engine_version`; plus tombstone/`renamed_from` list (empty for now — the mechanism must exist).
- **Managed set is a deliberate decision, not "everything"**: manage only teacher-editable artifact classes (start: `lenses/education/`, `curriculum/` templates). Engine-owned data (`ontology/`, `knowledge/`, `src/`) stays bundle-only — updated wholesale with the app, never materialized. Document the managed-set choice and its rationale in the report; it must be trivially extensible.
- Hashing: parse YAML → canonical dump → hash; raw-bytes fallback for non-parseable files. Add a test that reformatting (key reorder, trailing newline) does NOT change the hash. This kills pitfall #1.
- Materialization target: `~/.lingua-viva/templates/<relative path>`.

### Phase 2 — First-launch reconcile
- Trigger: current app version ≠ manifest `last_run_engine_version`, or manifest absent (fresh install → materialize all + write manifest).
- Per-artifact three-way classification and actions exactly per spec §3 table. Unmodified upgrades: temp-file → fsync → atomic rename. Modified: user file untouched byte-for-byte; new version staged under `~/.lingua-viva/updates-pending/<path>`; pending entry recorded. User-deleted: not resurrected. Unknown files: never touched — assert this in tests with a decoy user file in the managed dir.
- Symlink in live layer → classify as modified, never touch. Case-folded path comparisons.
- Manifest write is the LAST operation. Kill-mid-reconcile test: interrupt after some files, re-run, converges cleanly with no half-written artifact (temp+rename makes this provable).
- Wire into backend startup (`src/web.py` lifespan or equivalent) so it runs identically for desktop, CLI serve, and source installs. Must be fast (<100ms no-op path) — it runs every launch.

### Phase 3 — Conflict surface
- `lv doctor` + `/api/health`: new `updates_pending` item — count + artifact list, WARN (never FAIL) when nonzero. Message shape: "N template updates waiting — your customized versions were preserved."
- Minimal UI (Settings area): list pending artifacts with [Keep mine] [Take new] [View diff]. "Take new" archives the user's version to `~/.lingua-viva/archive/<path>.<ISO-date>` BEFORE replacing — nothing is ever destroyed. Respect rules 4+5 (route gate, UI contract).

### Phase 4 — Namespacing + schema versioning + downgrade guard
- Reserved shipped-ID namespace (`lv-`/`LV-` prefix): enforce at user-artifact **creation time** in whatever write paths create named artifacts (survey them; document which you gated).
- `schema_version` in managed shipped artifacts (add field, default 1); reconcile records it; a stub migration-runner hook keyed on version (identity migration for now — the seam is the deliverable, per HA `_async_migrate_func` pattern).
- Downgrade guard: if `last_run_engine_version` > current version → health WARN, reconcile does not write artifacts (read-only pass). Firefox-model, warn-not-block for now.

## Verification bar (all of it, before you write the report)

- All 8 acceptance checks in spec §5, each as an automated test where feasible (the kill-9 one may be a simulated-interrupt test).
- Full suite green, zero regressions (baseline was 859 passed as of 2026-07-27 — check current first and record it).
- `lv preflight` all checks pass.
- Live manual proof: run the served app, edit a managed template, bump a fake "shipped" version in a temp seed dir, trigger reconcile, show the edit survived and the pending update surfaced. Paste the transcript in the report.

## Deliverables

1. Code + tests, uncommitted.
2. `dev/reports/REPORT_ONE_BUTTON_UPDATE_2026-07-27.md` — what was built per phase, managed-set rationale, test counts before/after, live-proof transcript, anything deferred with reason.
3. `dev/INDEX.md`: update the SPEC_ONE_BUTTON_UPDATE row status (DRAFT → BUILT (uncommitted) or PARTIAL with exact phase boundary) in the same change-set. Statuses live ONLY in INDEX.
4. If you find pre-existing bugs adjacent to this work (pattern: this repo's audits usually do), fix nothing outside scope — log them in the report under "Found, not fixed."

## What is explicitly OUT of scope
- Mission Canvas (anything under `~/fde/mission-canvas`) — LV validates first.
- electron-updater/auto-update, delta downloads, Intel-Mac/universal build, Windows signing.
- The `desktop-v0.2.11` release itself — operator cuts tags.
