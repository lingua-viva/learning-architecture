# SPEC: Lingua Viva Full Artifact Hardening

**Date**: 2026-07-20
**Status**: DRAFT - execution handoff
**Companion prompt**: `dev/EXECUTION_PROMPT_LV_FULL_ARTIFACT_HARDENING_2026-07-20_CODEX.md`
**Expected report**: `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`

## 0. Purpose

This is the umbrella hardening pass for Lingua Viva. The goal is not to add
another feature tier. The goal is to make every artifact a real teacher,
coordinator, or operator can touch feel publishable, correct, and recoverable:

- `https://linguaviva.art` resolves, presents the right product, and its app
  download buttons do what they say.
- The GitHub release/download/install path is coherent across macOS, Windows,
  Linux, CLI, desktop, and source fallback.
- First run is humane: opening the app works, local-first defaults are clear,
  Ollama absence is handled without a dead end, and model download guidance is
  concrete.
- Every in-app use case that exists today is live-walked, not assumed from
  source: planning, preparation, microphone notes, observation capture, student
  lenses, assessments, parent drafts, Why, Privacy, Profile/export/clear,
  Provider settings, File Map, Reflect, Quick Capture, Health/Doctor, support
  bundle, PWA/offline/share, and coordinator/admin views.
- Every repo artifact that supports those experiences is either hardened,
  explicitly deferred with evidence, or marked for operator decision.

This pass should ship code fixes where the fix is clear and low-to-medium risk.
It should not silently widen the product. If an experience does not exist, do
not invent it; mark the absence as a gap or deferred item with a concrete
recommendation.

## 1. Required Reading

Read these before making changes:

1. `CLAUDE.md` - publication safety, repo architecture, runtime boundaries.
2. `dev/INDEX.md` - current spec/report status and companion artifacts.
3. `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md` - download button and
   release artifact contract, including unfinished phases.
4. `dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` and
   `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` -
   installer and release-script findings already handled or deferred.
5. `dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` and
   `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` - P0 behavior
   already verified and fixed.
6. `dev/reports/REPORT_LV_CLAUDIA_LENS_HARDENING_2026-07-20.md` - latest
   craft/copy hardening already applied.
7. `static/index.html`, `src/web.py`, `src/pwa.py`, `static/sw.js`,
   `static/offline.html`, `install.sh`, `install.ps1`, `.github/workflows/`,
   `desktop/package.json`, `desktop/electron/main.ts`.

Do not re-litigate already settled conclusions unless live verification proves
they are now false. If a prior report is wrong, call that out as a factual
correction in the final report.

## 2. Hard Constraints

- No real student data, institution names, colleague names, or private school
  documents in tests, screenshots, reports, logs, support bundles, or examples.
- Do not modify Tier 1 governance rules.
- Do not change Lingua Viva's protection model from architectural exclusion to
  runtime interception.
- Leave all changes uncommitted. The operator holds the commit window.
- If `static/index.html` or `src/web.py` changes, run
  `python3 scripts/check_ui_contract.py --bump`, then verify the contract.
- Use `python3 -m pytest -q tests/`, not bare `pytest`, unless you have a
  specific reason and record it.
- Treat `linguaviva.art`, GitHub release URLs, and installer downloads as live
  external surfaces. Verify them during execution, but do not claim their status
  from memory.
- Do not present proposed or deferred work as validated. Status labels must be
  honest.

## 3. Artifact Gauntlet

For each artifact or experience below, run the same gauntlet:

1. Inventory the real entry points from source and the running app.
2. Live-run the entry point the way a user would.
3. Record actual copy, links, response state, error state, and recovery path.
4. Compare against the expected product promise.
5. Fix clear defects. Do not fix vague preferences.
6. Add or update regression coverage for fixed behavior.
7. Re-run the live path after the fix.
8. Mark the row `PASS`, `FIXED`, `DEFERRED`, or `ESCALATED`.

The final report must include a table with every row below and any additional
artifact discovered during inventory.

## 4. Required Artifact Inventory

### Public Distribution

