# SPEC_DOWNLOAD_BUTTONS_2026-07-20

Status: DRAFT (unbuilt — this is the plan, not the ship)

## 0. Why this spec exists

`linguaviva.art/index.html` already has the download section built and
waiting:

```html
<div class="download-buttons" data-downloads-pending="true">
  <a id="btn-dl-mac" data-platform="mac" data-status="pending" data-release-slot="mac">Mac button pending</a>
  <a id="btn-dl-win" data-platform="windows" data-status="pending" data-release-slot="windows">Windows button pending</a>
  <a id="btn-dl-linux" data-platform="linux" data-status="pending" data-release-slot="linux">Linux button pending</a>
</div>
```

The copy on the page says it plainly: *"the links will stay inactive until
the release artifact contract is defined and tested."* This spec is that
contract — and the investigation behind it found the release artifact
pipeline is currently **broken and inconsistent with itself**, not just
"not wired to the site yet." Three different files disagree about the
product's name, install paths, and port. Fixing that is most of the work.

## 1. Current state of the world (verified, not assumed)

### 1.1 The one and only GitHub Release

`gh api repos/lingua-viva/learning-architecture/releases` → one release,
`v1.0.0`, published 2026-07-15, three assets:

| Asset | Size | Downloads |
|---|---|---|
| `sir-darwin-arm64` | 30.97 MB | 1 |
| `sir-linux-x86_64` | 32.51 MB | 8 |
| `sir-windows-x86_64.exe` | 32.81 MB | 1 |

These are **CLI binaries** (the `mc_cli.py`/`lv_cli.py`-style status/health
tool), not desktop app installers. There is no `.dmg`, no `.AppImage`, no
`.exe` installer anywhere in Releases. Notice the asset prefix is `sir-`,
not `lv-` — that matters in §1.2.

### 1.2 The three-way naming split (the actual bug)

The repo was rebranded from "Still I Rise" to "Lingua Viva" on 2026-07-18
(per `learning-architecture/CLAUDE.md` and the HANDOFF doc). The rebrand
touched `install.sh` and `lv.spec` but **not** `install.ps1` or either
`.github/workflows/*.yml` file. Result — three artifacts that all disagree:

| File | Product name | Binary name | Install dir | Port | Asset names it expects/produces |
|---|---|---|---|---|---|
| `install.sh` (current) | Lingua Viva | `lv` | `~/.lingua-viva` | 8787 | downloads `lv-darwin-arm64` / `lv-linux-x86_64` |
| `install.ps1` (stale) | **Still I Rise** | `sir` | `~/.still-i-rise` | **7896** | downloads `sir-windows-x86_64.exe` |
| `.github/workflows/release.yml` (stale) | Still I Rise | `sir` | — | — | builds `sir-darwin-arm64` / `sir-linux-x86_64` / `sir-windows-x86_64.exe` from **`mc.spec`** (a file that does not exist in this repo — only `lv.spec` exists) |
| `.github/workflows/install-test.yml` (stale) | Still I Rise | `sir` | — | — | asserts `~/.local/bin/sir` exists after running the *current* `install.sh` |

Concretely, right now:

- `curl -fsSL https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh | sh` tries to download `lv-darwin-arm64` or `lv-linux-x86_64`. **Neither asset exists** (Release only has `sir-*`). The download 404s, and `install.sh` silently falls through to the source-install path (git clone + pip install) — a materially worse first-run experience for zero good reason, and it never tells the user the binary path was even attempted-and-failed vs. "there was no binary release."
- `install.ps1` **would** successfully download `sir-windows-x86_64.exe` (names match `release.yml`'s old output) — but then installs it as "Still I Rise" into `~/.still-i-rise`, serving on port **7896**, not 8787. A Windows user who ran this today would get a working but wrongly-branded, wrong-port install that diverges from the Mac/Linux experience.
- `release.yml` would fail outright on a fresh run today: it runs `pyinstaller mc.spec`, and `mc.spec` doesn't exist in this repo (`ls` confirms only `lv.spec` is present at repo root). The v1.0.0 assets currently in Releases were built by an older version of this workflow, before the rebrand, and nothing has re-run successfully since.
- `install-test.yml` asserts the binary lands at `~/.local/bin/sir` after running `install.sh` — but `install.sh` installs it as `lv`. This CI check would fail today for reasons unrelated to whether the install actually works.

**None of this is hypothetical** — it's read directly from the files as
they exist right now, cross-checked against the live Releases API.

### 1.3 The desktop Electron app is real but never shipped anywhere

`desktop/` is a genuine Electron shell (`package.json` name
`lingua-viva-desktop`, version `0.2.0`, `appId org.linguaviva.teacher`,
`productName "Lingua Viva"`) that bundles the Python backend as
`extraResources` and targets `dmg` (mac), `nsis` (windows), `AppImage`
(linux) via `electron-builder`. A local build already exists at
`desktop/release/Lingua Viva-0.2.0.AppImage` — built by hand at some
point, never uploaded to GitHub Releases, and **no CI workflow builds or
publishes it at all**. `release.yml` only builds the PyInstaller CLI
binary, never touches `desktop/`.

So there are two independent "download" surfaces in this repo that have
never been reconciled:
1. **CLI binary** (`lv`/`sir`, PyInstaller, `lv.spec`) — serves the web UI
   on localhost, no native window chrome. This is what `install.sh` /
   `install.ps1` install.
2. **Desktop app** (Electron, `desktop/`) — a native window wrapping the
   same backend. This is what a "Download for Mac/Windows/Linux" button
   on a landing page conventionally implies, and what `productName
   "Lingua Viva"` + `appId org.linguaviva.teacher` were clearly built for.

The site's placeholder buttons (`data-platform="mac"` etc., one button per
OS, no "CLI vs desktop" distinction) read as promising the desktop
experience. Decide which one the buttons actually deliver — see §2.

