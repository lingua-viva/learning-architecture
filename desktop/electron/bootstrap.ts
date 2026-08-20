import { execFile, execFileSync, spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { appendFileSync, createWriteStream, existsSync, mkdirSync, unlinkSync } from "node:fs";
import https from "node:https";
import http from "node:http";
import os from "node:os";
import path from "node:path";

export const DEFAULT_PORT = 8787;
export const DEFAULT_MODEL = "qwen2.5:3b";

// Hardware-tier model map (same as MC onboarding.py and LV config.py)
const TIER_MODEL_MAP: Record<string, { model: string; sizeLabel: string }> = {
  ultra_gpu:  { model: "nemotron-3.5-lightning", sizeLabel: "23.7 GB" },
  strong_gpu: { model: "qwen2.5:14b",           sizeLabel: "9.0 GB" },
  mid_gpu:    { model: "qwen2.5:7b",            sizeLabel: "4.7 GB" },
  weak_gpu:   { model: "qwen2.5:3b",            sizeLabel: "1.9 GB" },
  cpu_only:   { model: "qwen2.5:3b",            sizeLabel: "1.9 GB" },
};

export type BootstrapCheck = {
  ok: boolean;
  detail: string;
};

export type BackendHandle = {
  process: ChildProcessWithoutNullStreams;
  url: string;
};

// --- GPU detection (ported from MC onboarding.py) ---

function estimateGpuGb(): number {
  // NVIDIA via nvidia-smi
  try {
    const out = execFileSync("nvidia-smi",
      ["--query-gpu=memory.total", "--format=csv,noheader,nounits"],
      { encoding: "utf8", timeout: 3000 });
    const mib = parseInt(out.trim().split("\n")[0], 10);
    if (mib > 0) return mib / 1000;
  } catch { /* no nvidia-smi */ }

  // Linux AMD: sysfs VRAM (+ GTT for APU)
  if (process.platform === "linux") {
    try {
      const { readdirSync, readFileSync } = require("node:fs") as typeof import("node:fs");
      const drmBase = "/sys/class/drm";
      for (const card of readdirSync(drmBase).sort()) {
        const vramPath = path.join(drmBase, card, "device", "mem_info_vram_total");
        try {
          const vramGb = parseInt(readFileSync(vramPath, "utf8").trim(), 10) / 1e9;
          const gttPath = path.join(drmBase, card, "device", "mem_info_gtt_total");
          let gttGb = 0;
          try { gttGb = parseInt(readFileSync(gttPath, "utf8").trim(), 10) / 1e9; } catch { /* no GTT */ }
          return gttGb > vramGb ? vramGb + gttGb : vramGb;
        } catch { continue; }
      }
    } catch { /* no sysfs */ }
  }

  // Apple Silicon: unified memory = GPU shares system RAM
  if (process.platform === "darwin" && os.arch() === "arm64") {
    return os.totalmem() / 1e9;
  }

  return 0;
}

function gpuTier(): string {
  const gb = estimateGpuGb();
  if (gb >= 32) return "ultra_gpu";
  if (gb >= 12) return "strong_gpu";
  if (gb >= 6) return "mid_gpu";
  if (gb >= 3) return "weak_gpu";
  return "cpu_only";
}

export function recommendedModel(): { model: string; tier: string; sizeLabel: string } {
  const tier = gpuTier();
  const entry = TIER_MODEL_MAP[tier] || TIER_MODEL_MAP.cpu_only;
  return { model: entry.model, tier, sizeLabel: entry.sizeLabel };
}

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
  // Check HTTP first (daemon may be running even if CLI isn't on PATH)
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch("http://127.0.0.1:11434/api/tags", { signal: controller.signal });
    clearTimeout(timer);
    if (resp.ok) {
      return { ok: true, detail: "Ollama daemon running" };
    }
  } catch { /* daemon not running, try CLI */ }

  // Fall back to CLI version check
  return execFileText("ollama", ["--version"], 5000);
}

