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

## Grounding Integrity Rate (GIR) — LV Definition

**GIR = 1 − (unsupported_claims + uncertainty_claims) / max(total_claims, 1)**

Method `claim_support_v1_heuristic`, implemented in `src/lingua_viva/grounding/build.py`
(schema in `grounding/schema.py`):

- **claims** = sentence fragments of the synthesized answer.
- **uncertainty_claims** = fragments containing hedge markers ("might", "possibly", "unclear"…).
  Hedged claims are honest — they cost score but are not lies.
- **grounded** = at least one *relevant* source backs the answer: a sources-ledger record
  (`local`/`drive`/`slack` tiers, token-overlap relevance against the query) or a knowledge
  citation. If grounded, `unsupported_claims = 0`; if not, every unhedged fragment is unsupported.
- `synthesis_confidence < 0.1` forces score to 0.0 — a degraded engine cannot claim grounding.
- The `external` tier is always `blocked` (`local_first_policy`). Student data never buys
  grounding from the cloud.

**The caught lie is mechanical, no interpretation:** the answer states something without a hedge,
and `tier_used == "none"` with no knowledge citation. That single condition drives the score down.

**Where it's computed — verdict, not reconstruction:** inline at Step 6.25 GROUND in
`src/pipeline.py`, immediately after SYNTHESIZE, while `sources_used` and `source_citations` are
still in memory. The verdict is stored on the path record (`gir_score`, `gir_method`) and in the
`GroundingResult`. Never recompute GIR later from logs or proxies — the real moment is the only
moment that has the ground truth.

**What grounds each output type:**

| Output | Grounding source fields |
|---|---|
| Ask answers / CEFR claims | `sources_used` (sources ledger) + `source_citations` (knowledge library) |
| Parent reports & help artifacts | `source_observation_ids` (`src/education/help_artifacts.py`) — every artifact carries the observation IDs behind it |
| Lesson materials | student-lens CEFR tier assignments + Manuale/curriculum alignment |
| Grouping/tier suggestions | student-lens evidence (`because` field) — the system suggests, the teacher decides; a tier is never changed by the system |

**Where the score closes the loop (all live):**
- Voice tone (`src/lingua_viva/voice_tone.py`): ≥0.8 plain · ≥0.4 clarify prefix ("let's double
  check this together") · <0.4 hedge. A confident voice on an ungrounded answer is a defect.
- Ask chat renders a GIR badge per answer; action plans carry a `GroundingSummary` badge.
- Golden workflow runner fails on `gir_out_of_range`; `scripts/run_lv_voice_gir_hardening.py`
  checks tone↔GIR consistency (plain tone with GIR <0.8 = `tone_mismatch_high_gir`).

**Lagging indicators — what drift looks like in an education app:**
- **Level inflation**: CEFR level claims moving up with no new observation records behind them.
- **Grouping staleness**: tier suggestions built from a lens whose newest observation predates
  the decision window.
- **Curriculum drift**: generated materials that cite no Manuale/curriculum source.
- **Tone mismatch**: plain (confident) voice with GIR below the plain threshold.

**Honest maturity label:** `claim_support_v1_heuristic` is sentence-level and token-overlap based,
not per-claim semantic verification. Known gap (intended v2): Ask answers about a specific student
do not yet check `source_observation_ids` linkage the way parent reports do — a CEFR claim in chat
can be "grounded" by a relevant ledger record without naming the observations behind the level.
Do not describe LV's GIR as claim-level verification until that lands.

---

## Repo Basics

- Single standalone repo: `git@lingua-viva:lingua-viva/learning-architecture.git`
- No monorepo, no subtrees. `git push origin main` is the entire push surface for code.
- Live site: https://linguaviva.art — served by GitHub Pages directly from `main:/docs`.
  There is no separate site repo in production. (A local-only draft exists at
  `/home/mical/linguaviva.art` with no git remote — it is not connected to anything and should
  be treated as dead, not a deploy target.)
- See `CLAUDE.md` for project scope, privacy rules, and general working conventions.
