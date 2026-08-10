# HANDOFF — Lingua Viva Next Window (2026-08-10)

You are the next build window for `~/learning-architecture` (Lingua Viva).
Read this whole document before touching anything. It tells you what is
built, what we learned (the doctrine is binding), and what you build next.

## 0. Ground rules (non-negotiable)

- `unset ANTHROPIC_API_KEY; export MC_AGENT=1` before any run. NEVER use API credits.
- **Rule 0**: PUSH = downloadable on the live site, right now. Not committed,
  not green CI, not a tag. See `AGENTS.md` for the 7-step checklist.
- This is a **shared, concurrently-edited repo**. Other windows may commit
  while you work. Isolate diffs hunk-level; never stash without immediately
  popping; `git pull --rebase` on push rejection.
- Privacy first: no student names, no institution names (publication-policy.md).
- Deterministic-first, local-first. Refusal is a feature. Honest degradation
  beats silent fallback, always.

## 1. Current state (verified 2026-08-10)

- **origin/main = `8b62d13`** (`chore(release): pin desktop-v0.2.50`). Local = origin. Clean except
  `ontology/proposals/CAND-B8CCB9C1.yaml` (deliberate probe residue — leave it) and 6 untracked dev docs.
- **Test suite: 2225 passed, 13 skipped.** Preflight 6/6. Teacher-readiness harness **19/19, 0 stubbed, 100%**.
- **Releases desktop-v0.2.48 / 49 / 50 all live**, 3 assets each, downloads answer 200, site pinned to v0.2.50.
- v0.2.48 was the **first-ever zero-touch release** (commit → tag → build → publish → site pin, no human).

### What the last two windows shipped

**P1 wiring-audit closures (this window, commits `9f34912`, `ae64910`):**
- **C10 blocked-provider chokepoint**: `config.requested_blocked_provider()` +
  `KNOWN_PROVIDER_NAMES` (config.py); refusal at top of `reason()` in both engines;
  `model_used="none:blocked_provider"`, zero egress, TTS-safe message. 4 locking tests.
- **C9 honest no-model degradation**: `model_answered` clause + honest banner
  (`none:deterministic_only`); `_query_timeout_error()` in web.py carries
  `model_used="none"` + `external_calls: 0` when provably local.
- **C8 latency**: slim tier prompts (<120 words, max_tokens=400) — 27.4s for 3 tiers live.
- **Release chain**: `workflow_call` restructure closed the GITHUB_TOKEN
  tag-trigger gap (auto-release.yml invokes desktop-release.yml directly);
  hdiutil retry (5x backoff) closed the "Resource busy" flake; **pin-after-proof**
  (`pin-site` job curls all 3 assets for 200 before pinning docs/index.html) put
  Rule 0 into the CI machinery itself. Proven live on v0.2.48→v0.2.50.

**Grind Wave 2 (parallel window, G1-G8 — see `SESSION_REPORT_LV_GRIND_WAVE_2_2026-08-10.md`):**
- G1 restricted safeguarding review workflow (coordinator-only status transitions —
  the former "missing state-machine instance" is now built and test-locked).
- G2 PoI progression panel in student lens. G4 holiday calendar for absence
  escalation. G5 parent recommendation through sharing matrix. G6 coursework
  enrichment (degrades deterministically). G7 BM25 library search.

### Open, operator-blocked (do NOT build around these)
Safeguarding Slack/Drive values; Perplexity key + `LV_ALLOW_RESEARCH=1`;
auto-release PAT secret. All fail closed where absent. Leave them.

## 2. What we learned (binding doctrine — three windows converged independently)

**The triad:**
1. **Contracts before surfaces.** Response envelope, UI contract, route
   reachability — defined day 1 — is a *velocity* argument: the router plug-in
   point let 3 windows build in parallel with zero collisions.
2. **Degradation is the product.** A local-first app for teachers spends most
   of its life degraded. Every degraded path must say honestly what happened
   (`none:*` sentinels, banners, `external_calls: 0`) — never pretend a model answered.
