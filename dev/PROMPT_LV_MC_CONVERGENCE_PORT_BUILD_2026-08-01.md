# Build Prompt — Port MC's Release-Pipeline Fixes to Lingua Viva

You are implementing `dev/SPEC_LV_MC_CONVERGENCE_PORT_2026-08-01.md` end to end.

Read first:

```text
dev/SPEC_LV_MC_CONVERGENCE_PORT_2026-08-01.md
learning-architecture/.github/workflows/auto-release.yml   (current, buggy version — this repo)
learning-architecture/.github/workflows/desktop-release.yml
learning-architecture/AGENTS.md   ("THE Definition of 'Pushed'" section)
learning-architecture/PUSH_TO_PRODUCTION.md
```

Also read the reference implementation this spec ports from — a sibling repo on the same machine,
already proven working in production as of 2026-07-31:

```text
../mission-canvas/.github/workflows/auto-release.yml
```

That file is the ground truth for job structure, ordering, and the exact safety comments to carry
over (the `needs:`-transitive-outputs lesson, the empty-`NEW_TAG` guard, etc.). Copy its structure;
adapt paths/tools/secret names to LV.

## Objective

Rebuild `learning-architecture/.github/workflows/auto-release.yml` so that a push to `main` reliably
produces exactly one live, working, correctly-pinned `desktop-v*` release — with no step that can
silently no-op (the tag-push-doesn't-trigger-the-build problem), no step that can leave the site
pointed at a dead link (the pin-before-verify ordering problem), and no accumulation of stale
releases. Add a minimal live-verify eval instrument to make the pipeline self-checking, and a
cleanup job to enforce "exactly one version live."

## Hard Rules

1. **Do not push to `main`, push tags, create GitHub releases, or delete any existing release/tag
   without explicit operator confirmation first.** This spec touches a live, currently-serving
   production release pipeline (`linguaviva.art`) — the safe sequence is: build and test the
   workflow file and the new eval instrument locally/in a branch, then stop and hand back to the
   operator before anything actually runs against the real repo's Actions or Releases.
2. **You cannot create the deploy-key secret yourself.** `LV_TAG_PUSH_DEPLOY_KEY` requires generating
   an SSH keypair, adding the public half as a repo deploy key (write access) on
   `lingua-viva/learning-architecture`, and adding the private half as a repo Actions secret — all
   three of those are GitHub-side actions requiring the operator's credentials/2FA. Generate the
   keypair, write the exact `gh` / GitHub UI steps needed, and stop there — do not attempt to use
   `gh secret set` or `gh api` against real credentials you don't have.
3. **Do not touch the 13 currently-live stale `desktop-v*` releases** until the new
   `cleanup-stale-releases` job is built, tested, and the operator has approved a first real run of
   the full rebuilt pipeline. Cleaning them up by hand first would remove the exact evidence this
   spec cites.
4. **Do not modify LV's tag-derivation logic** (`git tag -l 'desktop-v*' --sort=-v:refname`). Spec
   §2.5 is explicit that this stays as-is — do not copy MC's `package.json`-based version source.
5. Keep the new live-verify eval instrument minimal (§2.3's 3-4 checks), not a port of MC's full
   ~80-check `download_eval.py`. This is a release-pipeline gate, not a new general-purpose eval
   surface.

## Step 0: Baseline

```bash
cd ~/learning-architecture
git status --short --branch --untracked-files=all
git log --oneline -5
cat .github/workflows/auto-release.yml
gh release list --repo lingua-viva/learning-architecture --limit 30
git ls-remote --tags git@lingua-viva:lingua-viva/learning-architecture.git | grep -c desktop-v
```

Confirm the current state still matches the spec's evidence (13 stale releases, 18 tags vs 13
releases, pin-before-verify ordering, the GITHUB_TOKEN comment on the `Create release tag` step) —
if it has already changed, note what's different before proceeding.

## Step 1: Deploy Key (generate, hand off — do not self-apply)

```bash
ssh-keygen -t ed25519 -C "lv-tag-push-deploy-key" -f /tmp/lv_tag_push_deploy_key -N ""
cat /tmp/lv_tag_push_deploy_key.pub
```

Write out for the operator, verbatim:
1. Add the public key as a **Deploy key** on `lingua-viva/learning-architecture` → Settings → Deploy
   keys → Add deploy key → check "Allow write access".
2. Add the private key as a repo secret named `LV_TAG_PUSH_DEPLOY_KEY` → Settings → Secrets and
   variables → Actions → New repository secret.
3. Delete the local private key file (`/tmp/lv_tag_push_deploy_key*`) once both are added.

Do not proceed past this step's file changes being *tested* until the operator confirms the secret
exists.

## Step 2: Minimal Live-Download-Eval Instrument

Add a new module (suggested path, adjust to fit LV's existing `src/lingua_viva/` conventions):

```text
src/lingua_viva/download_eval.py
```

Checks (per spec §2.3 — keep to exactly these unless a real gap is found while building):
- `site_returns_200` — `https://linguaviva.art/` returns 200
- `pinned_tag_matches_expected` — the `desktop-v[0-9.]+` string in the live page matches a tag
  passed in as a parameter (this is the hard gate the `live-verify` job will check — equivalent to
  MC's `DL-71`)
- `desktop_asset_urls_302` — the `.dmg`/`.exe`/`.AppImage` GitHub release-download URLs for that tag
  each resolve with a 302
- `install_sh_points_at_source` (optional, cheap) — the install command on the live page still
  references `raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh`, not a
  duplicated/synced copy (guards the property in spec §3's install.sh row)

Wire a CLI verb to invoke it, e.g. `lv eval download --live --tag <tag> --json`, following whatever
CLI-registration pattern `src/lv_cli.py` already uses for other `eval`-style subcommands. Write a
test file (`tests/test_download_eval.py`) covering the non-network-dependent parts (URL construction,
JSON shape) — mock or skip the actual live HTTP calls in the unit test; the live-network path only
needs to work when GitHub Actions runs it for real.

## Step 3: Rebuild `auto-release.yml`

Target job order (mirrors MC's file):

```text
test-gate
  -> version-bump-and-tag   (tag-push step uses LV_TAG_PUSH_DEPLOY_KEY, per Step 1)
    -> wait-for-build-and-pin-site
      (poll `gh run list --workflow=desktop-release.yml` for a run whose headBranch == the new tag;
       only after conclusion == success, pin docs/index.html to that tag and commit+push to main)
      -> live-verify
        (needs: [wait-for-build-and-pin-site, version-bump-and-tag] — both, not just the first;
         copy MC's comment explaining why transitive needs-outputs don't propagate)
        -> cleanup-stale-releases
          (needs: [live-verify, version-bump-and-tag]; hard guard: refuse and exit 1 if NEW_TAG is
           empty, per MC's 2026-07-25 incident — copy the guard verbatim, not just the delete loop)
```

Concretely:
- `test-gate`: keep LV's existing pytest/health/backend-smoke steps as-is.
- `version-bump-and-tag`: keep LV's existing `git tag -l --sort=-v:refname`-based version derivation
  (do NOT switch to MC's `package.json`-based approach — spec §2.5). Change only the checkout/push
  credentials for the tag-push to use the new deploy key.
- `wait-for-build-and-pin-site`: new job. Move the existing "Pin live site to new tag" + "Commit site
  pin" steps here, gated behind a polling loop against `desktop-release.yml` runs for the new tag
  (adapt MC's polling loop — `gh run list --workflow=desktop-release.yml --event=push --json
  databaseId,headBranch,status,conclusion,createdAt`, matching `headBranch == NEW_TAG`).
- `live-verify`: new job. Call the Step 2 instrument with `--tag ${{ needs.version-bump-and-tag.outputs.new_tag }}`,
  hard-fail if `pinned_tag_matches_expected` doesn't pass, warn (don't fail) on the other checks.
- `cleanup-stale-releases`: new job. Copy MC's delete loop and its empty-`NEW_TAG` guard.

## Step 4: Verify Locally, Then Stop

```bash
# YAML sanity (no dedicated linter assumed — at minimum):
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/auto-release.yml'))"
pytest -q tests/test_download_eval.py
python3 -m src.lingua_viva.cli health   # or equivalent — confirm nothing else broke
```

Then **stop and report back to the operator** before:
- pushing this workflow file to `main`,
- confirming the deploy-key secret is in place,
- triggering a real end-to-end run.

## Definition of Done (mirrors spec §4)

- [ ] `LV_TAG_PUSH_DEPLOY_KEY` secret confirmed present (operator-added)
- [ ] `auto-release.yml` reordered, tag-push uses the deploy key
- [ ] `wait-for-build-and-pin-site` job added, site-pin moved into it, gated on confirmed build success
- [ ] `download_eval.py` built + tested + wired as `live-verify` job
- [ ] `cleanup-stale-releases` job added, with the empty-`NEW_TAG` guard
- [ ] One real end-to-end push verified against the same 7-step Definition-of-Pushed checklist MC used
- [ ] The 12 stale `desktop-v*` releases (all but whichever remains live after the first successful
      run) cleaned up
- [ ] `dev/INDEX.md` row for the spec updated to SHIPPED with commit hash + evidence
