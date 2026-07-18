import { app, BrowserWindow, ipcMain, Notification, session } from "electron";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  DEFAULT_PORT,
  checkOllama,
  checkPython,
  ensureOllamaModel,
  startBackend,
  waitForBackend
} from "./bootstrap";

type WindowState = {
  width: number;
  height: number;
  x?: number;
  y?: number;
};

type ProgressStep = {
  label: string;
  state: "pending" | "running" | "done" | "error";
  detail?: string;
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

let mainWindow: BrowserWindow | null = null;
let backend: ChildProcessWithoutNullStreams | null = null;
let isQuitting = false;
let backendRestartCount = 0;

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char] || char);
}

function progressHtml(steps: ProgressStep[]): string {
  const icon = {
    pending: "○",
    running: "⏳",
    done: "✓",
    error: "✗"
  };
  const rows = steps.map((step) => `
    <li class="${step.state}">
      <span>${icon[step.state]}</span>
      <div><strong>${escapeHtml(step.label)}</strong>${step.detail ? `<small>${escapeHtml(step.detail)}</small>` : ""}</div>
    </li>
  `).join("");
  return `<!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lingua Viva Starting</title>
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17211f; background: #f5f7f4; }
      main { width: min(460px, calc(100vw - 32px)); padding: 28px; background: #fff; border: 1px solid #d8dfdc; border-radius: 8px; box-shadow: 0 18px 48px rgba(23, 33, 31, .14); }
      h1 { margin: 0 0 6px; font-size: 26px; }
      p { margin: 0 0 18px; color: #66736f; }
      ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
      li { display: grid; grid-template-columns: 30px 1fr; gap: 10px; align-items: center; min-height: 42px; padding: 8px; border: 1px solid #d8dfdc; border-radius: 6px; }
      li.done span { color: #1f6f4a; }
      li.running span { color: #8a5b00; }
      li.error span { color: #b24b31; }
      small { display: block; color: #66736f; margin-top: 2px; }
      .privacy { margin-top: 18px; font-size: 13px; color: #17463b; }
    </style>
  </head>
  <body><main><h1>🌱 Lingua Viva</h1><p>Starting your local teacher workbench.</p><ul>${rows}</ul><div class="privacy">Everything stays on your machine.</div></main></body>
  </html>`;
}

async function showProgress(window: BrowserWindow, steps: ProgressStep[]): Promise<void> {
  await window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(progressHtml(steps))}`);
}

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
}

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

async function launchBackend(root: string, window: BrowserWindow): Promise<void> {
  const python = process.env.LV_PYTHON || "python3";
  const steps: ProgressStep[] = [
    { label: "Python", state: "running" },
    { label: "Ollama", state: "pending" },
    { label: "Starting server", state: "pending" },
    { label: "Ready", state: "pending" }
  ];
  await showProgress(window, steps);
  const pythonCheck = await checkPython(python);
  if (!pythonCheck.ok) {
    steps[0] = { label: "Python", state: "error", detail: pythonCheck.detail };
    await showProgress(window, steps);
    throw new Error(`Python check failed: ${pythonCheck.detail}`);
  }
  steps[0] = { label: "Python", state: "done", detail: pythonCheck.detail };
  steps[1] = { label: "Ollama", state: "running" };
  await showProgress(window, steps);

  const ollamaCheck = await checkOllama();
  if (ollamaCheck.ok && process.env.LV_SKIP_MODEL_PULL !== "1") {
    await ensureOllamaModel(process.env.LV_OLLAMA_MODEL || undefined);
  }
  steps[1] = {
    label: "Ollama",
    state: ollamaCheck.ok ? "done" : "error",
    detail: ollamaCheck.ok ? ollamaCheck.detail : "Install Ollama at ollama.com"
  };
  steps[2] = { label: "Starting server", state: "running" };
  await showProgress(window, steps);

  const started = startBackend(root, PORT, python);
  backend = started.process;
  backend.on("exit", () => {
    if (isQuitting) {
      return;
    }
    backend = null;
    if (backendRestartCount < 3) {
      backendRestartCount += 1;
      if (mainWindow) {
        void launchBackend(root, mainWindow);
      }
    }
  });

  const ready = await waitForBackend(started.url);
  if (!ready) {
    steps[2] = { label: "Starting server", state: "error", detail: "Health probe did not succeed." };
    await showProgress(window, steps);
    throw new Error("Lingua Viva server did not become healthy.");
  }
  steps[2] = { label: "Starting server", state: "done" };
  steps[3] = { label: "Ready", state: "done", detail: BACKEND_URL };
  await showProgress(window, steps);
}

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});

app.whenReady().then(async () => {
  const root = repoRoot();
  installCsp();
  installIpc(root);
  mainWindow = createWindow();
  await launchBackend(root, mainWindow);
  await mainWindow.loadURL(BACKEND_URL);
  mainWindow.webContents.send("lv:backend-ready", BACKEND_URL);
});

app.on("window-all-closed", () => {
  app.quit();
});
