# Build Report — One-Button Install-or-Update With User-Work Preservation

**Spec:** `dev/specs/SPEC_ONE_BUTTON_UPDATE_2026-07-27.md`
**Prompt:** `dev/EXECUTION_PROMPT_ONE_BUTTON_UPDATE_2026-07-27.md`
**Date:** 2026-07-27 (build ran into early 2026-07-28 local)
**Status:** BUILT — all phases (P0 + 1-4), uncommitted per the single-commit-window rule.

---

## 1. What was built, per phase

### P0 — Reflection-log rescue (independently shippable)

The teacher's private reflections were written to `LV_ROOT/dev/lv_revision_log.ndjson`
— *inside the app bundle*, erased wholesale on every desktop update
(electron-builder replaces `extraResources` in place, issue #4501).

- `src/web.py` `_revision_log_path()` now resolves to
  `lv_home()/dev/lv_revision_log.ndjson` (`LV_REVISION_LOG_PATH` env override).
- One-time legacy migration on startup (`_migrate_legacy_revision_log()`):
  copies **only teacher reflections** (`private: true` /
  `artifact_id == "lv-private-teacher-reflection"`) out of the bundle path —
  the committed repo copy is a dev audit trail Doctor validates, and source
  installs must not pollute the teacher's file with repo history.
- Two-layer idempotency: a `.migrated` sentinel short-circuits re-runs, and
  `revision_id` dedupe makes a crash between append and sentinel-write safe.
  Unreadable legacy → skip *without* sentinel (retried next launch). The
  legacy file is never written to.
- Startup wiring: `app.add_event_handler("startup", _startup_state_migrations)`
  — runs for desktop, `lv serve`, and source installs identically.

### Phase 1 — Manifest + seed/live layers (`src/lingua_viva/reconcile.py`, new)

- **Managed set (deliberate, not "everything"):** `lenses/education/` +
  `curriculum/` only. `ontology/`, `knowledge/`, `src/` stay engine-owned —
  they are code/reference the app must be able to replace wholesale;
  teachers customize lenses and curriculum, so only those are materialized
  into a live layer. `.py` files under managed dirs are excluded (engine
  code even if co-located).
- **Seed layer** = read-only bundle/checkout (`LV_SEED_ROOT` seam).
  **Live layer** = `~/.lingua-viva/templates/` (`LV_UPDATE_HOME` seam).
- **Canonicalized-content hashing:** YAML parse → sorted-key JSON → sha256,
  raw-bytes fallback. Fallback errs in the safe direction (false "modified"
  keeps a file; false "unmodified" would destroy one).
- `update_manifest.json` under `lv_home()`: `{hash, shipped_in,
  schema_version}` per artifact + `pending` + `tombstones` + `renamed_from`
  + `last_run_engine_version`. **Sole writer** is `_write_manifest()`; all
  writes temp+fsync+rename atomic.
- Engine version chain: `LV_ENGINE_VERSION` → `pyproject.toml` →
  `src.lingua_viva.__version__` (desktop bundles ship no pyproject —
  `__version__` synced 0.1.0 → 1.0.6, see §5).

### Phase 2 — First-launch reconcile

- `reconcile()`: fresh install → materialize + write manifest; same-version
  → fast no-op (<100ms, tested); downgrade → read-only report, **no writes**;
  else full three-way pass with the manifest written **last**
  (OSTree single-commit-point — a kill at any moment leaves the previous
  consistent state, proven by the kill-mid-reconcile test).
- Classification per spec §3: unmodified → silent upgrade; modified → keep
  the teacher's file byte-identical, stage new version under
  `updates-pending/`; deleted → not resurrected; unknown/user-created →
  never touched (case-folded collision check); symlinks → never touched.
- `reconcile_on_startup()` never raises — startup can't take the app down.

### Phase 3 — Conflict surface

- **Doctor:** `check_updates_pending()` — WARN
  "N template update(s) waiting — your customized versions were preserved."
  (never FAIL: preserved work is working-as-designed; the pacdiff lesson is
  that parked updates must be *visible*, and `check_update_downgrade()`
  (Firefox-model WARN). Both wired into `run_doctor()`.
- **Routes** (all three classified in `contracts/ROUTE_REACHABILITY.yaml`
  with UI call-site literals): `GET /api/updates/pending`,
  `GET /api/updates/diff?path=…`, `POST /api/updates/resolve`.
- **Settings UI:** "Template Updates" panel — per-file
  [Keep mine] [Take new] [View diff]. `keep_mine` adopts the new hash into
  the manifest (stops re-asking for this ship, re-asks on the next);
  `take_new` archives the teacher's copy to
  `~/.lingua-viva/archive/<path>.<ISO-date>` **before** replacing — nothing
  is ever destroyed.

### Phase 4 — Namespacing, schema versioning, downgrade guard

- `schema_version: 1` appended (text-append, no YAML re-dump — hashes of
  meaning-equivalent files stay stable) to all 10 `lenses/education/*.yaml`
  + `curriculum/lingua_viva_matrix.yaml`. Repo-level test enforces presence.
- **Creation-time namespace gate:** `validate_user_artifact_id()` rejects
  the reserved `lv-` prefix, case-folded (Anki lesson: solve collisions by
  construction). Write-path survey (§4) found exactly one caller-supplied
  artifact-ID path; it is now gated.
- **Migration runner:** `SCHEMA_MIGRATIONS` hook table +
  `_migrate_user_copy()` runs registered hooks stepwise on **user-owned live
  copies only** (shipped seeds migrate at build time). Identity today — the
  seam is the deliverable; proven by a test that registers a fake 1→2 hook.
- **Downgrade guard:** `downgrade_detected()` from the manifest's
  `last_run_engine_version` stamp; reconcile refuses to write; Doctor WARNs;
  `/api/updates/pending` surfaces it. (Accidentally proven live — see §6.)

## 2. Artifact-creation write-path survey (Phase 4 gate)

| Path | Caller-supplied ID? | Gated? |
|---|---|---|
| `StudentLensStore.create_lens(student_id=…)` (`src/education/student_lens.py`) | Yes — the only one | **Yes** — `validate_user_artifact_id`, raises `ObservationValidationError` |
| `POST /api/students` → `create_lens()` | No (uuid4 generated) | Safe by construction; transitively gated |
| `CAND-*` candidate files | System-generated prefix | No gate needed |
| Drive folder connect (`POST /api/google-drive/folders`) | Folder display name — external-system namespace, not a managed artifact ID | No gate needed |
| Reflection log `artifact_id` | Fixed system constant (`lv-private-teacher-reflection` — correctly lv-namespaced, it IS shipped) | No gate needed |

## 3. Tests

**44 new tests, all passing:**

- `tests/test_reflection_log_rescue.py` (8) — P0: default path under
  `lv_home()`, desktop POST never writes the bundle (byte-identical check),
  migration filters to teacher reflections only, sentinel idempotency,
  crash-retry dedupe, legacy never written, startup wiring.
- `tests/test_reconcile.py` (25) — incl. the **mandated reformat
  regression test** (key reorder + quoting + trailing-newline must NOT
  change the hash — pitfall #1: a reformat flipping hashes makes every
  pristine file read as "modified" and auto-update silently dies), <100ms
  no-op perf, kill-mid-reconcile convergence, downgrade read-only, unknown
  file/decoy/symlink rules, deletion not resurrected, collision both-survive,
  tombstone/rename mechanisms, schema-migration runner, creation-time gate,
  startup reconcile via TestClient.
- `tests/test_update_conflict_surface.py` (11) — Doctor WARN shape
  (warn-never-fail, checks actually registered in `run_doctor`), the three
  routes incl. take_new-archives-first and 400-input rejection.

**Suite:** **1079 passed / 13 skipped / 0 failed** (final run, 13m04s,
tree settled). Baseline at build start was 876 passed / 13 skipped /
8 failed (all 8 mid-flight-state: stale UI-contract lock +
route-reachability + preflight downstream + 3 concurrent-lane UI tests —
every one resolved by the responsible lane before close). The prompt's
"859 green" baseline was already stale when the build started; three
concurrent lanes kept adding tests throughout (876 → 990 → 1057 → 1079
observed across the build's four suite runs).

**Gates:** `lv preflight` 6/6 (ui_contract, golden_parses, imports,
ontology 111, no_conflicts, route_reachability). UI contract re-locked
**after** all UI changes — v34 → **v35** is this lane's bump (log line +
pinned test value updated per the ceremony). Concurrent lanes then carried
the lock to v36 (Drive workspace), v37 (Slack ops), v38 (their re-seal),
v39 (Sources view) — each with its own log line; final state v39,
pin 39, `check_ui_contract.py` OK.

### Spec §5 acceptance checks → covering tests

| # | Check | Test |
|---|---|---|
| 1 | Fresh install materializes; second launch no-ops | `test_fresh_install_materializes_and_second_run_noops`, `test_noop_path_is_fast` |
| 2 | Zero-edit update upgrades all, zero pending | `test_update_zero_edits_upgrades_all_zero_pending` |
| 3 | Edit preserved byte-identical + pending + health WARN | `test_user_edit_preserved_byte_identical_and_pending_staged` + `test_doctor_warns_on_pending_never_fails` |
| 4 | Deleted template not resurrected | `test_user_deleted_template_not_resurrected` |
| 5 | Collision both-survive; `lv-` rejected at creation | `test_new_shipped_artifact_colliding_with_user_file_both_survive`, `test_reserved_prefix_rejected_at_creation_time`, `test_create_lens_rejects_reserved_prefix` |
| 6 | Kill mid-reconcile → clean relaunch | `test_kill_mid_reconcile_rerun_converges` |
| 7 | Desktop reflection POST writes only lv_home; migration idempotent | `test_reflection_log_rescue.py` (all 8) |
| 8 | Downgrade → warn, no writes | `test_downgrade_is_read_only`, `test_doctor_warns_on_downgrade` |

## 4. Live manual proof (transcript, required by the prompt)

Real served app, repo checkout as seed, isolated `LV_UPDATE_HOME=/tmp/lv-live-proof`.

```
# 1. Boot v1.0.6 → fresh install materializes the live layer
$ LV_UPDATE_HOME=/tmp/lv-live-proof LV_ENGINE_VERSION=1.0.6 uvicorn src.web:app --port 8899
$ curl -s :8899/api/updates/pending
{"pending":[],"downgrade":null,"message":"Your customized versions were preserved."}

# 2. Teacher edits a managed template
$ echo "teacher_note: my grade-3 adaptation, do not lose" >> …/templates/lenses/education/observation-coach.yaml
$ md5sum …/observation-coach.yaml
d6bd67d1455046f4715953f57bdf06d7

# 3. Fake update: seed copied, shipped change added, engine 1.0.7 → reboot
$ LV_SEED_ROOT=/tmp/lv-fake-seed LV_ENGINE_VERSION=1.0.7 uvicorn src.web:app --port 8899
$ curl -s :8899/api/updates/pending
{"pending":[{"path":"lenses/education/observation-coach.yaml","shipped_in":"1.0.7",
  "staged_available":true}],"downgrade":null,…}

# 4. THE CHECK — the teacher's edit survived byte-identical
$ md5sum …/observation-coach.yaml
d6bd67d1455046f4715953f57bdf06d7        # same hash as before the update

# 5. Diff shows both sides
$ curl -s ":8899/api/updates/diff?path=lenses/education/observation-coach.yaml"
--- yours/lenses/education/observation-coach.yaml
+++ update/lenses/education/observation-coach.yaml
 confidence_adjustment: 0.0
+observation_prompt_v2: richer sentence starters shipped in 1.0.7
 schema_version: 1
-teacher_note: my grade-3 adaptation, do not lose

# 6. take_new archives BEFORE replacing
$ curl -s -X POST :8899/api/updates/resolve -d '{"path":"…","action":"take_new"}'
{"status":"resolved","action":"take_new",
 "archived_to":"/tmp/lv-live-proof/archive/lenses/education/observation-coach.yaml.2026-07-28"}
$ grep teacher_note /tmp/lv-live-proof/archive/lenses/education/*
teacher_note: my grade-3 adaptation, do not lose      # nothing destroyed
$ curl -s :8899/api/updates/pending
{"pending":[],…}
```

**Bonus live proof of the downgrade guard** (unplanned): a port collision
left the 1.0.6 server running after the 1.0.7 process had run its startup
reconcile (uvicorn runs lifespan before bind) and written
`last_run_engine_version: 1.0.7`. The still-running 1.0.6 server then
correctly reported
`"downgrade":{"last_run_engine_version":"1.0.7","engine_version":"1.0.6"}`
— exactly the Firefox-model behavior, observed live across two real
processes rather than simulated.

## 5. Adjacent findings — FOUND, NOT FIXED (and one sync fix)

1. **`src/lingua_viva/__init__.py` `__version__` was stale at 0.1.0**
   (pyproject says 1.0.6). *Synced to 1.0.6 in this build* because it is the
   desktop bundle's engine-version fallback — a stale value there means
   updates never reconcile. **Process gap remains open:** nothing keeps
   `pyproject.toml` and `__version__` in sync at release time; a stale bump
   would silently kill future reconciles. Candidate: a preflight check or
   release-workflow assert.
2. **`MANIFEST.yaml` version is stale at 1.0.3** (CLI shipped v1.0.6). Not
   touched — not used by the update path (deliberately: it isn't shipped in
   the desktop bundle either), but it will confuse the next person who
   greps for a version source.
3. **Concurrent-lane stale tests** (their uncommitted mid-flight work, not
   touched per the isolation rule): during the build,
   `test_ui_contract.py::test_sidebar_nav_contract_counts_and_handlers`,
   `test_teacher_ui_phase2.py::test_teacher_sidebar_contract` and
   `test_google_drive_app_integration.py::test_settings_ui_mounts_google_drive_controls`
   failed against the Drive-workspace lane's in-flight UI moves. All were
   fixed by those lanes themselves before this build closed (verified
   passing at final check). Left here as a record of what the interim
   suite failures were.
4. **`GET /api/session` route** reports permanently-inactive state on every
   real install (already classified `permanent` in ROUTE_REACHABILITY with
   its own spec) — noted only because the update panel now sits near it in
   Settings; no action.

## 6. Concurrent-session isolation

Three other lanes were active in this working tree during the build (Drive
workspace, Slack ops bot, Sources-view/File-Map UX). Verified before every
edit that my hunks isolate cleanly (`git diff` hunk inspection); their
edits to `tests/conftest.py` (LV_OPS_* env),
`contracts/ROUTE_REACHABILITY.yaml` (drive-folders entries), and
`contracts/UI_CONTRACT.yaml` (v36-v39 re-locks) were left untouched.
The Sources-view lane's Settings refactor (v39) landed *around* my
Template Updates panel mid-build — verified afterward that the panel, its
`renderUpdateControls()` wiring, and all three call-site literals survived
intact. Nothing was committed, stashed, or reverted.

## 7. Deferred / out of scope (per spec §4)

- Mission Canvas port (waits for ≥2 weeks LV production validation).
- electron-updater background auto-update (the button is the trigger;
  the userData-side manifest is updater-agnostic).
- Delta downloads; Intel-Mac build; Windows signing.
- Cutting desktop-v0.2.11 (operator: P0 + DMG-staple + Drive round-trip
  can ride one tag).
- `SHIPPED_TOMBSTONES` / `SHIPPED_RENAMES` are empty seams (mechanism
  tested, no shipped deletions/renames exist yet).
- Ethos taxonomy (`~/.lingua-viva/ethos.yaml`) is already user-owned
  outside the managed set — no reconcile interaction.

## 8. Hardening — 15-iteration adversarial loop (same day, post-build)

Method per iteration: probe first (live measurement, not inspection),
fix only measured real defects, add a pinning regression test, re-run.
All fixes in `src/lingua_viva/reconcile.py` + `src/web.py` (P0
migration); tests in `tests/test_reconcile.py` (25→35),
`tests/test_reflection_log_rescue.py` (8→10). Conflict-surface suite
(11) untouched and green throughout.

| # | Probe | Verdict | Fix |
|---|-------|---------|-----|
| 1 | 419-byte YAML alias bomb (billion laughs) into `canonical_hash` | **DEFECT (P1)** — parse hung >15s; startup reconcile parses teacher-writable files → app hangs forever on boot | `_NoAliasLoader` (SafeLoader that refuses `AliasEvent`) + 1MB parse cap; guard trips fall back to raw-bytes hash (safe direction: false "modified" preserves). `_migrate_user_copy` switched to the guarded parser too |
| 2 | Non-OSError (`ValueError`) raised for one artifact mid-pass | **DEFECT (P1)** — per-artifact catch was `OSError`-only; one bad artifact aborted the whole pass — zero files materialized on fresh install, no manifest | Broadened to `except Exception` (docstring already promised it); `KeyboardInterrupt` still propagates (kill-mid-reconcile test unchanged) |
| 3 | Hand-poisoned manifest pending rel `../OUTSIDE.txt` → take_new | **DEFECT** — write escaped `live_root()` (one level up; `../../` escapes update_home) while reporting "resolved" | `_is_safe_rel()` (no `..`/absolute/backslash + must sit under a managed prefix) enforced in `list_pending`/`pending_diff`/`resolve_pending` |
| 4 | Corrupt manifest shapes: non-dict pending entries, string-valued pending map | **DEFECT** — `AttributeError` → route 500 (Settings panel dead); `pending_count()` on `"corrupt"` returned 7 → Doctor warned "7 updates waiting" | `_pending_map()` tolerant accessor — corrupt shapes degrade to "nothing pending" |
| 5 | take_new when the live path is a teacher's symlink | **DEFECT** — silently replaced the symlink with a regular file, breaking the reconcile-side "symlinks never touched" promise | take_new now refuses with a teacher-facing error; keep_mine still works |
| 6 | Unreadable staged/live file during take_new (chmod 000) | **DEFECT** — `PermissionError` → route 500 | File-op block wrapped → error dict; pending entry kept so retry works (proven in test) |
| 7 | Legacy reflection log: intra-file duplicate revision_id; non-UTF8 bytes | **2 DEFECTS** — same-file duplicate migrated twice (`existing_ids` never updated during the run); `UnicodeDecodeError` past the `OSError` catch | Dedupe set updated per-append; `UnicodeDecodeError` added to the unreadable-legacy retry branch (sentinel stays unwritten) |
| 8 | Sentinel `_finish()` crash window (plain write_text, not atomic) | no defect — sentinel is written after appends are durable; partial sentinel only mis-reports the count; legacy file remains as source | — |
| 9 | `escapeHtml` in attribute context (`data-path="…"`) | no defect — escapes `"` and `'` | — |
| 10 | 39MB live file at a managed path → `pending_diff` | **DEFECT** — 41MB diff string into JSON + browser DOM (Settings hang); compute time itself fine (0.45s) | Response capped at 200KB with truncation notice; files untouched |
| 11 | `_version_tuple` odd inputs ("v1.0.7", "", "abc", "1.0.6-beta") | **DEFECT** — `v1.0.7` → `(0,0,7)`: a v-prefixed engine version trips the downgrade guard and silently disables reconcile forever (the exact silent-kill class §5 warns about) | Strip leading `v`/`V`; other odd shapes already degraded safely (pinned in test) |
| 12 | 4-way concurrent reconcile race (fresh install + update with a teacher edit) | no defect — all files land, no temp droppings, teacher edit survives, exactly one pending, post-race run is a fast no-op | — |
| 13 | Manifest deleted (partial backup restore) then relaunch | no defect — fresh-install pass preserves the edit + parks the new ship, re-adopts pristine files; pinned with a regression test | — |
| 14 | Doctor checks vs corrupt manifest JSON / chmod-000 update_home | no defect — never crash, degrade to pass; corrupt manifest self-heals next launch (iteration 13) with edits preserved | — |
| 15 | Full-suite + preflight re-verification | close-out | Full suite 1116 passed / 13 skipped / 1 failed — the single failure was `test_ui_contract` collected with a pre-v41 pin while three lanes' contract bumps (v40 Drive, v41 mine, v42 Slack-ops) landed mid-run; green on the settled tree (62/62 across contract + all three update-system suites). `lv preflight` 6/6 (source checkout; the frozen `lv` binary resolves bundle-internal paths and can't run repo checks). Iteration-7 web.py fixes sealed as deliberate contract bump v41 |

Score: 10 real defects fixed across 8 fixing iterations, 4 probes clean,
12 new regression tests. Every fix errs toward preservation — no failure
path can destroy a teacher file.

Contract-ceremony note (recurring trap, third occurrence today): v40
(Drive lane) sealed this lane's in-flight web.py edits and left the test
pin stale at 39; v41 (this lane) made the change deliberate and fixed
the pin; v42 (Slack-ops lane) then sealed over v41 the same way and
fixed its own pin. The MC v27/v28 trap generalizes: with N concurrent
lanes, every lock is provisional until all lanes close.

## 9. Independent review response (same day)

Review verdict: solid build, hardening confirmed 56/56 independently;
three findings. All three verified true, actions taken:

1. **Live layer never read (MAJOR, spec gap)** — confirmed: only
   `reconcile.py` references `~/.lingua-viva/templates/`; `LensEngine`
   (`lenses/engine.py:83`) and `CurriculumService`
   (`src/lingua_viva/curriculum.py:11`) read the bundle. Preserved
   working copies are currently inert. Next spec drafted:
   `dev/specs/SPEC_LIVE_LAYER_READ_PATH_2026-07-27.md` (DRAFT, operator
   review before build) — 2 read-path switches with guarded parse +
   bundle fallback + live-proof acceptance.
2. **Same-second reflection collapse (P2) — FIXED (contract v43)**:
   `revision_id` now `teacher-reflection-<uuid4>`; migration dedupe key
   is `(revision_id, content-hash)` — distinct same-second notes both
   survive, byte-identical double-submits still collapse. 2 new tests
   (rescue suite 10→12). Trade-off accepted in the preserve direction: a
   pre-uuid double-submit with differing timestamps now migrates twice
   (benign duplicate) rather than risking distinct-content loss.
3. **Private entry in public repo — WORKING-TREE SCRUB DONE, history
   rewrite = operator decision**: the `private:true` reflection naming
   the child (committed in 42c2a31, pushed) removed from
   `dev/lv_revision_log.ndjson` (10→9 lines; zero private entries
   remain). Rescued copy verified intact in
   `~/.lingua-viva/dev/lv_revision_log.ndjson` first — nothing lost.
   Sharper than the review stated: desktop bundles ship this file, so
   the migration would have injected that entry into EVERY teacher's
   local reflection file on first launch — the scrub also closes a
   cross-install leak. The pushed git history still contains the entry;
   rewrite/leave is the operator's call.
