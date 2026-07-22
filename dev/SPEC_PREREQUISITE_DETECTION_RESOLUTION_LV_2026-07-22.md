# SPEC: Prerequisite Detection & Resolution — Lingua Viva Desktop (LV-SETUP-PREREQ)

**Date**: 2026-07-22
**Status**: APPROVED — ready to build (LV is not mid-build; safe to implement)
**Author**: kiro.design
**Trigger**: Mac onboarding hangs at Python download — same bug as MC desktop
**Scope**: `desktop/electron/main.ts`, `desktop/electron/setup-wizard.html`, `desktop/electron/preload.ts`
**Risk level**: LOW — isolated to onboarding flow; cannot affect running app
**Sibling spec**: `mission-canvas/dev/SPEC_PREREQUISITE_DETECTION_RESOLUTION_2026-07-22.md`

---

## 1. The Problem (Observed)

On a fresh Mac with no Python installed, the Lingua Viva desktop app:

1. Opens the setup wizard (correct)
2. Detects "Python 3 not found" (correct)
3. Shows two buttons: "Install Python (automatic)" and "I'll install it myself"
4. **"Install Python (automatic)" opens python.org** — it's NOT automatic on macOS
5. Emits `python_install_failed` with message "Download Python from the site that just opened, then click retry below"
6. Shows "Open python.org" and "I've installed it — check again"
7. **Both visible primary actions open the same URL. The user is stuck.**

The `retrySetup` → `lv:setup:retryPython` bridge IS wired correctly in `preload.ts`. The retry button does work IF the user:
- Notices the browser opened (may be behind the app window)
- Navigates to the right download on python.org
- Downloads the .pkg (which one? macOS universal? ARM? Intel?)
- Runs the installer
- Comes back to the LV window
- Clicks "I've installed it — check again"

**That's 6 steps with zero guidance.** A teacher (the target user) will not complete this.

### Root Cause

Same as MC: the setup flow was designed Windows-first. On macOS, `installPython` degrades to "open a website" — which is a dead end for non-technical users.

---

## 2. What Lingua Viva Needs That MC Doesn't

LV's target users are **teachers**, not developers. They are:
- Non-technical (no terminal experience)
- On macOS (Italian/European school systems commonly use MacBooks)
- Likely don't have Homebrew, Xcode CLT, or any developer tools
- Need the install to WORK with one click or fail clearly with one action to fix it