3. **Teacher authority is the spine.** The teacher-confirmed state machine
   (suggest → teacher sees → confirm/dismiss → only confirmed affects reports →
   persisted + test-locked) is a **template, not a phase**. Apply it to every
   new suggestion-like feature. Five authority lanes: local private lens /
   teacher review queues / report-grade profile / share-export layer / runtime writes.

**The synthesis addition (drives Wave 1, item F1):**
4. **Safety paths must fail closed and be adversarially tested.** The
   safeguarding classifier once returned GREEN for "His dad hits him at home"
   — found by accident. A fail-open safety feature is worse than its absence:
   it manufactures trust. The fix class (round-up, personal-context secondary
   signals) is in `safeguarding.py`, but it is verified only against phrases
   someone happened to try.

**Supporting rules (each earned the hard way):**
- **One chokepoint per invariant.** Never enforce an invariant at N call
  sites; enforce it where the data must pass. (The dual-engine copy in
  pipeline.py forced every honesty fix to be made twice — Wave 2 retires it.)
- **Built-but-not-called regenerates after every build.** It is a standing
  class, not a one-time bug. It needs a standing instrument (Wave 1, F3).
- **`expected_fail` without expiry is a regression mask.** C11 and DR are
  permanent P0 expected_fails today. Verdict: require expiry or linked work
  item; red when lapsed (Wave 1, F2).
- **Containment by construction beats filtering.** The daily brief never
  *opens* the restricted store — that is stronger than any redaction filter.
- **Gate liveness = output growing** (wc -c twice), never pgrep alone.
- **Fix the class at the chokepoint, never just the reported surface, and add
  a test that locks the class.**

## 3. What you build next (operator-prioritized)

**Wave 1 — Fail-Closed Wave** (do this first; items independent):
- Spec: `dev/SPEC_LV_FAIL_CLOSED_WAVE_2026-08-10.md`
- Prompt: `dev/PROMPT_LV_FAIL_CLOSED_WAVE_BUILD_2026-08-10.md`
- F1 (P0): adversarial safeguarding corpus as a standing, growing fixture + harness check.
- F2 (P0): `expected_fail` expiry / linked-work-item mechanism.
- F3 (P1): standing built-but-not-called wiring instrument.

**Wave 2 — One Envelope** (calm-day refactor; only start after Wave 1 is green):
- Spec: `dev/SPEC_LV_ONE_ENVELOPE_2026-08-10.md`
- Prompt: `dev/PROMPT_LV_ONE_ENVELOPE_BUILD_2026-08-10.md`
- E1 (P1): one response envelope, one sentinel vocabulary, test-locked.
- E2 (P1): retire the legacy `pipeline.py` ReasoningEngine copy; DR expected_fail removed for real.
- E3 (P2): route remaining legacy parent-facing emitters through the sharing matrix.

**Explicitly deferred** (do not build unless the operator re-rules):
teacher-confirmed template extraction as its own wave (apply the template at
the next *new* suggestion feature instead); library-search embeddings;
anything on the operator-blocked list.

## 4. Verification commands (run before claiming anything)

```bash
unset ANTHROPIC_API_KEY; export MC_AGENT=1
python3 -m src.lingua_viva.cli preflight --json          # 6/6
python3 -m src.lingua_viva.cli eval teacher-readiness --json  # 19/19
pytest -q tests/                                          # 2225+ passed
```

Live walkthrough pattern: `uvicorn src.web:app --host 127.0.0.1 --port 8765`
with `LV_AUTH_MODE=local_header` + synthetic state; real HTTP calls; verify
liveness by output growth, not pgrep.

Push protocol: remote is `lingua-viva` (`git@lingua-viva:lingua-viva/learning-architecture.git`).
After push, Rule 0 applies — a push that touches `desktop/**`, `src/**`,
`static/**`, `docs/index.html`, or `pyproject.toml` fires auto-release; the
release is not "done" until all 3 assets answer 200 and the site pin commit
(`chore(release): pin desktop-vX.Y.Z`) is on origin.