### 1.4 Version drift

`MANIFEST.yaml` (repo root): `version: 1.0.0`.
`desktop/package.json`: `"version": "0.2.0"`.
Release tag: `v1.0.0`. These aren't necessarily wrong (CLI and desktop
shell can version independently) but nothing today documents which
version number the download buttons should display or link to.

## 2. Decision the operator needs to make before any code changes

**Which artifact do the three landing-page buttons deliver?**

- **Option A — CLI binary** (fast to fix: rename `sir-*` → `lv-*`, land
  Windows support in `install.sh` or point the Windows button at
  `install.ps1`, fix `release.yml`'s `mc.spec` → `lv.spec` typo). Result:
  clicking "Download for Mac" gets a terminal tool that opens a browser
  tab, not an app icon in Applications/dock. Cheapest path, but weaker
  "download the app" UX for a non-technical teacher audience — Claudia's
  actual users.
- **Option B — Desktop Electron app** (more work: wire `desktop/` into
  `release.yml` as a second build matrix, or a separate
  `desktop-release.yml`, using `electron-builder`'s existing `dist:mac` /
  `dist:win` / `dist:linux` scripts already in `package.json`; upload
  `.dmg`/`.exe`/`.AppImage` as release assets). Result: matches what the
  landing page visually promises (a downloadable app), matches
  `productName`/`appId` already set up for it, but is unbuilt CI and
  untested on Windows/Mac runners.
- **Option C — Both**, CLI for power users (`lv` binary via `install.sh`
  one-liner, likely linked from the GitHub README) and Electron `.dmg`/
  `.exe`/`.AppImage` for the three landing-page buttons specifically.

This spec is written to support Option C (it is a superset of A and B),
but the buttons themselves should point at whichever artifact the
operator picks. **Recommendation**: Option C. Claudia's landing page
targets non-technical teachers — a native app download is the
expectation a "Download for Mac" button sets. The CLI binary is the
right thing for `install.sh`'s existing curl-pipe audience (developers,
the GitHub README), a different funnel than the marketing site.

## 3. Build plan (Option C, in dependency order)

### Phase 1 — Fix the naming split (blocks everything else)

1. `install.ps1`: rebrand to Lingua Viva. Binary `sir` → `lv`, install
   dir `~/.still-i-rise` → `~/.lingua-viva`, port `7896` → `8787`, all
   "Still I Rise" strings → "Lingua Viva", asset name
   `sir-windows-x86_64.exe` → `lv-windows-x86_64.exe`, source-fallback
   entry point `src/mc_cli.py` → `src/lv_cli.py` (currently references
   the wrong CLI module entirely — this alone would break the Windows
   source-install fallback).
2. `.github/workflows/release.yml`: `pyinstaller mc.spec` → `pyinstaller
   lv.spec`; matrix asset names `sir-darwin-arm64` / `sir-linux-x86_64` /
   `sir-windows-x86_64.exe` → `lv-darwin-arm64` / `lv-linux-x86_64` /
   `lv-windows-x86_64.exe`; smoke-test env var `STILL_I_RISE_HOME` →
   `LINGUA_VIVA_HOME` (check `src/lv_cli.py` / `src/lingua_viva/config`
   for the actual env var name it reads — don't invent one, use whatever
   the app already honors); `cp dist/sir` / `dist/sir.exe` → `cp dist/lv`
   / `dist/lv.exe`.