| Artifact | Required checks |
|---|---|
| `https://linguaviva.art` | HTTPS 200, correct title/metadata, no stale product names, no dead assets, mobile and desktop rendering, no private or inflated claims, no broken visible CTAs. |
| Download buttons | macOS, Windows, Linux labels match actual assets; links resolve with HEAD/GET; disabled states are explicit and honest; no "download app" promise if only a CLI binary is delivered. |
| GitHub releases | Latest release assets match installer expectations; asset names, versions, checksums if present, and published tag are coherent. |
| `.github/workflows/release.yml` | Builds the artifacts the site and installers promise; smoke checks prove the binaries start and expose health. |
| `.github/workflows/install-test.yml` | Exercises meaningful install behavior; gaps for macOS/Windows are named or covered. |
| `desktop/` | Electron build contract is checked: bundled resources, Python/runtime dependency story, current version, output assets, and whether desktop is publishable or deferred. |

### Install And First Run

| Artifact | Required checks |
|---|---|
| `install.sh` | OS/arch detection, binary fallback, source fallback, idempotency, port conflict handling, Ollama detection, model pull guidance, provider config permissions, launcher creation, useful error output. |
| `install.ps1` | Same as `install.sh`, plus PowerShell syntax/structural checks and Windows-specific launcher/shortcut behavior where possible. |
| CLI entry points | `python3 -m src.lv_cli health`, `preflight`, `serve 8787`, `doctor`, and any advertised command work from repo root. |
| First app open | Role selection, local-first copy, no required API key, Provider/Ollama state, failed-provider recovery, default usable path when Ollama is missing. |

### App Shell And PWA

| Artifact | Required checks |
|---|---|
| Sidebar/nav | Teacher/admin/utility inventory, role switching, active state, keyboard focus, `aria-current`, no layout shift, mobile usability. |
| PWA manifest | Name, icons, shortcuts, start URL, display mode, screenshots if present, no stale labels. |
| Service worker/offline | App shell cached, API behavior honest offline, queued query behavior works or is clearly disabled, no misleading "saved" copy. |
| Offline page | Accurate product name, useful recovery, no dead actions. |

### Teacher Experiences

| Experience | Entry point | Required checks |
|---|---|---|
| Home / Daily Brief | Home view, `/api/brief`, `/api/teacher/today` | Brief copy, observation reminders, schedule input, student names from synthetic/local lenses only, no stale or deficit language. |
| Plan | Plan view, curriculum endpoints | Unit selection, grade change, source citation, empty/loading/error states. |
| Prepare / Activity Pack | Prepare view, `/api/prepare/activity` | Generated activity is classroom-usable, timeout copy, source citation, no invented student data, local-provider behavior. |
| Observe / Microphone Notes | Observe view, browser SpeechRecognition path, `/api/observe/capture` | Mic availability/fallback, permission denial, transcript editing, save confirmation, local-only copy, student-lens attachment. |
| Students / Student Lenses | Students view, `/api/students`, `/api/students/{id}/lens`, `/api/students/unobserved` | Creating/finding/selecting lenses is easy; empty roster is helpful; trajectory/tier language is asset-based; no real names. |
| Assess | Assess view, `/api/assess/rubric/{unit_id}` | Rubric language, band descriptors, student-safe assessment framing, grade/unit mismatch handling. |
| Ask | Ask view, `/api/query` | Routing, loading, failure, privacy trace, source citation, non-streamed response behavior, timeout/retry. |
| Parents | Parents view, `/api/parents/recommendation` | Draft warmth, teacher-edit stance, name/AI-attribution stripping, no "send" illusion, home activities practical. |
| Why | Why view, `/api/why` | Trace display uses hashes, no raw private query text, plain-language explanation, selected trace behavior. |
| Privacy | Privacy view, `/api/privacy`, `/api/publication/status` | External-call counts are real, publication safety copy is accurate, no unsupported guarantees. |
| Profile / Export / Clear | Profile view, `/api/profile`, `/api/profile/export`, `/api/profile/clear` | Export completeness, typed-confirmation clear, recovery copy, local-only scope. |
| Provider Settings | Settings view, `/api/provider`, `/api/provider/connect`, `/api/provider/disconnect` | Ollama absent/present states, API-key validation-before-save, model copy, local default remains usable. |
| File Map | File Map view, `/api/filemap/*` | Scan/exclude/clear behavior, student-zone exclusion, path display, empty/error states. |
| Reflect | Reflect view, `/api/reflect/note` | Local journal save, no accidental external route, helpful saved-state copy. |
| Quick Capture | Floating quick capture, `/api/query` with intent override | Two-click capture, deterministic trace toast, disabled/loading states, privacy promise accurate. |
| Health / Doctor | Health view, `/api/health`, `/api/support-bundle`, CLI doctor | Status classes, support bundle privacy, actionable WARN/PRIVATE_RISK states, no private upload. |

