Copy-paste this into a fresh session to execute
`dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`.

---

```markdown
You're working in `~/learning-architecture`. Read
`dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` in full before touching
anything — it's the handoff spec for this task. Also skim
`dev/REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md`, which it cites throughout — that report is
where today's release-pipeline work (Phases 1-2 of `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`) closed
out, and it names the exact gap this spec exists to close in its own words: Mac `install.sh` and
Windows `install.ps1` installer flows remain manually unverified, because CI
(`.github/workflows/install-test.yml`) only ever runs the Linux path.

## Why this task

Two release tags this cycle (`v1.0.1`, `v1.0.2`) failed in CI for reasons a closer read would
have caught before tagging — smoke-testing a CLI command that doesn't exist, then smoke-testing a
check that can't run from a frozen binary. `v1.0.3` succeeded. That failure pattern — code that
looks right until it's actually exercised — is exactly what CI still can't catch on the two
installer paths (`install.sh`'s macOS branch, all of `install.ps1`) it never runs. This spec asks
for one structured read-and-repro sweep over those specific files, the same discipline
`~/fde/mission-canvas` uses for its own hardening rounds (ground truth is read at cited lines and
reproduced, not assumed) — scaled down for this repo's much smaller surface: one sweep, not three
rounds, since there's no prior pass on this surface to build on.

## Start here — two findings already confirmed by reading, not yet fixed

§3 of the spec hands you two real bugs, found this session by reading both files in full line by
line (no prior sweep exists for this surface):

1. **F-1**: `install.sh:32` hardcodes `ARCH="arm64"` for every macOS host — there's no real
   `uname -m` detection. The release only ships one macOS asset (`lv-darwin-arm64`), so an Intel
   Mac gets told "✓ Detected arm64" (false) and silently downloads a binary it can't execute.
   Fix: detect real arch, fail loudly and clearly on unsupported ones (don't silently proceed).
2. **F-2**: `install.ps1:156` downloads straight to the final install path with
   `Invoke-WebRequest -OutFile "$installDir\lv.exe"` — no tempfile staging, no post-download
   size/validity check, `$binarySuccess = $true` set on no-throw alone. Compare this against
   `install.sh`'s own binary-install branch (lines ~197-201), which stages to a `mktemp` tempfile
   and checks `[ -s "$TMPFILE" ]` before moving it into place. `install.ps1` should match that
   pattern.

Reproduce both yourself first (mock a bad-arch host for F-1; mock a truncated/failed download for
F-2 — e.g. a server that closes the connection mid-response), fix them for real with regression
coverage, and treat these as your calibration case: both are the same *shape* of bug — a script
reporting success without having verified success. Anything else in the sweep matching that shape
deserves equal weight.

## The sweep

§4 of the spec lists 5 candidate leads (L-1 through L-5) — unverified, each needs either a
repro-and-fix or a written non-issue reason in your report:

- L-1: `INSTALL_DIR` variable reuse in `install.sh` (line 200 vs. line 324, same name, different
  meaning) — confirm it's genuinely unreachable as a bug today, or fix the shadowing.
- L-2: `install.sh:353` swallows stderr on the post-install health check — the exact kind of
  hidden detail that made today's two failed release tags slower to diagnose. Confirm whether
  that's acceptable or should surface to a log.
- L-3: `install.ps1`'s two empty `catch {}` blocks around `Start-Process` (binary path
  ~184-185, source-fallback path ~288-290) — confirm whether a failed server start is silently
  swallowed.
- L-4: the embedded native launcher heredocs (`lv-launch` in `install.sh`, `lv-launch.ps1` in
  `install.ps1`'s `Install-NativeLauncher`, lines ~36-135) have zero test coverage of any kind —
  confirmed via `grep -rn "install\.sh\|install\.ps1\|lv-launch" tests/`, which only turns up
  `test_project_metadata.py` reading the files as text, not executing them. `shellcheck` is not
  installed on this machine — confirm whether any extraction/exercise of this logic is possible
  without a full CI run, or note it as acknowledged-but-untestable here.
- L-5: `.github/workflows/install-test.yml` is confirmed Linux-only (`name: Install Test
  (Linux)`, single `ubuntu-latest` job) and only asserts binary path, "Web UI is live" in the
  log, and `lv health`/`lv health --json` exit behavior — it doesn't test installer idempotency
  (running install.sh twice), port-already-occupied behavior, or anything on `install.ps1`.
  Decide, and name the decision explicitly in your report, whether any of that gap is worth
  closing with a new CI job vs. accepted as out of budget for a repo this size — don't add a new
  runner unilaterally without flagging the runner-minutes tradeoff.

Every bug you fix needs a regression test — extend `tests/test_project_metadata.py` in its
existing style, or add a new file if the coverage doesn't fit that file's shape.

## What NOT to touch

- `desktop/` (Electron) and its release CI — that's Phase 3 of `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`,
  a separate, already-tracked, unbuilt item. Not this spec's job.
- `linguaviva.art` — already hardened and verified this session, out of scope here.
- The release build matrix itself (`release.yml`'s 3-platform build) — it's correct, verified via
  live 200-status asset checks in the report. This spec is about the install scripts' own
  correctness and what CI verifies *after* the build, not what CI builds.
- `lv.spec` / the application code the installers download — covered by the existing test suite,
  not this surface.

## Definition of done (spec §6 — full detail there)

- `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md` — iteration count,
  bugs-found/fixed table with line citations, before/after test-coverage state for this surface.
- F-1 and F-2 fixed with regression coverage.
- Every L-item resolved: fix+test, or written non-issue reasoning in the report.
- `python3 -m pytest tests/ -q` green.
- `python3 -m src.lv_cli health --json` (or this repo's equivalent) clean.
- `dev/INDEX.md` row for this spec updated from DRAFT to your real outcome, same commit as the
  report, backed by evidence you actually ran.

## Discipline

- Confirmed means reproduced — mock the bad-arch / bad-network condition and show the actual
  before/after behavior, don't reason your way to "confirmed" from reading alone.
- If anything in the sweep turns out to need a CI runner-minutes tradeoff decision (see L-5), name
  it explicitly for the operator rather than deciding solo and moving on quietly.
- Do not commit yourself unless explicitly told to in this session — leave changes
  staged/described for the operator's own commit window. Standing convention across this
  operator's repos.
- Report back when the sweep converges (a full pass finds zero new issues), and name the known
  constraint you're working under explicitly: no `shellcheck` on this machine, and no macOS/
  Windows CI runner to validate against live — your repros for F-1/F-2/L-3/L-4 will necessarily be
  local mocks/simulations rather than a real cross-platform CI run, and the report should say so
  plainly rather than implying more coverage than exists.

Start by reproducing F-1 and F-2, then move to L-1 through L-5 in order.
```