3. `.github/workflows/install-test.yml`: assertion `~/.local/bin/sir` →
   `~/.local/bin/lv`; any other `sir` references → `lv`.
4. Verify `src/lv_cli.py` responds correctly to `status`/`health` under
   the new binary name before merging — this is exactly the kind of
   silent-fallback bug `install-test.yml` exists to catch, so trust it
   once the naming is fixed rather than hand-verifying every path.

### Phase 2 — Re-cut the release with correct naming

5. Tag a new release (e.g. `v1.0.1` or `v1.1.0` — operator's call) so
   `release.yml` runs with the Phase 1 fixes and produces
   `lv-darwin-arm64`, `lv-linux-x86_64`, `lv-windows-x86_64.exe` as
   *actual* release assets matching what `install.sh`/`install.ps1` now
   request.
6. Confirm `install.sh` and `install.ps1` succeed end-to-end against the
   new release (this is exactly what `install-test.yml` automates for
   Linux — trust its result rather than re-deriving it by hand; Windows/
   Mac have no equivalent CI today, see §4 Gap G-5).

### Phase 3 — Desktop app build + publish (new work, no existing CI)

7. Add a `desktop-release.yml` workflow (or extend `release.yml` with a
   second matrix) triggered on the same `v*` tag push:
   - `os: macos-latest` → `cd desktop && npm ci && npm run dist:mac`
   - `os: windows-latest` → `cd desktop && npm ci && npm run dist:win`
   - `os: ubuntu-latest` → `cd desktop && npm ci && npm run dist:linux`
   - These scripts already exist verbatim in `desktop/package.json` —
     this is CI wiring, not new build logic.
8. electron-builder output goes to `desktop/release/` per the existing
   `directories.output` config. Upload the actual installer files (the
   `.dmg`, the NSIS `.exe`, the `.AppImage` — not the `linux-unpacked/`
   directory contents) as release assets, same job pattern as
   `release.yml`'s existing `upload-artifact` → `softprops/action-gh-release`
   two-step.
9. Verify `extraResources` in `package.json` — it copies `src/**`,
   `static/**`, `doctor/**`, `curriculum/**`, `governance/**`,
   `artifacts/**`, `claims/**`, `knowledge/**`, `ontology/education/**`,
   `requirements*.txt` into the bundle, explicitly excluding the 326KB
   `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` source document
   and `archive/**`. Confirm this list is still accurate (nothing new
   under `src/` or `static/` that the desktop app needs was added since
   this was last touched) — the local `Lingua Viva-0.2.0.AppImage`
   already in `desktop/release/` is a spot-check candidate: unpack it
   and diff its `resources/app` contents against the current source tree
   to catch drift before trusting the config blind.
10. Decide the desktop app's Python runtime story: does `extraResources`
    assume a system Python3 is present at runtime, or does it need the
    PyInstaller-frozen `lv` binary bundled instead? (`main.ts` — read it,
    not yet reviewed as of this spec — should show which.) If it shells
    out to system `python3`, that's an undisclosed dependency the
    landing page's "Download for Mac" promise doesn't currently
    account for; if a teacher's Mac has no Python 3.11+, the app breaks
    silently post-install. This needs a concrete answer, not an
    assumption, before Phase 3 ships.

### Phase 4 — Wire the landing page

11. Replace the `data-downloads-pending="true"` state in
    `linguaviva.art/index.html` once Phase 2 (CLI) and/or Phase 3
    (desktop) artifacts exist at stable, predictable URLs. GitHub
    Releases' `latest/download/<asset-name>` pattern (already used by
    `install.sh`) means the three buttons can be static links that never
    need updating on future releases, e.g.:
    ```
    https://github.com/lingua-viva/learning-architecture/releases/latest/download/Lingua-Viva-<version>.dmg
    https://github.com/lingua-viva/learning-architecture/releases/latest/download/Lingua-Viva-Setup-<version>.exe
    https://github.com/lingua-viva/learning-architecture/releases/latest/download/Lingua-Viva-<version>.AppImage
    ```
    Exact filenames depend on `electron-builder`'s actual output naming
    (verify against a real Phase-3 build — electron-builder's defaults
    interpolate `${productName}-${version}.${ext}`, but don't assume;
    read the actual filenames electron-builder produces in
    `desktop/release/` before hardcoding).
