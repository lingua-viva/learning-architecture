# Codex Final Execution Prompt: Lingua Viva Setup Wizard + Full Artifact Hardening

Copy everything below into a fresh Kiro session. Working directory:
`~/learning-architecture`.

This is a Codex-authored implementation prompt for Kiro. It is intentionally
explicit: the next session should be able to execute without guessing scope,
priority, output shape, or what "done" means.

---

```markdown
You're working in `~/learning-architecture`. This is a combined task:

1. **Build the desktop setup wizard** so teachers do not hit a dead app when
   Python, Ollama, or pip dependencies are missing.
2. **Run the full Lingua Viva artifact hardening pass** so the product is
   publishable across public site, downloads, onboarding, app use cases, and
   trust/privacy surfaces.

The setup wizard is the PRIORITY — it unblocks Jason and every future tester. The artifact
hardening follows and is thorough but secondary. Do not let the breadth of §2 delay shipping §1.
The product bar for the whole pass is: a non-technical teacher can download Lingua Viva, open it,
get through setup, capture useful classroom evidence, build or inspect student lenses, and understand
what stayed local without needing a developer in the room.

The output is not a chat summary. The output is working code, verified behavior,
and a report file with evidence.

## Execution Contract

Work in this order:

1. Read the required files.
2. Reproduce or directly inspect the current desktop setup failure mode.
3. Build the setup wizard.
4. Verify the desktop build.
5. Record Part 1 status in the report.
6. Start the local app and run the full artifact hardening gauntlet.
7. Fix concrete defects found during the gauntlet.
8. Run the full verification checklist.
9. Update `dev/INDEX.md`.
10. Give the final response under 150 words.

Do not invert this order. In particular, do not start broad UI hardening before
the setup wizard compiles.

## Required Reading (in order)

1. `CLAUDE.md` — publication safety, repo architecture, runtime boundaries
2. `dev/INDEX.md` — current spec/report status
3. `dev/specs/SPEC_DESKTOP_SETUP_WIZARD_2026-07-20.md` — the setup wizard spec (YOUR PRIMARY TASK)
4. `dev/specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md` — the umbrella hardening spec
5. `desktop/electron/main.ts` — current boot flow (you're rewriting lines 201-260)
6. `desktop/electron/bootstrap.ts` — existing Python/Ollama detection (extend, don't replace)
7. `desktop/electron/preload.ts` — current IPC bridge (extend)
8. `desktop/package.json` — build config
9. `install.sh`, `install.ps1` — reference for what deps are needed
10. `static/index.html`, `src/web.py` — the actual app you're booting into

Also read the Mission Canvas implementation you're porting from (reference only, do not modify):
- `~/fde/mission-canvas/desktop/electron/main.ts` — the working setup wizard
- `~/fde/mission-canvas/desktop/electron/setup-wizard.html` — the wizard UI

## Why You Specifically

The operator asked for Kiro because this is the same class of work just completed in Mission
Canvas: detail-driven hardening with live reproduction of every bug. You confirmed+fixed 6 bugs
in integration_onboarding.py, then built the MC setup wizard with a 15-iteration sweep that
caught 11 real issues (redirect following, Store aliases hanging, paths with spaces, missing pip
deps, early exit detection). Now port that same rigor here.

## Product Priorities To Bake Into The Pass

These are the five improvements the operator wants explicitly integrated. Treat them as acceptance
criteria for Part 2, and let them shape Part 1 copy where relevant.

1. **First-run setup must be brutally clear**
   - Opening Lingua Viva should immediately answer: what is happening, what runs locally, what Python
     is needed for, whether Ollama is installed, whether Ollama is optional, and what the next action is.
   - Missing Python, missing Ollama, failed model pull, failed pip deps, and backend start failure must
     all resolve to guided next actions, not terminal-style failure copy.
   - The app must remain honest about what works without Ollama and what improves after Ollama/model
     setup.

2. **The public download story must be coherent**
   - `https://linguaviva.art` buttons must match the artifact they deliver: desktop app, CLI/browser
     app, or intentionally disabled state.
   - Button labels, release assets, installer scripts, and documentation must not imply a native
     desktop app if the actual artifact is only a CLI that serves localhost.
   - Any missing publish/release/signing/DNS work must be marked `ESCALATED` with exact operator action.

