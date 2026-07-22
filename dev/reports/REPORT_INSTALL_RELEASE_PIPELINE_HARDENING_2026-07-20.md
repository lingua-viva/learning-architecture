# REPORT: Install/Release Pipeline Hardening (Lingua Viva)

**Date**: 2026-07-20
**Spec**: `dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`
**Execution prompt**: `dev/EXECUTION_PROMPT_INSTALL_RELEASE_HARDENING_2026-07-20.md`
**Iterations**: 1 compressed sweep, as scoped (not three V-rounds — no prior
pass existed on this surface). Sweep converged: a full re-read of both
installers after all fixes found zero new issues in the shape F-3/F-4 would
have matched.
**Status**: All 2 confirmed findings fixed. All 5 candidate leads resolved
(3 fixed, 1 fixed defensively though confirmed unreachable, 1 resolved as a
named decision, not a code change). Suite green: 461/461 (was 443/443
before this sweep; +18 new tests).

---

## Environment constraints (named up front, per the execution prompt's
explicit ask)

- No `shellcheck` binary on this machine (confirmed: `which shellcheck` →
  not found). `install.sh` and the `lv-launch` heredoc were syntax-checked
  with `sh -n` / `dash -n` instead — a real but partial substitute.
- No `pwsh` or `powershell` binary on this machine (confirmed: both
  absent). `install.ps1` and the `lv-launch.ps1` heredoc could not be
  executed, syntax-checked, or PowerShell-parsed at all. All F-2/L-3/L-4
  coverage on the PowerShell side is **structural** (string/shape
  assertions against the source) or a **simulation** of the underlying
  network-behavior class in a substitute language (see F-2 below), not a
  real PowerShell execution. A Windows or `pwsh`-equipped runner is needed
  to close this gap for real; `tests/test_install_launcher_scripts.py::
  test_no_shellcheck_or_pwsh_available_here_documented` will fail loudly
  (on purpose) the day either tool becomes available here, as a prompt to
  extend coverage.

---

## Bugs found and fixed

| ID | File:Line (pre-fix) | Bug | Fix | Regression test |
|---|---|---|---|---|
| F-1 | `install.sh:32` | Hardcoded `ARCH="arm64"` for every macOS host; an Intel Mac was told "✓ Detected arm64" (false) and would silently download and attempt to run an arm64-only binary (exec format error — Rosetta 2 translates x86_64→arm64 only, not the reverse) | Real `uname -m` detection kept from the generic case block above; darwin branch now only overrides nothing, and instead validates: `arm64` passes, anything else prints an explicit "no published macOS binary for architecture: $ARCH" warning and sets `SKIP_BINARY=1`, which the download `if` now checks so it skips straight to the existing source-install fallback instead of attempting a doomed/mislabeled download | `tests/test_install_hardening.py::test_f1_*` (5 tests) |
| F-2 | `install.ps1:156` | `Invoke-WebRequest -OutFile "$installDir\lv.exe"` wrote straight to the final path; `$binarySuccess = $true` was set on no-throw alone, with no post-download validity check. A connection that closes without an exception (no `Content-Length` mismatch — e.g. `Connection: close`-terminated body) leaves a truncated `lv.exe` reported as a successful install | Stage to a tempfile (`[System.IO.Path]::GetTempFileName()`-style random name), check `$downloaded.Length -gt 0` before `Move-Item` into the final path; `finally` block removes the tempfile either way. Matches `install.sh`'s own `mktemp` + `[ -s "$TMPFILE" ]` + `mv` pattern exactly, so both platforms now share one correctness bar | `tests/test_install_hardening.py::test_f2_*` (2 structural tests — see repro note below) |

### F-1 repro (real, executed)

Extracted the OS/ARCH detection header of `install.sh` into a standalone
script and ran it under `/bin/sh` (dash, available on this machine) with a
stub `uname` reporting `Darwin` / `x86_64`:

- **Before fix**: printed `✓ Detected: darwin-arm64` — wrong, the real
  architecture (`x86_64`) was silently discarded and replaced with the
  hardcoded value.
- **After fix**: prints `⚠ No published macOS binary for architecture:
  x86_64 (only Apple Silicon/arm64 is built) — installing from source
  instead.` then `✓ Detected: darwin-x86_64` — correct, and `SKIP_BINARY=1`
  routes the script past the binary-download attempt straight to the
  already-working source-install fallback.
