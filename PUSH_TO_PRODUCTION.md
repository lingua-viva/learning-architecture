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

## Rule 4: Three specific macOS signing failures, and their real fixes

Getting `CSC_LINK` set is not the end of it. On 2026-07-22, six consecutive `desktop-v0.2.2`
build attempts failed, each with a different error, each requiring the actual CI log to diagnose
(the "Package with electron-builder" step, not the "Verify macOS signature" gate — that gate
never even ran because packaging failed first every time). In order encountered:

**4a. `security: SecKeychainItemImport: Unable to decode the provided data.`**
OpenSSL 3.x's default `.p12` export (PBES2, PBKDF2, AES-256-CBC) is not readable by macOS's
legacy `SecKeychainItemImport` API, which `security import` uses. `openssl pkcs12 -export -legacy`
is **not** the fix either — it produces RC2-40-CBC, which current OpenSSL itself can't even read
back (`unsupported ... Algorithm (RC2-40-CBC : 0)`). The actual fix is to force the exact legacy
cipher suite explicitly:
```bash
openssl pkcs12 -export \
  -inkey developer_id.key -in developerID_application.pem -certfile DeveloperIDG2CA.pem \
  -out signing.p12 -passout pass:"$PASSWORD" \
  -certpbe pbeWithSHA1And3-KeyTripleDES-CBC \
  -keypbe pbeWithSHA1And3-KeyTripleDES-CBC \
  -macalg sha1
```
Verify locally before uploading: `openssl pkcs12 -info -in signing.p12 -passin pass:"$PASSWORD" -nokeys`
must show `pbeWithSHA1And3-KeyTripleDES-CBC`, not `PBES2`/`AES-256-CBC` and not `RC2`.

**4b. `entitlements.mac.plist: cannot read entitlement data`** (during electron-builder's deep-sign
pass over nested framework resources, e.g. `Electron Framework.framework/.../locale.pak` — the
top-level `.app` signs fine and logs a "signing" line, which is misleading; the failure is later,
in `readDirectoryAndSign`). Root cause: `mac.entitlements`/`entitlementsInherit` in
`desktop/package.json` must be a path that resolves correctly from wherever `codesign` actually
runs. A bare filename (`"entitlements.mac.plist"`) combined with a custom
`directories.buildResources` override does **not** work — electron-builder passes the raw config
string straight to `codesign --entitlements <value>` without resolving it against
`buildResourcesDir` first. Putting the physical file at the *default* `buildResources` location
(`desktop/build/`) is necessary but **not sufficient** by itself. The fix that actually works,
confirmed against Mission Canvas's proven-working config:
```json
"directories": { "output": "release" },
"mac": {
  "entitlements": "build/entitlements.mac.plist",
  "entitlementsInherit": "build/entitlements.mac.plist"
}
```
i.e. an explicit relative path from the project root (where `package.json` lives), no
`buildResources` override, file physically present at that exact path. Root has a `build/` entry
in `.gitignore` — you must `git add -f` the entitlements file or it silently won't be in the repo
checkout that CI builds from.

**4c. `Cannot use password credentials, API key credentials and keychain credentials at once`**
(from `@electron/notarize`, during the same deep-sign/notarize pass, once 4a and 4b are both
fixed). This looks like an environment leak (stray `APPLE_ID`/`APPLE_ID_PASSWORD`) but on
GitHub-hosted runners it isn't — those vars are never set, and explicitly setting them to `''` in
the workflow (a first attempt) changes nothing. The real cause is in `app-builder-lib`'s
`macPackager.js` (`generateNotarizeOptions`): when `mac.notarize` in `package.json` is an object
with a `teamId` field, that `teamId` gets merged into the *same* options object as the API-key
credentials (`appleApiKey`/`appleApiKeyId`/`appleApiIssuer`) before being handed to
`@electron/notarize`. `@electron/notarize`'s validator (`isNotaryToolPasswordCredentials`) treats
**`teamId` presence alone** — regardless of whether `appleId`/`appleIdPassword` are also set — as
a signal that password-based credentials are in play. With both apiKey and (spuriously) password
credentials detected, it throws. This is specific to `electron-builder ^24.13.3` /
`@electron/notarize 2.2.1`. Upgrading to `electron-builder ^25.1.8` (matching Mission Canvas's
pinned version) clears this specific error, but **was not sufficient on its own** — see 4d.
(`notarize: false` is **not** a fix — it ships a genuinely unnotarized `.dmg` that Gatekeeper will
block; this violates Rule 2 even if the build goes green.)

