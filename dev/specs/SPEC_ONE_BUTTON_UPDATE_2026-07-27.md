# SPEC: One-Button Install-or-Update With User-Work Preservation

- **Date**: 2026-07-27
- **Status**: DRAFT (see `dev/INDEX.md` for the live status)
- **Scope**: Lingua Viva first. Mission Canvas inherits this pattern only after LV validates it in production (operator ruling 2026-07-27).
- **Research grounding**: `dev/RESEARCH_UPDATE_PRESERVATION_2026-07-27.md` — every design rule below traces to a documented real system (dpkg, RPM, pacman, OSTree, VS Code, Anki, Obsidian, Home Assistant, Blender, Firefox, Squirrel/electron-builder). No guessed mechanisms.

---

## 1. Problem

One download button on linguaviva.art must:

1. **Fresh machine** → install the whole app.
2. **Existing install** → bring in new engine code and new/improved shipped templates.
3. **Never** overwrite or delete anything the teacher made or modified — lenses and canvases are malleable by design and will adapt around each teacher over time.

The tension: shipped artifacts must be updatable, user artifacts must be untouchable, and one file can migrate between those categories the moment a teacher edits it. A static "updatable vs. protected" list cannot express that — the classification must be **computed per file at update time**.

### Incidents grounding this spec (all verified live 2026-07-27)

| Incident | Where | Class |
|---|---|---|
| Teacher private reflections append **inside the app bundle** (`LV_ROOT/dev/lv_revision_log.ndjson`) — erased on every app update, mutates the signed macOS bundle | `src/web.py:332` (`_revision_log_path`) | Pitfall #6: mutable state in updater-owned territory |
| MC's onboarding does `shutil.rmtree` + recopy of templates — user edits to shipped templates silently destroyed | `mission-canvas/src/onboarding.py:862-868` | Pitfall: silent overwrite (the exact failure LV must never inherit) |
| Site download pins went stale silently (0.2.7 served through two releases) | fixed 2026-07-26, `scripts/mc_push.py` `_bump_site_pins` + `_verify_live` | Delivery-surface staleness |

---

## 2. Current state — what already works (verified, do not rebuild)