3. **Student lens creation must feel first-class**
   - The Students view must make it easy to create, select, inspect, and recover student lenses.
   - Empty roster, missing selected student, deleted data, invalid student id, and first observation
     states must be helpful.
   - Lens language must remain competence-based and publication-safe; no real names or deficit labels.

4. **Microphone note capture must be hardened**
   - Observe must handle unsupported browsers, permission denial, no speech recognized, partial
     transcript, edit-before-save, save failure, and save success.
   - After saving, the teacher must understand which local lens was updated and what stayed local.
   - The fallback typed-note path must be as usable as the microphone path.

5. **Trust surfaces should read as one coherent cockpit**
   - Why, Privacy, Profile/export/clear, Health/Doctor, and support bundle should agree with each other.
   - A teacher should be able to answer: what happened, what stayed on this machine, what left, what the
     app knows about me/my class, how to export it, how to delete it, and what to send support.
   - Do not add a new privacy architecture. Make the existing local-first architecture legible and
     internally consistent.

## PART 1: Desktop Setup Wizard (DO THIS FIRST)

### The Problem
Teachers on Windows download Lingua Viva, open it, and hit:
"Python check failed: python3 not found" → dead app. Same bug as Mission Canvas had.
The current `launchBackend()` in main.ts throws on Python failure. Game over.

### Reproduction / Inspection Requirement

Before changing the boot flow, prove the current failure shape in one of these
ways:

- Preferred: run or simulate a desktop start with `python3` unavailable and
  show that the old boot path falls into the dead progress/error state.
- Acceptable if the current machine cannot remove Python safely: cite the exact
  current code path in `desktop/electron/main.ts` and `bootstrap.ts` that calls
  `checkPython("python3")`, renders the failure, and throws before the app can
  recover.

Record this in the report as the "before" state. Do not spend more than 20
minutes trying to create a destructive local Python-free environment.

### What to Build

1. **`desktop/electron/setup-wizard.html`** — Guided onboarding page
   - Copy structure from MC's `setup-wizard.html`
   - Rebrand: Lingua Viva green palette (`#17463b` brand, `#f5f7f4` surface, `#ffffff` panel)
   - Title: "Lingua Viva" / subtitle: "Setting up your teacher workbench"
   - 3 steps: Python → Ollama → Server (same JS handler logic as MC)
   - "Install Python" button → silent install on Windows, opens python.org on Mac/Linux
   - "Skip" option for Ollama (not blocking)
   - Never shows an error screen. Always shows a next action.
   - Copy must make the first-run path clear: Lingua Viva runs locally; Python starts the local app;
     Ollama is optional/recommended for local reasoning; skipping Ollama should not feel like breaking
     the app.
   - Include explicit states for: checking, present, missing, installing, install failed, skipped,
     retry available, starting server, server failed, and app ready.
   - Avoid technical blame language. Say what the user can do next.

2. **Extend `desktop/electron/bootstrap.ts`**
   - Add `detectPython()` — tries `python`, `python3`, `py` (Windows-first order)
   - Add `downloadFile(url, dest, maxRedirects=10)` — HTTPS, follows redirects, 5min timeout
   - Add `installPythonWindows()` — downloads python-3.12.4-amd64.exe, `/quiet PrependPath=1`
   - Add `installOllamaWindows()` — downloads OllamaSetup.exe (3 redirects!), `/VERYSILENT`
   - Add `installPythonDeps(cmd, root)` — `python -m pip install --quiet pyyaml fastapi uvicorn httpx websockets`
   - Add `refreshWindowsPath()` — reads System + User PATH via PowerShell
   - Keep all process execution shell-safe. Do not introduce `shell: true` for paths that may contain
     spaces.
   - Ensure temp downloads are cleaned up on failure.

