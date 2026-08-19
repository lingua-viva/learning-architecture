import { app, BrowserWindow, dialog, ipcMain, Notification, session, shell } from "electron";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { readFile, unlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  DEFAULT_PORT,
  checkOllama,
  detectPython,
  ensureOllamaModel,
  installPythonWindows,
  installOllamaWindows,
  ensurePythonEnv,
  verifyPythonDeps,
  refreshWindowsPath,
  recommendedModel,
  startBackend,
  waitForBackend
} from "./bootstrap";

type WindowState = {
  width: number;
  height: number;
  x?: number;
  y?: number;
};

const PORT = Number(process.env.LV_APP_PORT || DEFAULT_PORT);
const BACKEND_URL = `http://127.0.0.1:${PORT}`;
const CSP = [
  "default-src 'self' http://127.0.0.1:8787",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "font-src 'self' data:",
  "connect-src 'self' http://127.0.0.1:8787 ws://127.0.0.1:8787",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'"
].join("; ");

// Allowed external URLs for the setup wizard
const ALLOWED_EXTERNAL_URLS = [
  "https://www.python.org/downloads/",
  "https://python.org/downloads/",
  "https://ollama.com",
  "https://ollama.com/download",
];

let mainWindow: BrowserWindow | null = null;
let backend: ChildProcessWithoutNullStreams | null = null;
let isQuitting = false;
let backendRestartCount = 0;
let pythonCmd = "python3"; // resolved during setup

function repoRoot(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "app");
  }
  return path.resolve(app.getAppPath(), "..");
}

function windowStatePath(): string {
  return path.join(app.getPath("userData"), "window-state.json");
}

function readWindowState(): WindowState {
  try {
    const parsed = JSON.parse(readFileSync(windowStatePath(), "utf8")) as Partial<WindowState>;
    return {
      width: Math.max(900, Number(parsed.width || 1180)),
      height: Math.max(680, Number(parsed.height || 820)),
      x: typeof parsed.x === "number" ? parsed.x : undefined,
      y: typeof parsed.y === "number" ? parsed.y : undefined
    };
  } catch {
    return { width: 1180, height: 820 };
  }
}

function saveWindowState(window: BrowserWindow): void {
  const bounds = window.getBounds();
  mkdirSync(path.dirname(windowStatePath()), { recursive: true });
  writeFileSync(windowStatePath(), JSON.stringify(bounds, null, 2));
}

function installCsp(): void {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [CSP]
      }
    });
  });
}

