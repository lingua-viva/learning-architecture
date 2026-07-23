# Lingua Viva Desktop — Full Resolution Report

**Date**: 2026-07-22
**Duration**: ~4 hours (11:00 → 17:30 PDT)
**Outcome**: App downloads, opens, and runs on fresh Macs. Verified on 3 independent machines.
**Final version**: v0.2.5 (live on linguaviva.art)

---

## The Problem Statement

The Lingua Viva desktop app could not be downloaded and opened by a stranger on macOS. Multiple independent failure modes compounded, each masking the next. The demo was tomorrow.

---

## Timeline of Fixes (v0.2.1 → v0.2.5)

| Version | What Was Broken | What Was Fixed |
|---|---|---|
| **v0.2.1** | App unsigned (ad-hoc/Electron default). Gatekeeper hard-blocks it. "Notarization indicates this code has been revoked." | — (this was the starting state) |
| **v0.2.2** | ↑ Fixed. Signed + notarized (Developer ID: Mical Neill, XWT7RB624U). Gatekeeper accepts. | Added signing keychain, notary API key, separate `xcrun notarytool` step, hard CI verification gate. |
| **v0.2.3** | Setup wizard loops: asks for Python even when installed, Ollama detection fails even when running, full wizard restarts on server crash. | 4 fixes: `detectPythonBroad()` for initial check, `checkOllama()` via HTTP first, no full-flow restart on server crash, 4-min Ollama timeout. |
| **v0.2.4** | Server fails to start: "Check Python dependencies or port 8787." pip install silently fails because macOS Python has no SSL root certs. | pip install tries `--trusted-host pypi.org` fallback, port cleanup (`lsof + kill`) before server start. |
| **v0.2.5** | Server STILL fails: `/api/health` returns 500 (crashes on missing README.md), then pipe buffer fills and Python process deadlocks permanently. | Health endpoint wrapped in try/except, `check_readme_overclaims()` skips if file missing, stdio pipes drained with `.resume()`. |

---

## Root Causes (in order of discovery)

### 1. No Code Signing or Notarization (v0.2.1)

**Symptom**: Gatekeeper blocks the app on any Mac. "This code has been revoked."

**Root cause**: `desktop-release.yml` had zero signing steps. electron-builder produced an ad-hoc signed binary with `Identifier=Electron`, `TeamIdentifier=not set`.

