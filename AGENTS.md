# Lingua Viva / Learning Architecture — Agent Rules

## THE Definition of "Pushed" — Read This First

**PUSH = the file is downloadable, working, right now, by clicking the button on
https://linguaviva.art.**

Nothing else counts as pushed. Not "committed." Not "on `main`." Not "the workflow is green."
Not "the tag exists." Not "the URL returns 200." If a user cannot click the download button on
the live site and get a working app *today*, the work does not exist. It is not 90% done, not
"basically pushed," not "just needs the secrets" — it is **not pushed**, full stop.

This has been miscommunicated across tens of conversations and multiple agent sessions (Claude,
Kiro). The failure pattern every time: an agent commits code, or pushes to `main`, or even cuts a
release tag — and reports "pushed" or "done" — while the actual download link on the live site
still serves old or broken content. That is a 100% failure by this project's standard, even if
every intermediate step succeeded.

### Before you ever say "pushed" or "done," verify all of these, in order:

1. **Is it on `main`?**
   ```bash
   git rev-list --left-right --count origin/main...HEAD   # must be "0  0"
   ```
2. **Is there a release tag that actually contains this code, and did the build succeed?**
   Committing to `main` does NOT trigger a release. You need a tag (`v*` for CLI,
   `desktop-v*` for desktop) pushed, and the resulting CI run must be green.
   ```bash
   gh run list --workflow=desktop-release.yml --limit 1
   ```
3. **If it's a signed macOS build, is it actually signed?** A green CI run is not enough —
   read the log itself.
   ```bash
   gh run view <run-id> --log | grep -A5 "Verify macOS signature"
   # must show: ✓ Signed by team: XWT7RB624U — not "TeamIdentifier=not set"
   ```
4. **Does `docs/index.html` point at that exact release tag?** The desktop download buttons
   are pinned to a literal tag string, not `/latest`. A new release changes nothing for users
   until this file is also updated and pushed.
   ```bash
   grep -o 'desktop-v[0-9.]*' docs/index.html | sort -u
   ```
5. **Is that HTML actually live?** GitHub Pages redeploys `docs/index.html` on push to `main`,
   ~30-60s delay. Check the live site, not just the repo.
   ```bash
   curl -sI https://linguaviva.art/ | head -1
   ```
6. **Does the download link on the live site actually resolve to that build?**
   ```bash
   curl -sI "https://github.com/lingua-viva/learning-architecture/releases/download/<tag>/LinguaViva.dmg" | head -1
   # 302 confirms the file exists — it does NOT confirm it's signed. See step 3.
   ```
7. **Is there exactly one version live?** If an old release/tag with the same asset names is
   still around, delete it. Two coexisting versions is itself a failure state per this repo's
   demo requirements — no overlap, ever.

Only after all seven check out can you say "pushed." If you skip a step and say "pushed" anyway,
that is the exact failure this file exists to stop.

Full mechanics, the two release tracks, and the historical incidents behind each rule above:
see [`PUSH_TO_PRODUCTION.md`](PUSH_TO_PRODUCTION.md).

---

## Repo Basics

- Single standalone repo: `git@lingua-viva:lingua-viva/learning-architecture.git`
- No monorepo, no subtrees. `git push origin main` is the entire push surface for code.
- Live site: https://linguaviva.art — served by GitHub Pages directly from `main:/docs`.
  There is no separate site repo in production. (A local-only draft exists at
  `/home/mical/linguaviva.art` with no git remote — it is not connected to anything and should
  be treated as dead, not a deploy target.)
- See `CLAUDE.md` for project scope, privacy rules, and general working conventions.