- **User work is already outside the bundle.** Teacher/student lenses live in `~/.lingua-viva/runtime/student_lenses.db` (SQLite) + `runtime/teacher_lenses/`; imports, `file_map.yaml`, `config/providers.json`, `*.ndjson` stores all under `lv_home()` (`src/lingua_viva/config.py:39-49`, single seam, env-overridable).
- **The button already "installs or updates" mechanically.** NSIS reinstalls over itself; macOS drag-replaces the .app; `install.sh`/`install.ps1` detect `.git` and `git pull` (`install.sh:351-357`, `install.ps1:261-268`). `~/.lingua-viva` survives all paths.
- **Shipped resources are already immutable on macOS** (signed + notarized bundle; electron-builder replaces `extraResources` wholesale on update — electron-builder #4501). This is a feature: the bundle is the read-only **seed layer**.
- **The one violation** of the seam is the revision log (§1 table, P0 below). Every other write path audited clean (`demo_path`, `export_dir`, `ingest-tmp` → all `lv_home()`).

What does NOT exist yet: any manifest/provenance of shipped artifacts, any reconcile step after update, any conflict surface, any `schema_version`/downgrade stamp, `lv update` CLI.

---

## 3. Design (industry-consensus pattern: hash manifest + three-way compare)

Per file, on first launch after an update, compare **old-shipped hash** (manifest) vs **on-disk content** vs **new-shipped hash** (bundle seed):

| On-disk vs old-shipped | Action | Precedent |
|---|---|---|
| Identical (unmodified) | Silently upgrade to new version | dpkg/RPM/pacman/OSTree unanimous |
| Different (user-modified) | **Keep user's file.** Park new version as pending update, surface in-app | RPM `%config(noreplace)` → `.rpmnew`; pacman `.pacnew` |
| Missing (user deleted it) | Treat as modification — do NOT resurrect | dpkg deleted-counts-as-modified rule |
| Not in manifest at all (user-created) | Never touch, ever | all systems: unknown files invisible to updater |

### P0 — Reflection-log relocation (ship in desktop-v0.2.11, before any teacher updates)

1. `_revision_log_path()` default → `lv_home() / "dev" / "lv_revision_log.ndjson"` (env override `LV_REVISION_LOG_PATH` unchanged).
2. One-time migration at startup: if the legacy `LV_ROOT/dev/lv_revision_log.ndjson` exists and is readable, append its entries to the new path once (idempotent marker in the new file or a `.migrated` sentinel), never write to the old path again. Teachers on 0.2.9/0.2.10 desktop have potentially days of reflections at the legacy path — this is the only window to rescue them.
3. Test: reflection POST in desktop mode (`LV_DESKTOP=1`) writes only under `lv_home()`; migration test with a seeded legacy file.

### Phase 1 — Manifest + seed/live layers

- **Seed layer**: shipped templates stay read-only in app resources (current `extraResources`: `lenses/`, `ontology/`, `curriculum/`, `knowledge/`...). The app NEVER writes here (P0 closes the one violation).
- **Live layer**: `~/.lingua-viva/templates/<domain>/...` — materialized working copies the teacher may edit.
- **Manifest**: `~/.lingua-viva/update_manifest.json` — for every materialized shipped artifact: relative path, canonicalized-content hash as shipped, shipping app version, `schema_version`. Plus `last_run_engine_version` (downgrade stamp) and tombstone/`renamed_from` entries.
- **Single writer**: new module `src/lingua_viva/reconcile.py` is the ONLY code allowed to write the manifest (dpkg sole-writer model — two writers is Pitfall #3). Manifest write is the LAST step of any reconcile (OSTree single-commit-point).
- **Hash canonicalized content**, not raw bytes: parse YAML → canonical dump → hash. Kills Pitfall #1 (a reformat/newline flip misclassifying everything as modified). Non-parseable file → raw-bytes hash fallback.

### Phase 2 — First-launch reconcile

Trigger: app version ≠ manifest's recorded version (covers desktop update, `git pull`, and fresh install where manifest is absent → materialize everything).

Per artifact, apply the §3 table. Mechanics:
- Unmodified upgrade: write-temp → fsync → rename (atomic per file).
- Modified: leave user file byte-identical; record pending-update entry `{path, new_hash, shipped_in_version}` in manifest; stage new version under `~/.lingua-viva/updates-pending/<path>`.
- Shipped-artifact removal/rename upstream: only via explicit manifest tombstone/`renamed_from` shipped with the release; modified-check before delete (dpkg-maintscript-helper semantics). No tombstone → old live copy left alone.
- Symlinks in the live layer: treat as user-modified, never touch. Case-folded path comparison (macOS/Windows are case-insensitive); CI check rejects case-colliding shipped names.
- Crash mid-reconcile: safe by construction — per-file atomic writes, manifest (the classification source of truth) committed last, reconcile idempotent on re-run.

### Phase 3 — Conflict surface (the pacdiff lesson: parked updates rot unseen = Pitfall #2)

- `lv doctor` + `/api/health` gain an `updates_pending` item: "N template updates waiting — your customized versions were preserved."
- Minimal UI: list pending artifacts, per-item **[Keep mine] [Take new] [View diff]**. Take-new archives the user's version to `~/.lingua-viva/archive/<path>.<date>` before replacing (nothing is ever destroyed).
- Unresolved conflicts are a visible health WARN, never a silent state.

### Phase 4 — Namespacing, schema versioning, downgrade guard

- **Reserved namespace**: shipped artifact IDs use the `lv-` prefix (already largely true, e.g. `LV-CUR-003`). User-created artifact IDs are validated at **creation time** to reject the reserved prefix (Anki numeric-ID lesson: solve collisions by construction, not at update time).
- **`schema_version`** field in every shipped artifact; on-first-launch migration runner for user-owned copies (HA `_async_migrate_func` pattern); missing keys handled by defaults-merge at read time (Obsidian `Object.assign(DEFAULT, user)` pattern). Migrate shipped seeds at build time; only user copies migrate at runtime.
- **Downgrade guard**: if `last_run_engine_version` > current app version, warn (Firefox `compatibility.ini` model; HA major/minor contract: minor bumps stay backward-readable, major bumps may refuse).

---

## 4. Explicit non-goals (this spec)

- Mission Canvas port — separate spec after ≥2 weeks of LV production validation. MC additionally needs the `onboarding.py` rmtree fix and has a different template-instantiation path.
- Delta/partial downloads (full-bundle replace is the atomic unit — Squirrel model).
- Background auto-update (electron-updater) — the button IS the update trigger for now; wire `autoUpdater` later without changing this design (userData-side manifest is updater-agnostic).
- Intel-Mac/universal build — tracked separately (release-surface question, not update-system).

## 5. Acceptance checks

1. Fresh install → materialize + manifest written; second launch → reconcile no-ops (idempotent).
2. Update with zero user edits → all templates upgraded, zero pending.
3. Edit one shipped template, update → edit preserved byte-identical, new version pending, health WARN visible.
4. Delete one shipped template, update → not resurrected.
5. Create `user-` artifact, update ships colliding-ID template → both survive (namespace separation); creation-time rejection of `lv-` prefix covered by test.
6. Kill -9 mid-reconcile → relaunch completes cleanly, no corrupt/half-written artifact (temp+rename verified).
7. Reflection POST in desktop mode writes only under `lv_home()`; legacy-log migration idempotent (P0).
8. Downgrade run → warning surfaced, no artifact writes.

## 6. Pitfall → mitigation map (top 5 of 10; full list in research doc)

| # | Pitfall (likelihood-ranked) | Mitigation in this design |
|---|---|---|
| 1 | App reformats pristine YAML → everything "modified", auto-update silently dies | Canonicalized-content hashing; app never serializes back to live-layer files it didn't change |
| 2 | Parked `.new` updates rot unseen → schema drift, "app broke" | Phase 3 conflict surface as a health item, not a dotfile |
| 3 | Manifest drift / two writers | `reconcile.py` sole writer; manifest-vs-disk verify each launch; unknown → never touch |
| 4 | Shipped ID collides with user-created artifact | Reserved `lv-` namespace enforced at creation time |
| 5 | Shipped template renamed/removed → orphans | Manifest tombstones + `renamed_from`, modified-check before delete |
