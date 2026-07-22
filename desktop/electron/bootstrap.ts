import { execFile, execFileSync, spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { createWriteStream, existsSync, unlinkSync } from "node:fs";
import https from "node:https";
import http from "node:http";
import os from "node:os";
import path from "node:path";

export const DEFAULT_PORT = 8787;
export const DEFAULT_MODEL = "qwen2.5:3b";

export type BootstrapCheck = {
  ok: boolean;
  detail: string;
};

export type BackendHandle = {
  process: ChildProcessWithoutNullStreams;
  url: string;
};

// --- Low-level helpers ---

function execFileText(command: string, args: string[], timeoutMs = 8000): Promise<BootstrapCheck> {
  return new Promise((resolve) => {
    const child = execFile(command, args, { timeout: timeoutMs }, (error, stdout, stderr) => {
      if (error) {
        resolve({ ok: false, detail: String(stderr || error.message).trim() });
        return;
      }
      resolve({ ok: true, detail: String(stdout || stderr).trim() });
    });
    // Ensure the process is killed on timeout (Windows Store aliases can hang)
    child.on("error", () => { /* handled by callback */ });
  });
}

// --- Python detection (multi-candidate) ---

export async function checkPython(pythonCommand = "python3"): Promise<BootstrapCheck> {
  const result = await execFileText(pythonCommand, ["--version"], 5000);
  if (!result.ok) {
    return result;
  }

  const version = result.detail.match(/Python\s+(\d+)\.(\d+)/);
  if (!version) {
    return { ok: false, detail: result.detail || "Unable to parse Python version." };
  }

  const major = Number(version[1]);
  const minor = Number(version[2]);
  if (major < 3 || (major === 3 && minor < 10)) {
    return { ok: false, detail: `Python 3.10+ required; found ${result.detail}.` };
  }
  return result;
}

export async function detectPython(): Promise<{ ok: boolean; command: string; detail: string }> {
  // Windows-first order: python (the common Windows name), python3, py (launcher)
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

// --- Ollama detection ---

export async function checkOllama(): Promise<BootstrapCheck> {
  return execFileText("ollama", ["--version"], 5000);
}

export async function ensureOllamaModel(model = DEFAULT_MODEL): Promise<BootstrapCheck> {
  const available = await checkOllama();
  if (!available.ok) {
    return { ok: false, detail: "Ollama is not installed or not on PATH." };
  }
  return execFileText("ollama", ["pull", model], 120000);
}

// --- File download with redirect following ---

export function downloadFile(url: string, dest: string, maxRedirects = 10): Promise<void> {
  return new Promise((resolve, reject) => {
    if (maxRedirects <= 0) {
      reject(new Error("Too many redirects"));
      return;
    }

    const proto = url.startsWith("https") ? https : http;
    const request = proto.get(url, (response) => {
      // Follow redirects (301, 302, 303, 307, 308)
      if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        let redirectUrl = response.headers.location;
        if (redirectUrl.startsWith("/")) {
          const parsed = new URL(url);
          redirectUrl = `${parsed.protocol}//${parsed.host}${redirectUrl}`;
        }
        downloadFile(redirectUrl, dest, maxRedirects - 1).then(resolve, reject);
        return;
      }

      if (!response.statusCode || response.statusCode !== 200) {
        response.resume();
        reject(new Error(`Download failed: HTTP ${response.statusCode}`));
        return;
      }

      const file = createWriteStream(dest);
      response.pipe(file);
      file.on("close", () => resolve());
      file.on("error", (err: Error) => {
        file.close();
        try { unlinkSync(dest); } catch { /* ignore */ }
        reject(err);
      });
    });
    request.on("error", (err: Error) => {
      try { unlinkSync(dest); } catch { /* ignore */ }
      reject(err);
    });
    // Timeout after 5 minutes
    request.setTimeout(300000, () => {
      request.destroy();
      try { unlinkSync(dest); } catch { /* ignore */ }
      reject(new Error("Download timed out"));
    });
  });
}

// --- Windows PATH refresh ---

export function refreshWindowsPath(): void {
  if (process.platform !== "win32") return;
  try {
    const userPath = execFileSync("powershell", [
      "-NoProfile", "-Command",
      "[Environment]::GetEnvironmentVariable('Path', 'User')"
    ], { encoding: "utf8", timeout: 10000 }).trim();
    const systemPath = execFileSync("powershell", [
      "-NoProfile", "-Command",
      "[Environment]::GetEnvironmentVariable('Path', 'Machine')"
    ], { encoding: "utf8", timeout: 10000 }).trim();
    if (userPath || systemPath) {
      process.env.PATH = [userPath, systemPath].filter(Boolean).join(";");
    }
  } catch { /* PATH refresh failed — user may need to restart app */ }
}

// --- Python installer (Windows) ---

export async function installPythonWindows(): Promise<void> {
  const installerUrl = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe";
  const tmpDir = os.tmpdir();
  const installerPath = path.join(tmpDir, "python-3.12.4-amd64.exe");

  await downloadFile(installerUrl, installerPath);

  return new Promise((resolve, reject) => {
    const proc = spawn(installerPath, [
      "/quiet",
      "InstallAllUsers=0",
      "PrependPath=1",
      "Include_pip=1",
      "Include_test=0",
      "Include_launcher=1",
    ], { windowsHide: true });

    proc.on("error", (err) => {
      try { unlinkSync(installerPath); } catch { /* ignore */ }
      reject(err);
    });
    proc.on("close", (code) => {
      try { unlinkSync(installerPath); } catch { /* ignore */ }
      if (code === 0) {
        refreshWindowsPath();
        resolve();
      } else {
        reject(new Error(`Python installer exited with code ${code}`));
      }
    });
  });
}

// --- Ollama installer (Windows) ---

export async function installOllamaWindows(): Promise<void> {
  const installerUrl = "https://ollama.com/download/OllamaSetup.exe";
  const tmpDir = os.tmpdir();
  const installerPath = path.join(tmpDir, "OllamaSetup.exe");

  await downloadFile(installerUrl, installerPath);

  return new Promise((resolve, reject) => {
    const proc = spawn(installerPath, ["/VERYSILENT", "/NORESTART"], { windowsHide: true });

    proc.on("error", (err) => {
      try { unlinkSync(installerPath); } catch { /* ignore */ }
      reject(err);
    });
    proc.on("close", (code) => {
      try { unlinkSync(installerPath); } catch { /* ignore */ }
      if (code === 0) {
        // Try to start Ollama service — may not auto-start after silent install
        try {
          spawn("ollama", ["serve"], {
            detached: true,
            stdio: "ignore",
            windowsHide: true,
          }).unref();
        } catch { /* will start on next login if not now */ }
        resolve();
      } else {
        reject(new Error(`Ollama installer exited with code ${code}`));
      }
    });
  });
}

// --- Python dependency installer ---

export async function installPythonDeps(pythonCmd: string, repoRoot: string): Promise<void> {
  const deps = ["pyyaml", "fastapi", "uvicorn", "httpx", "websockets"];
  const args = pythonCmd === "py"
    ? ["-3", "-m", "pip", "install", "--quiet", ...deps]
    : ["-m", "pip", "install", "--quiet", ...deps];

  return new Promise((resolve) => {
    const proc = spawn(pythonCmd, args, {
      cwd: repoRoot,
      windowsHide: true,
      stdio: "pipe",
    });
    proc.on("close", () => resolve());
    proc.on("error", () => resolve()); // Non-fatal — server may still start
  });
}

// --- Backend health probe ---

export async function probeHealth(url: string, timeoutMs = 3000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${url}/api/health`, { signal: controller.signal });
    if (!response.ok) {
      return false;
    }
    const body = await response.json() as { status?: unknown };
    return typeof body.status === "string";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function waitForBackend(url: string, deadlineMs = 45000, backendProcess?: ChildProcessWithoutNullStreams): Promise<boolean> {
  const started = Date.now();
  let exited = false;
  const exitHandler = () => { exited = true; };
  if (backendProcess) {
    backendProcess.on("exit", exitHandler);
  }
  try {
    while (Date.now() - started < deadlineMs) {
      if (exited) return false; // Backend died — break early
      if (await probeHealth(url)) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return false;
  } finally {
    if (backendProcess) {
      backendProcess.removeListener("exit", exitHandler);
    }
  }
}

// --- Backend start ---

export function startBackend(repoRoot: string, port = DEFAULT_PORT, pythonCommand = "python3"): BackendHandle {
  const webPath = path.join(repoRoot, "src", "web.py");
  if (!existsSync(webPath)) {
    throw new Error(`Lingua Viva server not found at ${webPath}`);
  }

  const child = spawn(pythonCommand, [webPath, String(port)], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      LV_DESKTOP: "1"
    },
    stdio: "pipe",
    windowsHide: true
  });

  return {
    process: child,
    url: `http://127.0.0.1:${port}`
  };
}