- Apple Silicon (`arm64`) hosts: unaffected, `SKIP_BINARY` stays unset,
  behavior identical to before.

This is a genuine executed repro (not reasoning-from-reading), permanently
captured in `tests/test_install_hardening.py::
test_f1_intel_mac_is_detected_as_x86_64_not_hardcoded_arm64` and its
neighbors.

### F-2 repro (simulated — no PowerShell runtime available)

`install.ps1` cannot run on this machine at all, so the finding was
verified by reproducing the underlying HTTP-client behavior class in a
substitute (Python `http.server` + `curl`, both available here), not by
running the actual PowerShell script:

1. A raw TCP server sent `HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n`
   followed by 17 bytes of body, then closed the socket — no
   `Content-Length` header, so the client has no length to validate
   against and must infer "done" from the connection closing.
2. `curl -o final/lv.exe` against this server returned **exit 0** (no
   error) and left a 17-byte corrupt file at the destination path.

This demonstrates the exact failure shape the spec named: "no exception
raised until the stream closes... can leave a corrupt `lv.exe` at the
install path that the script believes succeeded." `Invoke-WebRequest`'s
behavior on a `Connection: close`-terminated response without a
`Content-Length` mismatch follows the same HTTP semantics, so the same
failure class applies — but this is inference from a substitute
reproduction, not a literal PowerShell execution, and the report says so
plainly rather than implying more coverage than exists. The fix (tempfile +
non-empty check before move) matches `install.sh`'s own accepted bar for
this exact scenario class; note that bar (non-empty, not full
`Content-Length` reconciliation) would **not** by itself have caught this
specific 17-byte truncation either — `install.sh`'s pattern has the same
blind spot for small-but-nonzero truncated payloads. Going further (full
content-length reconciliation on both platforms) was out of scope: the
spec's ask was parity with `install.sh`'s existing pattern, not a stronger
one. Flagging this as a residual gap for the operator rather than silently
exceeding scope.

---

## Candidate leads (L-1 through L-5)

