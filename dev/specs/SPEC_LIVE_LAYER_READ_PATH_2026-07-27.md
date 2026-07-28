# SPEC — Live-Layer Read Path (close the one-button-update loop)

**Date**: 2026-07-27 · **Status**: DRAFT (see `dev/INDEX.md` for the live status)
**Origin**: independent review of SPEC_ONE_BUTTON_UPDATE_2026-07-27 (review
finding 1 — a spec gap, faithfully implemented, not a builder error).
**Revision**: v2 same day — post-review rewrite; rolls in the reviewer's
"start-over" findings (overlay model, namespace guard, deletion-semantics
decision, Doctor visibility, suite hermeticity, restart hint).

## 1. The gap

The one-button-update system materializes, reconciles, and preserves
teacher working copies under `~/.lingua-viva/templates/` — but **nothing
reads them**. Verified:

- `LensEngine` loads lenses from the bundle (`lenses/engine.py:80-96`,
  `Path(__file__).parent`, subdirs `core`/`professional`/`education`,
  keyed by the YAML `name:` field — last load wins).
- `CurriculumService` reads the bundle matrix
  (`src/lingua_viva/curriculum.py:11`); constructed per-request in
  `src/web.py` routes.
- The only module in `src/` referencing the live layer is `reconcile.py`.

So a teacher edit to a live-layer template is preserved forever but has
zero effect on app behavior, and the Settings "Template Updates" panel
describes files that don't do anything. Built-not-mounted, at
architecture level. Not a data-loss risk — but until closed, "canvases
adapt around the teacher" is untrue for the managed set.

## 2. Design — overlay, not per-file existence checks

**Model: bundle first, live overlay second, live wins by lens name.**
Per-file "does a live twin exist?" checks were the v1 draft; the overlay
is strictly better because one mechanism yields both behaviors we want:

1. **Shadowing** — a teacher-edited copy of a shipped education lens
   replaces the bundle copy (same `name:` → overlay wins).
2. **Teacher-created lenses load** — a new `.yaml` the teacher drops in
   `~/.lingua-viva/templates/lenses/education/` becomes a real lens.
   Without this, the reconcile's "unknown files: never touch" rule
   preserves files that are still inert — the F1 gap recreated one level
   down. (These files are already active-content by design: the shipped
   lens the teacher edits feeds system prompts today.)

### 2a. `LensEngine._load_lenses` (`lenses/engine.py`)

- Load bundle `core`, `professional`, `education` exactly as today.
- Then overlay: for every `*.yaml` under
  `live_root()/lenses/education/` (path via
  `src.lingua_viva.reconcile.live_root()` — single path seam), parse
  with **guarded semantics** (§2c) and register the lens.
- **Namespace guard**: if the overlay lens's `name` collides with a lens
  loaded from bundle `core/` or `professional/`, **skip it** and record
  it (surface per §2d). The live education layer may only shadow or add
  education-scope names — a teacher file named `kaizen` must not hijack
  a core lens via dict-key overwrite. Case-fold the name comparison.
- Explicit `lenses_dir=` argument (tests): overlay applies only when
  `lenses_dir` is the default (None). Tests constructing
  `LensEngine(some_tmp_dir)` keep exact current behavior.

### 2b. `CurriculumService` (`src/lingua_viva/curriculum.py`)

- Default `matrix_path` resolves to
  `live_root()/curriculum/lingua_viva_matrix.yaml` **iff that file
  exists and passes the guarded parse at resolve time**; else the bundle
  path. Explicit `matrix_path` arguments (tests) unchanged.
- Note: routes construct `CurriculumService()` per request, so curriculum
  live edits apply per request — no restart needed for curriculum
  (restart-to-apply still governs lenses; see §5).

### 2c. Guards (both consumers)

- Live-layer files are teacher-writable: every parse goes through
  `reconcile._parse_yaml_guarded` semantics (alias-bomb refusal + 1MB
  cap — hardening §8 iteration 1 applies to *every* live parse, not
  just hashing).
- A live file that fails to parse / trips a guard / isn't a dict →
  **skip it, keep the bundle copy if one exists**. Fail toward shipped
  behavior, never toward a crash or a half-loaded engine.
- The `from src.lingua_viva.reconcile import live_root, _parse_yaml_guarded`
  import must be failure-tolerant (Doctor's pass-if-import-fails
  pattern): a broken update subsystem must never take lens loading
  down. On import failure → bundle-only behavior, identical to today.