12. Per button (`#btn-dl-mac`, `#btn-dl-win`, `#btn-dl-linux`):
    - Remove `btn-disabled`, `aria-disabled="true"`, `tabindex="-1"`.
    - Set `href` to the release asset URL from step 11.
    - Update `data-status="pending"` → `data-status="active"` (or drop
      the attribute if `app.js` doesn't key off it — confirmed by
      reading `app.js` in full: nothing in it currently reads
      `data-status`, `data-platform`, or `data-release-slot` at all; the
      only JS behavior tied to these buttons today is the
      `.btn-disabled` click/keydown suppression at the bottom of the
      file, which becomes dead code for these three elements once
      `btn-disabled` is removed from them).
    - Remove `data-downloads-pending="true"` from the parent
      `.download-buttons` div once all three are live (useful as a
      single grep-able flag for "are downloads live yet" until then).
    - Update the button label from placeholder text ("Mac button
      pending") to something real ("Download for Mac (Apple Silicon)" —
      confirm arch: `install.sh` hardcodes `ARCH="arm64"` for darwin,
      i.e. Intel Macs are NOT currently supported by the CLI path either;
      decide whether Phase 3's `dist:mac` needs a `--x64` build too or
      whether Apple Silicon-only is the accepted scope for v1).
    - Also update the `<a href="#download">` nav-anchor button near the
      top of the page ("Download buttons coming next") and the
      `<span class="mobile-download-note">` copy once real links exist.

### Phase 5 — Platform detection (optional, nice-to-have)

13. `app.js` currently has zero platform-detection logic — all three
    buttons render identically regardless of visiting OS. Consider
    detecting `navigator.userAgent`/`navigator.platform` to highlight or
    pre-select the visitor's likely platform (mirrors common patterns on
    Obsidian/Notion/Discord download pages), but this is cosmetic, not
    load-bearing — ship Phase 4 without it first.

## 4. Gaps and open questions found during this review

- **G-1 (blocking)**: `release.yml` references `mc.spec`, which doesn't
  exist. Any tag push today produces a failed CI run, not new binaries.
  Must fix before re-cutting any release (§3 Phase 1, step 2).
- **G-2 (blocking)**: Live release assets are `sir-*`, install scripts
  request `lv-*`/mismatched names. `install.sh`'s binary path 404s
  silently today. Must fix before "download buttons" can point at real,
  working artifacts (§3 Phase 1-2).
- **G-3**: No CI builds or publishes the desktop Electron app at all.
  `desktop/release/Lingua Viva-0.2.0.AppImage` is a manual, one-off,
  unreleased build. If the landing page buttons are meant to deliver the
  desktop app (§2 recommendation), this is entirely new CI work, not a
  fix (§3 Phase 3).
- **G-4**: `main.ts`'s Python runtime strategy for the packaged desktop
  app has not been read/verified as part of this spec — needed before
  Phase 3 ships (§3 step 10).
- **G-5**: `install-test.yml` only covers Linux end-to-end (`curl | sh`
  on `ubuntu-latest`). No equivalent CI exists for `install.ps1` on
  Windows or `install.sh` on macOS — both are exactly the paths this
  spec's download buttons depend on. Worth a follow-up spec, out of
  scope here.
- **G-6**: Only `arm64` macOS binaries are built/supported anywhere in
  this repo (CLI: hardcoded in `install.sh`; desktop: unconfirmed, see
  G-4). No Intel Mac path exists. Decide if that's acceptable for v1 or
  needs a `dist:mac --x64` addition to Phase 3.
- **G-7**: No version-number contract between `MANIFEST.yaml` (1.0.0),
  `desktop/package.json` (0.2.0), and the git tag (`v1.0.0`). Not
  blocking for this spec, but the landing page will eventually want to
  display a "current version" string somewhere near the buttons — decide
  which source of truth that reads from.

## 5. Definition of done

- [ ] Phase 1 landed: `install.sh`, `install.ps1`, both workflow files
      agree on product name, binary name, install dir, port, and asset
      names.
- [ ] Phase 2 landed: a real tagged release exists whose assets exactly
      match what `install.sh`/`install.ps1` request; both scripts
      verified end-to-end (Linux via `install-test.yml`, Mac/Windows via
      manual verification per G-5).
- [ ] Decision made and recorded (§2) on CLI vs. desktop vs. both for the
      three landing-page buttons.
- [ ] If desktop chosen/included: Phase 3 CI exists, produces real
      `.dmg`/`.exe`/`.AppImage` assets attached to the release, G-4
      answered and documented.
- [ ] Phase 4 landed: all three buttons on `linguaviva.art` are live —
      correct `href`, no `btn-disabled`/`aria-disabled`/`tabindex="-1"`,
      accurate label copy, `data-downloads-pending` removed from the
      parent div, nav-anchor and mobile-note copy updated.
- [ ] This spec's status line updated in `dev/INDEX.md` on ship, evidence
      column pointing at the shipped commit(s) and the live release tag.
