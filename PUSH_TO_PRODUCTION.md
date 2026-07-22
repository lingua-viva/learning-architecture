# Push to Production — Lingua Viva / Learning Architecture

> **Read this before pushing anything user-facing.** Written 2026-07-22 after losing 4 hours of
> demo-prep time to a stalled build, then discovering the live desktop download had never been
> signed — Gatekeeper would have blocked it live in front of the demo audience. Both problems
> were invisible from `git push` succeeding and the download URL returning a valid HTTP status.
> Every rule below closes one specific way this repo's release path has silently lied.

---

## Architecture: What Serves What

This is a **single standalone repo** — no monorepo, no subtrees, no separate site repo.

```
git@lingua-viva:lingua-viva/learning-architecture.git
(SSH key: ~/.ssh/lingua-viva, Host alias "lingua-viva" in ~/.ssh/config)
                        │
                        │ git push origin main
                        ▼
        ┌───────────────────────────────────┐
        │  learning-architecture (GitHub)    │
        │  branch: main                      │
        └───────────────┬─────────┬──────────┘
                         │         │
        docs/ folder ────┘         └──── tags fire CI
        served via                        │
        GitHub Pages              ┌────────┴────────┐
        (legacy build,            │                 │
        source = main:/docs)      ▼                 ▼
                         release.yml         desktop-release.yml
                         (tags: v*)          (tags: desktop-v*)
                         CLI binaries        Desktop .dmg/.exe/.AppImage
                              │                       │
                    releases/latest/download   pinned tag in docs/index.html
                    (install.sh, install.ps1)  (btn-dl-mac, btn-dl-win)
                         │
                         ▼
                  https://linguaviva.art  (CNAME, custom domain, HTTPS approved)
```

**There is no separate `linguaviva.art` site repo in production.** A standalone draft exists
locally at `/home/mical/linguaviva.art` (2 commits, `1b6a248`/`7c3a2b8`, no git remote configured)
— it was an early landing-page prototype, reused Mission Canvas's layout as reference only, and
was **never wired to GitHub Pages**. The actual live site is `docs/index.html` inside this repo,
confirmed via `gh api repos/lingua-viva/learning-architecture/pages` (`source.branch: main`,
`source.path: /docs`, `cname: linguaviva.art`). **Do not edit `/home/mical/linguaviva.art` and
expect it to reach production — it's orphaned.** If a future session wants to formally retire it,
say so explicitly; until then, treat it as dead weight, not a deploy target.

---

## The Two Release Tracks (do not confuse them)

| | CLI release | Desktop release |
|---|---|---|
| Tag pattern | `v{MAJOR}.{MINOR}.{PATCH}` | `desktop-v{MAJOR}.{MINOR}.{PATCH}` |
| Workflow | `.github/workflows/release.yml` | `.github/workflows/desktop-release.yml` |
| Assets | `lv-darwin-arm64`, `lv-linux-x86_64`, `lv-windows-x86_64.exe` | `LinguaViva.dmg`, `LinguaViva-Setup.exe`, `LinguaViva.AppImage` |
| `prerelease` flag | **must be `false`** (this is what `install.sh`/`install.ps1` fetch via `releases/latest/download/`) | **must stay `true`** — otherwise it steals the `latest` slot and breaks `curl \| sh` installs for the CLI |
| How the site finds it | `releases/latest/download/<binary>` — always current, no manual URL update needed | **pinned literal tag** in `docs/index.html` (`btn-dl-mac`, `btn-dl-win`) — a new desktop release does **nothing** for users until someone edits the HTML |

Because the desktop download URL is pinned, cutting a new `desktop-v*` release and stopping there
is a no-op for anyone hitting the site. You must also update `docs/index.html` and push `main`
again.

---

## Rule 1: A commit on `main` is not a release

Pushing to `main` updates the repo. It does **not** rebuild CLI or desktop binaries, and it does
**not** update anything a user downloads. Both release workflows trigger only on a **tag push**:

```bash
git push origin main               # code is now on GitHub — nobody downloads anything new yet
git tag v1.0.4                     # CLI release
git push origin v1.0.4              # NOW release.yml fires

git tag desktop-v0.2.2             # desktop release
git push origin desktop-v0.2.2      # NOW desktop-release.yml fires
```

This exact confusion is what cost 4 hours on 2026-07-22: a Kiro session pushed fixes to `main`,
then repeatedly re-checked a build log from a stale run, waiting for a rebuild that no tag had
ever requested.

---

## Rule 2: HTTP 200/302 is not proof the app works

`curl -sI <download-url>` confirms GitHub is serving *a* file. It says nothing about whether that
file is signed, notarized, or will actually open on a user's machine. On 2026-07-22, every HTTP
check on `desktop-v0.2.1` returned a clean 302 while the `.dmg` inside was ad-hoc signed
(`codesign -dv` showed `TeamIdentifier=not set`) — meaning Gatekeeper hard-blocks it on any
current macOS install. It would have failed live in the demo.

**The only real verification is reading the CI log itself**, not the HTTP status:

```bash
gh run list --workflow=desktop-release.yml --limit 1
gh run view <run-id> --log | grep -A5 "Verify macOS signature"
# Look for: "✓ Signed by team: XWT7RB624U" — not "TeamIdentifier=not set"
```

As of 2026-07-22 (commit `de828b4`), `desktop-release.yml` has a **hard CI gate**: the macOS build
step reads `codesign -dv` on the built `.app` and fails the job outright if `TeamIdentifier` isn't
set. A green desktop-release run now *does* mean it's signed — but only for runs after that
commit. **`desktop-v0.2.1` (published 20:22 UTC) predates the fix (pushed 20:45 UTC) and is
confirmed unsigned. Do not point the demo at it.**

