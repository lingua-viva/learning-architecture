# REPORT — Live-Layer Read Path (SPEC_LIVE_LAYER_READ_PATH_2026-07-27)

**Date**: 2026-07-27 · **Status**: BUILT (uncommitted — operator's single commit window)
**Spec**: `dev/specs/SPEC_LIVE_LAYER_READ_PATH_2026-07-27.md` (v2, overlay model)
**Execution prompt**: `dev/EXECUTION_PROMPT_LIVE_LAYER_READ_PATH_2026-07-27.md`
**Closes**: review finding 1 on the one-button update system
(`REPORT_ONE_BUTTON_UPDATE_2026-07-27.md` §9.1) — the live layer at
`~/.lingua-viva/templates/` was preserved but never read.

## Summary

Two readers added, zero new routes, zero write paths, reconcile machinery
untouched. Teacher edits to live-layer education lenses and the curriculum
matrix now actually change app behavior:

- **LensEngine** (`lenses/engine.py`): bundle loads exactly as before, then
  overlays every `*.yaml` under `live_root()/lenses/education/` — live wins
  by case-folded lens `name`. Teacher-created lenses become real lenses.
- **CurriculumService** (`src/lingua_viva/curriculum.py`): default matrix
  resolves to the live copy iff it exists and passes the guarded parse at
  construction; per-request route construction means curriculum edits apply
  on the next request, no restart.
- **Doctor** (`doctor/support_loop/doctor.py`): new `live_templates` check
  (WARN, never FAIL) lists live files that failed the guarded parse and
  files skipped by the namespace guard.
- **UI** (`static/index.html`, contract v45): Template Updates take-new
  success message now carries the restart hint.

## Per-phase detail

### Phase 0 — Hermeticity (already satisfied; verified, not assumed)
The autouse `_hermetic_lv_state` fixture in `tests/conftest.py` (line 74)
already pointed `LV_UPDATE_HOME` at a per-test tmp dir before this build.
Layering verified: update-system tests' own fixtures (e.g.
`test_reconcile.py:49`) run after the autouse fixture, so their override
wins. **Baseline full suite before any read-path change: 1159 passed /
13 skipped / 0 failed (352s)** — fixture inert, tree green.

### Phase 1 — LensEngine overlay
- Overlay only on default construction; `LensEngine(explicit_dir)` keeps
  exact bundle-only behavior (tested).
- Namespace guard: bundle load records case-folded names from `core/` and
  `professional/` (`_protected_names`); overlay collisions are skipped and
  recorded in `self.skipped_live` (list of `{path, reason}` dicts).
- Shadowing is case-folded: a live lens whose name differs only in case
  replaces the bundle entry without leaving a duplicate.
- Every live parse goes through `reconcile._parse_yaml_guarded` (alias-bomb
  refusal + 1MB cap). Failure → skip + record, bundle copy stands.
- Import tolerance: the `from src.lingua_viva.reconcile import …` is
  wrapped; ImportError → overlay silently disabled (bundle-only).
- **Import-direction proof**: `src/web.py:38` inserts `LV_ROOT` into
  `sys.path` before anything imports, so wherever `lenses.engine` is
  importable, `src.lingua_viva.reconcile` resolves too. Verified live in
  the source checkout (`python3 -c` import both, OK) and by the served-app
  proof below (backend launched as `python3 -m src.web`, overlay active —
  same launch shape as the desktop bundle backend). The routes' own
  runtime imports of reconcile (web.py:628/1996+) are the standing proof
  that this import direction works in the shipped layout.
- Doctor helper: module-level `scan_live_lens_issues()` in
  `lenses/engine.py` — recomputes the skip list by constructing a default
  engine (~19ms). Chosen over reading a cached engine because Doctor runs
  out-of-process from the per-request pipeline engines.

### Phase 2 — CurriculumService live matrix
- `matrix_path` default changed to `None` → `_resolve_live_matrix()`:
  live path wins iff file exists + guarded parse yields a non-empty dict;
  the parsed data pre-populates the cache (the teacher file is never
  re-read with unguarded YAML — no TOCTOU between validation and load).
  Explicit `matrix_path` args bypass live resolution entirely.
- All existing callers construct `CurriculumService()` (default) — no
  call-site changes needed.
- End-to-end route proof (automated):
  `test_curriculum_live_edit_serves_on_next_request_via_route` — live
  matrix edited **between two requests** on the same TestClient session;
  second request serves the edit. No restart.

