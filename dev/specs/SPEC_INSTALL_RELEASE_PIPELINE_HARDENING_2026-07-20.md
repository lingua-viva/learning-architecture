# SPEC: Install/Release Pipeline Hardening (Lingua Viva)

**Date**: 2026-07-20
**Status**: DRAFT — handoff for a detail-driven sweep
**Surface**: `install.sh`, `install.ps1`, native launcher heredocs
(`lv-launch` / `lv-launch.ps1`), `.github/workflows/release.yml`,
`.github/workflows/install-test.yml`
**Trigger**: same pattern as Mission Canvas's V3→V5 rounds on
`integration_onboarding.py` (`~/fde/mission-canvas/dev/SPEC_INTEGRATION_ONBOARDING_HARDENING_V5_2026-07-20.md`),
scaled down for this repo's size — one compressed round instead of three,
since the target surface here is ~700 lines of shell/PowerShell/YAML across
4 files rather than a single 465-line Python module with a 15-iteration
precedent sweep already run against a sibling file.

## 1. Why this surface, and why now

`dev/REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md` (this repo) closed out
the download-buttons work with `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md` at
`SHIPPED (partial)`. Its own words, verbatim, are the opening for this spec:

> Mac and Windows CLI binaries were built and smoke-tested in CI. Linux
> installer was verified end-to-end in CI. Mac `install.sh` and Windows
> `install.ps1` installer flows remain manually unverified.

That gap — CI only exercises the Linux path
(`.github/workflows/install-test.yml`, confirmed below, `name: Install Test
(Linux)`) — is exactly the shape of gap MC's V-series sweeps exist to close:
code that shipped, passed the tests that were written, but was never put
through the same fuzz/read/repro rigor on its untested branches. Two
release tags this cycle (`v1.0.1`, `v1.0.2`) already failed in CI for
reasons a closer read would have caught before tagging (§1 of MC's V5 spec
documents the same failure pattern in a different module: smoke-testing a
command that doesn't exist, then smoke-testing a check that can't run from
a frozen binary). The install scripts are the next most likely place for
that same class of "looks right, never exercised" bug, precisely because
they are the two paths CI doesn't touch.

This module was never given a hardening sweep before. There is no "round
1" fix commit to cite — this spec's §3 confirmed findings come directly
from a first structured read of `install.sh` and `install.ps1` in full
(391 and 303 lines respectively), done in this session, not from a prior
pass.

## 2. Scope

**In scope**:
- `install.sh` (391 lines) — binary-install branch (lines ~193-302) and
  source-fallback branch (lines ~306-391).
- `install.ps1` (303 lines) — `Install-NativeLauncher` (lines ~36-135),
  binary-install path, source-fallback path.
- The embedded native-launcher heredocs both scripts write to disk
  (`lv-launch`, `lv-launch.ps1`) — currently zero test coverage of any
  kind (confirmed: `grep -rn "install\.sh\|install\.ps1\|lv-launch"
  tests/` matches only `tests/test_project_metadata.py`, which reads the
  files as text for naming-contract assertions, not behavior).
- `.github/workflows/release.yml` — build/smoke/publish job structure,
  to the extent it explains why some install-script bugs would or
  wouldn't be caught before a tag goes live.
- `.github/workflows/install-test.yml` — confirmed Linux-only
  (`name: Install Test (Linux)`, single `curl-install` job on
  `ubuntu-latest`, no macOS/Windows runners).

**Out of scope**:
- `desktop/` (Electron app) and its release CI — that is Phase 3 of
  `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`, a separate unbuilt work item, not
  this spec's job.
- `linguaviva.art` landing page — already hardened and verified this
  session (`REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`, "Landing Site"
  section), not touched here.
- `lv.spec` (PyInstaller build config) and the CLI/runtime code the
  installers download and invoke — those are covered by the existing
  442-test suite and `mc`-equivalent health checks; this spec is about the
  install/launch mechanics, not the application they install.