This means:
- Xcode Command Line Tools is NOT the right primary path (teachers don't know what "command line tools" are)
- Homebrew is NOT appropriate (they don't have it and shouldn't need it)
- The .pkg installer IS the right answer — but it must be downloaded and opened FOR them

---

## 3. LV Prerequisites

| Prerequisite | Why | Blocking? | macOS Resolution |
|---|---|---|---|
| **Python 3.11+** | Backend (lv_cli.py, web.py) | ✅ YES | Auto-download .pkg + open |
| **pip** | Install deps (fastapi, pdfplumber, etc.) | ✅ YES | Comes with Python .pkg |
| **Python deps** | fastapi, uvicorn, pyyaml, pdfplumber, sqlite-vec | ✅ YES | `pip install` (automatic after Python) |
| **Ollama** | Local AI reasoning (lesson plans, assessments) | ❌ NO (app works without) | Download .dmg/zip + open |
| **Ollama model** | Actual inference | ❌ NO | `ollama pull qwen2.5:3b` (automatic if Ollama running) |

### Dependency Graph

```
Python 3.11+ → pip → Python deps → LV Server (port 8787) → Ready
                                         ↑
Ollama (optional) → Model pulled ───────┘ (enables AI features)
```

---

## 4. Revised macOS Flow

### 4.1 Python on macOS — Auto-Download + Open

Instead of opening python.org and hoping the user figures it out, **download the .pkg directly and open it**:

```typescript
async function installPythonMacOS(): Promise<void> {
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
  // Python.org provides universal2 .pkg installers that work on both architectures
  const pkgUrl = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-macos11.pkg";
  const dest = path.join(os.tmpdir(), "python-3.12.4-macos11.pkg");

  emitProgress(window, "python_installing", "Downloading Python installer...");
  await downloadFile(pkgUrl, dest);
  
  emitProgress(window, "python_installing", "Opening installer — follow the prompts...");
  // Open the .pkg — macOS Installer.app handles the GUI
  spawn('open', [dest], { detached: true }).unref();
  
  // Start polling for Python to appear
  startPythonPolling();
}
```

**What the user sees**:
1. Click "Install Python"
2. Progress: "Downloading Python installer..."  (~30s)
3. macOS Installer.app opens with familiar "Continue → Install → Done" flow
4. User clicks through the standard macOS installer (they know this pattern)
5. Wizard auto-detects Python and advances (no "retry" click needed)

### 4.2 Background Polling (Auto-Detection After Install)

Once any install is triggered, poll every 2 seconds:

```typescript
let pythonPollTimer: NodeJS.Timeout | null = null;

function startPythonPolling(): void {
  emitProgress(window, "python_polling", 
    "We'll continue automatically once Python is installed...");
  
  pythonPollTimer = setInterval(async () => {
    const result = await detectPython();
    if (result.ok) {
      clearInterval(pythonPollTimer!);
      pythonPollTimer = null;
      emitProgress(window, "python_installed", result.detail);
      pythonResolved = true;
      resolveWait(result.command);
    }
  }, 2000);

  // Timeout after 5 minutes
  setTimeout(() => {
    if (pythonPollTimer) {
      clearInterval(pythonPollTimer);
      emitProgress(window, "python_install_failed",
        "Python installer may still be running. Click below when it's done.");
    }
  }, 300000);
}
```

### 4.3 Ollama on macOS — Direct Download + Open

Same pattern — don't open ollama.com. Download the installer and open it:

```typescript
async function installOllamaMacOS(): Promise<void> {
  // Ollama distributes a .zip containing Ollama.app for macOS
  const zipUrl = "https://ollama.com/download/Ollama-darwin.zip";
  const dest = path.join(os.tmpdir(), "Ollama-darwin.zip");

  emitProgress(window, "ollama_installing", "Downloading Ollama...");
  await downloadFile(zipUrl, dest);
  
  emitProgress(window, "ollama_installing", "Installing Ollama...");
  // Unzip to /Applications (or ~/Applications)
  execSync(`unzip -o -q "${dest}" -d "${os.homedir()}/Applications/"`, { timeout: 30000 });
  
  // Launch Ollama.app (it auto-starts the daemon)
  spawn('open', [`${os.homedir()}/Applications/Ollama.app`], { detached: true }).unref();
  
  // Poll for Ollama daemon to come alive
  startOllamaPolling();
  
  // Clean up zip
  try { fs.unlinkSync(dest); } catch {}
}
```

### 4.4 Python Path Detection (macOS-specific)

After installation, Python may not be on PATH in the Electron process. Check standard locations:

```typescript
async function detectPython(): Promise<{ ok: boolean; command: string; detail: string }> {
  // Standard paths where Python installs on macOS
  const candidates = [
    'python3',                                    // PATH (if refreshed)
    '/usr/local/bin/python3',                     // python.org .pkg installs here
    '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3',  // Framework install
    '/opt/homebrew/bin/python3',                  // Homebrew (Apple Silicon)
    '/usr/bin/python3',                           // Xcode CLT
  ];
  
  for (const cmd of candidates) {
    try {
      const version = await tryPythonCmd(cmd);
      return { ok: true, command: cmd, detail: `Python ${version} found` };
    } catch { /* try next */ }
  }
  
  return { ok: false, command: '', detail: 'Python not found' };
}
```

---

## 5. Revised Setup Wizard UI

### 5.1 Python Missing (macOS) — New Button Layout

```
┌─────────────────────────────────────────────────┐
│  ① Python                                    !  │
│  Python is needed to run Lingua Viva.           │
│                                                 │
│  ┌─────────────────────────────────────┐       │
│  │  Install Python                      │       │
│  │  (Downloads the installer — you'll   │       │
│  │   see a familiar "Install" dialog)   │       │
│  └─────────────────────────────────────┘       │
│                                                 │
│  We'll continue automatically once it's done.   │
└─────────────────────────────────────────────────┘
```

**One button. One action.** No "I'll install it myself." No "Open python.org." The button downloads the .pkg and opens it. The wizard polls and advances automatically.

### 5.2 Python Installing (auto-polling active)

```
┌─────────────────────────────────────────────────┐
│  ① Python                                    ⟳  │
│  Python installer is running — click "Install"  │
│  in the dialog that opened, then we'll          │
│  continue automatically.                        │
│  ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░ polling...               │
└─────────────────────────────────────────────────┘
```

### 5.3 Ollama Missing — New Button Layout

```
┌─────────────────────────────────────────────────┐
│  ② Ollama (local AI — optional)              !  │
│  Adds AI reasoning for lesson planning and      │
│  assessments. The app works without it.         │
│                                                 │
│  ┌─────────────────────────────────────┐       │
│  │  Install Ollama                      │       │
│  │  (One-click download)                │       │
│  └─────────────────────────────────────┘       │
│                                                 │
│  ┌─────────────────────────────────────┐       │
│  │  Skip — I'll add it later            │       │
│  └─────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

---

## 6. Complete `main.ts` Changes

### 6.1 Replace `waitForPythonResolution` (lines 183-228)

**Current**: On macOS, opens python.org and waits for manual retry.
**New**: Downloads .pkg, opens it, polls automatically.

```typescript
function waitForPythonResolution(window: BrowserWindow): Promise<string> {
  return new Promise((resolve) => {
    let pollTimer: NodeJS.Timeout | null = null;
    
    const startPolling = () => {
      pollTimer = setInterval(async () => {
        const result = await detectPython();
        if (result.ok) {
          cleanup();
          emitProgress(window, "python_installed", result.detail);
          resolve(result.command);
        }
      }, 2000);
      
      // 5-minute timeout
      setTimeout(() => {
        if (pollTimer) {
          clearInterval(pollTimer);
          emitProgress(window, "python_install_failed",
            "Still waiting. If the installer finished, try closing and reopening Lingua Viva.");
        }
      }, 300000);
    };
    
    const handleInstall = async () => {
      if (process.platform === "win32") {
        // Existing Windows flow — unchanged
        emitProgress(window, "python_installing", "Downloading Python 3.12...");
        try {
          await installPythonWindows();
          emitProgress(window, "python_install_progress", "90");
          emitProgress(window, "python_installed", "Python 3.12 installed");
          cleanup();
          const recheck = await detectPython();
          resolve(recheck.ok ? recheck.command : "python");
        } catch (err) {
          emitProgress(window, "python_install_failed", 
            String(err instanceof Error ? err.message : err));
        }
      } else {
        // macOS/Linux: download .pkg directly, open it, poll
        emitProgress(window, "python_installing", "Downloading Python installer...");
        try {
          const pkgUrl = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-macos11.pkg";
          const dest = path.join(os.tmpdir(), "python-3.12.4-macos11.pkg");
          await downloadFile(pkgUrl, dest);
          
          emitProgress(window, "python_installing",
            "Opening installer — follow the prompts, then we'll continue automatically.");
          spawn('open', [dest], { detached: true }).unref();
          startPolling();
        } catch (err) {
          // Download failed — fall back to opening website
          shell.openExternal("https://www.python.org/downloads/");
          emitProgress(window, "python_install_failed",
            "Download failed — install from the page that opened, then we'll detect it automatically.");
          startPolling();
        }
      }
    };

    const handleRetry = async () => {
      emitProgress(window, "python", "Checking again...");
      const recheck = await detectPython();
      if (recheck.ok) {
        cleanup();
        emitProgress(window, "python_installed", recheck.detail);
        resolve(recheck.command);
      } else {
        emitProgress(window, "python_install_failed",
          "Not found yet. The installer may still be running.");
      }
    };

    const cleanup = () => {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      ipcMain.removeHandler("lv:setup:installPython");
      ipcMain.removeHandler("lv:setup:retryPython");
    };

    ipcMain.handle("lv:setup:installPython", handleInstall);
    ipcMain.handle("lv:setup:retryPython", handleRetry);
  });
}
```

### 6.2 Replace `waitForOllamaResolution` (current: opens website and immediately resolves)

**Current**: On macOS, opens ollama.com and skips. User never gets Ollama.
**New**: Downloads Ollama.app, installs it, polls for daemon.

```typescript
function waitForOllamaResolution(window: BrowserWindow): Promise<void> {
  return new Promise((resolve) => {
    let pollTimer: NodeJS.Timeout | null = null;
    
    const startOllamaPolling = () => {
      pollTimer = setInterval(async () => {
        try {
          const status = await checkOllama();
          if (status.ok) {
            cleanup();
            emitProgress(window, "ollama_installed", status.detail || "Ollama ready");
            resolve();
          }
        } catch { /* keep polling */ }
      }, 2000);
      
      setTimeout(() => {
        if (pollTimer) {
          clearInterval(pollTimer);
          // Timeout — skip and continue
          cleanup();
          emitProgress(window, "ollama_skipped");
          resolve();
        }
      }, 120000); // 2 minutes for Ollama
    };
    
    const handleInstall = async () => {
      if (process.platform === "win32") {
        // Existing Windows flow
        emitProgress(window, "ollama_installing", "Downloading Ollama...");
        try {
          await installOllamaWindows();
          emitProgress(window, "ollama_installed", "Ollama installed");
          cleanup();
          resolve();
        } catch {
          cleanup();
          emitProgress(window, "ollama_skipped");
          resolve();
        }
      } else if (process.platform === "darwin") {
        emitProgress(window, "ollama_installing", "Downloading Ollama...");
        try {
          const zipUrl = "https://ollama.com/download/Ollama-darwin.zip";
          const dest = path.join(os.tmpdir(), "Ollama-darwin.zip");
          await downloadFile(zipUrl, dest);
          
          emitProgress(window, "ollama_installing", "Installing Ollama app...");
          const appDest = path.join(os.homedir(), "Applications");
          fs.mkdirSync(appDest, { recursive: true });
          execSync(`unzip -o -q "${dest}" -d "${appDest}/"`, { timeout: 30000 });
          
          // Launch Ollama.app — it starts the daemon automatically
          spawn('open', [path.join(appDest, 'Ollama.app')], { detached: true }).unref();
          
          try { fs.unlinkSync(dest); } catch {}
          
          emitProgress(window, "ollama_installing", 
            "Ollama is starting — this takes a moment the first time...");
          startOllamaPolling();
        } catch (err) {
          // Download failed — fall back to opening website
          shell.openExternal("https://ollama.com/download");
          cleanup();
          emitProgress(window, "ollama_skipped");
          resolve();
        }
      } else {
        // Linux: run the official install script
        emitProgress(window, "ollama_installing", "Installing Ollama...");
        try {
          execSync('curl -fsSL https://ollama.com/install.sh | sh', 
            { timeout: 120000, stdio: 'pipe' });
          emitProgress(window, "ollama_installed", "Ollama installed");
          cleanup();
          resolve();
        } catch {
          shell.openExternal("https://ollama.com/download");
          cleanup();
          emitProgress(window, "ollama_skipped");
          resolve();
        }
      }
    };

    const handleSkip = () => {
      cleanup();
      emitProgress(window, "ollama_skipped");
      resolve();
    };

    const cleanup = () => {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      ipcMain.removeHandler("lv:setup:installOllama");
      ipcMain.removeHandler("lv:setup:skipOllama");
    };

    ipcMain.handle("lv:setup:installOllama", handleInstall);
    ipcMain.handle("lv:setup:skipOllama", handleSkip);
  });
}
```

### 6.3 Enhance `detectPython` with macOS-specific paths

Add `/usr/local/bin/python3` and `/Library/Frameworks/Python.framework/Versions/*/bin/python3` to the candidate list — the python.org .pkg installs there, not on PATH within the Electron process.

---

## 7. Revised `setup-wizard.html` Changes

### 7.1 Python fail state — single button, clear messaging

Replace the current two-button layout:

```javascript
case 'python_fail':
  state.python = 'missing';
  setStep(els.pythonStep, 'needs-action');
  setIcon(els.pythonStep, '!');
  els.pythonDetail.textContent = 'Python is needed to run Lingua Viva.';
  showAction(`
    <button class="btn btn-primary" onclick="installPython()">
      Install Python
    </button>
    <p style="color: var(--text-muted); font-size: 12px; margin-top: 10px;">
      Downloads the installer (~30MB) — you'll see a familiar "Install" dialog.
    </p>
  `);
  break;
```

### 7.2 New polling state

```javascript
case 'python_polling':
  setStep(els.pythonStep, 'active');
  setIcon(els.pythonStep, '⟳');
  els.pythonDetail.textContent = detail || 'Waiting for Python install to finish...';
  showAction(`
    <p style="color: var(--text-muted); font-size: 13px;">
      Follow the installer prompts — we'll continue automatically.
    </p>
    <button class="btn btn-secondary" onclick="retryPython()" style="margin-top: 12px;">
      Check now
    </button>
  `);
  break;
```

---

## 8. Edge Cases

| Edge Case | Mitigation |
|---|---|
| .pkg download fails (network) | Fall back to opening python.org + start polling |
| Gatekeeper blocks .pkg from untrusted developer | python.org packages are signed by PSF — Gatekeeper allows them |
| User dismisses macOS installer without completing | Polling continues; shows "Check now" button after 2 min |
| Python installs to non-standard location | detectPython checks 5 standard macOS paths |
| Ollama.app Gatekeeper warning on first open | First-launch Gatekeeper dialog is normal; user clicks "Open" |
| Ollama daemon takes >30s to start on first launch | Polling continues for 2 minutes before auto-skipping |
| Port 8787 already in use | Existing `server_fail` handler covers this |
| ARM vs Intel Mac | python.org .pkg is universal (macos11.pkg works on both) |
| User closes wizard and reopens app | Full detection runs again from scratch — idempotent |
| Linux: no sudo available for Ollama install | Show the curl command and let user run it manually |

---

## 9. What Does NOT Change

- Windows flow: already works (silent installers). Unchanged.
- Server startup: unchanged (pip install + spawn python).
- preload.ts: already correctly wired (`installPython → lv:setup:installPython`, `retrySetup → lv:setup:retryPython`). No changes needed.
- Ollama model pull: happens AFTER server starts, in the web wizard's onboarding. Unchanged.
- The `install.sh` curl-pipe flow: separate path, already handles source fallback. Unchanged.

---

## 10. Build Order

1. **Add macOS Python paths to `detectPython`** — check `/usr/local/bin/python3` etc. (15 min)
2. **Add `downloadFile` utility** if not already available (check if MC's is importable) (15 min)
3. **Replace macOS Python install with .pkg download + open** (30 min)
4. **Add background polling after install trigger** (30 min)
5. **Replace macOS Ollama install with .zip download + open** (30 min)
6. **Update `setup-wizard.html`** — single button, polling state, clear messaging (30 min)
7. **Test on macOS**: fresh state (no Python, no Ollama) → full flow → app running (30 min)
8. **Verify Windows still works**: run existing test on Windows (15 min)

**Total**: ~3.5 hours

---

## 11. Definition of Done

- [ ] macOS: "Install Python" downloads .pkg and opens macOS Installer (no browser)
- [ ] macOS: "Install Ollama" downloads .zip, unzips, launches Ollama.app (no browser)
- [ ] Auto-polling: wizard advances automatically when Python/Ollama detected (no manual retry)
- [ ] Single button: no duplicate actions, no "I'll do it myself" alongside "Install"
- [ ] Fallback: if download fails, THEN open website + still poll
- [ ] PATH detection: finds Python at `/usr/local/bin/python3` post-install
- [ ] Timeout: after 5 min (Python) or 2 min (Ollama), show helpful message
- [ ] Windows: unchanged, still passes
- [ ] Linux: Ollama installs via curl script (if available), else opens website

---

## 12. Provenance

- Bug report: Mac onboarding test 2026-07-22 (operator)
- LV desktop code: `learning-architecture/desktop/electron/main.ts`
- LV wizard UI: `learning-architecture/desktop/electron/setup-wizard.html`
- LV preload: `learning-architecture/desktop/electron/preload.ts` (verified: bridge is correct)
- MC sibling spec: `mission-canvas/dev/SPEC_PREREQUISITE_DETECTION_RESOLUTION_2026-07-22.md`
- LV install.sh: `learning-architecture/install.sh` (source fallback path, for reference)

---

*This can be built NOW — Lingua Viva is not mid-build. The fix is isolated to the desktop setup wizard and cannot affect the running app.*