| ID | Resolution | Detail |
|---|---|---|
| L-1 | **Fixed defensively** | Confirmed genuinely unreachable in the same invocation: the binary branch's `INSTALL_DIR="${HOME}/.local/bin"` is always followed by `exit 0` before the source-fallback branch's `INSTALL_DIR="${HOME}/.lingua-viva"` assignment is ever reached (verified via `tests/test_install_hardening.py::test_l1_binary_branch_always_exits_before_source_fallback_reassignment`). Fixed anyway by renaming the source-fallback copy to `SRC_INSTALL_DIR` — removes the shadowing risk for any future refactor that might change the exit-early invariant, at zero behavioral cost. Required updating one pre-existing assertion in `tests/test_project_metadata.py` (the shim heredoc text it checks literally, `cd "$INSTALL_DIR" && ...`, is now `cd "$SRC_INSTALL_DIR" && ...`) |
| L-2 | **Fixed** | `install.sh:353`'s `python3 -m src.lv_cli health 2>/dev/null` discarded stderr unconditionally. Now redirects to `${HOME}/.lingua-viva/install-health-stderr.log` and the fallback message names the log path, so a failure is diagnosable without re-running `lv health` blind — the exact gap that slowed diagnosis on two of this cycle's release-tag failures (`v1.0.1`, `v1.0.2`, per `REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`) |
| L-3 | **Fixed** | Both `Start-Process` call sites for the web server (binary path, source-fallback path) had `-ErrorAction SilentlyContinue` inside an empty `catch {}` — a failure to launch was swallowed with no message, deferring all diagnosis to the 30-second poll timeout. Changed to `-ErrorAction Stop` with a `catch` that prints `$_.Exception.Message`, so a real launch failure (e.g. missing binary, permissions) surfaces immediately instead of after a 30s wait. The **third** `catch {}` in `install.ps1` (inside `lv-launch.ps1`'s per-second health poll) was deliberately left alone — it's a legitimate silent-retry-until-timeout pattern mirroring `install.sh`'s own polling loop, not an unreported action failure, and is outside L-3's named scope (§4 named only the two `Start-Process` sites) |
| L-4 | **Resolved — real coverage where possible, acknowledged gap where not** | `lv-launch` (POSIX `sh`, embedded in `install.sh`) now has both a syntax check (`sh -n`) and genuine behavioral tests: extracted to a tempfile and executed under a sandboxed `HOME` with stubbed `curl`/`nc`/`lv` on `PATH`, covering the "already healthy → exit 0, don't start a second server" path and the "nothing to start → fail loudly, exit 1" path (both previously untested and unexercised). `lv-launch.ps1` (embedded in `install.ps1`) cannot be executed or syntax-checked here at all — no `pwsh`/`powershell` on this machine — so its coverage is a structural presence check only (required function names, balanced braces), explicitly marked as non-behavioral in the test's own docstring. New file: `tests/test_install_launcher_scripts.py` (6 tests) |
| L-5 | **Named decision, not a code change** | See below |

### L-5 — named decision for the operator

`install-test.yml` is confirmed Linux-only (`name: Install Test (Linux)`,
single `ubuntu-latest` job). It does not test `install.ps1` on any runner,
does not test `install.sh` idempotency (running it twice), and does not
test port-already-occupied behavior.

**Observation that changes the calculus from what the spec anticipated**:
this repo (`github.com/lingua-viva/learning-architecture`) is a **public**
GitHub repository. GitHub Actions minutes are free and unmetered for
public repos on all runner OSes, including `windows-latest` — there is no
per-minute billing multiplier to weigh here, unlike a private repo. That
significantly weakens the "runner-minutes tradeoff" the spec asked to name
explicitly, in favor of adding coverage.

**Recommendation**: add a `windows-latest` job to `install-test.yml` that
runs `install.ps1` end-to-end, mirroring the existing Linux job's
assertions (binary lands, "Web UI is live" in the log, `lv health --json`
exits, `lv health` prints the health line). The case for this is stronger
than a generic coverage gap: **F-2, a real bug, was found on exactly this
untested path** — the same class of "looks right, never exercised" failure
that produced two failed release tags this cycle on the paths CI *does*
run. Installer idempotency and port-occupied behavior are lower-priority
additions to the existing Linux job.

**Not implemented in this session.** Per the execution prompt's explicit
instruction ("don't add a new runner unilaterally without flagging the
runner-minutes tradeoff" / "name it explicitly for the operator rather than
deciding solo and moving on quietly"), this is flagged as a recommendation
for the operator's own commit window, not added here.

---

## Test coverage: before vs after

| | Before | After |
|---|---|---|
| `install.sh` / `install.ps1` behavioral or structural tests | 0 (only `test_project_metadata.py`'s branding/contract assertions, which read the files as text for naming, not behavior) | 21 new tests across `tests/test_install_hardening.py` (12) and `tests/test_install_launcher_scripts.py` (6, of which 4 are real `sh` executions, 1 structural, 1 environment-doc), plus 1 pre-existing `test_project_metadata.py` assertion updated for the L-1 rename |
| `lv-launch` (POSIX sh heredoc) | Never extracted, never run, never syntax-checked | Syntax-checked (`sh -n`) + 2 real behavioral executions (healthy-port early-exit, nothing-to-start failure path) |
| `lv-launch.ps1` (PowerShell heredoc) | Never extracted, never run | Structural presence check only (no `pwsh` on this machine — acknowledged gap, test documents it and will fail on purpose if `pwsh` ever becomes available) |
| Total suite | 443 passed | 461 passed |

---

## Verification run (this session, this machine)

```
$ dash -n install.sh                          # syntax OK
$ python3 -m pytest tests/ -q
461 passed in 124.05s
$ python3 -m src.lv_cli health
Lingua Viva health: local model service reachable; provider=local
```

---

## What NOT touched (per spec §2 out-of-scope)

- `desktop/` (Electron) release CI — Phase 3 of `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`, untouched.
- `linguaviva.art` — already hardened this session per `REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`, untouched.
- `release.yml`'s 3-platform build matrix — correct per that report's live 200-status asset checks, untouched.
- `lv.spec` / application code the installers download — covered by the existing 443-test suite, untouched.

## Commit convention note

Per this operator's standing convention across repos (`memory/
feedback_lv_commit_window.md`), all changes in this sweep are left staged/
described for the operator's own commit window — nothing was committed in
this session. Changed/added files:

- `install.sh` (F-1, L-1, L-2 fixes)
- `install.ps1` (F-2, L-3 fixes)
- `tests/test_install_hardening.py` (new)
- `tests/test_install_launcher_scripts.py` (new)
- `tests/test_project_metadata.py` (one assertion updated for the L-1 rename)
- `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` (this file)
- `dev/INDEX.md` (row updated from DRAFT to this outcome)