### Phase 3 — Doctor visibility
`check_live_templates()` clones the `check_updates_pending` import-tolerant
skeleton: lens-engine import failure → pass/skipped; scan failure → WARN;
issues → WARN listing path + reason (teacher-facing message: "customized
lens file could not be used — the shipped version is serving instead");
clean → pass. Wired into `run_doctor()` after `check_update_downgrade()`.
Live-verified through the served `/api/health` (see transcript step 6).

### Phase 4 — Restart hint + contract
Take-new success message now: *"Saved — restart Lingua Viva to use the new
version. Your old copy was archived, not deleted."* Keep-mine message
deliberately unchanged: with the overlay live, the kept copy is already
the one serving — a restart hint there would be false. Contract bumped
v44 → **v45** with log line; lock re-sealed after the edit (ceremony
order respected); pin updated; 6/6 contract tests green.
(Process note: first bump attempt double-bumped to v46 because the version
was hand-edited before running `--bump`, which auto-increments; corrected
by resetting to 44 and letting `--bump` produce the single legitimate v45.)

### Phase 5 — Startup ordering (verify, don't assume): PER-REQUEST
`LensEngine` never constructs at import time or startup. The only runtime
constructor is `Pipeline.__init__` (`src/pipeline.py:502`), reached
exclusively via `run_teacher_query` (`src/lingua_viva/app.py:22`), which
`/api/query` lazily imports **per request** (`src/web.py:2439`). Uvicorn
serves requests only after startup handlers — including
`_startup_state_migrations`' reconcile — complete. Therefore:
- **No one-launch staleness**: the first post-update query already sees the
  reconciled live layer.
- Lenses in practice reload **per query**, not per restart — the restart
  hint is conservative (a restart also works; the hint can never mislead
  into a stale state). This also makes the overlay-scan budget a per-query
  cost, which is why it was measured precisely (below).

## Verification bar

- **Overlay scan overhead**: 0.88ms for 10 live files (bundle-only 18.57ms
  vs bundle+overlay 19.45ms), plus a regression test asserting full engine
  construction < 100ms (`test_overlay_scan_overhead_under_100ms`).
- **New tests**: 26 in `tests/test_live_layer_read_path.py` covering all
  9 acceptance checks at the automated level (shadowing, new teacher lens,
  case-folded shadowing, core+professional hijack guard, corrupt /
  alias-bomb / oversize / non-mapping live files, fresh-home
  byte-identical, explicit-dir overlay-off, reconcile-import-failure
  fallback for both readers, take_new→next-construction end-to-end,
  curriculum live/corrupt/explicit/route-level, Doctor warn/pass/wiring/
  import-failure).
- **Update-system tests**: 58/58 green (test_reconcile 35,
  test_update_conflict_surface 11, test_reflection_log_rescue 12) —
  reconcile untouched, hermeticity layering intact.
- **Existing lens consumers**: test_lenses + test_ethos green (72 with the
  new file); 5 bare `LensEngine()` sites unmodified.
- **Full suite**: baseline 1159 passed / 13 skipped → post-build run
  recorded below.
- **`lv preflight` from source** (`python3 -m src.lingua_viva.cli
  preflight`): 6/6 (contract v45 sealed).

### Full-suite result (post-build)
**1260 passed / 13 skipped / 4 failed** (345s). All 4 failures are the
contract-race signature, not this build:
`test_ui_contract.py::test_ui_contract_check_passes` +
`::test_ui_contract_lock_matches_live_files` and the two
`test_lv_preflight.py` tests that embed the same contract check. Diagnosis
(execution-prompt rule 5): the Slack-ops lane sealed v46→v47 mid-run and
kept editing protected files afterward — `scripts/check_ui_contract.py` at
suite close reported `static/index.html` drifted from the v47 lock (earlier
in the window it was `src/web.py`; the pass/fail state flipped within
0.27s between two consecutive runs, proving live concurrent editing).
This build's own seal was verified green in a settled moment:
`tests/test_ui_contract.py` 6/6 with my restart-hint string present and
sealed since v45 (carried intact through the v46/v47 locks). The 4
failures will clear when the Slack lane re-seals its lock.
Note the first post-build suite attempt was killed externally at 22%
(exit 144, resource contention across concurrent lanes); the numbers
above are from the completed retry.
`lv preflight` from source at close: 4/6 — the two failures are the same
lane's in-flight work (contract drift + unregistered
`POST /api/ops/review/reclassify` in `ROUTE_REACHABILITY.yaml`), owned by
that lane.

## Live proof (acceptance #1) — served app, isolated home, transcript

