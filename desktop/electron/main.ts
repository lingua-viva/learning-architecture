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

async function launchBackend(root: string): Promise<void> {
  const python = process.env.LV_PYTHON || "python3";
  const pythonCheck = await checkPython(python);
  if (!pythonCheck.ok) {
    throw new Error(`Python check failed: ${pythonCheck.detail}`);
  }

  const ollamaCheck = await checkOllama();
  if (ollamaCheck.ok && process.env.LV_SKIP_MODEL_PULL !== "1") {
    await ensureOllamaModel(process.env.LV_OLLAMA_MODEL || undefined);
  }

  const started = startBackend(root, PORT, python);
  backend = started.process;
  backend.on("exit", () => {
    if (isQuitting) {
      return;
    }
    backend = null;
    if (backendRestartCount < 3) {
      backendRestartCount += 1;
      void launchBackend(root);
    }
  });

  const ready = await waitForBackend(started.url);
  if (!ready) {
    throw new Error("Lingua Viva server did not become healthy.");
  }
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
  await launchBackend(root);
  await mainWindow.loadURL(BACKEND_URL);
  mainWindow.webContents.send("lv:backend-ready", BACKEND_URL);
});

app.on("window-all-closed", () => {
  app.quit();
});