- Any change to what CI *builds* (the 3-platform release matrix is correct
  per the report's verified 200-status asset checks) — this spec is about
  what CI *verifies after* building, and about the install scripts'
  internal correctness on the two platforms CI never runs.

## 3. Confirmed findings — read against the file, not assumed

**F-1 — `install.sh:32` hardcodes `arm64` for every macOS host, regardless
of actual architecture.**

```sh
darwin) PLATFORM="darwin"; ARCH="arm64" ;;  # Single universal binary
```

The comment claims this is fine because the release ships "a single
universal binary" — but the release matrix in `release.yml` builds and
publishes exactly one macOS asset, `lv-darwin-arm64` (arm64-only, not a
lipo'd universal binary; confirmed against the asset list in
`REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`'s "Live release" section).
On an Intel Mac, line 37's "✓ Detected" message reports `arm64` as
detected (it wasn't — it was assumed), then the script proceeds to
download `lv-darwin-arm64` and attempt to run a non-executable binary. The
correct behavior is either (a) detect real arch via `uname -m` and fail
loudly with a clear message on `x86_64` hosts since no Intel asset exists,
or (b) if an Intel asset is added later, actually detect and fetch it.
Right now the failure mode is silent-wrong-download, not a clean error.

**F-2 — `install.ps1:156` has no atomic-download-then-validate pattern,
unlike `install.sh`'s equivalent path.**

`install.sh`'s binary branch (lines ~197-201) downloads to a `mktemp`
tempfile, checks `[ -s "$TMPFILE" ]` (non-empty) before `mv`-ing it into
place — a partial/failed download never lands at the final path.
`install.ps1:156` does the opposite:

```powershell
Invoke-WebRequest -Uri $url -OutFile "$installDir\lv.exe" -UseBasicParsing -ErrorAction Stop
```

This writes directly to the final destination with no staging file and no
post-download size/validity check; `$binarySuccess = $true` is set
immediately on no-throw. A connection that drops mid-download (no
exception raised until the stream closes, or a proxy that returns a
truncated 200) can leave a corrupt `lv.exe` at the install path that the
script believes succeeded. This is the exact asymmetry the report's
caveat points at — the one installer path CI does verify (Linux) has the
safer pattern; the two paths CI doesn't verify (`install.sh`'s own darwin
branch, and all of `install.ps1`) each have a distinct, real defect.

## 4. Candidate leads — unverified, confirm or refute each with a live repro

- **L-1 — `INSTALL_DIR` variable reuse in `install.sh`.** Line 200 sets
  `INSTALL_DIR="${HOME}/.local/bin"` for the binary branch; line 324 sets
  `INSTALL_DIR="${HOME}/.lingua-viva"` for the source-fallback branch —
  same variable name, different meaning, different directory kind (one is
  a bin dir for a single executable, the other is an app home). Safe
  today only because the binary branch unconditionally `exit 0`s at line
  301 before the source-fallback branch's assignment is ever reached in
  the same run. Confirm: is there any code path (error handling, a future
  refactor, a sourced-then-modified copy) where both branches could
  execute in the same shell invocation? If genuinely unreachable, say so
  explicitly rather than silently leaving the shadowing in place.
- **L-2 — `install.sh:353` swallows stderr on the post-install health
  check.** `python3 -m src.lv_cli health 2>/dev/null || echo "  (Run 'lv
  health' to verify)"` discards whatever `health` actually printed on
  failure. Two of today's three release-tag attempts
  (`v1.0.1`/`v1.0.2`, per `REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`
  Phase 2) failed for reasons that would have been diagnosable faster with
  visible stderr. Confirm whether this swallow is intentional
  (cosmetic install-time UX) or should surface the real error to a log
  file at minimum.
- **L-3 — `install.ps1`'s server-start `catch {}` blocks are empty at two
  call sites** (binary path ~184-185, source-fallback path ~288-290) —
  confirm whether a failed `Start-Process` is silently swallowed with the
  script still reporting success downstream, the way F-2 shows the
  download check being skipped.
- **L-4 — native launcher scripts have zero test coverage.**
  `Install-NativeLauncher` (install.ps1:36-135) embeds a `lv-launch.ps1`
  heredoc containing its own health-check-and-idempotent-restart logic
  (`Test-PortOpen`), plus a `.bat` wrapper and `.lnk` shortcut creation via
  COM object with a try/catch fallback. `install.sh` embeds an analogous
  `lv-launch` heredoc. Neither has ever been executed under test — only
  read. Confirm: can either be extracted and exercised (even a syntax/
  static check, since no `shellcheck` binary is installed on this
  machine — confirmed absent) without a full install-CI run, or does
  this remain acknowledged-but-untestable-in-this-environment?
- **L-5 — CI only catches what it explicitly asserts.**
  `install-test.yml` asserts: binary lands at `~/.local/bin/lv` (exact
  path only — would not catch F-1-style wrong-arch on macOS since it never
  runs on macOS), "Web UI is live" appears in the log, `lv health --json`
  exits, and `lv health` prints "Lingua Viva health:". It does not assert
  installer idempotency (running install.sh twice), does not assert
  behavior when the target port is already occupied, and does not assert
  anything about `install.ps1` on any runner. Confirm which of these gaps
  are worth a `windows-latest` job addition to `install-test.yml` vs.
  accepted as out-of-budget for a repo this size.

## 5. Method

One compressed sweep, not three separate V-rounds (this repo's install
surface is roughly a sixth the size of MC's onboarding module and has no
prior sweep to build on — there is nothing "V3" or "V4" already shipped
here to iterate past). Read every branch of `install.sh` and
`install.ps1` end to end, including the embedded heredoc launcher scripts
as their own unit. For each of §4's leads, either produce a live repro
(a controlled bad-network/bad-arch/bad-permission condition on a real or
mocked run) or a written reason it's a non-issue, matching the ground-
truth discipline `AGENTS.md`-derived repos use elsewhere: confirmed means
reproduced, not reasoned about. Treat §3's two findings as the calibration
case — F-1 is a silent-wrong-asset bug, F-2 is a silent-corrupt-install
bug; both are the same *shape* of problem (a script reports success when
it didn't actually verify success), so any other candidate that fits that
shape deserves equal weight.

## 6. Definition of done

- `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` —
  iteration count, bugs-found/fixed table with line citations, before/
  after state of test coverage for this surface.
- `install.sh:32` (F-1) fixed: real `uname -m` detection on darwin, clear
  failure on unsupported arch rather than silent wrong-download.
- `install.ps1:156` (F-2) fixed: tempfile-stage-then-validate-then-move,
  matching `install.sh`'s existing pattern, so both platforms share one
  correctness bar.
- Every L-item in §4 resolved to either a fix + regression coverage, or a
  written non-issue justification in the report.
- Any new coverage added for `tests/test_project_metadata.py` or a new
  test file, in that file's existing style (see current naming-contract
  tests as the pattern).
- `python3 -m pytest tests/ -q` green.
- `python3 -m src.lv_cli health --json` (or repo-equivalent) clean.
- `dev/INDEX.md` row for this spec updated from DRAFT to the real outcome,
  same commit as the report, backed by evidence actually run.

## 7. Open question for operator

None blocking. If the sweep concludes a macOS/Windows CI runner should be
added to `install-test.yml` (closing L-5 fully rather than partially),
that's a CI-cost/runner-minutes tradeoff worth a named decision in the
report rather than added unilaterally — flag it, don't just add it.