**Fix**: Ported Mission Canvas's proven signing pipeline:
- Keychain setup step (imports .p12 cert)
- `xcrun notarytool submit --wait` as a separate step (not electron-builder's built-in `notarize` which had credential conflicts)
- Hard CI gate: build fails if `TeamIdentifier` is missing after signing

**Complications encountered (9 CI iterations)**:
1. OpenSSL 3.x .p12 format incompatible with macOS `SecKeychainItemImport` → rebuilt with 3DES+SHA1 ciphers
2. Entitlements path resolution (electron-builder looks in `buildResources/` dir) → moved to `desktop/build/`
3. `@electron/notarize` credential conflict ("Cannot use password, API key and keychain at once") → bypassed entirely with direct `xcrun notarytool`
4. `invalidPEMDocument` from notarytool → separated signing and notarization into distinct workflow steps

**Blocker**: GitHub secrets needed to be set on `lingua-viva/learning-architecture`. Required generating a classic PAT with `repo` + `workflow` scope (fine-grained PATs don't expose the Secrets permission clearly in the UI).

### 2. Setup Wizard Loops and Re-Asks (v0.2.3)

**Symptom**: Wizard asks to install Python even when it's already installed. Asks for Ollama even when it's running. Restarts the entire flow on server failure.

**Root causes**:
- `detectPython()` only checked `python3` on PATH. Electron's process PATH doesn't include `/usr/local/bin/` where the .pkg installs Python.
- `checkOllama()` only ran `ollama --version` (CLI). If Ollama.app is running but CLI isn't on PATH, it returns false.
- Server crash triggered `runSetupFlow()` from the top (re-asked all prerequisites).

**Fixes**:
- `detectPythonBroad()`: checks 5 standard macOS paths (`/usr/local/bin/python3`, `/Library/Frameworks/Python.framework/Versions/3.{11,12,13}/bin/python3`, `/opt/homebrew/bin/python3`)
- `checkOllama()`: checks HTTP `localhost:11434/api/tags` FIRST, falls back to CLI
- Server retry only restarts the server process, not the whole wizard
- Extended Ollama polling timeout from 2min to 4min (first-launch setup with "Move to Applications" dialog takes time)

### 3. pip Install Fails Silently (v0.2.4)

**Symptom**: "Server did not start. Check Python dependencies or port 8787."

**Root cause**: Python 3.12 from python.org ships WITHOUT SSL root certificates. `pip install` fails with `SSL: CERTIFICATE_VERIFY_FAILED` when trying to reach PyPI. The `installPythonDeps` function resolved silently on any error.

**Additional issues**:
- Missing `--break-system-packages` flag (PEP 668 on macOS 14+)
- Missing packages (`pdfplumber`, `sqlite-vec`) that install.sh has but desktop didn't

**Fix**: pip install now tries 4 strategies in order:
1. `--break-system-packages` (normal)
2. `--break-system-packages` + `--trusted-host pypi.org --trusted-host files.pythonhosted.org` (SSL bypass)
3. Bare install (older pip compatibility)
4. Bare + `--trusted-host`

Also: port 8787 cleanup (`lsof + kill -9`) before spawning the server to prevent "address already in use" on retry.

### 4. Health Endpoint Crashes + Pipe Deadlock (v0.2.5)

**Symptom**: Server process starts and accepts TCP connections, but never responds to any HTTP request. Wizard times out and reports "Server did not start."

**Root cause** (diagnosed independently by two testers):
1. `/api/health` calls `run_doctor()` which calls `check_readme_overclaims()` which reads `README.md` — a file that exists in the repo but is NOT packaged in the Electron app. `FileNotFoundError` propagates → FastAPI returns 500 → Electron's readiness probe fails.
2. Electron spawns Python with `stdio: "pipe"` but NEVER reads stdout/stderr. Each 500 response dumps a full traceback (~50 lines) to stderr. After ~15 polls (10 seconds), macOS's 64KB pipe buffer fills. Python's next `write()` call blocks forever, deadlocking the entire asyncio event loop. TCP connections are accepted (kernel-level) but no HTTP response is ever produced.

**Fix**:
1. `check_readme_overclaims()`: skip gracefully if README doesn't exist
2. Health endpoint: wrapped in try/except, returns `{"status": "degraded", "error": "..."}` instead of crashing
3. `child.stdout.resume()` + `child.stderr.resume()` to always drain pipes

---

## What's Now Verified Working

| Check | Status |
|---|---|
| Download from linguaviva.art | ✅ One version (v0.2.5), correct links |
| Signed with Developer ID | ✅ Mical Neill (XWT7RB624U) |
| Notarized | ✅ Apple accepted |
| Gatekeeper | ✅ Accepted on fresh Macs |
| Python detection (already installed) | ✅ No re-ask |
| Ollama detection (daemon running) | ✅ HTTP check passes |
| pip install (no SSL certs) | ✅ Trusted-host fallback |
| Server starts | ✅ Health returns 200 |
| App UI loads | ✅ Verified on 3 machines |
| CI hard gate (can't ship unsigned) | ✅ Build fails if TeamIdentifier missing |

---

## Architecture Decisions Made

1. **Signing and notarization are SEPARATE CI steps.** electron-builder signs. `xcrun notarytool` notarizes. The built-in `mac.notarize` integration has credential conflicts that wasted 4 builds.

2. **The health endpoint must never crash.** It's a liveness probe, not a dev audit. Wrapped in try/except permanently.

3. **Stdio pipes must always be drained.** Any child process spawned with `stdio: "pipe"` that isn't read will eventually deadlock. `.resume()` is the minimum viable drain.

4. **pip install must handle the SSL-less macOS Python.** Every python.org .pkg install ships without root certs. `--trusted-host` is the workaround that doesn't require user action.

5. **Detection must check RUNNING STATE, not just PATH.** Ollama detection checks HTTP (is it actually serving?) not CLI (is the binary findable?). Python detection checks known macOS install paths, not just `$PATH`.

---

## Files Changed (v0.2.1 → v0.2.5)

| File | Changes |
|---|---|
| `.github/workflows/desktop-release.yml` | Keychain setup, notary key staging, `xcrun notarytool` step, signature verification gate |
| `desktop/package.json` | `mac.notarize: false`, `hardenedRuntime`, `entitlements`, version bumps |
| `desktop/build/entitlements.mac.plist` | New file (JIT + unsigned memory + disable library validation for Electron V8) |
| `desktop/electron/bootstrap.ts` | `checkOllama()` HTTP-first, `installPythonDeps` 4-strategy cascade, `startBackend` port cleanup + pipe drain |
| `desktop/electron/main.ts` | `detectPythonBroad()` for initial check, no full-flow restart, 4-min Ollama timeout |
| `desktop/electron/setup-wizard.html` | Single Python button, polling state UI |
| `doctor/support_loop/doctor.py` | `check_readme_overclaims()` skips if file missing |
| `src/web.py` | Health endpoint wrapped in try/except |

---

## Secrets Required (for future reference)

These 5 secrets must exist on `lingua-viva/learning-architecture` (GitHub → Settings → Secrets):

| Secret | Purpose |
|---|---|
| `CSC_LINK` | .p12 certificate (base64, 3DES+SHA1 format) |
| `CSC_KEY_PASSWORD` | Password for the .p12 |
| `APPLE_API_KEY_BASE64` | App Store Connect API key (.p8, base64) |
| `APPLE_API_KEY_ID` | Key ID (594LJ446PR) |
| `APPLE_API_ISSUER` | Issuer ID (ae104d24-be49-4054-992d-9b28be3ded83) |

Set via classic PAT with `repo` + `workflow` scope. Fine-grained PATs don't reliably expose the Secrets permission.

---

## Lessons

1. **"CI green" ≠ "download works."** The build passed for weeks while producing an unsigned app that Gatekeeper blocked on every Mac.

2. **Five independent failure modes stacked.** Each one was masked by the one above it. You couldn't see the pip SSL issue until signing worked. You couldn't see the README crash until pip installed. You couldn't see the pipe deadlock until the health endpoint was exercised.

3. **Test from the outside in.** Download → open → Gatekeeper → wizard → server → UI. Every internal test (unit tests, `mc health`, CI green) missed all five bugs because they don't exercise the delivery surface.

4. **The health endpoint is the most critical code in a desktop app.** If it crashes, the wrapper thinks the server is down, and the user sees "Server did not start" with no way to proceed. It must be trivial and indestructible.

5. **macOS Python from python.org is hostile to pip by default.** No SSL certs, PEP 668 blocks installs, and the binary lands outside the Electron process's PATH. All three must be handled explicitly.

---

*Report by kiro.design. Verified on 3 independent machines (2 external testers + operator). Demo-ready as of 2026-07-22 17:31 PDT.*