Isolation: `LV_UPDATE_HOME=LV_CONFIG_HOME=/tmp/lv-livelayer-proof-1222493`
(operator's real `~/.lingua-viva` untouched by the proof environment);
`LV_REASON_TIMEOUT_SECONDS=100`; local Ollama.

1. **Launch** `python3 -m src.web 8799` under the isolated home → startup
   reconcile materialized the live layer (10 education lenses + matrix)
   into the empty proof home. `/api/health` 200.
2. **Baseline query** `POST /api/query {"query": "Tell me about planning a
   xylophone lesson for my class"}` →
   `MODEL: ollama/qwen2.5:3b`, content: *"Certainly! Let's break down the
   process of planning an xylophone lesson… ### 1. **Objective Setting**…"*
   — no marker (52s).
3. **Teacher edit** of the LIVE copy
   `$PROOF_HOME/templates/lenses/education/observation-coach.yaml`:
   added `on_signal_keywords: [xylophone]` and a `system_prompt_modifier`
   first line *"MANDATORY OUTPUT RULE: the very first line of your reply
   must be exactly this and nothing else: LIVE LAYER ACTIVE"*.
4. **Restart** the server (same isolated env).
5. **Same query** →
   `MODEL: ollama/qwen2.5:7b`, content begins:
   **`LIVE LAYER ACTIVE LENS: OBSERVATION COACH`**
   *"**Observation Scenario:** In the upcoming xylophone lesson, students
   will be introduced to basic rhythms and note reading…"*
   — the live-layer edit changed served lens behavior end-to-end.
6. **Doctor end-to-end**: dropped `broken.yaml` (`name: [unclosed`) into
   the live education dir → served `/api/health` returned
   `warn live_templates — 1 customized lens file could not be used — the
   shipped version is serving instead.`
7. Server stopped, proof home left in /tmp (disposable).

Honest notes on the proof:
- qwen2.5:**3b** ignored the marker instruction even though the marker was
  mechanically verified present in the composed system prompt (offset
  744/1204 via `apply_lenses` under the proof env) — the read path was
  already proven at that point; switching the proof-home provider config to
  qwen2.5:**7b** produced the visible first-line compliance. Model
  instruction-following, not the read path, was the variable.
- Diagnosis during the proof: the app's default
  `LV_REASON_TIMEOUT_SECONDS=20` is too short for full context-builder
  prompts on this machine's local models — every query fell back to
  `[Local reasoning … no model available]` until raised to 100. Logged
  under Found-not-fixed.
- One early proof launch (before `LV_CONFIG_HOME` was also isolated) ran
  one eval-mode query with provider/trace state resolving to the real
  `~/.lingua-viva`: appended ~1 line each to the operator's traces /
  request-outcome / privacy-event NDJSON logs. No template, lens, config,
  or session state touched; append-only observability files; left as-is
  rather than hand-editing operator logs. (The prompt's warning about
  exactly this trap was right — `LV_UPDATE_HOME` alone is not full
  isolation; both homes are isolated in the transcript above.)

## Acceptance checks (spec §6)

| # | Check | Result |
|---|-------|--------|
| 1 | Live edit → restart → behavior reflects edit | LIVE PROOF above + `test_live_edit_shadows_bundle_education_lens` |
| 2 | New teacher lens loads + applies | `test_teacher_created_lens_loads_and_activates` |
| 3 | Core/professional collision → skip + Doctor WARN | `test_core_lens_name_cannot_be_hijacked`, `test_professional_lens_name_guard_is_case_folded`, `test_doctor_live_templates_warns_never_fails_on_issues` |
| 4 | Corrupt/bomb/oversize → bundle serves, fast, WARN | corrupt/bomb/oversize/non-mapping tests + 0.88ms measured + live Doctor proof |
| 5 | Live file deleted → bundle serves | fresh-home test (§2e fallback semantics) |
| 6 | Fresh home → byte-identical behavior | `test_fresh_home_is_byte_identical_to_bundle_load` + baseline suite green pre-change |
| 7 | take_new → next launch serves it + hint shown | `test_take_new_resolution_serves_through_engine_next_construction` + v45 hint |
| 8 | Curriculum live edit next request; corrupt → bundle | route-level + corrupt-matrix tests |
| 9 | Reconcile import failure → bundle, no crash | import-failure tests for engine, curriculum, Doctor |

## Found, not fixed (out of scope)

1. **`LV_REASON_TIMEOUT_SECONDS` default (20s) starves real local queries**:
   with the full context-builder prompt, qwen2.5:3b/7b on this machine takes
   30–80s; every `/api/query` silently degrades to the
   `[Local reasoning … no model available]` placeholder. The route's own
   `timeout_seconds` budget (25s default) compounds this. Teachers on
   modest hardware may be seeing placeholders for every Ask. Candidate:
   raise the default, or adaptive timeout, or surface "model still
   thinking" honestly instead of the placeholder.
2. **Model-resolution tier 3 beats the documented dev override**: the
   ontology's `classification.default_model` (tier 3) shadows
   `LV_REASON_MODEL` (tier 4) whenever the node names any default, making
   the env var nearly dead in practice. Docstring in
   `src/lingua_viva/reasoning.py:41-46` presents this order as deliberate,
   so not touched — but as a *dev/test seam* the env var arguably belongs
   above tier 3.
3. **Composed lens prompts can conflict**: core `reflection` and the
   shadowed `observation-coach` both issued output-format contracts; the
   3b model followed whichever sat lower in the stack. Not a read-path
   defect (composition order is pre-existing `apply_lenses` behavior), but
   lens-contract collisions will confuse small models. Candidate: lens
   priority field or single-active-format rule.
4. (Carried from parent report) `pyproject.toml` vs `__init__.__version__`
   release-sync check still missing; `MANIFEST.yaml` version still stale
   at 1.0.3.

## Out of scope — respected
No reconcile/manifest changes (only a consumer of its public seams), no
hot-reload feature, no lens enable/disable, no Mission Canvas, no release
tag, no commits (operator's single commit window), no new routes.
