# Lingua Viva Site + Release Pipeline Report — 2026-07-20

## Scope

This report records the work completed in the `linguaviva.art` landing-page
and Lingua Viva download-button/release-pipeline pass.

Repos touched:
- `/home/mical/linguaviva.art`
- `/home/mical/learning-architecture`

Repos explicitly checked and not changed:
- `/home/mical/missioncanvas.ai`

## Landing Site

Standalone site created at `/home/mical/linguaviva.art`.

Commits:
- `1b6a248` — `Create Lingua Viva landing page`
- `7c3a2b8` — `Harden Lingua Viva landing page`

Work completed:
- Created a separate static site for `linguaviva.art`.
- Added `CNAME`, `index.html`, `style.css`, `app.js`, icons, manifest,
  robots, sitemap, README, `.nojekyll`, and `404.html`.
- Reused the Mission Canvas site structure as a layout reference only;
  no Mission Canvas infra or deployment config was reused or changed.
- Rewrote the page around Lingua Viva as an open-source, local-first
  education tool for teachers.
- Removed third-party font calls so the site makes no external network
  requests on load.
- Added accessibility hardening: skip link, keyboard focus states,
  reduced-motion handling, and safer disabled download controls.
- Added responsive hardening for desktop, tablet, mobile, and 320px narrow
  screens.
- Left the download buttons intentionally pending with stable IDs:
  - `btn-dl-mac`
  - `btn-dl-win`
  - `btn-dl-linux`

Landing-site verification:
- Browser checks passed with no console errors.
- Browser checks passed with no external requests.
- Browser checks passed with no horizontal overflow.
- Static checks found no Mission Canvas or Still I Rise residue in the site
  code.
- Final screenshots:
  - `/tmp/linguaviva-desktop-final.png`
  - `/tmp/linguaviva-mobile-final.png`
  - `/tmp/linguaviva-narrow-final.png`

## Download-Button Phase 0

Read and verified:
- `CLAUDE.md`
- `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`
- `dev/EXECUTION_PROMPT_DOWNLOAD_BUTTONS_2026-07-20.md`
- `install.sh`
- `install.ps1`
- `.github/workflows/release.yml`
- `.github/workflows/install-test.yml`
- `desktop/package.json`
- `desktop/electron/main.ts`
- `desktop/electron/bootstrap.ts`

Confirmed starting state:
- Live `v1.0.0` release only had old `sir-*` assets.
- `install.sh` expected `lv-*`, so binary download could miss the release
  assets.
- `install.ps1` was still branded as Still I Rise, installed `sir`, used
  `~/.still-i-rise`, served on port `7896`, and referenced `src/mc_cli.py`.
- `.github/workflows/release.yml` referenced missing `mc.spec`.
- `.github/workflows/install-test.yml` expected `~/.local/bin/sir`.
- The Electron desktop app existed locally, but no desktop release CI existed.
- The Electron app currently starts the backend through system `python3`;
  this remains a Phase 3 runtime-packaging decision.

Phase 0 baseline:
- `python3 -m pytest tests/ -q`: `442 passed`
- `python3 -m src.lingua_viva.cli preflight`: `5/5 PASS`
- `python3 -m src.lingua_viva.cli health --full --json`: pytest, gauntlet,
  golden eval, and server 5xx checks passed; Doctor was WARN.
- Doctor WARN was due to local worktree/private-source exclusions.

## Spec Baseline

Commit:
- `44bc0af` — `docs(engine): specify download button release contract`

Files:
- `dev/INDEX.md`
- `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`
- `dev/EXECUTION_PROMPT_DOWNLOAD_BUTTONS_2026-07-20.md`

## Phase 1 — Naming Split Fix

Commit:
- `60faae5` — `fix(engine): align release installer naming`

Files changed:
- `install.ps1`
- `.github/workflows/release.yml`
- `.github/workflows/install-test.yml`
- `tests/test_project_metadata.py`

Work completed:
- Rebranded Windows installer from Still I Rise to Lingua Viva.
- Changed Windows install dir to `~/.lingua-viva`.
- Changed Windows binary to `lv.exe`.
- Changed Windows release asset to `lv-windows-x86_64.exe`.
- Changed Windows web port from `7896` to `8787`.
- Changed Windows source fallback from `src/mc_cli.py` to `src/lv_cli.py`.
- Rejected 32-bit Windows explicitly because no 32-bit release asset is
  planned.