function emitProgress(window: BrowserWindow, step: string, detail?: string): void {
  window.webContents.send("lv:setup:progress", { step, detail });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- Setup flow (replaces old launchBackend) ---

async function runSetupFlow(root: string, window: BrowserWindow): Promise<void> {
  // Load the setup wizard HTML
  const wizardPath = path.join(
    app.getAppPath(),
    app.isPackaged ? "dist/electron" : "electron",
    "setup-wizard.html"
  );
  await window.loadFile(wizardPath);
  await sleep(300); // let renderer initialize its IPC listener

  // Step 1: Python detection
  emitProgress(window, "python", "Checking for Python...");
  const pythonResult = await detectPythonBroad();

  if (pythonResult.ok) {
    pythonCmd = pythonResult.command;
    emitProgress(window, "python_ok", pythonResult.detail);
  } else {
    emitProgress(window, "python_fail", "Python is needed to run Lingua Viva locally.");
    // Wait for user to resolve Python (install or retry via IPC)
    pythonCmd = await waitForPythonResolution(window);
  }

  // Step 2: Ollama detection
  // LV_SKIP_OLLAMA=1: headless/CI boot gate (packaged-artifact fresh-install
  // test in desktop-release.yml) — the Ollama step waits on a wizard click,
  // which never comes without a human. Skipping it only skips the model; the
  // dependency install + backend boot under test are unaffected.
  emitProgress(window, "ollama", "Checking for Ollama...");
  const ollamaCheck = process.env.LV_SKIP_OLLAMA === "1"
    ? { ok: false, detail: "skipped (LV_SKIP_OLLAMA=1)" }
    : await checkOllama();

  // P1-1 (Claudia QA 2026-08-03): the model pull used to be fire-and-forget
  // with .catch(() => {}) — a failed or timed-out pull left the teacher with
  // no model and no message. Now the pull runs concurrently with dependency
  // install/server start (so a 2GB download never blocks the app opening),
  // but its RESULT is awaited and reported before the wizard finishes.
  let modelPull: Promise<{ ok: boolean; detail: string }> | null = null;

  // Hardware-adaptive model selection (same process as Mission Canvas):
  // detect GPU tier, pick the right model size automatically.
  const hwRec = recommendedModel();
  const modelOverride = process.env.LV_OLLAMA_MODEL || undefined;

  if (ollamaCheck.ok) {
    emitProgress(window, "ollama_ok", ollamaCheck.detail);
    if (process.env.LV_SKIP_MODEL_PULL !== "1") {
      const modelName = modelOverride || hwRec.model;
      emitProgress(window, "model",
        `Preparing ${modelName} for your hardware (${hwRec.tier}, ${hwRec.sizeLabel})...`);
      modelPull = ensureOllamaModel(modelOverride)
        .catch((err) => ({ ok: false, detail: String(err instanceof Error ? err.message : err) }));
    }
  } else if (process.env.LV_SKIP_OLLAMA === "1") {
    emitProgress(window, "ollama_skipped");
  } else {
    emitProgress(window, "ollama_warn");
    // Wait for user decision (install or skip)
    await waitForOllamaResolution(window);
    // If they installed Ollama during resolution, still ensure a model exists.
    if (process.env.LV_SKIP_MODEL_PULL !== "1" && (await checkOllama()).ok) {
      const modelName = modelOverride || hwRec.model;
      emitProgress(window, "model",
        `Preparing ${modelName} for your hardware (${hwRec.tier}, ${hwRec.sizeLabel})...`);
      modelPull = ensureOllamaModel(modelOverride)
        .catch((err) => ({ ok: false, detail: String(err instanceof Error ? err.message : err) }));
    }
  }

  // Step 3: Install Python deps + start server.
  // D1-P0-001 (2026-08-10): this used to be fire-and-forget — the installer
  // resolved even when every pip attempt failed (Ubuntu ships python3 with
  // no pip at all), the backend then died on `import fastapi`, and the
  // wizard showed a generic message. Now the install FAILS CLOSED: setup
  // stops here with the real error and a Retry button, and the backend runs
  // from Lingua Viva's own venv so the machine's pip situation is irrelevant.
  emitProgress(window, "server", "Installing dependencies...");
  const envReady = await ensurePythonEnv(pythonCmd, (msg) => emitProgress(window, "server", msg));
  if (!envReady.ok) {
    emitProgress(window, "server_fail",
      `Dependencies did not install: ${envReady.detail} (full log: ~/.lingua-viva/logs/setup.log)`);
    await waitForRetry(window, root);
    return;
  }
  pythonCmd = envReady.pythonCmd;

  // P0-1 (Claudia QA 2026-08-03): verify every critical package actually
  // imports in the Python that will run the server, and say so plainly when
  // voice deps are missing — the backend boots fine without them, so nothing
  // else would ever tell the teacher why her mic does nothing.
  const depCheck = await verifyPythonDeps(pythonCmd);
  if (depCheck.missingServer.length > 0) {
    emitProgress(window, "server_fail",
      `Required components are missing after install (${depCheck.missingServer.join(", ")}). See ~/.lingua-viva/logs/setup.log, then Retry setup.`);
    await waitForRetry(window, root);
    return;
  }
  if (depCheck.missingVoice.length > 0) {
    emitProgress(window, "voice_warn",
      "Voice transcription components could not be installed. You can still type everything — voice input will be unavailable until setup is retried.");
  }

  emitProgress(window, "server", "Starting Lingua Viva...");
  const started = startBackend(root, PORT, pythonCmd);
  backend = started.process;

  // Early exit detection — only retry server start, not the whole wizard
  backend.on("exit", (code) => {
    if (isQuitting) return;
    backend = null;
    if (backendRestartCount < 2 && mainWindow && code !== 0) {
      backendRestartCount += 1;
      emitProgress(window, "server", `Retrying server start (attempt ${backendRestartCount + 1})...`);
      const retryStarted = startBackend(root, PORT, pythonCmd);
      backend = retryStarted.process;
      backend.on("exit", () => { backend = null; });
      void waitForBackend(retryStarted.url, 30000, retryStarted.process).then((ok) => {
        if (ok) {
          emitProgress(window, "server_ok");
          emitProgress(window, "loading");
          void window.loadURL(BACKEND_URL);
        }
      });
    }
  });

  const ready = await waitForBackend(started.url, 45000, started.process);
  if (!ready) {
    emitProgress(window, "server_fail", "Server did not start. Check Python dependencies or port 8787.");
    // Keep wizard open with retry — don't throw
    await waitForRetry(window, root);
    return;
  }

  emitProgress(window, "server_ok");

  // Model pull result is VERIFIED and REPORTED, never silent — but a long
  // download must not hold the app hostage. Give it a short grace window; if
  // it's still running, open the app and report via system notification when
  // it finishes either way.
  if (modelPull) {
    const raced = await Promise.race([
      modelPull.then((r) => ({ done: true as const, result: r })),
      sleep(15000).then(() => ({ done: false as const, result: null })),
    ]);
    if (raced.done && raced.result) {
      const modelResult = raced.result;
      emitProgress(window, modelResult.ok ? "model_ok" : "model_warn",
        modelResult.ok
          ? "Local AI model ready."
          : "The local AI model could not be downloaded. Questions will not get answers until it is — restart the app to retry.");
    } else {
      emitProgress(window, "model", "AI model still downloading — the app will open now and let you know when it's ready.");
      void modelPull.then((modelResult) => {
        try {
          new Notification({
            title: "Lingua Viva",
            body: modelResult.ok
              ? "Local AI model is ready — questions now get answers."
              : "The AI model download failed. Restart Lingua Viva to retry.",
          }).show();
        } catch { /* notifications unavailable — model state still visible via /api/query message */ }
      });
    }
  }

  emitProgress(window, "loading");
  await sleep(200);

  // Load the real app
  await window.loadURL(BACKEND_URL);
  window.webContents.send("lv:backend-ready", BACKEND_URL);
}

// --- Resolution helpers (IPC-driven pauses) ---

function waitForPythonResolution(window: BrowserWindow): Promise<string> {
  return new Promise((resolve) => {
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const startPolling = () => {
      emitProgress(window, "python_polling",
        "Follow the installer prompts — we'll continue automatically.");
      pollTimer = setInterval(async () => {
        const result = await detectPythonBroad();
        if (result.ok) {
          cleanup();
          emitProgress(window, "python_installed", result.detail);
          resolve(result.command);
        }
      }, 2000);
      // Timeout after 5 minutes
      setTimeout(() => {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
          emitProgress(window, "python_install_failed",
            "Still waiting. If the installer finished, click below.");
        }
      }, 300000);
    };

    const handleInstall = async () => {
      if (process.platform === "win32") {
        emitProgress(window, "python_installing", "Downloading Python 3.12...");
        try {
          await installPythonWindows();
          emitProgress(window, "python_install_progress", "90");
          emitProgress(window, "python_installed", "Python 3.12 installed");
          cleanup();
          const recheck = await detectPythonBroad();
          resolve(recheck.ok ? recheck.command : "python");
        } catch (err) {
          emitProgress(window, "python_install_failed", String(err instanceof Error ? err.message : err));
        }
      } else if (process.platform === "darwin") {
        // macOS: download the .pkg directly and open it
        emitProgress(window, "python_installing", "Downloading Python installer...");
        try {
          const { downloadFile } = await import("./bootstrap");
          const os = await import("node:os");
          const { spawn } = await import("node:child_process");
          const pkgUrl = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-macos11.pkg";
          const dest = path.join(os.tmpdir(), "python-3.12.7-macos11.pkg");
          await downloadFile(pkgUrl, dest);
          emitProgress(window, "python_installing",
            "Opening installer — click \"Continue\" then \"Install\"...");
          spawn("open", [dest], { detached: true }).unref();
          startPolling();
        } catch (err) {
          // Download failed — fall back to website + poll
          shell.openExternal("https://www.python.org/downloads/");
          emitProgress(window, "python_install_failed",
            "Download failed — install from the page that opened.");
          startPolling();
        }
      } else {
        // Linux: open website + poll
        shell.openExternal("https://www.python.org/downloads/");
        emitProgress(window, "python_install_failed",
          "Install Python 3.11+ from your package manager, then we'll detect it.");
        startPolling();
      }
    };

    const handleRetry = async () => {
      if (process.platform === "win32") {
        refreshWindowsPath();
      }
      emitProgress(window, "python", "Checking again...");
      const recheck = await detectPythonBroad();
      if (recheck.ok) {
        emitProgress(window, "python_installed", recheck.detail);
        cleanup();
        resolve(recheck.command);
      } else {
        emitProgress(window, "python_install_failed",
          "Not found yet. The installer may still be running.");
        if (!pollTimer) startPolling();
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

/** Broader Python detection — checks standard macOS install paths beyond just PATH. */
async function detectPythonBroad(): Promise<{ ok: boolean; command: string; detail: string }> {
  // First try the normal detection
  const normal = await detectPython();
  if (normal.ok) return normal;

  // On macOS, the python.org .pkg installs to paths that may not be on
  // the Electron process's PATH. Check them directly.
  if (process.platform === "darwin") {
    const { checkPython } = await import("./bootstrap");
    const macPaths = [
      "/usr/local/bin/python3",
      "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
      "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
      "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
      "/opt/homebrew/bin/python3",
    ];
    for (const cmd of macPaths) {
      try {
        const { existsSync } = await import("node:fs");
        if (!existsSync(cmd)) continue;
        const result = await checkPython(cmd);
        if (result.ok) {
          return { ok: true, command: cmd, detail: result.detail };
        }
      } catch { /* try next */ }
    }
  }

  return { ok: false, command: "", detail: "Python 3.10+ not found" };
}

function waitForOllamaResolution(window: BrowserWindow): Promise<void> {
  return new Promise((resolve) => {
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const startOllamaPolling = () => {
      pollTimer = setInterval(async () => {
        const status = await checkOllama();
        if (status.ok) {
          cleanup();
          emitProgress(window, "ollama_installed", "Ollama ready");
          resolve();
        }
      }, 2000);
      // Auto-skip after 4 minutes if Ollama never comes up
      setTimeout(() => {
        if (pollTimer) {
          cleanup();
          emitProgress(window, "ollama_skipped");
          resolve();
        }
      }, 240000);
    };

    const handleInstall = async () => {
      if (process.platform === "win32") {
        emitProgress(window, "ollama_installing", "Downloading Ollama...");
        try {
          await installOllamaWindows();
          emitProgress(window, "ollama_installed", "Ollama installed");
          cleanup();
          resolve();
        } catch {
          emitProgress(window, "ollama_skipped");
          cleanup();
          resolve();
        }
      } else if (process.platform === "darwin") {
        emitProgress(window, "ollama_installing", "Downloading Ollama...");
        try {
          const { downloadFile } = await import("./bootstrap");
          const os = await import("node:os");
          const fs = await import("node:fs");
          const { execSync, spawn } = await import("node:child_process");
          const zipUrl = "https://ollama.com/download/Ollama-darwin.zip";
          const dest = path.join(os.tmpdir(), "Ollama-darwin.zip");
          await downloadFile(zipUrl, dest);

          emitProgress(window, "ollama_installing", "Installing Ollama app...");
          const appDest = path.join(os.homedir(), "Applications");
          fs.mkdirSync(appDest, { recursive: true });
          execSync(`unzip -o -q "${dest}" -d "${appDest}/"`, { timeout: 60000 });

          // Launch Ollama.app — it auto-starts the daemon
          spawn("open", [path.join(appDest, "Ollama.app")], { detached: true }).unref();
          try { fs.unlinkSync(dest); } catch {}

          emitProgress(window, "ollama_installing",
            "Ollama is starting — this takes a moment the first time...");
          startOllamaPolling();
        } catch {
          // Download failed — open website and skip
          shell.openExternal("https://ollama.com/download");
          emitProgress(window, "ollama_skipped");
          cleanup();
          resolve();
        }
      } else {
        // Linux: try the official install script
        try {
          const { execSync } = await import("node:child_process");
          emitProgress(window, "ollama_installing", "Installing Ollama...");
          execSync("curl -fsSL https://ollama.com/install.sh | sh",
            { timeout: 120000, stdio: "pipe" });
          emitProgress(window, "ollama_installed", "Ollama installed");
          cleanup();
          resolve();
        } catch {
          shell.openExternal("https://ollama.com/download");
          emitProgress(window, "ollama_skipped");
          cleanup();
          resolve();
        }
      }
    };

    const handleSkip = () => {
      emitProgress(window, "ollama_skipped");
      cleanup();
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

function waitForRetry(window: BrowserWindow, root: string): Promise<void> {
  return new Promise((resolve) => {
    const handleRetry = async () => {
      ipcMain.removeHandler("lv:setup:retryPython");
      // Re-run the full setup flow
      await runSetupFlow(root, window);
      resolve();
    };
    // Reuse the retry handler to allow recovery from server failure
    ipcMain.handle("lv:setup:retryPython", handleRetry);
  });
}

// --- Standard IPC ---

function installIpc(root: string): void {
  ipcMain.handle("lv:get-version", () => app.getVersion());
  ipcMain.handle("lv:notify", (_event, payload: { title?: string; body?: string }) => {
    if (Notification.isSupported()) {
      new Notification({
        title: payload.title || "Lingua Viva",
        body: payload.body || ""
      }).show();
    }
    return { ok: true };
  });
  ipcMain.handle("lv:read-file", async (_event, relativePath: string) => {
    const resolved = path.resolve(root, relativePath);
    if (!resolved.startsWith(root + path.sep)) {
      throw new Error("Path outside Lingua Viva app bundle.");
    }
    if (!existsSync(resolved)) {
      throw new Error("File not found.");
    }
    return readFile(resolved, "utf8");
  });
  ipcMain.handle("lv:pick-folder", async () => {
    // Directory-only picker for the Sources view; never a file dialog.
    const result = await dialog.showOpenDialog({ properties: ["openDirectory"] });
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0];
  });
  ipcMain.handle("lv:print-html", async (_event, html: string) => {
    // Native print for packet HTML (FIX_PREPARE_CLASS_MATERIALS 2026-08-18,
    // Issue 8). The renderer's iframe-srcdoc print trick renders blank under
    // the app CSP + sandbox, so printing happens in a dedicated hidden
    // window instead. The HTML is written to a temp file (data: URLs choke
    // on large packets) and removed afterwards.
    if (typeof html !== "string" || !html.trim()) {
      return { ok: false, error: "empty_document" };
    }
    const tempPath = path.join(
      os.tmpdir(),
      `lv-print-${Date.now()}-${Math.random().toString(36).slice(2)}.html`
    );
    await writeFile(tempPath, html, "utf8");
    return await new Promise((resolve) => {
      const printWindow = new BrowserWindow({
        show: false,
        webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false }
      });
      const cleanup = () => {
        if (!printWindow.isDestroyed()) printWindow.close();
        unlink(tempPath).catch(() => undefined);
      };
      printWindow.webContents.once("did-finish-load", () => {
        printWindow.webContents.print({}, (success, failureReason) => {
          cleanup();
          resolve(success ? { ok: true } : { ok: false, error: failureReason || "print_cancelled" });
        });
      });
      printWindow.webContents.once("did-fail-load", () => {
        cleanup();
        resolve({ ok: false, error: "load_failed" });
      });
      printWindow.loadFile(tempPath).catch(() => {
        cleanup();
        resolve({ ok: false, error: "load_failed" });
      });
    });
  });
  ipcMain.handle("lv:setup:openExternal", (_event, url: string) => {
    // Only allow known safe URLs
    if (ALLOWED_EXTERNAL_URLS.some((allowed) => url.startsWith(allowed))) {
      shell.openExternal(url);
    }
    return { ok: true };
  });
}

// --- Window management ---

function createWindow(): BrowserWindow {
  const state = readWindowState();
  const window = new BrowserWindow({
    title: "Lingua Viva",
    width: state.width,
    height: state.height,
    x: state.x,
    y: state.y,
    minWidth: 900,
    minHeight: 640,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  window.on("close", () => saveWindowState(window));
  window.once("ready-to-show", () => window.show());
  return window;
}

function stopBackend(): void {
  if (!backend || backend.killed) {
    return;
  }
  const child = backend;
  backend = null;
  child.kill("SIGTERM");
  setTimeout(() => {
    if (!child.killed) {
      child.kill("SIGKILL");
    }
  }, 3000).unref();
}

// --- App lifecycle ---

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});

app.whenReady().then(async () => {
  const root = repoRoot();
  installCsp();
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === "media");
  });
  installIpc(root);
  mainWindow = createWindow();
  await runSetupFlow(root, mainWindow);
});

app.on("window-all-closed", () => {
  app.quit();
});