### 2d. Visibility (the pacdiff lesson applies to the read path too)

A corrupt live file silently serving the bundle copy — or a
namespace-guard skip — is a rot-unseen state: the teacher edited a
file, nothing changed, no one said why. New Doctor check
`live_templates` (WARN, never FAIL):

- live education files that failed the guarded parse ("your customized
  X couldn't be read — the shipped version is being used"), and
- overlay files skipped by the namespace guard.

Implementation: a small pure function in `reconcile.py` (or the engine)
that Doctor calls, same import-tolerant pattern as
`check_updates_pending`.

### 2e. Deletion semantics — explicit decision

Live file missing → **the bundle copy serves** (fallback). Consequence,
stated plainly: a teacher cannot *remove* a shipped lens by deleting
their live copy — behavior reverts to shipped. This deliberately
diverges in spirit from the reconcile's "deletion counts as
modification" file rule, because at the behavior layer accidental
deletion is far likelier than intentional removal, and fail-toward-
shipped is the teacher-safe default. Lens *disabling* is a separate
future feature (an `enabled: false` field or UI toggle), not this spec.
The reconcile side is untouched: it still never resurrects the file.

## 3. UI: restart hint (small, contract-ceremony)

Once `take_new`/live edits actually change behavior, the missing
restart cue becomes real teacher confusion. After a successful
`resolve` in the Template Updates panel, show: "Saved — restart Lingua
Viva to use the new version." Curriculum needs no hint (per-request).
This is a served-UI change → bump `contracts/UI_CONTRACT.yaml` per its
ceremony (v43 as of this writing — **check current**, three lanes are
moving it).

## 4. Hermeticity — do this FIRST, not after tests break

After this change, every bare `LensEngine()` becomes sensitive to the
real `~/.lingua-viva/templates/` on the developer's machine (5 test
call sites + `Pipeline.__init__` + app runtime; conftest deliberately
does not force `LV_CONFIG_HOME` — the same trap the
`LV_LOCAL_IMPORTS_DIR` seam fixed for `extraction_sources`). Required:
an autouse conftest fixture pointing `LV_UPDATE_HOME` at a per-test tmp
dir, so the suite never reads or writes the operator's live layer.
Update-system tests that already set `LV_UPDATE_HOME` via their own
fixtures must keep working (their override wins).

## 5. Startup ordering — verify, don't assume

First launch after an update: if `LensEngine` constructs before the
startup reconcile upgrades the live layer, lenses are one launch stale.
Establish which happens first in the real app (uvicorn lifespan
handlers vs. first `Pipeline()` construction). If construction is
lazy/per-request → no issue; if import-time → either move it after
startup or document one-launch staleness as accepted (restart-to-apply
already governs lenses). Record the answer in the report.

## 6. Acceptance

1. Teacher edits `~/.lingua-viva/templates/lenses/education/<x>.yaml` →
   restart → lens behavior reflects the edit (**live-proof against the
   served app, transcript in the report** — not just a unit test).
2. Teacher drops a NEW `my-class-voice.yaml` in the live education dir →
   restart → the lens exists and applies.
3. Overlay lens whose `name` collides with a core/professional bundle
   lens → bundle lens unchanged, overlay skipped, Doctor WARN lists it.
4. Corrupt / alias-bomb / >1MB live file → bundle copy serves, startup
   fast (<100ms overhead budget for the overlay scan), Doctor WARN
   lists it.
5. Live file deleted → bundle copy serves (documented §2e semantics).
6. `LV_UPDATE_HOME` empty/fresh (no live layer) → behavior byte-identical
   to today; all existing lens/curriculum/pipeline tests pass unmodified.
7. `take_new` through the Settings panel → next launch serves the new
   content (end-to-end: the panel's promise becomes true); restart hint
   shown.
8. Curriculum live edit → next request serves it; corrupt live matrix →
   bundle matrix serves.
9. Reconcile module import failure (simulated) → lens loading and
   curriculum fall back to bundle, no crash.

## 7. Non-goals

- No hot-reload for lenses; restart-to-apply is fine for v1.
- No live-layer write path from the UI (teachers edit via filesystem /
  the Template Updates panel; a template editor is a separate product
  decision).
- No lens disable/enable feature (§2e).
- No change to the reconcile/manifest machinery — this spec only adds
  readers.
- MC port waits for the same ≥2-week LV validation gate as the parent
  spec.