**4d. `Error: invalidPEMDocument`** (from `xcrun notarytool` via `@electron/notarize`, once 4a-4c
are all cleared — signing succeeds, notarization itself fails parsing the `.p8` API key). Root
cause was never conclusively identified — the local `.p8` file was verified byte-for-byte clean
(`openssl pkey -noout -text`, full hexdump: standard PKCS#8 PEM, no BOM, no CRLF), and switching
the workflow's base64 decode from `echo | base64 --decode` to `printf | base64 --decode` (theory:
trailing newline corruption) did **not** fix it — the identical error recurred on the very next
build. **The actual, proven fix (confirmed working, 2026-07-22): stop routing through
`@electron/notarize` entirely.** Split packaging and notarizing into two separate CI steps —
`electron-builder` signs only (`mac.notarize` omitted from `package.json` entirely, or explicitly
`false`, since notarization is no longer its job), then a dedicated step calls `xcrun notarytool
submit ... --wait` and `xcrun stapler staple` directly:
```yaml
- name: Package with electron-builder   # signs only, no notarize config
  run: ./node_modules/.bin/electron-builder --mac dmg
- name: Notarize macOS app
  env:
    APPLE_API_KEY_BASE64: ${{ secrets.APPLE_API_KEY_BASE64 }}
    APPLE_API_KEY_ID: ${{ secrets.APPLE_API_KEY_ID }}
    APPLE_API_ISSUER: ${{ secrets.APPLE_API_ISSUER }}
  run: |
    mkdir -p "$RUNNER_TEMP/api-key"
    echo "$APPLE_API_KEY_BASE64" | base64 --decode > "$RUNNER_TEMP/api-key/AuthKey.p8"
    APP=$(find desktop/release -name "*.app" -type d | head -1)
    ditto -c -k --keepParent "$APP" "$RUNNER_TEMP/app-to-notarize.zip"
    xcrun notarytool submit "$RUNNER_TEMP/app-to-notarize.zip" \
      --key "$RUNNER_TEMP/api-key/AuthKey.p8" --key-id "$APPLE_API_KEY_ID" \
      --issuer "$APPLE_API_ISSUER" --wait --timeout 10m
    xcrun stapler staple "$APP"
```
This is also what Apple's own docs recommend directly, and sidesteps whatever `@electron/notarize`
was doing wrong with the decoded key — never fully diagnosed, not worth chasing further now that
there's a working path. Confirmed end-to-end on `desktop-v0.2.2`: `status: Accepted` from Apple's
notary service, `The staple and validate action worked!`, `spctl`/`codesign --verify` both clean.

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


---

## The Onboarding Flow (what happens AFTER the download works)

The desktop app runs a setup wizard on first launch. This wizard has failed on every Mac tested
until v0.2.5. These are the requirements for the wizard to succeed — if any regress, the app
will show "Server did not start" even if the download/signing/notarization are perfect.

### The flow (in order)

```
1. Detect Python (checkPython)
2. If missing → download .pkg → open → poll until detected
3. Detect Ollama (checkOllama via HTTP localhost:11434)
4. If missing → download → install → poll (or skip)
5. Install pip dependencies (installPythonDeps — 4-strategy cascade)
6. Start server (startBackend — spawn web.py on port 8787)
7. Poll /api/health until 200
8. Load the app UI
```

### What breaks it (all proven on real machines, 2026-07-22)

| Failure | Root Cause | How We Fixed It |
|---|---|---|
| "Install Python" opens browser, user stuck | macOS handler just called `shell.openExternal` | Download .pkg directly + open + auto-poll |
| Asks to install Python when already installed | Electron PATH doesn't include `/usr/local/bin` | `detectPythonBroad()` checks 5 macOS paths |
| Ollama detected as missing when it's running | Checked CLI (`ollama --version`) not daemon | Check HTTP `localhost:11434/api/tags` first |
| pip install fails silently | macOS Python has no SSL certs + PEP 668 | 4-strategy cascade: `--break-system-packages` + `--trusted-host` |
| Server starts but health returns 500 | `run_doctor()` reads `README.md` which isn't in packaged app | try/except on health endpoint + skip check if file missing |
| Server hangs permanently after ~10 seconds | Electron doesn't read stdout/stderr, pipe buffer fills | `child.stdout.resume()` + `child.stderr.resume()` |
| Retry restarts entire wizard (re-asks Python/Ollama) | `runSetupFlow()` called from scratch on server exit | Only retry the server start, not the whole wizard |
| Port 8787 "already in use" on retry | Previous server process still dying | `lsof + kill -9` before each spawn |

### Rules for not breaking the onboarding

1. **`/api/health` must NEVER crash.** It's the readiness probe. Wrap it in try/except permanently.
   A health endpoint that raises = app that won't open.

2. **Any file read in `run_doctor()` or health checks must check `exists()` first.** The packaged
   app (`Contents/Resources/app/`) does NOT contain README.md, `.git/`, or other repo-only files.
   Every doctor check must degrade gracefully in packaged mode.

3. **pip install must handle the SSL-less Python.** `python.org` .pkg installs ship without root
   CA certs. The `--trusted-host` fallback is required. Do not remove it.

4. **Python detection must check macOS-specific paths**, not just PATH. The Electron process
   inherits a minimal PATH that often doesn't include `/usr/local/bin` or `/Library/Frameworks/`.

5. **Stdio pipes must always be drained.** If you spawn a child process with `stdio: "pipe"`,
   attach `.on("data")` handlers OR call `.resume()`. An undrained pipe deadlocks the child after
   64KB of output.

6. **Don't re-run the full setup wizard on server crash.** Only retry the server start. The user
   already answered the Python/Ollama questions — don't ask again.

### How to verify the onboarding after changes

```bash
# On a Mac with Python already installed:
# - Open the app → wizard should show Python ✓ immediately (no install prompt)
# - Ollama ✓ if running, or skip option if not
# - Server starts → app loads

# Backend health check (from Terminal while app is running):
curl -s http://127.0.0.1:8787/api/health | python3 -c "import sys,json; r=json.loads(sys.stdin.read()); print(r.get('status','healthy'))"
# Must return something (even "degraded") — never hang, never 500

# After quitting the app:
lsof -i :8787
# Must be empty — no orphaned Python processes
```

### Files that control the onboarding

| File | What it does |
|---|---|
| `desktop/electron/main.ts` | Setup flow, Python/Ollama detection, install handlers |
| `desktop/electron/bootstrap.ts` | `checkPython`, `checkOllama`, `installPythonDeps`, `startBackend` |
| `desktop/electron/setup-wizard.html` | Wizard UI states and button actions |
| `src/web.py` | The backend server (health endpoint at `/api/health`) |
| `doctor/support_loop/doctor.py` | Health checks (must never crash in packaged mode) |

---
