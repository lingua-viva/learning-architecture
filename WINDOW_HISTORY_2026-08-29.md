# Window History — 2026-08-29

This file records the work completed in this Codex window for Lingua Viva.

## Starting Point

Mical asked to review Mission Canvas build-agent recommendations and apply only the parts that would materially benefit Lingua Viva teachers and administrators. The working repos reviewed were:

- `/home/mical/linguaviva.art`
- `/home/mical/learning-architecture`

The real product/runtime repo is `/home/mical/learning-architecture`. The public site repo is not the production source for the app runtime.

I also read the Codex voice lens at:

- `/home/mical/fde/organized/agent-steering-archive/CODEX_VOICE_LENS.md`

and used the Claudia Canu lens in `CLAUDE.md` to guide the later UX pass.

## Teacher/Admin Reliability Work

### Fixed Teacher-Facing Failures

The recommendation identified 8 teacher-facing failures:

- 6 document-to-lens failures in `tests/test_document_to_lens.py`
- 2 lesson-plan grounding failures in `tests/test_lesson_plan_artifact.py`

Both groups were fixed.

Document-to-lens failures were caused by Python 3.12 event-loop behavior in the test harness after previous `asyncio.run()` calls. I replaced the affected `asyncio.get_event_loop().run_until_complete(...)` calls with `asyncio.run(...)`.

Lesson-plan grounding failures were caused by duplicate keys in `src/lingua_viva/lesson_materials.py` that overwrote normalized fallback-safe fields with raw model fields. I removed the duplicate overwrite so omitted IB fields stay honest and hallucinated learner-profile attributes do not render.

### Added Governance Honesty

Added `check_governance_honesty()` in:

- `src/lingua_viva/governance.py`

It verifies:

- privacy log presence/activity
- signed governance pack HMAC verification
- dashboard counters against privacy and trace ledgers
- external-call under-reporting

Fresh installs with no activity report `PASS` with `NO_ACTIVITY`, not fake failure.

Tests added:

- `tests/test_governance_honesty.py`

### Added `lv improve`

Added a small teacher/admin improvement surface:

- `src/lingua_viva/improve_surface.py`
- `src/lingua_viva/cli.py`

Command:

```bash
python3 -m src.lv_cli improve
```

It composes teacher readiness, route reachability, governance honesty, admin metrics, measurement value, and optional live production download checks.

### Added `lv closing`

Added a release-facing gate with exactly four checks:

- gauntlet
- pipeline
- artifacts
- preflight

Files:

- `src/lingua_viva/closing.py`
- `src/lingua_viva/cli.py`
- `tests/test_closing.py`

Command:

```bash
python3 -m src.lv_cli closing
```

This intentionally does not port Mission Canvas's larger improvement machinery. It is a compact release gate for teacher/admin outcomes.

### Added Measurement Value Manifest

Added:

- `config/measurement_manifest.yaml`

It maps checks/instruments to user value categories and lifecycle states, so measurement without classroom/admin value can be reviewed or retired.

### Hardened Document Import Path Handling

Added app-owned import-log path confinement:

- `src/lingua_viva/docpipe/lens_extract.py`
- `src/lingua_viva/routers/document_import.py`

New test:

- `tests/test_document_import_security.py`

Client-supplied extraction log paths are now resolved under the app-owned imports directory and must be `.ndjson`.

### Updated Contracts And Pins

Updated:

- `contracts/ROUTE_REACHABILITY.yaml`
- `contracts/UI_CONTRACT.yaml`
- `contracts/UI_CONTRACT.lock`
- `tests/test_ui_contract.py`
- `tests/gauntlet/test_05_knowledge_grounding.py`
- `CLAUDE.md`

Notable updates:

- route reachability now includes document import/apply routes
- UI contract bumped first to v170 for import-preview language
- knowledge library expected file count updated to 8
- `CLAUDE.md` now records the current 111-node classification system

## Claudia UX Pass

Mical then asked for 5 UX improvements chosen through the Claudia Canu lens. I made five teacher-facing UI changes in:

- `static/index.html`

and added:

- `tests/test_claudia_ux_surface.py`

### 1. Home Next-Best Action

Home now renders a `Start here` panel based on the morning state:

