# Memory: LV Setup Wizard And Full Artifact Hardening

**Date**: 2026-07-20
**Repo**: `~/learning-architecture`
**Purpose**: durable handoff for the next agent/session implementing the Lingua
Viva setup wizard and full artifact hardening pass.

## Current Canonical Prompt

Use this file as the implementation handoff:

`dev/EXECUTION_PROMPT_LV_SETUP_WIZARD_AND_HARDENING_2026-07-20_KIRO.md`

It has been revised into a Codex-authored final execution prompt for Kiro. It
is intentionally explicit and should be read in full before touching code.

Short kickoff prompt:

```markdown
You are working in `~/learning-architecture`.

Read this file in full before touching anything:

`dev/EXECUTION_PROMPT_LV_SETUP_WIZARD_AND_HARDENING_2026-07-20_KIRO.md`

Execute it exactly.

Priority order:
1. Build and verify the Lingua Viva desktop setup wizard first.
2. Then run the full artifact hardening sweep.
3. Keep the five priority gates explicit: first-run/Ollama, public downloads,
   student lenses, microphone notes, and trust cockpit.
4. Write the required report:
   `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`
5. Update `dev/INDEX.md`.
6. Do not commit.

Hard rules:
- No real student data, institution names, or private school documents.
- Do not modify Tier 1 governance.
- Verify live behavior, not just source.
- If `static/index.html` or `src/web.py` changes, bump the UI contract.
- Final response under 150 words with setup status, report path, top 3 risks,
  and test result.
```

## What Was Created Or Revised

Created:

- `dev/specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`
- `dev/EXECUTION_PROMPT_LV_FULL_ARTIFACT_HARDENING_2026-07-20_CODEX.md`

Updated:

- `dev/INDEX.md` with a DRAFT row for
  `SPEC_LV_FULL_ARTIFACT_HARDENING`
- `dev/EXECUTION_PROMPT_LV_SETUP_WIZARD_AND_HARDENING_2026-07-20_KIRO.md`
  to make it the main combined handoff

This memory file was added afterward to preserve the context.

## Why The Combined Prompt Exists

The operator had a Kiro-created prompt for:

1. Building the Lingua Viva desktop setup wizard.
2. Running the full artifact hardening sweep afterward.

Codex added the broader product priorities and tightened the handoff so the
next agent does not have to infer what matters most.

The setup wizard remains first priority because it unblocks real testers:
teachers on Windows should not open the desktop app and hit a dead
`python3 not found` failure. The app must guide them through Python, Ollama,
pip dependencies, and server startup.

The full artifact hardening pass comes second and validates the rest of the
product surface.

## The Five Priority Gates

These are the product improvements Codex recommended and the operator asked to
integrate:

1. **First-run/Ollama clarity**
   - Opening Lingua Viva should explain what is happening, what runs locally,
     why Python is needed, whether Ollama is installed, whether Ollama is
     optional, and what to do next.

2. **Public download coherence**
   - `linguaviva.art` download buttons must match the artifact they deliver.
     If the product delivers a native app, say that. If it delivers a CLI that
     opens localhost, say that. Missing publish/release/signing work must be
     escalated exactly.

3. **Student lens creation**
   - Student lenses are central to the promise. Creating, selecting, updating,
     inspecting, and recovering them should feel first-class.

4. **Microphone note capture**
   - Observation capture must handle unsupported browsers, permission denial,
     no speech recognized, transcript editing, typed fallback, save success,
     save failure, and clear local-lens confirmation.

5. **Trust cockpit consistency**
   - Why, Privacy, Profile/export/clear, Health/Doctor, and support bundle
     should tell one coherent story: what happened, what stayed local, what
     left, what the app knows, how to export, how to delete, and what to send
     support.

## Key Execution Rules To Preserve

- Do not commit.
- Do not use real student data, institution names, colleague names, or private
  school documents.
- Do not modify Tier 1 governance.
- Do not change Lingua Viva's protection model from architectural exclusion to
  runtime interception.