### Coordinator/Admin Experiences

| Experience | Entry point | Required checks |
|---|---|---|
| Programme | Admin/coordinator Programme, `/api/admin/programme` | Honest maturity, source clarity, no institution-specific claims. |
| Evidence | `/api/admin/evidence` | If deferred, copy is clear; if implemented, data is real and source-backed. |
| Capacity | `/api/admin/capacity` | Same deferred/implemented honesty; no staffing or colleague specifics. |
| Trends | `/api/admin/trends` | Same deferred/implemented honesty; no unsupported analytics claims. |

### Backend And Data Artifacts

| Artifact | Required checks |
|---|---|
| `src/web.py` API surface | Every route has sane success/error responses, JSON shapes match UI assumptions, no private data leakage in logs or paths. |
| `src/lingua_viva/*` | Privacy log, request log, traces, reasoning, publication status, support bundle, file map, config, provider state. |
| `src/education/*` | Student lens, observation capture, parent report, assessment, content differentiator, morning brief, curriculum service. |
| `doctor/*` | Artifact gauntlet, support loop, privacy checks, local-only bundle behavior. |
| `contracts/UI_CONTRACT.*` | Lockfile matches any UI change and contract tests cover the changed surface. |
| Docs/specs/reports | `dev/INDEX.md` status truth, no stale claims, no hidden TODO that affects user-facing correctness. |

## 5. Implementation Rules

- Prefer fixing actual defects over producing a long audit with no changes.
- Keep changes closely scoped to each artifact. Avoid broad refactors unless a
  shared helper clearly prevents repeated bugs.
- Every shipped fix gets one of: unit test, integration/API test, UI contract
  assertion, script syntax check, live curl/browser verification, or a written
  reason why automated coverage is not possible in this environment.
- If a live-site or release issue requires publishing, tagging, or DNS/CDN
  access unavailable in this session, do not fake it. Mark it `ESCALATED` with
  exact operator action needed.
- If an artifact is intentionally deferred, make the user-facing copy honest
  and record the deferral. Do not bury deferred behavior behind optimistic copy.

## 6. Verification Commands

Minimum verification before closing:

```bash
python3 -m pytest -q tests/
python3 -m src.lv_cli preflight
python3 scripts/check_ui_contract.py
python3 -m py_compile src/web.py src/lv_cli.py src/pwa.py
sh -n install.sh
```

Also run the app and live-walk it:

```bash
python3 -m src.lv_cli serve 8787
curl -fsS http://127.0.0.1:8787/api/health
curl -fsS http://127.0.0.1:8787/ | head
```

For live distribution:

```bash
curl -I https://linguaviva.art
curl -fsSL https://linguaviva.art | head
gh api repos/lingua-viva/learning-architecture/releases/latest
```

Use browser automation or screenshots for responsive/PWA/sidebar checks when
available. Record exact commands and outcomes in the report.

## 7. Deliverables

1. `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`
   - Findings first, ordered by severity.
   - Full artifact inventory table with `PASS` / `FIXED` / `DEFERRED` /
     `ESCALATED`.
   - Public site/download verification table with exact URLs, status codes,
     and timestamps.
   - Onboarding/Ollama verification table.
   - Per-experience table for all teacher and coordinator views.
   - List of fixes shipped, with file references.
   - Test/live-verification evidence.
   - Factual corrections to earlier specs/reports, if any.
   - Operator-only follow-up actions, if any.
2. Code/docs/tests changed as needed.
3. `dev/INDEX.md` updated from this spec's DRAFT row to the real outcome when
   execution completes.

## 8. Definition Of Done

- Every required artifact row has evidence.
- The app starts locally and every advertised in-app experience has been
  walked from the UI, not only via direct API calls.
- `linguaviva.art` and download buttons are either verified correct or
  escalated with exact publication/release work needed.
- First-run and Ollama-missing flows leave the user with a usable next step.
- Student lens creation/selection, microphone note capture, and parent draft
  generation are easy enough for a teacher to recover from ordinary mistakes.
- All fixed behavior has regression coverage appropriate to risk.
- Full test suite and required verification commands are recorded.
- Publication safety is preserved.
- No commit is made.
