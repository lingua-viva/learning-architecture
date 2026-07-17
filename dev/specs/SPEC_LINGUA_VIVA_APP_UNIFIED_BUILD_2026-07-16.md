# Lingua Viva App Unified Build Spec

**Status**: proposed unified build spec  
**Date**: 2026-07-16  
**Repo**: `/home/mical/learning-architecture`  
**Branch**: `LINGUA-VIVA-UPDATE`  
**Product boundary**: Lingua Viva production repo, not Mission Canvas/FDE  

## 0. Purpose

Build the working Lingua Viva teacher app in this repository, using the new local Doctor/support-loop content, the accountable curriculum rules, and the publication-readiness audit, without hosting Lingua Viva runtime features inside Mission Canvas.

The app should serve teachers first. Doctor belongs in the app shell as a Help/Health affordance, not as a permanent global nav item and not inside Mission Canvas.

## 1. Baseline From 2026-07-16 Testing

Commands run from `/home/mical/learning-architecture`:

```bash
python3 -m doctor.support_loop
```

Result: failed with CLI usage error. The module requires a subcommand:

```text
lv: error: the following arguments are required: command
```

Follow-up intended invocation:

```bash
python3 -m doctor.support_loop doctor
```

Result: `PRIVATE_RISK`.

Reported issues:

- `LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md` missing at root.
- `dev/lv_artifact_gauntlet.py` missing.
- Worktree has local changes.
- Artifact gauntlet failed.
- Possible private/student data path found; contents were not read.
- Support bundle is not implemented in Phase A app flow.

Artifact gauntlet:

```bash
python3 doctor/lv_artifact_gauntlet.py
```

Result: failed.

- Missing required file: `LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md`
- README must use designed-to integration wording.
- README must use assessment coherence wording.

Existing app tests:

```bash
python3 -m pytest tests/ -q
```

Result: `348 passed in 175.45s`.

Focused PWA tests after static boundary cleanup:

```bash
python3 -m pytest tests/test_pwa_assets.py tests/test_pwa_routes.py -q
```

Result: `8 passed in 0.36s`.

## 2. Boundary Findings

The production Lingua Viva repo is `/home/mical/learning-architecture`. The archival FDE workspace is `/home/mical/fde/implementations/education/lingua-viva`.

Current app/runtime code still contains substantial Mission Canvas inheritance:

- `src/web.py` is titled and configured as Mission Canvas and includes fallback MC HTML.
- `src/api_server.py`, `src/mc_cli.py`, `src/pipeline.py`, `src/gates/*`, `src/missions/*`, and related tests are MC-shaped runtime infrastructure.
- `static/index.html` is branded as Still I Rise, but still exposes pipeline steps and `/api/query` style interaction.
- `static/offline.html` previously contained visible Mission Canvas copy; this has been changed to Lingua Viva copy.
- PWA queue identifiers were renamed from `MC_*`/`mc.*` to `LV_*`/`lv.*` in `static/` and matching tests.
- No misplaced Doctor button or `/api/lingua-viva/doctor` endpoint was found in this repo's `static/index.html` during this pass.
- Existing Phase B and hardening specs still contain old FDE and Mission Canvas target paths; this spec supersedes those paths for this repo.

Do not add or preserve Mission Canvas action registries, connector frameworks, CRM/support/sales code, governance gates, or generalized MC pipeline UX as Lingua Viva product features.

## 3. Source Specs Incorporated

This build spec incorporates:

- `SPEC_LINGUA_VIVA_LOCAL_SUPPORT_LOOP_2026-07-16.md`
- `SPEC_LINGUA_VIVA_DOCTOR_PHASE_B_SUPPORT_BUNDLE_2026-07-16.md`
- `SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM_2026-07-16.md`
- `LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md`

UX inspiration may be taken from `/home/mical/fde/mission-canvas/dev/SPEC_SIDEBAR_AND_CX_DESIGN_2026-07-16.md` only as principles:

- navigation is task-based;
- every visible task must do something useful quickly;
- trust/status belongs in a quiet bottom or utility area;
- the interface should be smaller than the system behind it.

Do not copy MC sidebar actions, action IDs, registries, connectors, or gates.

## 4. Product Shape

Lingua Viva should open to a teacher workbench, not a chat-first MC shell.

Primary teacher tasks:

- **Plan**: view curriculum sequence, grade band, framework alignment, and teacher notes.
- **Prepare**: generate or assemble classroom-ready activity drafts from approved local source material.
- **Assess**: use CEFR-informed and school assessment structures as design aids, without claiming validated outcomes.
- **Reflect**: capture private teacher implementation notes and anonymized revision suggestions.
- **Health**: run Doctor from the Help/Health affordance.

Suggested shell:

- Left rail or compact sidebar: `Plan`, `Prepare`, `Assess`, `Reflect`.
- Bottom/utility area: `Health`, `Settings`, `Privacy`.
- Main pane: selected teacher workflow.
- Right details pane where useful: evidence, source status, claim maturity, or privacy notes.

Doctor is not a top-level curriculum task. It appears as:

- a small health indicator in the app chrome;
- a Help/Health menu item;
- a result panel when run.

## 5. Runtime Architecture

Recommended target layout:

```text
doctor/
  support_loop/
  lv_support.py
  lv_artifact_gauntlet.py

src/
  lingua_viva/
    app.py
    routes.py
    curriculum.py
    health.py
    support_bundle.py
    publication_rules.py

static/
  index.html
  sw.js
  manifest.json
  offline.html

tests/
  test_lingua_viva_routes.py
  test_lingua_viva_static.py
  test_lingua_viva_health.py
  test_lingua_viva_support_bundle.py
```