3. **Rewrite `desktop/electron/main.ts` boot flow** (lines 201-260)
   - Remove `launchBackend()` and the inline `progressHtml()` function
   - Replace with `runSetupFlow()` that:
     a. Loads setup-wizard.html immediately
     b. Runs `detectPython()` → on fail, pauses + shows install button
     c. Runs `checkOllama()` → on fail, shows install/skip
     d. Runs `installPythonDeps()` (non-fatal)
     e. Starts backend via existing `startBackend(root, PORT, pythonCmd)`
     f. Waits for health, loads real app URL
   - Add early-exit detection in backend wait loop
   - Keep window management, CSP, IPC handlers untouched
   - If setup cannot complete, keep the wizard open with recovery actions. Do not replace it with a
     raw stack trace, dead progress screen, or "Python not found" dead end.
   - Store the resolved Python command and pass that exact command into `startBackend(root, PORT,
     pythonCmd)`.
   - Keep Ollama non-blocking. Python is required to start the local server; Ollama is recommended for
     local reasoning, but skipping it must still continue.

4. **Extend `desktop/electron/preload.ts`**
   - Add: `installPython`, `retrySetup`, `installOllama`, `skipOllama`, `openExternal`, `onSetupProgress`
   - Validate URLs before opening external links. Only allow known Python/Ollama/help URLs.
   - Avoid exposing arbitrary shell or filesystem operations to the renderer.

5. **Update `desktop/package.json`**
   - Build script: add setup-wizard.html copy to `dist/electron/`
   - Verify `desktop/dist/electron/setup-wizard.html` exists after `npm run build`.

### Known Bugs to Pre-Fix (from MC sweep)

| # | Bug | Fix |
|---|-----|-----|
| 1 | `checkPython("python3")` fails on Windows | `detectPython()` with candidate list |
| 2 | Windows Store python alias hangs | 5s timeout in execFileText (verify kill) |
| 3 | Ollama download needs 3 redirects | `downloadFile` with recursive redirect, maxRedirects=10 |
| 4 | PATH not refreshed after Python install | `refreshWindowsPath()` reads System+User |
| 5 | pip deps missing → server ImportError | `installPythonDeps()` before server start |
| 6 | Backend dies → 45s useless polling | Detect process exit event, break poll |
| 7 | Paths with spaces break with shell:true | bootstrap.ts already doesn't use shell:true ✓ |
| 8 | macOS: no retry button after python.org | Emit progress event to show retry UI |

### Definition of Done (Part 1)

- `cd desktop && npm run build` succeeds
- setup-wizard.html present in `dist/electron/`
- No hardcoded `"python3"` in any spawn path (use resolved command)
- First-run copy clearly explains Python, Ollama, local-first behavior, and what still works if Ollama
  is skipped or missing