---

## Rule 3: Check secrets before you trust a signing-dependent workflow

Both signing paths (macOS notarization, Windows Azure Trusted Signing) depend on GitHub repo
secrets that cannot be read back once set — you can only confirm presence, never value. Use the
diagnostic workflow instead of guessing:

```bash
gh workflow run check-signing-secrets.yml
gh run list --workflow=check-signing-secrets.yml --limit 1
gh run view <run-id> --log | grep -E "SET|MISSING"
```

As of 2026-07-22, all 8 secrets are `MISSING` on this repo:
`CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_API_KEY_BASE64`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`
(macOS), `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (Windows). The workflow code
that consumes them is correct and ported from Mission Canvas's proven config — the repo secrets
themselves are the missing piece, and only a repo admin with GitHub UI access can add them
(Settings → Secrets and variables → Actions). An agent cannot do this step.

Until they're set, any macOS desktop build will fail loudly at the "Verify macOS signature" step
(by design — see Rule 2) rather than silently shipping unsigned. Windows builds currently have no
equivalent hard gate; treat any Windows `.exe` as unverified until Azure secrets are confirmed
`SET` and a signed build has been checked the same way as Rule 2.

---

## Cutting a Desktop Release (full sequence)

1. Confirm signing secrets are `SET` (Rule 3). If any are `MISSING`, stop — the build will fail.
2. Bump `"version"` in `desktop/package.json` and commit it to `main` through the normal push
   (so the tag target actually contains the bump).
3. Tag and push:
   ```bash
   git tag desktop-v0.2.2
   git push origin desktop-v0.2.2
   ```
4. Watch the run, don't just wait for green:
   ```bash
   gh run list --workflow=desktop-release.yml --limit 1
   gh run view <run-id> --log | grep -A5 "Verify macOS signature"
   ```
5. Confirm the release and its `prerelease: true` flag:
   ```bash
   gh release view desktop-v0.2.2
   ```
6. Update the pinned URLs in `docs/index.html` (`btn-dl-mac`, `btn-dl-win` — both `href`
   attributes) to the new tag, commit, push `main`.
7. Verify live (Pages redeploy takes ~30-60s):
   ```bash
   grep -o 'desktop-v[0-9.]*' docs/index.html | sort -u   # must show exactly ONE tag
   curl -sI "https://linguaviva.art/" | head -1
   curl -sI "https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.2/LinguaViva.dmg" | head -1
   # Must be 302 — but this only proves the file exists, not that it's signed (Rule 2)
   ```
8. Retire the old release/tag so exactly one version is ever live:
   ```bash
   gh release delete desktop-v0.2.1 --yes
   git push origin --delete desktop-v0.2.1
   ```

## Cutting a CLI Release

```bash
git tag v1.0.4
git push origin v1.0.4
gh run list --workflow=release.yml --limit 1
gh release view v1.0.4   # confirm prerelease: false, all 3 binaries attached
curl -sI "https://github.com/lingua-viva/learning-architecture/releases/latest/download/lv-darwin-arm64" | head -1
```
No HTML update needed — `install.sh`/`install.ps1` always resolve `releases/latest`.

---

## Things That Will Break If You Forget

| Forgotten step | What breaks | How long until noticed |
|---|---|---|
| Push a tag, not just a commit | No new release exists at all — CI never runs | Immediately, if you check; otherwise indefinitely |
| Update `docs/index.html` after a desktop release | Site keeps serving the old pinned tag forever | Only when someone diffs the HTML or a user reports a stale download |
| Keep desktop releases `prerelease: true` | Desktop release steals `latest` from CLI; `curl \| sh` installs 404 | Immediately for any new CLI installer |
| Verify the CI log (not just HTTP status) after a signing-dependent build | An unsigned/broken `.dmg` ships and looks identical to a working one until a user opens it | Live, in front of whoever's demoing it |
| Delete the old release/tag when cutting a new one | Two versions coexist; `docs/index.html` and reality can point at different builds, or an old broken one lingers as a trap for the next session | Next confused debugging session |

---

## Quick Reference

```bash
# Verify signing secrets before any macOS-dependent build
gh workflow run check-signing-secrets.yml
gh run list --workflow=check-signing-secrets.yml --limit 1
gh run view <run-id> --log | grep -E "SET|MISSING"

# Cut + verify a desktop release
git tag desktop-vX.Y.Z && git push origin desktop-vX.Y.Z
gh run view $(gh run list --workflow=desktop-release.yml --limit 1 --json databaseId -q '.[0].databaseId') --log | grep -A5 "Verify macOS signature"

# Cut a CLI release
git tag vX.Y.Z && git push origin vX.Y.Z

# Confirm exactly one desktop version is referenced live
grep -o 'desktop-v[0-9.]*' docs/index.html | sort -u

# Retire an old release
gh release delete desktop-vOLD --yes && git push origin --delete desktop-vOLD
```

---

*Written 2026-07-22 after a same-day incident: a stalled Kiro window cost 4 hours of demo-prep
time (Rule 1), followed by discovering the live desktop download (`desktop-v0.2.1`) was
ad-hoc-signed and would have failed Gatekeeper live in front of the demo audience (Rule 2). This
class of error — "looks green, actually broken" — had reportedly recurred 20-30 times before this
doc existed. If it recurs again, the gap is in this doc, not in memory; fix the doc.*