- Changed release workflow from `mc.spec` to `lv.spec`.
- Changed release asset names from `sir-*` to `lv-*`.
- Changed release workflow smoke env from `STILL_I_RISE_HOME` to
  `LV_CONFIG_HOME`.
- Changed install-test assertions from `sir` to `lv`.
- Added regression coverage for the release/install naming contract.

Phase 1 verification:
- Targeted metadata test: `3 passed`
- Full test suite: `443 passed`
- Preflight: `5/5 PASS`
- Full health: pytest, gauntlet, golden eval, and server 5xx checks passed;
  Doctor remained WARN for expected local context.
- Stale-name scan on Phase 1 target files: clean.

## Phase 2 — CLI Release Re-Cut

The intended patch release started at `v1.0.1`, but CI exposed additional
release-pipeline bugs. Failed tags were left as historical evidence; no
successful release was created for them.

Failed attempt:
- Tag: `v1.0.1`
- Commit: `4dbb52d` — `fix(engine): bump CLI release version`
- Failure: workflows still smoke-tested `lv status`, but the current CLI has
  no `status` command.

Failed attempt:
- Tag: `v1.0.2`
- Commit: `797a52c` — `fix(engine): repair CLI release smoke checks`
- Fixes included source fallback shell shim repair and changing workflow smoke
  command from `status` to `preflight`.
- Failure: `preflight` is a source-tree check and does not work correctly from
  the frozen PyInstaller binary.

Successful attempt:
- Tag: `v1.0.3`
- Commit: `c86fb76` — `fix(engine): use health for CLI release smoke`
- Changed release smoke to `lv health --json`.
- Changed install-test to verify `lv health --json` and normal `lv health`.
- Bumped `pyproject.toml` and `MANIFEST.yaml` to `1.0.3`.

Live release:
- URL: `https://github.com/lingua-viva/learning-architecture/releases/tag/v1.0.3`
- Published: `2026-07-20T17:44:51Z`
- Assets:
  - `lv-darwin-arm64`
  - `lv-linux-x86_64`
  - `lv-windows-x86_64.exe`

CI evidence:
- Release Binary: `29764711261` passed.
- Install Test Linux on tag: `29764711037` passed.
- Install Test Linux on main: `29764709197` passed.

Asset URL verification:
- `latest/download/lv-darwin-arm64`: `200`
- `latest/download/lv-linux-x86_64`: `200`
- `latest/download/lv-windows-x86_64.exe`: `200`

## Spec Status Update

Commit:
- `b0c530a` — `docs(engine): record partial download release ship`

Files changed:
- `dev/INDEX.md`
- `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`

Status:
- `SPEC_DOWNLOAD_BUTTONS_2026-07-20` is now `SHIPPED (partial)`.

Reason:
- Phases 1-2 shipped.
- Phases 3-4 remain pending.

## Current State

`/home/mical/learning-architecture`:
- Clean.
- Synced with `origin/main`.
- Latest commit: `b0c530a`.
- Successful live tag: `v1.0.3`.

`/home/mical/linguaviva.art`:
- Clean.
- Landing page built and hardened.
- Download buttons still pending by design.

`/home/mical/missioncanvas.ai`:
- Clean.
- Not touched.

## Remaining Work

Phase 3:
- Decide whether landing-page buttons should ship CLI only, desktop app only,
  or both.
- Recommendation remains both: CLI for developer/README install, desktop
  installers for teacher-facing landing-page buttons.
- Add desktop installer CI for `.dmg`, `.exe`, and `.AppImage`.
- Resolve Electron runtime packaging: it currently depends on system `python3`.

Phase 4:
- Wire `linguaviva.art` buttons once the chosen assets exist.
- If wiring CLI first, the CLI asset links now exist.
- If wiring desktop app, wait for desktop CI and exact installer filenames.
- Update button labels, remove disabled state, remove `data-downloads-pending`,
  and update the hero/download copy.

Important caveat:
- Mac and Windows CLI binaries were built and smoke-tested in CI.
- Linux installer was verified end-to-end in CI.
- Mac `install.sh` and Windows `install.ps1` installer flows remain manually
  unverified.
