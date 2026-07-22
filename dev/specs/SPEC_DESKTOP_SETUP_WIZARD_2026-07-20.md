# SPEC: Lingua Viva Desktop Setup Wizard — Guided Onboarding (Never Fail)

**Date**: 2026-07-20
**Status**: READY FOR IMPLEMENTATION
**Author**: kiro.design (spec), operator (approval)
**Target repo**: `/home/mical/learning-architecture`
**Modeled on**: Mission Canvas desktop setup wizard (implemented same day, this repo)

---

## Problem Statement

Teachers and administrators downloading Lingua Viva hit the same wall Jason
hit with Mission Canvas today: Python 3 is not installed, the app shows a
cryptic error ("Python check failed"), and they're stuck. The app never
recovers. This has happened multiple times across multiple rebuild attempts.

The current Lingua Viva desktop boot (`desktop/electron/main.ts`, lines
201–260) calls `checkPython()` → on failure → renders an error in the progress
HTML → throws → the app is dead. Same pattern, same outcome, same user
abandonment.

**The principle**: An onboarding experience that fails is not an onboarding
experience. Hermes asks 10 questions before you start. We guide you through
setup — Python, Ollama, dependencies — with one-click installs. **Never fail.
Always guide.**

---

## Audience

- **Teachers** (non-technical, Windows laptops from the school)
- **Administrators** (slightly more technical, but not developers)
- No "professional vs personal" question needed — all users are educators

---

## What Already Exists (Do Not Rewrite)

| File | Purpose | Keep? |
|------|---------|-------|
| `desktop/electron/bootstrap.ts` | `checkPython()`, `checkOllama()`, `ensureOllamaModel()`, `startBackend()`, `waitForBackend()` | Keep — extend, don't replace |
| `desktop/electron/main.ts` | Boot flow, progress HTML, window management | **Rewrite boot flow only** (lines 201–260) |
| `desktop/electron/preload.ts` | IPC bridge (currently minimal) | Extend with setup IPC |
| `desktop/package.json` | Build config, electron-builder | Update build script |
| `install.sh` / `install.ps1` | Shell/PowerShell installers | Separate — not in scope |

---

## What to Build

### 1. Setup Wizard HTML (`desktop/electron/setup-wizard.html`)

A self-contained HTML page (no framework, no build step) that:

- Loads instantly as the first thing the user sees
- Shows 3 steps: Python → Ollama → Server
- Uses the Lingua Viva design language (green palette from `static/index.html`: `--brand: #17463b`, `--surface: #f5f7f4`, `--panel: #ffffff`)
- Each step has: icon, title, detail text, progress bar (optional)
- When a dep is missing: shows a friendly "Install" button, not an error
- When installing: shows spinner + progress
- When done: auto-transitions to the real app
- **No** "professional vs personal" question — everyone is a teacher/admin

Copy the MC setup-wizard.html structure and:
- Replace branding (color scheme, title "Lingua Viva", subtitle "Setting up your teacher workbench")
- Remove any MC-specific language
- Keep the same JS handler structure (`handleProgress`, step states, button actions)

### 2. Update `bootstrap.ts` — Add Windows Python Detection + Installers

The existing `checkPython(pythonCommand = "python3")` only tries one command.

**Add**:
```typescript
export async function detectPython(): Promise<{ ok: boolean; command: string; detail: string }> {
  // Try multiple commands — Windows doesn't have python3
  const candidates = process.platform === "win32"
    ? ["python", "python3", "py"]
    : ["python3", "python"];

  for (const cmd of candidates) {
    const result = await checkPython(cmd);
    if (result.ok) {
      return { ok: true, command: cmd, detail: result.detail };
    }
  }
  return { ok: false, command: "", detail: "Python 3.10+ not found" };
}
```

**Add timeout** to `execFileText` (already has 8000ms default — but Windows
Store aliases can hang, so verify it actually kills the process on timeout).

**Add installer functions** (port from MC):
- `installPythonWindows()` — downloads `python-3.12.4-amd64.exe`, runs `/quiet InstallAllUsers=0 PrependPath=1`, refreshes PATH
- `installOllamaWindows()` — downloads `OllamaSetup.exe` (follows 3 redirects via GitHub), runs `/VERYSILENT /NORESTART`, starts service
- `downloadFile(url, dest, maxRedirects=10)` — HTTPS with redirect following, timeout, proper cleanup
- `installPythonDeps(pythonCmd, repoRoot)` — `python -m pip install --quiet pyyaml fastapi uvicorn httpx websockets`

### 3. Rewrite `main.ts` Boot Flow (lines 201–260)

Replace `launchBackend()` with:

```typescript
async function runSetupFlow(root: string, window: BrowserWindow): Promise<void> {
  // Load wizard HTML
  const wizardPath = path.join(app.getAppPath(), app.isPackaged ? "dist/electron" : "electron", "setup-wizard.html");
  await window.loadFile(wizardPath);
  await sleep(300); // let renderer initialize

  // Step 1: Python
  emitProgress(window, "python", "Checking for Python...");
  const pythonResult = await detectPython();
  if (pythonResult.ok) {
    pythonCmd = pythonResult.command;
    emitProgress(window, "python_ok", pythonResult.detail);
  } else {
    emitProgress(window, "python_fail", "Python is needed to run Lingua Viva.");
    await waitForPythonResolution(); // pauses until user installs
  }

  // Step 2: Ollama
  emitProgress(window, "ollama", "Checking for Ollama...");
  // ... (same pattern as MC)

  // Step 3: Install deps + start server
  emitProgress(window, "server", "Installing dependencies...");
  await installPythonDeps(pythonCmd, root);
  emitProgress(window, "server", "Starting Lingua Viva...");
  // ... start backend, wait, load URL
}
```

Key differences from MC:
- `pythonCommand` is passed to `startBackend(root, PORT, pythonCmd)` — already supported by bootstrap.ts!
- Model pull: `ensureOllamaModel()` already exists — use it after Ollama is confirmed
- Backend spawn: bootstrap.ts already uses `spawn(pythonCommand, ...)` with `windowsHide: true` — correct
- **No `shell: true`** (bootstrap.ts doesn't use it — already safe for paths with spaces)

### 4. Update `preload.ts` — Expose Setup IPC

Add to the contextBridge:
```typescript
installPython: () => ipcRenderer.invoke("lv:setup:installPython"),
retrySetup: () => ipcRenderer.invoke("lv:setup:retryPython"),
installOllama: () => ipcRenderer.invoke("lv:setup:installOllama"),
skipOllama: () => ipcRenderer.invoke("lv:setup:skipOllama"),
openExternal: (url: string) => ipcRenderer.invoke("lv:setup:openExternal", url),
onSetupProgress: (callback) => {
  ipcRenderer.on("lv:setup:progress", (_event, payload) => callback(payload));
}
```

### 5. Update `package.json` Build Script

Change from `tsc -p tsconfig.json` to also copy setup-wizard.html:
```json
"build": "tsc -p tsconfig.json && node -e \"require('fs').copyFileSync('electron/setup-wizard.html','dist/electron/setup-wizard.html')\""
```

### 6. Update `electron-builder` `files` Array

Ensure `dist/electron/setup-wizard.html` is included (already covered by `dist/electron/**/*`).

---

## Bugs Already Known (Port from MC Hardening)

These were found during the MC 15-iteration sweep and apply identically here:

| # | Bug | Fix |
|---|-----|-----|
| 1 | `checkPython("python3")` fails on Windows (no `python3` command) | Use `detectPython()` with candidate list |
| 2 | Windows Store python alias hangs spawn | 5s timeout already in `execFileText` (verify kill works) |
| 3 | Ollama download needs 3 redirects | `downloadFile` with recursive redirect following |
| 4 | After Python install, PATH not refreshed | Refresh System + User PATH via PowerShell |
| 5 | pip deps not installed → server crashes with ImportError | Add `installPythonDeps` step before server start |
| 6 | Backend dies immediately → 45s useless polling | Detect `process.exit` event, break poll early |
| 7 | Paths with spaces (e.g. `C:\Users\Maria Rossi\`) | bootstrap.ts already uses `spawn()` without `shell:true` ✓ |
| 8 | macOS/Linux: no retry button after opening python.org | Emit `python_install_failed` to show retry UI |

---

## Definition of Done

- [ ] `cd desktop && npm run build` succeeds
- [ ] On Windows with no Python: wizard shows "Install Python" button, installs, proceeds
- [ ] On Windows with Python: wizard shows ✓, proceeds to Ollama check
- [ ] On macOS with no Python: wizard shows "Install Python" → opens python.org → shows retry
- [ ] Ollama missing: shows install/skip options, never blocks forever
- [ ] Server starts and loads the real UI (port 8787)
- [ ] The old `progressHtml()` inline boot screen is removed (replaced by wizard)
- [ ] No reference to hardcoded `"python3"` in any spawn path
- [ ] `desktop/dist/electron/setup-wizard.html` present after build

---

## What NOT to Change

- `install.sh` / `install.ps1` — separate distribution path, not this spec's scope
- The web app UI (`static/index.html`) — untouched
- `src/web.py` — the Python server itself
- The ontology, knowledge library, lenses, curriculum — no data layer changes
- Desktop electron-builder config (app signing, assets) — working, leave alone

---

## Execution Notes

- **Start by copying** `mission-canvas/desktop/electron/setup-wizard.html` and adapting the branding. This is the fastest path since the JS handler logic is identical.
- **The bootstrap.ts `checkPython` already takes a command parameter** — the multi-command detection just needs to wrap it. This is much easier than MC where everything was hardcoded.
- **The `startBackend` function already accepts `pythonCommand`** — no refactor needed, just pass the resolved command.
- **Test on a Windows machine** (or ask Jason to test the next build). The whole point is: Jason clicks the installer, sees the wizard, clicks "Install Python", waits 30s, and he's in.

---

## Commit Shape

Single commit:
```
feat(desktop): setup wizard — guided onboarding, never fail on missing deps

Same pattern as Mission Canvas (2026-07-20): detect → guide → install → proceed.
Teachers on Windows no longer hit a dead end when Python isn't installed.
Wizard handles Python, Ollama, and pip deps with one-click installs.
```