- observation gaps route to Observe
- pending support decisions route to Students
- otherwise it routes to Prepare

This turns the dashboard from status display into a classroom-start action.

### 2. Prepare Empty-Source Guard

Prepare now disables generation buttons until Claudia has either:

- selected coursework, or
- typed a topic

This prevents confident-looking filler based on the generic `"Current lesson"` fallback.

### 3. Observe Keeps Current Learner Selected

After saving an observation, the form clears the note fields but preserves the selected learner.

This supports the real classroom workflow where Claudia may capture several observations for the same child in a row.

Switching to a different student still clears the old note fields to prevent cross-student saves.

### 4. Parent Summary Review Checklist

Parent summaries now require a visible teacher review checklist before copy or print are enabled.

The checklist covers:

- removal of private details that should not be shared
- evidence support for every claim
- tone matching the teacher and family context

This adds useful friction at the family-facing boundary.

### 5. Privacy Log-Driven Verdict

The Privacy page no longer always shows `all local`.

It now reads the actual local privacy counters:

- `all local` when no external calls are recorded
- `student data local` when non-student Ask calls were sent externally

This keeps privacy reassurance honest.

The UI contract was bumped again to v171 for this deliberate UX pass.

## Verification Run

Commands run after the teacher/admin reliability work:

```bash
python3 -m pytest tests/test_lesson_plan_artifact.py tests/test_document_to_lens.py -q
python3 -m pytest tests/gauntlet -q
python3 doctor/lv_artifact_gauntlet.py
python3 -m src.lv_cli preflight --json
python3 -m pytest tests/test_governance_honesty.py tests/test_governance_control_plane.py tests/test_improve_surface.py tests/test_lesson_plan_artifact.py tests/test_document_to_lens.py tests/gauntlet -q
python3 -m src.lv_cli improve --no-readiness --live --json
python3 -m src.lv_cli closing
python3 -m pytest tests -q
```

Key results:

- document-to-lens tests passed
- lesson-plan artifact tests passed
- education gauntlet passed: 81/81
- artifact gauntlet passed
- preflight passed
- `lv closing` passed
- full suite passed: `2639 passed, 13 skipped in 658.49s`

Commands run after the Claudia UX pass:

```bash
python3 -m pytest tests/test_claudia_ux_surface.py tests/test_ui_contract.py tests/test_home_view.py tests/test_parent_summary_finish.py tests/test_observation_double_save.py tests/test_action_registry.py -q
python3 scripts/check_ui_contract.py
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('static/index.html', 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
for (const [i, script] of scripts.entries()) {
  new Function(script);
  console.log(`script ${i + 1}: syntax ok`);
}
NODE
python3 -m src.lv_cli closing
python3 -m pytest tests -q
```

Key results:

- focused UX/UI suite passed: `45 passed`
- UI contract passed: `contract v171, 3 files locked`
- inline script syntax passed
- `lv closing` passed:
  - gauntlet PASS
  - pipeline PASS
  - artifacts PASS
  - preflight PASS
- full suite passed: `2644 passed, 13 skipped in 670.51s`

## Current Working Tree Summary

Modified files include:

- `CLAUDE.md`
- `contracts/ROUTE_REACHABILITY.yaml`
- `contracts/UI_CONTRACT.yaml`
- `contracts/UI_CONTRACT.lock`
- `src/lingua_viva/cli.py`
- `src/lingua_viva/docpipe/lens_extract.py`
- `src/lingua_viva/governance.py`
- `src/lingua_viva/lesson_materials.py`
- `src/lingua_viva/routers/document_import.py`
- `static/index.html`
- `tests/gauntlet/test_05_knowledge_grounding.py`
- `tests/test_document_to_lens.py`
- `tests/test_ui_contract.py`

New files include:

- `WINDOW_HISTORY_2026-08-29.md`
- `config/measurement_manifest.yaml`
- `src/lingua_viva/closing.py`
- `src/lingua_viva/improve_surface.py`
- `tests/test_claudia_ux_surface.py`
- `tests/test_closing.py`
- `tests/test_document_import_security.py`
- `tests/test_governance_honesty.py`
- `tests/test_improve_surface.py`

## Suggested Commit Message

```bash
git add -A
git commit -m "feat: improve Lingua Viva teacher and admin release surfaces"
```
