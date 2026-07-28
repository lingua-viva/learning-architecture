# EXECUTION PROMPT — Live-Layer Read Path: Build SPEC_LIVE_LAYER_READ_PATH_2026-07-27

Copy everything below the line into a fresh agent window in `~/learning-architecture`.

---

You are building `dev/specs/SPEC_LIVE_LAYER_READ_PATH_2026-07-27.md` (v2, post-review
rewrite) in `~/learning-architecture` (Lingua Viva). Read that spec FIRST, in full.
Context you need but the spec doesn't carry:

This closes review finding 1 on the one-button update system
(`dev/reports/REPORT_ONE_BUTTON_UPDATE_2026-07-27.md`, esp. §8 hardening loop —
its alias-bomb and rot-unseen lessons are baked into this spec's guards). The
update system materializes teacher-editable templates into
`~/.lingua-viva/templates/` and preserves teacher edits across updates — but
nothing reads that live layer. You are adding the two readers
(`lenses/engine.py` LensEngine, `src/lingua_viva/curriculum.py`
CurriculumService) so preserved customizations actually change app behavior.
`src/lingua_viva/reconcile.py` already exists and provides `live_root()` and
`_parse_yaml_guarded()` — reuse them; do NOT duplicate path or guard logic, and
do NOT modify the reconcile/manifest machinery itself.

## Hard rules (violating any of these is a failed build)

1. **NEVER commit or push.** The operator holds the single commit window. Leave
   everything uncommitted. No `git stash`, no `git checkout --`, no reverting
   anything you didn't write.
2. **Concurrent-session hazard**: the working tree carries uncommitted work from
   several lanes (one-button update, Drive workspace, Slack ops, Sources view).
   Run `git status` at start, note what's there, touch none of it. Your diff must
   isolate cleanly (hunk-level).
3. **Privacy per `CLAUDE.md`**: no student data, no institution names.
4. **The app must NEVER write into `LV_ROOT`** (bundle/repo). This build is
   read-path only — you should be adding zero write paths anywhere.
5. **UI contract**: the restart-hint (spec §3) touches served UI → bump
   `contracts/UI_CONTRACT.yaml` per its own ceremony. It was v43 at spec time —
   **check the current version first**; three lanes moved it v40→v43 in one day
   and every lock is provisional until all lanes close. If your full-suite run
   fails ONLY on the UI-contract pin test, re-check whether another lane bumped
   the contract mid-run before assuming your change broke it.
6. **Route-reachability gate**: you should need NO new routes. If you find you
   do, stop and reconsider — the spec is deliberately reader-only.
7. **Failure direction is law**: every failure path (bad parse, guard trip,
   import failure, missing file) must land on *shipped bundle behavior*, never a
   crash, never a half-loaded engine, never a teacher file modified.

## Build order (stop-points between phases; verify each before the next)

### Phase 0 — Hermeticity FIRST (spec §4; do not skip to the fun part)

Add an autouse conftest fixture pointing `LV_UPDATE_HOME` at a per-test tmp dir.
Without it, every bare `LensEngine()` (5 existing test call sites,
`Pipeline.__init__` at `src/pipeline.py:502`) starts reading the developer's
real `~/.lingua-viva/templates/` the moment you wire the overlay — on the
operator's machine that dir will exist with real content. Constraints:
- Update-system tests (`tests/test_reconcile.py` etc.) set `LV_UPDATE_HOME` via
  their own fixtures — their override must win (monkeypatch layering: verify,
  don't assume).
- Run the full suite ONCE after this fixture alone, before any read-path change.
  It must be green — this proves the fixture is inert. Record the count.

### Phase 1 — LensEngine overlay (spec §2a, §2c)

- Bundle load exactly as today, then overlay every `*.yaml` under
  `live_root()/lenses/education/` — live wins by lens `name`, case-folded.
- Namespace guard: overlay may only shadow/add names not owned by bundle
  `core/`/`professional/` lenses. Track which names came from which subdir
  during bundle load; collisions → skip + record on the engine (e.g.
  `self.skipped_live: list[dict]` with path + reason — Doctor reads it or a
  standalone helper recomputes it; your choice, document it).
- Guarded parse for ALL live reads (`_parse_yaml_guarded` semantics: alias
  refusal + 1MB cap). Any failure → skip + record, bundle copy stands.
- Import tolerance: wrap the `from src.lingua_viva.reconcile import …` so
  ImportError → overlay silently disabled (bundle-only, today's behavior).
  Check the import direction actually works from `lenses/engine.py` in BOTH a
  source checkout and the desktop bundle layout (backend runs `python src/web.py`
  from the app root; `sys.path` gymnastics differ — test the import, don't
  assume).
- `LensEngine(explicit_dir)` (tests pass a dir): overlay OFF. Only the default
  construction gets the overlay.

### Phase 2 — CurriculumService live matrix (spec §2b)

- Default `matrix_path` → live matrix iff exists + guarded-parse passes at
  resolve time, else bundle path. Explicit `matrix_path` args unchanged.
- Per-request construction means curriculum edits apply without restart —
  verify one route end-to-end.

### Phase 3 — Doctor visibility (spec §2d)

- New check `live_templates`: WARN listing (a) live education files failing the
  guarded parse, (b) overlay files skipped by the namespace guard. Never FAIL —
  same import-tolerant skeleton as `check_updates_pending` in
  `doctor/support_loop/doctor.py:321`. Wire into `run_doctor()`.

### Phase 4 — Restart hint (spec §3)

- Template Updates panel (`static/index.html`, `renderUpdateControls()` around
  line 1870): after a successful resolve, show "Saved — restart Lingua Viva to
  use the new version." Follow the existing escapeHtml discipline (it is used
  in attribute contexts here). Bump + re-lock the UI contract with a log line.

### Phase 5 — Startup ordering (spec §5; verify, don't assume)

Establish when `LensEngine` actually constructs relative to the startup
reconcile (`_startup_state_migrations` in `src/web.py`). Grep who instantiates
`Pipeline`/the native runtime and when. If lazy/per-request → fine, say so in
the report. If import-time → document one-launch staleness as accepted (do NOT
restructure app startup to fix it; restart-to-apply already governs lenses).

## Verification bar (all of it, before you write the report)

- All 9 acceptance checks in spec §6, each as an automated test where feasible.
- Acceptance #1 as a LIVE manual proof: served app, edit a live-layer lens
  (e.g. append a `system_prompt_modifier` line), restart, show the lens output
  changed. Paste the transcript in the report. Do it under an isolated
  `LV_UPDATE_HOME=/tmp/...` — never against the operator's real
  `~/.lingua-viva` (the one-button live proof polluted real state once already).
- Overlay scan overhead: measure it (<100ms budget, spec §6.4) — the reconcile
  suite has a `test_noop_path_is_fast` pattern to copy.
- Full suite green (current baseline ≈1120 passed / 13 skipped — check first and
  record; the tree moves daily). Zero regressions in the 5 existing
  `LensEngine()` test sites and `tests/test_ethos.py` (school-ethos lens loads
  through this same engine — do not break it).
- `lv preflight` 6/6 — run it from SOURCE (`python3 -m src.lingua_viva.cli
  preflight`); the frozen `lv` binary resolves bundle-internal paths and cannot
  check the repo.
- 56+ update-system tests (`test_reconcile`, `test_reflection_log_rescue`,
  `test_update_conflict_surface`) still green — you didn't touch reconcile, so
  any failure there means your hermeticity fixture broke their env layering.

## Deliverables

1. Code + tests, uncommitted.
2. `dev/reports/REPORT_LIVE_LAYER_READ_PATH_2026-07-27.md` — what was built per
   phase, the startup-ordering answer (Phase 5), import-direction proof (Phase
   1), test counts before/after, live-proof transcript, overlay-scan timing,
   anything deferred with reason.
3. `dev/INDEX.md`: update the SPEC_LIVE_LAYER_READ_PATH row status (DRAFT →
   BUILT (uncommitted) or PARTIAL with exact phase boundary). Statuses live ONLY
   in INDEX.
4. Pre-existing bugs found adjacent to this work: fix nothing outside scope —
   log them in the report under "Found, not fixed."

## What is explicitly OUT of scope

- Any change to `reconcile.py`'s reconcile/manifest logic (adding a small pure
  helper for Doctor is fine).
- Hot-reload, lens enable/disable, a template-editor UI.
- Mission Canvas (anything under `~/fde/mission-canvas`).
- Cutting any release tag — operator only.