async function ollamaHasModel(model: string): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch("http://127.0.0.1:11434/api/tags", { signal: controller.signal });
    clearTimeout(timer);
    if (!resp.ok) return false;
    const body = await resp.json() as { models?: Array<{ name?: string }> };
    return (body.models || []).some((m) => {
      const name = m.name || "";
      // "qwen2.5:3b" matches exactly; a tagless request matches any tag of it.
      return name === model || name === `${model}:latest`
        || (!model.includes(":") && name.split(":")[0] === model);
    });
  } catch {
    return false;
  }
}

export async function ensureOllamaModel(model?: string): Promise<BootstrapCheck> {
  // P1-1 (Claudia QA 2026-08-03): this used to be a 120s CLI pull, called
  // fire-and-forget. A ~2GB model on school wifi takes far longer than 120s,
  // so the pull timed out silently and the teacher ended up with no model and
  // a cryptic placeholder on every question. Now: generous timeout, verified
  // outcome (the model must actually be in /api/tags afterwards), and an HTTP
  // fallback for the daemon-running-without-CLI case checkOllama supports.
  const available = await checkOllama();
  if (!available.ok) {
    return { ok: false, detail: "Ollama is not installed or not on PATH." };
  }

  // Hardware-aware model selection (same process as Mission Canvas):
  // detect GPU tier, pick the right model. For ultra_gpu (nemotron), only
  // use it if already installed — the 23.7GB pull requires explicit consent
  // from the setup wizard. Otherwise fall back to strong_gpu tier.
  if (!model) {
    const rec = recommendedModel();
    if (rec.tier === "ultra_gpu") {
      // Only use nemotron if already installed (consent-gated)
      if (await ollamaHasModel(rec.model)) {
        model = rec.model;
      } else {
        model = TIER_MODEL_MAP.strong_gpu.model;
      }
    } else {
      model = rec.model;
    }
  }

  if (await ollamaHasModel(model)) {
    return { ok: true, detail: `Model ${model} already available.` };
  }

  const cliResult = await execFileText("ollama", ["pull", model], 1800000); // 30 min
  if (!cliResult.ok) {
    // CLI missing or failed — try the daemon's HTTP pull endpoint.
    try {
      const resp = await fetch("http://127.0.0.1:11434/api/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: model, stream: false }),
      });
      if (!resp.ok) {
        return { ok: false, detail: `Model pull failed (CLI: ${cliResult.detail}; HTTP: ${resp.status}).` };
      }
    } catch (err) {
      return { ok: false, detail: `Model pull failed: ${cliResult.detail || String(err)}` };
    }
  }

  // Trust nothing: verify the model is actually there now.
  if (await ollamaHasModel(model)) {
    return { ok: true, detail: `Model ${model} ready.` };
  }
  return { ok: false, detail: `Model ${model} still not available after pull.` };
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

// LV-5 (v0.2.12): deps are PINNED to the exact versions the test suite is
// validated against. Unpinned installs pulled starlette 1.3.1 (via latest
// fastapi), which removed app.add_event_handler and crashed the backend at
// import on every fresh install. Exact pins also make "Retry setup"
// deterministic: pip converges to this known-good set instead of silently
// upgrading (and re-breaking) an already-working machine. starlette is
// pinned explicitly because fastapi's own range allows it to drift.
// When bumping any pin: update the smoke test in
// .github/workflows/desktop-release.yml and re-run the full suite.
export const PINNED_DEPS = [
  "pyyaml==6.0.3",
  "fastapi==0.124.4",
  "starlette==0.50.0",
  "uvicorn==0.33.0",
  "httpx==0.28.1",
  "websockets==15.0.1",
  "pdfplumber==0.11.9",
  "openpyxl>=3.1,<4",
  "python-docx>=1.1,<2",
  "sqlite-vec==0.1.9",
  "faster-whisper==1.1.1",
  // P0 (Chip 0.2.31 regression, 2026-08-04): faster-whisper imports
  // requests through its model-download path. It arrived transitively via
  // huggingface-hub until that stack moved to httpx, leaving voice probes
  // false on fresh teacher machines. Keep it explicit until the build-time
  // lockfile fully closes transitive drift.
  "requests>=2.28",
  // P0-1 (Claudia QA 2026-08-03): av + ctranslate2 are TRANSITIVE deps of
  // faster-whisper. Left implicit, pip's resolution failed silently on a
  // teacher machine (--quiet swallowed the error) and every voice feature
  // died with "stt available: false". Listed explicitly so a failure is a
  // failure of a named dep, and verified after install (verifyPythonDeps).
  // Ranges, not exact pins: both ship platform-specific compiled wheels and
  // the compatible exact version differs per OS/arch/Python.
  "av>=11.0",
  "ctranslate2>=4.0,<5",
  "python-multipart==0.0.27",
  // P1-2 (Chip QA 0.2.36): docpipe's validate.py imports jsonschema for
  // schema validation. Without it, /api/sync/status and any vault path
  // throws ModuleNotFoundError, surfacing as a red "Something went wrong"
  // banner on every Settings/view load.
  "jsonschema>=4.0,<5",
  // Fix #3 (FIXES_NEEDED_v0.2.68): reportlab powers every PDF route
  // (artifacts router). Without it the router fails to import on startup,
  // all PDF endpoints 404, and the app silently loses a third of its routes.
  "reportlab>=4.0",
];

