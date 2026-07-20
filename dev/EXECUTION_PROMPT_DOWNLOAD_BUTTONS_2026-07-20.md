Copy-paste this into a fresh Claude Code session (or hand to a subagent) to execute
`dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`.

---

```markdown
You are working in two repos:
- `~/learning-architecture` — Lingua Viva app + landing-page source (this repo)
- `~/linguaviva.art` — the deployed GitHub Pages landing page (separate repo,
  origin `github.com/lingua-viva` — same org, different remote)

Read `~/learning-architecture/dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md` in
full before touching anything. It documents a verified, not hypothetical,
bug: the release pipeline is self-contradicting across three files (product
name, binary name, install dir, and port all disagree), and the live GitHub
Release's asset names don't match what `install.sh` downloads. Confirm this
is still true before you start — things may have moved since the spec was
written:

```bash
gh api repos/lingua-viva/learning-architecture/releases | jq '.[0].assets[].name'
cat ~/learning-architecture/install.sh | grep -A2 'BINARY='
cat ~/learning-architecture/install.ps1 | grep -A2 '\$binary ='
```

## Decision required before Phase 3

The spec (§2) lays out three options for what the landing page's three
download buttons actually deliver: the CLI binary (`lv`), the Electron
desktop app, or both. The spec recommends **both** — CLI via `install.sh`
for the GitHub README/developer audience, desktop `.dmg`/`.exe`/`.AppImage`
for the three landing-page buttons, since Claudia's teacher audience expects
an app icon, not a terminal tool. If the operator hasn't confirmed this
choice with you directly, stop and ask before starting Phase 3 — Phases 1-2
are unconditional fixes either way and safe to start immediately.

## Execution order (do not reorder — later phases depend on earlier ones)

**Phase 1 — Fix the naming split** (spec §3, blocks everything else)
1. Rebrand `install.ps1`: `sir` → `lv`, `~/.still-i-rise` → `~/.lingua-viva`,
   port `7896` → `8787`, all "Still I Rise" copy → "Lingua Viva", asset name
   `sir-windows-x86_64.exe` → `lv-windows-x86_64.exe`, and fix the
   source-fallback entry point `src/mc_cli.py` → `src/lv_cli.py` (currently
   points at the wrong CLI module — a second, separate bug).
2. Fix `.github/workflows/release.yml`: `mc.spec` → `lv.spec` (the current
   file doesn't exist — this is why the workflow would fail outright on any
   fresh tag push), asset names `sir-*` → `lv-*`, smoke-test env var
   `STILL_I_RISE_HOME` → whatever `src/lv_cli.py` / `src/lingua_viva/config`
   actually reads (check, don't guess).
3. Fix `.github/workflows/install-test.yml`: assertion path
   `~/.local/bin/sir` → `~/.local/bin/lv`.
4. Run the existing test suite (`python3 -m pytest tests/ -q`) — this phase
   shouldn't touch app code, so it should stay green throughout. If
   anything in `tests/` references `sir`/`mc_cli` naming in ways this phase
   didn't anticipate, that's new information — investigate before
   proceeding, don't paper over it.

**Phase 2 — Re-cut the release**
5. Tag a new release once Phase 1 is merged (ask the operator for the
   version number — don't invent one; `MANIFEST.yaml` says `1.0.0`,
   `desktop/package.json` says `0.2.0`, neither is obviously "next").
6. Confirm the new release's assets are named `lv-darwin-arm64`,
   `lv-linux-x86_64`, `lv-windows-x86_64.exe` and that `install.sh` /
   `install.ps1` successfully download and run them — Linux is covered by
   `install-test.yml`; Mac/Windows have no CI (spec's Gap G-5) so verify by
   hand or flag to the operator that this remains unverified.

**Phase 3 — Desktop app CI** (only if the operator confirmed desktop is in
scope per the decision above)
7. Add a `desktop-release.yml` workflow (or a second matrix in
   `release.yml`) that runs `desktop/package.json`'s existing
   `dist:mac` / `dist:win` / `dist:linux` scripts on the matching GH-hosted
   runner for each, on the same `v*` tag trigger.
8. Before trusting `desktop/package.json`'s `extraResources` file list,
   unpack the local `desktop/release/Lingua Viva-0.2.0.AppImage` (already
   built, never shipped) and diff its bundled `resources/app` contents
   against the current source tree — catch drift before it ships blind.
9. Answer spec Gap G-4: does the packaged desktop app assume a system
   Python 3.11+ at runtime, or does it need the frozen `lv` binary bundled
   instead? Read `desktop/electron/main.ts` — it hasn't been reviewed yet.
   If it shells out to system Python, decide whether that's an acceptable
   undisclosed dependency for a "Download for Mac" button or needs fixing
   first.
10. Upload the real installer files (`.dmg`, NSIS `.exe`, `.AppImage` — not
    the `linux-unpacked/` directory) as release assets on the same tag,
    same `upload-artifact` → `softprops/action-gh-release` pattern
    `release.yml` already uses.

**Phase 4 — Wire the landing page** (`~/linguaviva.art`, separate repo)
11. Confirm the exact asset filenames electron-builder actually produced in
    Phase 3 (don't assume the `${productName}-${version}.${ext}` default —
    read the real output) and the CLI filenames from Phase 2, then update
    the three buttons in `index.html`:
    - `#btn-dl-mac`, `#btn-dl-win`, `#btn-dl-linux`
    - remove `btn-disabled`, `aria-disabled="true"`, `tabindex="-1"`
    - set real `href` to
      `https://github.com/lingua-viva/learning-architecture/releases/latest/download/<asset>`
    - update label text from the placeholder ("Mac button pending" etc.) to
      real copy — note current CLI/desktop mac builds are Apple Silicon
      only (spec Gap G-6); say so if that's still true, don't imply Intel
      support that doesn't exist
    - remove `data-downloads-pending="true"` from the parent
      `.download-buttons` div once all three are live
    - update the `<a href="#download">` nav-anchor ("Download buttons
      coming next") and `<span class="mobile-download-note">` copy to match
12. Bump the cache-busting query param on changed assets (`?v=YYYYMMDD-NNN`
    pattern already used elsewhere in `index.html`).

**Phase 5 — optional, do not block on this**
13. Platform-detection JS in `app.js` to highlight the visitor's likely OS.
    Cosmetic only — ship Phase 4 without it if time-constrained.

## Discipline while executing

- This is `~/learning-architecture` — Palette-governed, two-layer repo.
  Read `CLAUDE.md` at repo root before your first commit. Commit convention:
  `<type>(<scope>): <description>` (types: feat/fix/docs/refactor; scopes:
  case-study/method/resume/engine/lens/skill/meta — use `engine` for this
  work).
- Never commit yourself unless explicitly told to in this session — leave
  changes staged/described and let the operator drive the commit, per this
  repo's existing convention (see `feedback_lv_commit_window.md` if you have
  memory access: operator has one dedicated commit window for this repo).
- `dev/` file discipline applies: spec status changes go in the same commit
  as the code that ships them. Update `dev/INDEX.md`'s row for
  `SPEC_DOWNLOAD_BUTTONS_2026-07-20.md` from DRAFT to SHIPPED (or
  SHIPPED (partial) if you stop after Phase 2) in the commit that finishes
  each phase, with real evidence (test run output, CI run URL, live release
  tag) — not a claim.
- Run `python3 -m pytest tests/ -q` before and after each phase. If the
  count or pass rate changes unexpectedly, stop and explain why before
  continuing — don't push through a red suite.
- Every check you perform against live systems (GitHub Releases API, CI run
  status, actual electron-builder output filenames) should be a real command
  you ran, not an assumption carried over from the spec — the spec was
  accurate as of 2026-07-20 but state may have moved.
- If you hit something the spec didn't anticipate (a fourth naming
  inconsistency, a CI permission issue, a missing secret for code signing),
  don't silently route around it — surface it plainly, the way the spec's
  own Gaps section (§4) does.

Start with Phase 1, step 1. Report back after each phase, not at the end —
this is exactly the kind of multi-phase work where a wrong turn in Phase 1
should be caught before it's baked into Phase 2's release tag.
```