- If `static/index.html` or `src/web.py` changes, run:

```bash
python3 scripts/check_ui_contract.py --bump
python3 scripts/check_ui_contract.py
```

- Use:

```bash
python3 -m pytest -q tests/
```

not bare `pytest`, unless there is a recorded reason.

- Verify `linguaviva.art` and GitHub release state live. Do not rely on memory.

## Required Reading For The Implementer

The canonical prompt already lists this, but the high-level set is:

- `CLAUDE.md`
- `dev/INDEX.md`
- `dev/specs/SPEC_DESKTOP_SETUP_WIZARD_2026-07-20.md`
- `dev/specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`
- `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`
- `dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`
- `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`
- `dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
- `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
- `dev/reports/REPORT_LV_CLAUDIA_LENS_HARDENING_2026-07-20.md`
- `desktop/electron/main.ts`
- `desktop/electron/bootstrap.ts`
- `desktop/electron/preload.ts`
- `desktop/package.json`
- `static/index.html`
- `src/web.py`

Reference implementation to read, not modify:

- `~/fde/mission-canvas/desktop/electron/main.ts`
- `~/fde/mission-canvas/desktop/electron/setup-wizard.html`

## Expected Implementation Shape

Part 1: desktop setup wizard.

- Add `desktop/electron/setup-wizard.html`.
- Extend `desktop/electron/bootstrap.ts` with Python detection, downloads,
  Windows installers, dependency install, and PATH refresh.
- Rewrite the desktop boot flow in `desktop/electron/main.ts` so setup guides
  the user instead of throwing.
- Extend `desktop/electron/preload.ts` with setup IPC.
- Update `desktop/package.json` so the wizard HTML is copied into
  `dist/electron/`.
- Verify `cd desktop && npm run build`.

Part 2: full artifact hardening.

- Start the app locally.
- Live-walk every public, install, onboarding, teacher, coordinator, PWA,
  backend, privacy, support, and docs/status artifact listed in the umbrella
  spec.
- Fix concrete defects.
- Add regression coverage where appropriate.
- Write:

`dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`

- Update `dev/INDEX.md` with the real outcome.

## Stop And Escalate Conditions

Escalate instead of pretending to finish if the fix requires:

- DNS/CDN hosting access
- GitHub release publishing or tag creation
- code signing
- private credentials
- policy/governance decisions
- private school documents
- a Windows live test that cannot be run from the current machine

Structural verification is acceptable for Windows-only paths if the current
machine cannot run Windows. The report must say what was structurally verified
and what manual Windows test remains.

## Verification Checklist

Minimum:

```bash
cd desktop && npm run build
cd .. && python3 -m pytest -q tests/
python3 -m src.lv_cli preflight
python3 scripts/check_ui_contract.py
python3 -m py_compile src/web.py src/lv_cli.py src/pwa.py
sh -n install.sh
python3 -m src.lv_cli serve 8787
curl -fsS http://127.0.0.1:8787/api/health
curl -I https://linguaviva.art
```

Also use, when available:

```bash
rg -n "python3" desktop/electron
rg -n "Still I Rise|sir-|7896|Mission Canvas" .
gh api repos/lingua-viva/learning-architecture/releases/latest
```

Do not rewrite historical specs/reports just because rebrand grep finds old
terms. Fix live product surfaces, installers, workflows, and current
user-facing docs.

## Final Report Shape

The hardening report should include:

- Findings first, ordered by severity.
- Part 1 desktop setup wizard status.
- Five Priority Gates table.
- Full artifact inventory table.
- Public site/download verification table.
- Teacher and coordinator experience table.
- Backend/privacy/support/docs table.
- Verification commands and results.
- Factual corrections to prior reports, if any.
- Operator follow-ups, if any.

## Current State Caveat

This memory reflects the handoff/prompt-writing work only. It does not claim
the setup wizard or hardening implementation has been run. The next session
must execute the canonical prompt and verify live behavior.