`src/web.py` may temporarily serve the app during migration, but the unified build target is a Lingua Viva app module, not Mission Canvas with renamed labels.

The local web app should expose only Lingua Viva endpoints:

```text
GET  /
GET  /manifest.json
GET  /sw.js
GET  /offline.html
GET  /api/health
POST /api/doctor/run
POST /api/support-bundle
GET  /api/curriculum/overview
GET  /api/curriculum/grade/{grade}
GET  /api/publication/status
```

Avoid `/api/lingua-viva/*` inside Mission Canvas. In this repo, plain `/api/doctor/run` and `/api/support-bundle` are already scoped by the app.

## 6. Doctor Integration

Use the existing Doctor engine in `doctor/support_loop`.

Required fixes before claiming Doctor health:

- Decide whether canonical gauntlet path is `doctor/lv_artifact_gauntlet.py` or `dev/lv_artifact_gauntlet.py`, then align Doctor and gauntlet checks.
- Decide whether publication audit canonical path is `dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md` or root `LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md`, then align Doctor and gauntlet checks.
- Preserve `.docx` no-edit rule.
- Preserve private path scan by path/metadata only.
- Report `PRIVATE_RISK` without reading raw private contents.

App behavior:

- Health affordance runs the same code path as `python3 -m doctor.support_loop doctor`.
- UI displays status, summary, failed/warn check names, privacy notes, and next actions.
- Raw logs are hidden by default.
- Repair/update actions are deferred until implemented and tested.
- Doctor may create `.lv_support/` logs locally; these remain ignored runtime state.

## 7. Support Bundle Phase B

Implement Phase B in this repo, not in FDE or Mission Canvas.

Target modules:

```text
doctor/support_loop/bundle.py
doctor/support_loop/redaction.py
src/lingua_viva/support_bundle.py
```

Target endpoint:

```text
POST /api/support-bundle
```

Bundle directory:

```text
.lv_support/bundles/lv-support-YYYYMMDDTHHMMSSZ/
```

Bundle may include:

- redacted Doctor result;
- gauntlet output;
- YAML/NDJSON parse status;
- branch and git status for relevant paths;
- manifest of included/excluded files;
- redaction count report.

Bundle must exclude contents for:

- `*.docx`
- student observations
- IEPs
- progress reports
- individual scores
- parent communications
- private databases
- secrets, tokens, API keys
- `.lv_support/`

No upload. No zip by default. No screenshots unless separately requested and redacted.

## 8. Curriculum Governance In App

The app must encode the accountable curriculum rules as product constraints:

- `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` remains authoritative until explicitly promoted.
- No `.docx` modification without explicit request.
- `curriculum/lingua_viva_matrix.yaml` remains non-authoritative until promoted.
- Public claims need evidence and maturity labels.
- CEFR wording uses designed-to/target language, not achievement language.
- Student, teacher, parent, colleague, and institution-private data must not leak.
- Public materials follow the zero-AI-attribution rule.
- Revision changes need accountable proof in `dev/lv_revision_log.ndjson`.

The app may display source status and claim maturity, but it must not imply publication readiness while the audit says the package is not publication-ready.

## 9. Publication Readiness Requirements

Before any public app/download release:

- README public wording is downgraded to supported designed/proposed claims.
- Root/path mismatch for the audit file is resolved.
- Gauntlet passes.
- Doctor does not report missing canonical files.
- Reference redistribution status is reviewed.
- Institution-identifying details are approved or removed from public surfaces.
- No student/private content appears in app static assets, bundled artifacts, support bundles, or public docs.

## 10. Migration Plan

1. Freeze current MC-shaped runtime as legacy until replaced.
2. Align Doctor and gauntlet canonical paths.
3. Add Lingua Viva app module and route tests.
4. Replace the visible teacher shell with Lingua Viva task navigation.
5. Move Doctor into Help/Health affordance.
6. Implement local support bundle creation.
7. Add static and endpoint tests for Health and support bundle.
8. Remove or archive MC-only runtime files once no tests/imports depend on them.
9. Run full validation and append a revision-log entry for the unified build.

## 11. Validation Commands

Run before accepting the unified build:

```bash
python3 -m pytest doctor/support_loop/tests/ -q
python3 -m doctor.support_loop doctor
python3 doctor/lv_artifact_gauntlet.py
python3 -m pytest tests/ -q
python3 -m py_compile doctor/lv_support.py doctor/lv_artifact_gauntlet.py doctor/support_loop/*.py src/lingua_viva/*.py
rg -n "Mission Canvas|mission-canvas|/home/mical/fde|/api/lingua-viva|MC_|mc\\." static src tests README.md doctor
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx
```

Expected final state:

- Doctor status is `OK`, `WARN`, or documented `FIXABLE`; not missing canonical files.
- Artifact gauntlet passes.
- Full tests pass.
- No visible Mission Canvas branding remains in Lingua Viva app surfaces.
- Any remaining MC references are archived specs or explicitly legacy code pending removal.
- `.docx` has no git status output.

## 12. Acceptance Criteria

- Lingua Viva app serves teachers through Plan/Prepare/Assess/Reflect workflows.
- Doctor is a Help/Health affordance, not global nav and not hosted in Mission Canvas.
- Support bundle is local, redacted, and never uploaded.
- Curriculum governance constraints are enforced by copy, checks, and tests.
- Public claim wording follows the readiness audit.
- No FDE path is required for normal production operation.
- No MC runtime machinery is required for Lingua Viva-specific app behavior.
- Validation commands pass or produce documented, user-visible failures.
