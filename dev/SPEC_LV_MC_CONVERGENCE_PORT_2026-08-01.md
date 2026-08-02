# SPEC: Port Useful Changes from Mission Canvas's 2026-07-31 Convergence Run to Lingua Viva

**Date**: 2026-08-01
**Status**: DRAFT — not yet built, pending operator review
**Source run**: `mission-canvas/dev/HANDOFF_CONVERGENCE_RUN_2026-07-31.md` (first full end-to-end run of
`mc improve`'s self-improvement loop, run to convergence 2026-07-31) plus the same-day CI
troubleshooting that followed it while pushing that run's fixes to production.
**Systems**: Release/CI pipeline (primary); eval/gauntlet architecture (investigated, not applicable —
see §3).
**Primary artifact(s) to build**: `.github/workflows/auto-release.yml` (rewrite), a new minimal
live-download-eval instrument (new file, name TBD by implementer — suggest
`src/lingua_viva/download_eval.py` + `lv eval download` CLI verb), one new repo secret
(`LV_TAG_PUSH_DEPLOY_KEY`).
**Selection rationale**: MC's convergence run itself (2 classifier/aggregation bugs fixed) doesn't
port to LV — verified below, LV doesn't have the affected code paths. But *shipping* that run's
fixes to production this session surfaced two real, live, currently-unresolved MC release-pipeline
bugs, and fixing them revealed that LV has the near-identical defect class, already self-documented
in LV's own `auto-release.yml` as a known, unresolved gap since 2026-07-29 — and it is currently
live: **13 stale `desktop-v*` pre-releases are simultaneously live on LV's GitHub right now**, and
5 of LV's last 18 desktop tags have no corresponding release at all (orphaned/failed builds). This
is the same "Definition of Pushed" failure class LV's own `AGENTS.md` and `PUSH_TO_PRODUCTION.md`
already treat as a first-class incident category for MC. This spec closes it using MC's
already-proven fix as the template.

---

## 1. What Was Actually Investigated

Per the operator's request, every fix and finding from MC's 2026-07-31 convergence run (and the
push-to-production troubleshooting immediately after it) was checked against LV's current codebase
for applicability. Findings below are evidence-based — each item states what was checked and what
was found, not assumed.

## 2. Applicable — Build This

### 2.1 Root cause: LV's tag push cannot trigger its own build workflow

**Evidence**: `learning-architecture/.github/workflows/auto-release.yml`, step `Create release tag`,
already carries this comment (written 2026-07-29, still true as of this spec):

> KNOWN GAP (found 2026-07-29): this push uses the default GITHUB_TOKEN via actions/checkout's
> persisted credentials. GitHub deliberately does NOT fire other workflows (incl. this repo's
> desktop-release.yml, which triggers on `push: tags: ['desktop-v*']`) for pushes authored by
> GITHUB_TOKEN... every tag this step creates needs a manual re-push... to actually build.

MC hit and solved the identical restriction in its own `auto-release.yml`
(`version-bump-and-tag` job): a dedicated SSH deploy key (repo secret `MC_TAG_PUSH_DEPLOY_KEY`,
added 2026-07-23 specifically for this purpose) checks out and pushes as an external actor instead
of via `GITHUB_TOKEN`, which does trigger `desktop-release.yml` normally.

**Fix**: Generate a dedicated SSH deploy key for `lingua-viva/learning-architecture` (write access),
add the private half as repo secret `LV_TAG_PUSH_DEPLOY_KEY`, and use
`webfactory/ssh-agent@v0.9.0` + `actions/checkout@v4` with `ssh-key: ${{ secrets.LV_TAG_PUSH_DEPLOY_KEY }}`
for the tag-creating step only (mirrors MC's `version-bump-and-tag` job structure verbatim — see
MC's `.github/workflows/auto-release.yml` for the exact block to copy).

### 2.2 Ordering bug: LV pins the live site *before* confirming the build succeeded

**Evidence**: reading LV's `auto-release.yml` job order top to bottom: `Compute next desktop tag`
(pure string math, no build has happened yet) → `Pin live site to new tag` (commits `docs/index.html`
pointing at that not-yet-built tag) → `Create release tag` (pushes the tag that — per §2.1 — often
doesn't even trigger a build). The site can be pinned to a tag whose build later fails, never runs,
or is still in flight, with nothing to catch it.

Confirmed this isn't theoretical:
```
$ gh release list --repo lingua-viva/learning-architecture --limit 30 | grep desktop-v | wc -l
13
$ git ls-remote --tags <repo> | grep -c desktop-v
18
```
5 of the last 18 desktop tags have no release — evidence of builds that failed or silently never ran
under the current pin-then-hope ordering. The current live pin (`desktop-v0.2.24`) happens to be
healthy today, but the mechanism that would have caught it if it weren't doesn't exist.

MC's `auto-release.yml` fixes this with a `wait-for-build-and-pin-site` job that sits *between* tag
creation and site-pinning, polling `gh run list --workflow=desktop-release.yml` for the specific tag
and hard-failing the whole release if that run's conclusion isn't `success` — the site is pinned
only after that job passes. LV's simpler single-repo site (no separate `missioncanvas.ai`-style repo
to clone — LV's site lives in `docs/` in the same repo) makes this even easier to port than the MC
version: no second deploy key is needed for the site-pin commit itself, only the tag push (§2.1).

**Fix**: Reorder LV's job into: `test-gate` → `version-bump-and-tag` (tag push only, using the
§2.1 deploy key) → `wait-for-build-and-pin-site` (poll `desktop-release.yml` for this tag; pin
`docs/index.html` and commit only on confirmed success) → `live-verify` (§2.3) →
`cleanup-stale-releases` (§2.4).

### 2.3 Missing gate: no live-verify step exists at all

**Evidence**: `grep -rln "download_eval\|live-verify\|DL-71" learning-architecture` returns nothing.
LV has no automated live-site/download verification instrument of any kind — MC's
`src/download_eval.py` (backing `mc eval download --live`, ~80 checks, `DL-01`..`DL-80`) has no LV
counterpart.

**Fix**: Build a minimal version scoped to what LV's release pipeline actually needs as a hard gate
— not all 80 of MC's checks, just enough to make `wait-for-build-and-pin-site` accountable for what
it just did:
- site returns 200
- pinned tag in `docs/index.html` matches the tag just shipped (MC's `DL-71` equivalent — this is
  the one that must hard-fail the release, per MC's own comment: "the check this job exists to
  gate")
- the 3 desktop asset download URLs (`.dmg`/`.exe`/`.AppImage`) for that tag resolve (302)
- (optional, cheap) the `install.sh` line in `docs/index.html` still points at
  `raw.githubusercontent.com/.../main/install.sh` (guards the one thing keeping LV immune to MC's
  §3.3 finding — see below)

Wire it as a new job `live-verify` (`needs: [wait-for-build-and-pin-site, version-bump-and-tag]` —
copy MC's comment about `needs` not including *transitive* outputs verbatim; this exact mistake
caused MC's 2026-07-25 mass-release-deletion incident, see §2.4).

### 2.4 Missing gate: no cleanup-stale-releases step exists at all

**Evidence**: 13 `desktop-v*` pre-releases are live simultaneously right now (§2.2's `gh release
list` output above, `0.2.10` through `0.2.24` with gaps). Every one of them is a clickable,
downloadable release on GitHub. This directly violates the "exactly one version live" principle
`AGENTS.md`'s Definition-of-Pushed checklist (step 7, ported to LV's own `AGENTS.md`) already
requires.

**Fix**: Port MC's `cleanup-stale-releases` job verbatim, including its hard-won safety guard:
```yaml
if [ -z "${NEW_TAG}" ]; then
  echo "REFUSING to clean up: NEW_TAG is empty — deleting 'everything except the empty string' means deleting every live release."
  exit 1
fi
```
This guard exists in MC specifically because on 2026-07-25 a `needs:` misconfiguration (missing the
direct dependency needed for output propagation) left `NEW_TAG` empty and the job deleted every
live `desktop-v*` release, including the one just shipped. Port the guard, not just the delete loop.

### 2.5 One thing to *not* port — flag it as a difference worth keeping

MC's `version-bump-and-tag` computes the "next" version by reading `desktop/package.json` on
`main` and incrementing its patch number. This is the exact mechanism that caused the tag-collision
bug fixed live during this session's push (a prior run's version-bump commit never landed on `main`,
so `package.json` and the actual tag history silently diverged, and the next run recomputed a
version that already had a real, published release under it).

LV's existing approach — `git tag -l 'desktop-v*' --sort=-v:refname | head -1`, deriving "next"
directly from the real tag history rather than a file that can drift from it — does not have this
specific failure mode. **Recommendation: keep LV's current tag-derivation logic as-is; do not copy
MC's package.json-based version source.** (Worth separately flagging to MC that LV's approach is
more robust here — out of scope for this spec, noted for completeness.)

## 3. Investigated — Not Applicable (documented so this isn't re-investigated later)

| MC fix/finding this session | Why it does not port to LV |
|---|---|
| gw/gvl 5s reachability timeout too short, causing false `*_server_unreachable` (fixed, commit `895fcb37`) | LV has no equivalent runtime code. `src/lingua_viva/golden_workflows/runner.py` has no reachability/timeout check at all (`grep -n "timeout\|unreachable\|urlopen"` returns nothing), and `dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md`'s golden-voice-loop instrument was never actually built into code (`grep -rln "golden_voice_loop\|GoldenVoiceLoop" src/` returns nothing) — confirmed left uncommitted/unbuilt at the end of the 2026-07-29/30 overnight session per that session's own handoff. Nothing to fix yet; re-check this table entry once that spec is actually built. |
| Gauntlet PROTECT/decoy misattribution — `if "protect" in exp:` key-presence bug vs. `exp.get("protect")` truthiness (fixed, commit `d3939af7`, in `improvement_circuit.py`'s `measure()`) | LV has no `improvement_circuit.py` / no `mc improve`-equivalent recursive self-improvement loop with classifier-scored gauntlet aggregation at all (confirmed: `grep -rln "def analyze\|def measure\|improvement_journal" src/ doctor/` finds nothing matching that architecture). LV's gauntlets (`tests/evals/layer5_gauntlets/*.py`) are individual pytest scenario files, not an aggregation function that could carry this exact key-presence-vs-truthiness bug. Swept `src/` and `doctor/` for the same anti-pattern generically (`"protect" in`, `"decoy" in`, `"is_decoy" in`, `"passed" in`) — zero hits. |
| Wizard-contract test hardcoded a stale expected version (`test_capability_ux.py`, fixed 70→71) | LV has the identical guard pattern (`tests/test_ui_contract.py`, `EXPECTED_VERSION = 86` vs. `contracts/UI_CONTRACT.yaml`'s `version: 86`) — checked, currently in sync (`pytest tests/test_ui_contract.py -q` → 6 passed). No action needed now, but this is the same drift class MC just hit; if `UI_CONTRACT.yaml`'s version is ever bumped without updating `EXPECTED_VERSION` in the same commit (LV's own test file already warns about this at line 5), it'll fail exactly the way MC's did. Nothing to build — just noting the shared risk. |
| `install.sh` drift between source and the publicly-served copy (MC's `DL-15`, found live this session, fixed by syncing `pretendhome/missioncanvas.ai`) | LV's architecture is structurally immune to this specific failure mode: LV's site lives in `docs/` *inside the same repo* as `install.sh` (confirmed: no separate `linguaviva.art` site repo is wired to production — `PUSH_TO_PRODUCTION.md` line 42 explicitly states this), and the install command on `docs/index.html` points directly at `raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh` rather than a duplicated/synced copy. There is no second copy that can go stale. No fix needed; §2.3's optional check just guards this property from silently regressing if the link is ever hand-edited. |

## 4. Definition of Done

- [ ] `LV_TAG_PUSH_DEPLOY_KEY` secret exists (dedicated SSH deploy key, write access, added to the
      `lingua-viva/learning-architecture` repo)
- [ ] `auto-release.yml` reordered per §2.2, tag-push step uses the new deploy key per §2.1
- [ ] New `wait-for-build-and-pin-site` job added, site-pin commit moved into it, gated on
      `desktop-release.yml` reaching `conclusion: success` for the exact tag just created
- [ ] New minimal live-download-eval instrument built (§2.3) and wired as a `live-verify` job
- [ ] New `cleanup-stale-releases` job added, including the empty-`NEW_TAG` guard (§2.4)
- [ ] End-to-end proof: one real push through the full rebuilt pipeline, confirmed via the same
      7-step Definition-of-Pushed checklist MC used this session (tag exists → build succeeded →
      signed/notarized → site pinned → site live → download resolves → exactly one release live)
- [ ] The 12 currently-stale `desktop-v*` releases (all but the one that should remain live) cleaned
      up as part of, or immediately after, the first successful run of the rebuilt pipeline
- [ ] `dev/INDEX.md` row added/updated on ship, per this repo's own documented convention

## 5. Explicitly Out of Scope

- Rewriting LV's tag-derivation logic (§2.5 — keep as-is)
- Building the golden-voice-loop instrument itself (separate, already-specced, unbuilt work —
  `dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md`)
- Building an `mc improve`-equivalent recursive self-improvement loop for LV (no evidence this was
  requested; LV's `doctor/` + `improvement_audit.py` tooling is a different, already-functioning
  architecture, not a gap)