- On Windows without Python: wizard shows install button (don't need to run live — verify logic)
- On any platform with Python: wizard shows ✓, proceeds to Ollama
- Backend starts via `startBackend(root, PORT, resolvedCmd)`
- Missing Ollama offers install and skip, and skip proceeds to server startup
- Backend early exit is surfaced immediately with a retry or guidance state
- Existing tests still pass: `python3 -m pytest -q tests/`

If you cannot live-test Windows, say so plainly and include structural evidence:
the IPC handler, installer command, PATH refresh, retry path, and no-`python3`
spawn grep result.

## PART 2: Full Artifact Hardening (AFTER Part 1 ships)

Read `dev/specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md` in full — it has the complete
artifact inventory. Key areas:

- Live-verify `https://linguaviva.art` (HTTPS, download buttons, no dead links)
- Walk every teacher experience from the UI (not just API calls)
- Walk coordinator/admin views
- Verify install scripts (`sh -n install.sh`, PowerShell syntax check)
- Verify PWA/offline/service worker behavior
- Fix concrete defects, add regression tests
- Mark each artifact: PASS / FIXED / DEFERRED / ESCALATED

### Part 2 Method

Use this loop for each artifact. Keep the report open while you work.

1. **Inventory**: identify the UI button/view, route, script, workflow, doc, or live URL.
2. **Live-run**: exercise the entry point as a real user would. Use browser automation where helpful.
3. **Compare**: note what the product promises versus what actually happens.
4. **Decide**:
   - `PASS`: works and copy is honest.
   - `FIXED`: defect found and corrected in this pass.
   - `DEFERRED`: real product scope exists but should not be built now.
   - `ESCALATED`: requires operator credentials, release publishing, DNS, signing, or policy decision.
5. **Verify**: add/run the smallest meaningful test or live check.
6. **Record**: update the report row before moving on.

Do not batch 20 findings in your head. Write evidence as you go.

### Minimum Artifact Rows To Cover

Your report must include at least these rows, plus any additional artifact you
discover:

| Group | Rows |
|---|---|
| Public distribution | `https://linguaviva.art`, each visible download button, GitHub latest release, release workflow, install-test workflow, desktop packaging |
| Install/setup | `install.sh`, `install.ps1`, desktop setup wizard, Python detection, Ollama install/skip, pip deps, backend launch, CLI `serve`, CLI `health`, CLI `preflight`, CLI `doctor` |
| App shell/PWA | sidebar/nav, role switcher, keyboard/focus state, manifest, icons, service worker, offline page, share/offline queue if present |
| Teacher use cases | Home, Plan, Prepare, Observe microphone, Observe typed note, Students/lenses, Assess, Ask, Parents, Why, Privacy, Profile/export/clear, Provider Settings, File Map, Reflect, Quick Capture, Health/support bundle |
| Coordinator/admin | Programme, Evidence, Capacity, Trends |
| Backend/data | `src/web.py` route contracts, privacy log, request log, traces, support bundle, file map, provider config, student lens store, observation capture, parent report, assessment generator |
| Docs/status | README/install docs that affect users, `dev/INDEX.md`, relevant specs/reports that make status claims |

### Part 2 Priority Gates

Do the full umbrella inventory, but give extra attention to these five gates:

1. **First-run/onboarding/Ollama gate**
   - Verify desktop wizard, web first-run role modal, Provider Settings, Ollama missing state, model
     guidance, failed provider connect, and successful local startup all tell one coherent story.
   - Fix copy or state transitions that leave a non-technical teacher unsure what to do next.

2. **Download/publication gate**
   - Verify live site buttons, release asset names, installer target names, README/install docs, and
     desktop artifact story all align.
   - If the public site cannot be fixed from this repo/session, write the exact publish step needed.

3. **Student lens gate**
   - Live-walk creating or bootstrapping a lens, selecting a student, saving an observation into that
     lens, viewing the updated lens, and recovering from missing/empty student data.
   - If creating a lens is not actually available from the UI, either build the smallest first-class
     creation flow or mark it as a top-priority gap with a precise implementation note.

4. **Microphone observation gate**
   - Test browser support/no-support states, permission denial copy where possible, typed fallback,
     transcript edit, save success, and save failure.
   - Verify no external path is introduced for student observation text.

5. **Trust cockpit gate**
   - Cross-check Why, Privacy, Profile/export/clear, Health/Doctor, and support bundle against the same
     sample action.
   - Verify trace hashes, external-call counts, local data summary, export contents, clear behavior, and
     support bundle privacy do not contradict each other.
   - Fix inconsistencies or report them as ranked findings.

### Hard Rules (both parts)

- No real student data, institution names, or private school documents anywhere
- Do not modify Tier 1 governance
- Do not commit — leave everything staged for operator
- If you edit `static/index.html` or `src/web.py`, run
  `python3 scripts/check_ui_contract.py --bump`
- Use `python3 -m pytest -q tests/` for the full suite
- Do not claim `linguaviva.art` status from memory — verify live
- If something needs DNS/release/signing access, mark it ESCALATED

### Stop / Escalate Conditions

Stop broadening scope and write an `ESCALATED` row if any of these are true:

- Fixing the issue requires pushing, tagging, publishing a GitHub release,
  changing DNS/CDN hosting, code signing, or accessing accounts unavailable in
  the session.
- The apparent fix would change privacy/governance architecture instead of copy,
  UI state, route handling, packaging, or tests.
- The user-facing claim depends on data that is not in the repo or cannot be
  verified without private school documents.
- Windows-only behavior cannot be live-tested from the current machine. In that
  case, still do structural verification and name the manual Windows test.

Do not block Part 1 on Part 2 escalation. If the setup wizard compiles and the
local app can start, Part 1 can be marked complete even if public publishing
work remains escalated.

### Verification Before Closing

```bash
cd desktop && npm run build
cd .. && python3 -m pytest -q tests/
python3 -m src.lv_cli preflight
python3 scripts/check_ui_contract.py
python3 -m py_compile src/web.py src/lv_cli.py src/pwa.py
sh -n install.sh
python3 -m src.lv_cli serve 8787  # then walk it in browser
curl -I https://linguaviva.art
```

Add these checks when the relevant tools are available:

```bash
rg -n "python3" desktop/electron
rg -n "Still I Rise|sir-|7896|Mission Canvas" .
gh api repos/lingua-viva/learning-architecture/releases/latest
```

Interpretation rules:

- `rg -n "python3" desktop/electron` may find copy, docs, or fallback labels,
  but must not find a hardcoded backend spawn path that ignores detected Python.
- Rebrand grep hits may be legitimate in historical specs/reports; do not
  rewrite history. Fix only live product surfaces, installers, workflows, and
  current docs that a user would follow.
- If `gh` is unavailable or unauthenticated, use public GitHub release URLs via
  `curl` and record the limitation.

### Deliverables

1. Working setup wizard (Part 1) — the code changes described above
2. `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md` — full artifact inventory with
   status table, findings ordered by severity, fixes shipped with file refs, verification evidence
3. `dev/INDEX.md` updated for both specs (setup wizard + hardening)

The hardening report must include a separate section titled **Five Priority Gates** with the final
status of:
- first-run/onboarding/Ollama
- public download story
- student lens creation
- microphone note capture
- trust cockpit consistency

Use this report skeleton:

```markdown
# REPORT: LV Full Artifact Hardening

## Findings
| Severity | Finding | Evidence | Fix / next action |

## Part 1: Desktop Setup Wizard
| Check | Status | Evidence |

## Five Priority Gates
| Gate | Status | Evidence | Remaining action |

## Full Artifact Inventory
| Artifact | Entry point | Status | Evidence | Fix shipped or next action |

## Public Site And Downloads
| URL/button | Expected | Actual | Status | Evidence |

## Teacher And Coordinator Experiences
| Experience | Status | Evidence | Fix shipped or next action |

## Backend, Privacy, Support, Docs
| Artifact | Status | Evidence | Fix shipped or next action |

## Verification
| Command | Result |

## Factual Corrections To Prior Reports
None, or list exact correction.

## Operator Follow-Ups
None, or list exact action, owner, and blocker.
```

### Discipline

- Start with Part 1. Build the setup wizard. Verify it compiles. Then move to Part 2.
- When Part 1 compiles, pause long enough to record its status in the report before widening into
  artifact hardening.
- If the umbrella hardening surfaces something that needs a governance or product decision,
  stop and flag it — that's not a two-way door.
- Report back when each part converges. Don't go silent.
- The setup wizard is the thing that unblocks real testers TODAY. Everything else is important
  but not as urgent. Ship Part 1 with confidence before broadening scope.

### Final Response

Under 150 words. Include only:

- setup wizard status
- hardening report path
- top 3 remaining risks or "none"
- final test result

Do not restate the whole task.
```
