import { app, BrowserWindow, ipcMain, Notification, session, shell } from "electron";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  DEFAULT_PORT,
  checkOllama,
  detectPython,
  ensureOllamaModel,
  installPythonWindows,
  installOllamaWindows,
  installPythonDeps,
  refreshWindowsPath,
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
  const pythonResult = await detectPython();

  if (pythonResult.ok) {
    pythonCmd = pythonResult.command;
    emitProgress(window, "python_ok", pythonResult.detail);
  } else {
    emitProgress(window, "python_fail", "Python is needed to run Lingua Viva locally.");
    // Wait for user to resolve Python (install or retry via IPC)
    pythonCmd = await waitForPythonResolution(window);
  }

  // Step 2: Ollama detection
  emitProgress(window, "ollama", "Checking for Ollama...");
  const ollamaCheck = await checkOllama();

  if (ollamaCheck.ok) {
    emitProgress(window, "ollama_ok", ollamaCheck.detail);
    // Pull model in background (non-blocking for startup)
    if (process.env.LV_SKIP_MODEL_PULL !== "1") {
      ensureOllamaModel(process.env.LV_OLLAMA_MODEL || undefined).catch(() => {});
    }
  } else {
    emitProgress(window, "ollama_warn");
    // Wait for user decision (install or skip)
    await waitForOllamaResolution(window);
  }

  // Step 3: Install Python deps + start server
  emitProgress(window, "server", "Installing dependencies...");
  await installPythonDeps(pythonCmd, root);

  emitProgress(window, "server", "Starting Lingua Viva...");
  const started = startBackend(root, PORT, pythonCmd);
  backend = started.process;

  // Early exit detection
  backend.on("exit", () => {
    if (isQuitting) return;
    backend = null;
    if (backendRestartCount < 3 && mainWindow) {
      backendRestartCount += 1;
      void runSetupFlow(root, mainWindow);
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
  emitProgress(window, "loading");
  await sleep(200);

  // Load the real app
  await window.loadURL(BACKEND_URL);
  window.webContents.send("lv:backend-ready", BACKEND_URL);
}

// --- Resolution helpers (IPC-driven pauses) ---

function waitForPythonResolution(window: BrowserWindow): Promise<string> {
  return new Promise((resolve) => {
    const handleInstall = async () => {
      if (process.platform === "win32") {
        emitProgress(window, "python_installing", "Downloading Python 3.12...");
        try {
          await installPythonWindows();
          emitProgress(window, "python_install_progress", "90");
          emitProgress(window, "python_installed", "Python 3.12 installed");
          cleanup();
          // Re-detect to get the resolved command
          const recheck = await detectPython();
          resolve(recheck.ok ? recheck.command : "python");
        } catch (err) {
          emitProgress(window, "python_install_failed", String(err instanceof Error ? err.message : err));
        }
      } else {
        // macOS/Linux: open python.org and show retry
        shell.openExternal("https://www.python.org/downloads/");
        emitProgress(window, "python_install_failed", "Download Python from the site that just opened, then click retry below.");
      }
    };

    const handleRetry = async () => {
      if (process.platform === "win32") {
        refreshWindowsPath();
      }
      emitProgress(window, "python", "Checking again...");
      const recheck = await detectPython();
      if (recheck.ok) {
        emitProgress(window, "python_installed", recheck.detail);
        cleanup();
        resolve(recheck.command);
      } else {
        emitProgress(window, "python_install_failed", "Still not found. Install Python 3.10+ and try again.");
      }
    };

    const cleanup = () => {
      ipcMain.removeHandler("lv:setup:installPython");
      ipcMain.removeHandler("lv:setup:retryPython");
    };

    ipcMain.handle("lv:setup:installPython", handleInstall);
    ipcMain.handle("lv:setup:retryPython", handleRetry);
  });
}

function waitForOllamaResolution(window: BrowserWindow): Promise<void> {
  return new Promise((resolve) => {
    const handleInstall = async () => {
      if (process.platform === "win32") {
        emitProgress(window, "ollama_installing", "Downloading Ollama...");
        try {
          await installOllamaWindows();
          emitProgress(window, "ollama_installed", "Ollama installed");
          cleanup();
          resolve();
        } catch (err) {
          // Fallback: skip and continue
          emitProgress(window, "ollama_skipped");
          cleanup();
          resolve();
        }
      } else {
        shell.openExternal("https://ollama.com/download");
        emitProgress(window, "ollama_skipped");
        cleanup();
        resolve();
      }
    };

    const handleSkip = () => {
      emitProgress(window, "ollama_skipped");
      cleanup();
      resolve();
    };

    const cleanup = () => {
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
  installIpc(root);
  mainWindow = createWindow();
  await runSetupFlow(root, mainWindow);
});

app.on("window-all-closed", () => {
  app.quit();
});
