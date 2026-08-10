# Lingua Viva Day-One Fresh-Install Walkthrough — 2026-08-10

## Verdict

- Run status: BLOCKED
- Highest severity: P0
- Release gate: HOLD
- Tested artifact: live-site Linux download, `desktop-v0.2.50` / `LinguaViva.AppImage`
- Target machine: Ubuntu 24.04.4 LTS, x86_64, Wayland session
- Required run environment: `ANTHROPIC_API_KEY` unset, `MC_AGENT=1`
- Fresh-state method: launched downloaded AppImage with isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME` under `/tmp/lv-day-one-2026-08-10/run-1786389561`
- Model state on actual machine: Ollama present; `qwen2.5:3b` present

The real day-one path did not reach the app. The desktop setup shell opened, but the packaged backend never reached `/api/health` because the fresh user environment had no installed FastAPI dependency and the setup flow did not successfully populate it.

## Source / Download Evidence

- Live site `https://linguaviva.art/` returned HTTP 200 and served only `desktop-v0.2.50`.
- Live page exposed the three expected download links:
  - `LinguaViva-Setup.exe`
  - `LinguaViva.AppImage`
  - `LinguaViva.dmg`
- `LinguaViva.AppImage` downloaded from the live link and was executed directly.
- Downloaded AppImage:
  - Path: `/tmp/lv-day-one-2026-08-10/LinguaViva.AppImage`
  - Size: 106 MiB
  - SHA-256: `641455e45d536067f0f55c0066ff579dfb56074cfa64134b66c7a2df447a9544`
- GitHub release metadata confirmed `desktop-v0.2.50` published `2026-08-10T14:01:36Z` with all three assets.

## Findings

| ID | Severity | User symptom | Evidence | Likely owner | Next action |
|----|----------|--------------|----------|--------------|-------------|
| D1-P0-001 | P0 | A fresh teacher install cannot reach Lingua Viva after first launch; the setup flow stalls/fails before the app opens. | Backend log at `/tmp/lv-day-one-2026-08-10/run-1786389561/fresh-home/.lingua-viva/logs/backend.log`; `src/web.py:32`; `desktop/electron/bootstrap.ts:361`; `desktop/electron/main.ts:170` and `desktop/electron/main.ts:205` | Desktop setup / packaging | Make dependency install fail hard with visible detail, and make fresh user dependency install actually populate the Python environment used to launch `src/web.py`. Retest with an empty user home. |

### D1-P0-001 — Fresh AppImage Launch Fails Before App Opens

Repro steps:

1. Start from the live site, not the checkout: download `https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.50/LinguaViva.AppImage`.
2. Mark executable with `chmod +x LinguaViva.AppImage`.
3. Launch with an empty user state:
   ```bash
   unset ANTHROPIC_API_KEY
   export MC_AGENT=1
   export HOME=/tmp/lv-day-one-2026-08-10/run-1786389561/fresh-home
   export XDG_CONFIG_HOME=/tmp/lv-day-one-2026-08-10/run-1786389561/xdg-config
   export XDG_DATA_HOME=/tmp/lv-day-one-2026-08-10/run-1786389561/xdg-data
   export XDG_CACHE_HOME=/tmp/lv-day-one-2026-08-10/run-1786389561/xdg-cache
   /tmp/lv-day-one-2026-08-10/LinguaViva.AppImage --no-sandbox
   ```
4. Probe `http://127.0.0.1:8787/api/health`.

Expected:

- Setup installs/verifies required server dependencies, starts the backend, and opens the app.
- If setup cannot install dependencies, the teacher sees a blocking setup error with enough detail to act.

Actual:

- `/api/health` never responds.
- Backend log repeats:
  ```text
  Traceback (most recent call last):
    File "/tmp/.mount_LinguaOK25Cm/resources/app/src/web.py", line 32, in <module>
      from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
  ModuleNotFoundError: No module named 'fastapi'
  ```
- Liveness check used output growth, not process presence:
  - AppImage stdout/stderr log stayed at `375` bytes across a 3 second interval.
  - Backend log stayed at `1265` bytes across a 3 second interval.

Source-line anchors:

- Backend import that fails: `src/web.py:32`
- Dependency list includes FastAPI: `desktop/electron/bootstrap.ts:302` through `desktop/electron/bootstrap.ts:334`
- Dependency installer resolves even after all pip attempts fail: `desktop/electron/bootstrap.ts:361` through `desktop/electron/bootstrap.ts:367`
- Setup warns on missing server dependencies but continues to start backend: `desktop/electron/main.ts:170` through `desktop/electron/main.ts:181`
- Setup eventually emits generic server failure after backend cannot become healthy: `desktop/electron/main.ts:204` through `desktop/electron/main.ts:208`

Screenshot:

- Not captured. GNOME denied the noninteractive screenshot request with `org.freedesktop.DBus.Error.AccessDenied: Screenshot is not allowed`. The backend log above is the primary evidence.

## Walkthrough Coverage

Completed:

- Live-site download path.
- Fresh-state first launch using the downloaded AppImage.
- Real machine model inventory: Ollama is installed and `qwen2.5:3b` is present.
- Backend liveness checked by output growth and HTTP health probe.

Blocked by D1-P0-001:

- Empty-state app UX.
- Onboard student and PoI.
- Capture observation.
- Lesson materials.
- Parent report.
- Safeguarding must-flag restricted-ledger check.
- Student-lens non-leak check.
- No-local-model honest banner/no-fake-answer path.
- With-local-model answer path.

Not applicable on this target:

- macOS Gatekeeper first-run behavior. This run was on Ubuntu; the live DMG link resolves, but Gatekeeper/signing behavior cannot be exercised on this machine.

## Known Operator-Blocked Items

Not flagged:

- Slack/Drive escalation values.
- Perplexity key / `LV_ALLOW_RESEARCH=1`.

The run failed before reaching any path that depends on these values.

## Retest Scenario For Closure

1. On a machine or isolated user state with no Lingua Viva config and no Python user-site Lingua Viva dependencies, download the live AppImage from `https://linguaviva.art/`.
2. Launch the downloaded artifact with `ANTHROPIC_API_KEY` unset and `MC_AGENT=1`.
3. Confirm setup reaches `/api/health`.
4. Continue the day-one teacher path: empty state, student + PoI, observation, lesson materials, parent report, restricted safeguarding ledger, student-lens non-leak, no-model honesty, and model-present behavior.