// macOS python.org installs ship WITHOUT SSL certs configured (need
// "Install Certificates.command"). --trusted-host is the retry fallback.
const SSL_WORKAROUND = [
  "--trusted-host", "pypi.org",
  "--trusted-host", "pypi.python.org",
  "--trusted-host", "files.pythonhosted.org",
];

function stateDir(): string {
  return path.join(os.homedir(), ".lingua-viva");
}

function appendSetupLog(text: string): void {
  try {
    const logDir = path.join(stateDir(), "logs");
    mkdirSync(logDir, { recursive: true });
    appendFileSync(path.join(logDir, "setup.log"), text);
  } catch { /* logging must never break setup */ }
}

function lastLines(text: string, n = 8): string {
  const lines = text.trim().split("\n").filter((l) => l.trim().length > 0);
  return lines.slice(-n).join("\n");
}

type RunResult = { code: number | null; output: string };

// D1-P0-001 (day-one walkthrough 2026-08-10): the old installer ran pip with
// --quiet, piped stderr into the void, and resolved even when every attempt
// failed — the THIRD recurrence of the swallowed-error class (P0-1 Claudia QA
// 08-03, Chip 0.2.31). Every setup command now has its full output captured
// to ~/.lingua-viva/logs/setup.log, and failures carry the real error text.
function runLogged(cmd: string, args: string[], timeoutMs = 1800000): Promise<RunResult> {
  return new Promise((resolve) => {
    appendSetupLog(`\n[${new Date().toISOString()}] $ ${cmd} ${args.join(" ")}\n`);
    let output = "";
    let settled = false;
    const finish = (code: number | null, extra?: string) => {
      if (settled) return;
      settled = true;
      if (extra) output += extra;
      appendSetupLog(`${output}\n[exit=${code}]\n`);
      resolve({ code, output });
    };
    let proc: ReturnType<typeof spawn>;
    try {
      proc = spawn(cmd, args, { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
    } catch (err) {
      finish(-1, String(err));
      return;
    }
    const timer = setTimeout(() => {
      try { proc.kill("SIGKILL"); } catch { /* already gone */ }
      finish(-1, "\n[setup command timed out]");
    }, timeoutMs);
    proc.stdout?.on("data", (d) => { output += String(d); });
    proc.stderr?.on("data", (d) => { output += String(d); });
    proc.on("error", (err) => { clearTimeout(timer); finish(-1, String(err)); });
    proc.on("close", (code) => { clearTimeout(timer); finish(code); });
  });
}

function venvPythonPath(venvDir: string): string {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

export type PythonEnvResult = {
  ok: boolean;
  /** The interpreter that must run the backend (venv python on success). */
  pythonCmd: string;
  detail: string;
};

// D1-P0-001 root cause: Ubuntu (and Debian) ship python3 with NO pip and NO
// ensurepip — `python3 -m pip` dies instantly with "No module named pip" on
// any machine that never installed python3-pip. The app only ever worked on
// dev machines because ~/.local already had pip and every dependency.
// Fix: give Lingua Viva its own virtualenv (created with --without-pip, which
// works even when ensurepip is stripped), bootstrap pip into it from the
// official PyPA zipapp, and install the pinned deps there. The venv is also
// immune to --break-system-packages/PEP 668 and to user-site drift.
export async function ensurePythonEnv(
  basePython: string,
  onProgress?: (message: string) => void,
): Promise<PythonEnvResult> {
  const venvDir = path.join(stateDir(), "pyenv");
  const venvPy = venvPythonPath(venvDir);
  const prefix = basePython === "py" ? ["-3"] : [];

  // 1. Create the venv (idempotent — reused on every later launch).
  if (!existsSync(venvPy)) {
    onProgress?.("Creating Lingua Viva's Python environment...");
    const created = await runLogged(basePython, [...prefix, "-m", "venv", "--without-pip", venvDir], 120000);
    if (created.code !== 0 || !existsSync(venvPy)) {
      // venv unavailable on this interpreter — fall back to installing
      // directly with the base python's own pip (works wherever pip exists,
      // e.g. python.org installs). Still fail-closed if that fails too.
      const legacy = await installDepsDirect(basePython);
      if (legacy.ok) {
        return { ok: true, pythonCmd: basePython, detail: "Dependencies installed (no venv support on this Python)." };
      }
      return {
        ok: false,
        pythonCmd: basePython,
        detail: `Could not create a Python environment (${lastLines(created.output, 3)}) and direct install also failed (${legacy.detail}).`,
      };
    }
  }

  // 2. Ensure pip exists inside the venv (bootstrap from PyPA's zipapp).
  const pipProbe = await runLogged(venvPy, ["-m", "pip", "--version"], 30000);
  if (pipProbe.code !== 0) {
    onProgress?.("Downloading the Python package installer...");
    const pipPyz = path.join(stateDir(), "pip.pyz");
    try {
      await downloadFile("https://bootstrap.pypa.io/pip/pip.pyz", pipPyz);
    } catch (err) {
      return {
        ok: false,
        pythonCmd: venvPy,
        detail: `Could not download the package installer (${err instanceof Error ? err.message : String(err)}). Check the internet connection, then Retry setup.`,
      };
    }
    let boot = await runLogged(venvPy, [pipPyz, "install", "pip"], 300000);
    if (boot.code !== 0) {
      boot = await runLogged(venvPy, [pipPyz, "install", ...SSL_WORKAROUND, "pip"], 300000);
    }
    try { unlinkSync(pipPyz); } catch { /* best effort */ }
    if (boot.code !== 0) {
      return { ok: false, pythonCmd: venvPy, detail: `Could not install pip: ${lastLines(boot.output)}` };
    }
  }

  // 3. Install the pinned dependencies. NO --quiet — ever again.
  onProgress?.("Installing Lingua Viva's components (the first run can take a few minutes)...");
  let install = await runLogged(venvPy, ["-m", "pip", "install", ...PINNED_DEPS]);
  if (install.code !== 0) {
    install = await runLogged(venvPy, ["-m", "pip", "install", ...SSL_WORKAROUND, ...PINNED_DEPS]);
  }
  if (install.code !== 0) {
    return { ok: false, pythonCmd: venvPy, detail: lastLines(install.output) };
  }
  return { ok: true, pythonCmd: venvPy, detail: "Python environment ready." };
}

// Legacy fallback: the pre-venv 4-attempt cascade, now with output captured
// and an honest failure result instead of a silent resolve.
async function installDepsDirect(basePython: string): Promise<{ ok: boolean; detail: string }> {
  const prefix = basePython === "py" ? ["-3"] : [];
  const attempts: string[][] = [
    ["--break-system-packages"],
    ["--break-system-packages", ...SSL_WORKAROUND],
    [],
    [...SSL_WORKAROUND],
  ];
  let lastOutput = "";
  for (const extra of attempts) {
    const result = await runLogged(basePython, [...prefix, "-m", "pip", "install", ...extra, ...PINNED_DEPS]);
    if (result.code === 0) return { ok: true, detail: "ok" };
    lastOutput = result.output;
  }
  return { ok: false, detail: lastLines(lastOutput) };
}

// --- Post-install dependency verification (P0-1, Claudia QA 2026-08-03) ---
//
// Even with ensurePythonEnv failing closed, the only honest check is
// importing each package in the same Python that will run the server —
// voice deps are NOT server deps: the backend boots fine without them and
// the mic just silently does nothing. Two tiers:
//   server: backend cannot start without these — surface loudly.
//   voice:  backend runs, but every voice feature is dead — surface as a
//           voice-specific warning so the wizard can say so in plain words.

export type DepVerification = {
  ok: boolean;
  missingServer: string[];
  missingVoice: string[];
};

const SERVER_IMPORTS = [
  "yaml", "fastapi", "starlette", "uvicorn", "httpx",
  "websockets", "pdfplumber", "sqlite_vec", "requests", "multipart", "jsonschema",
];
const VOICE_IMPORTS = ["av", "ctranslate2", "faster_whisper"];

export async function verifyPythonDeps(pythonCmd: string): Promise<DepVerification> {
  // One subprocess, one report: try each import independently so we can name
  // exactly what is missing instead of stopping at the first failure.
  const probe = [
    "import importlib, json",
    `mods = ${JSON.stringify([...SERVER_IMPORTS, ...VOICE_IMPORTS])}`,
    "missing = []",
    "for m in mods:",
    "    try:",
    "        importlib.import_module(m)",
    "    except Exception:",
    "        missing.append(m)",
    "print(json.dumps(missing))",
  ].join("\n");
  const args = pythonCmd === "py" ? ["-3", "-c", probe] : ["-c", probe];
  const result = await execFileText(pythonCmd, args, 30000);
  if (!result.ok) {
    // Could not even run Python — treat everything as unverified/missing.
    return { ok: false, missingServer: [...SERVER_IMPORTS], missingVoice: [...VOICE_IMPORTS] };
  }
  let missing: string[] = [];
  try {
    const parsed = JSON.parse(result.detail.trim().split("\n").pop() || "[]");
    if (Array.isArray(parsed)) missing = parsed.filter((m): m is string => typeof m === "string");
  } catch {
    return { ok: false, missingServer: [...SERVER_IMPORTS], missingVoice: [...VOICE_IMPORTS] };
  }
  const missingServer = missing.filter((m) => SERVER_IMPORTS.includes(m));
  const missingVoice = missing.filter((m) => VOICE_IMPORTS.includes(m));
  return { ok: missing.length === 0, missingServer, missingVoice };
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

  // Kill any lingering process on our port (prevents "address already in use" on retry)
  try {
    if (process.platform !== "win32") {
      execFileSync("sh", ["-c", `lsof -t -i :${port} | xargs kill -9 2>/dev/null || true`], { timeout: 3000 });
    } else {
      // P0-B: Windows port cleanup — find and kill any process holding our port
      execFileSync("cmd", ["/c", `for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') do taskkill /F /PID %a 2>nul`], { timeout: 5000, windowsHide: true });
    }
  } catch { /* best effort */ }

  // P1-5/F6: prevent .pyc writes into the signed bundle (breaks codesign)
  // P0-A: prevent OpenMP DLL collision on Windows (libiomp5md vs libomp140)
  const backendEnv: Record<string, string> = {
    ...process.env as Record<string, string>,
    PYTHONUNBUFFERED: "1",
    PYTHONDONTWRITEBYTECODE: "1",
    KMP_DUPLICATE_LIB_OK: "TRUE",
    LV_DESKTOP: "1"
  };

  const child = spawn(pythonCommand, [webPath, String(port)], {
    cwd: repoRoot,
    env: backendEnv,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true
  });

  // P0-B: log backend output to file for diagnostics (instead of drain-and-
  // discard, which caused orphaned backends to freeze when their reader died).
  const logDir = path.join(process.env.HOME || process.env.USERPROFILE || repoRoot, ".lingua-viva", "logs");
  try { mkdirSync(logDir, { recursive: true }); } catch { /* best effort */ }
  const logPath = path.join(logDir, "backend.log");
  try {
    const logStream = createWriteStream(logPath, { flags: "a" });
    child.stdout?.pipe(logStream);
    child.stderr?.pipe(logStream);
  } catch {
    // Fallback: drain without blocking (original behavior)
    child.stdout?.resume();
    child.stderr?.resume();
  }

  return {
    process: child,
    url: `http://127.0.0.1:${port}`
  };
}
