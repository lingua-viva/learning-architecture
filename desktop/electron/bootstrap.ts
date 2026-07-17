import { execFile, spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
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

function execFileText(command: string, args: string[], timeoutMs = 8000): Promise<BootstrapCheck> {
  return new Promise((resolve) => {
    execFile(command, args, { timeout: timeoutMs }, (error, stdout, stderr) => {
      if (error) {
        resolve({ ok: false, detail: String(stderr || error.message).trim() });
        return;
      }
      resolve({ ok: true, detail: String(stdout || stderr).trim() });
    });
  });
}

export async function checkPython(pythonCommand = "python3"): Promise<BootstrapCheck> {
  const result = await execFileText(pythonCommand, ["--version"]);
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

export async function waitForBackend(url: string, deadlineMs = 45000): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < deadlineMs) {
    if (await probeHealth(url)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

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
