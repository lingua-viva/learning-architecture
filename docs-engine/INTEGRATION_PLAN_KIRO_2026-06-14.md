# Integration Plan — Kiro Closes MC Standalone

**Date**: 2026-06-14
**Owner**: kiro.design
**Method**: Dogfooding MC process (invoke pipeline at each decision point)
**Feedback loop**: Phase → feedback from Claude/others → iterate → next phase

---

## Semantic Blueprint

- **Goal**: Integrate all extracted modules into the MC standalone repo with zero regressions
- **Roles**: Kiro owns implementation. Human holds veto. Claude provides feedback between phases.
- **Capabilities**: Python pipeline, Node.js hub, bridges, lib modules, missions engine
- **Constraints**: No regressions. Tests must pass after every phase. Sanitizer unification before new features.
- **Non-goals**: Not deploying to client VPSes yet. Not building the instance factory yet. Not touching GitHub Pages.

---

## Phases

### Continuous Practice: Docker as Deploy Target

Each phase contributes a Dockerfile (if applicable) and updates `docker-compose.yml`.
Docker is the DEPLOY target, not the dev environment.

- Dev (you): `./mc start` → runs locally, no containers, fast iteration
- Production (clients): `docker compose up -d` → runs everything containerized

Don't Docker-ize ontology/knowledge (mounted as volumes). Don't Docker-ize development.
Simple images: `FROM python:3.12-slim` and `FROM node:20-slim`.

---

### Phase 0: Baseline Freeze + Regression Guard

**What**: Lock current behavior. Ensure all tests pass. Establish the "before" state.

**Actions**:
1. Run full test suite, capture baseline: `cd fde/mission-canvas && python3 -m pytest -q`
2. Run MC health: `./mc health`
3. Document current file count, test count, health score
4. Verify Codex's sanitizer tests pass (Node.js): `node test_external_sanitizer.mjs`
5. Verify hub sanitizer tests pass: `cd runtime/hub && node test_external_sanitizer.mjs`
6. Create a `PHASE_0_BASELINE.md` with all results

**Exit criteria**: All tests green. Baseline documented. Can always revert to this state.

---

### Phase 1: Sanitizer Unification

**What**: Merge the 3 sanitizer implementations into one canonical service.

**Current state**:
- `src/gateway/sanitizer.py` (Python, 3-layer: regex → NER → ontology)
- `data_boundary.mjs` (Node.js in palette/mission-canvas server)
- `peers/hub/external_sanitizer.mjs` (Node.js in hub)
- `lib/safety_patterns.py` (my extraction — regex PII + command safety)

**Target state**: One Python FastAPI service at `localhost:6100/sanitize`.
All surfaces call it. One test suite. One update point.

**Actions**:
1. Build `sanitizer/` service directory with FastAPI app + `sanitizer/Dockerfile`
2. Expose: `POST /sanitize` → `{ok, blocked, text, redactions, reason}`
3. Port all regex patterns from all 3 sources into one
4. Wire hub `server.mjs` to call `http://localhost:6100/sanitize` before external model calls
5. Wire pipeline to call the same service (or import directly since it's Python)
6. Retire `external_sanitizer.mjs` and `data_boundary.mjs` sanitize functions
7. Tests: POST with PII, verify redaction. POST clean, verify pass-through.
8. Add `sanitizer` service to `docker-compose.yml`

**Exit criteria**: One sanitizer, called by all surfaces, all existing tests still pass. Dockerfile works.

---

### Phase 2: Classification Verification

**What**: Confirm Claude's classification improvements are stable. Wire description indexing (Layer 2).

**Actions**:
1. Run golden dataset: verify 53/97 (55%) accuracy holds
2. Add Layer 2: tokenize node descriptions into signal index (Claude's insight #3)
3. Run golden dataset again: measure improvement
4. If regression: revert Layer 2, keep Layer 1 only
5. Wire `learned_weights.yaml` so successful paths boost signals (Layer 4 foundation)

**Exit criteria**: Accuracy ≥ 55% (no regression). Layer 2 adds measurable improvement or is reverted.

---

### Phase 3: lib/ Consolidation + Web Search

**What**: Bring shared utilities into the repo without duplication.

**Actions**:
1. Compare my `lib/scheduler.py` with their `src/cron.py` — keep theirs, add features from mine (YAML config, notify callback) if missing
2. Merge `lib/safety_patterns.py` into `src/gates/entry.py` as an additional detection layer (command safety + PII regex)
3. Bring `lib/skill_loader.py` in as-is (loads SKILL.md format, complements existing YAML skills)
4. Bring `lib/web_search.py` in as `src/gateway/web_search.py` (extends beyond Perplexity-only)
5. Remove any dead code or unused imports
6. Run tests

**Exit criteria**: No duplicate functionality. All tests pass. `./mc health` ≥ 94%.

---

### Phase 4: Bridges Integration

**What**: Add 6 communication platform bridges to MC. Tropical IT directly requested multi-channel. Normalized pattern for all 7 means any client can flip a config to enable a channel.

**Actions**:
1. Move `bridges/` directory into `fde/mission-canvas/bridges/`
2. Resolve conflict with existing `bridges/telegram/bot.py` — keep theirs for telegram, add my 6 new ones
3. Update `bridges/__init__.py` to export all 7 (telegram + email + slack + whatsapp + discord + signal + teams)
4. Wire bridges into pipeline: inbound message → sanitizer → classify → agent → respond → store
5. Add one integration test: mock email inbound → verify pipeline fires → verify store records it
6. Update README

**Exit criteria**: `from bridges import EmailBridge, SlackBridge, ...` works. Pipeline integration test passes.

---

### Phase 5: Missions Engine

**What**: Add multi-step workflow orchestration. Market-validated (OpenClaw's most successful artifact). Direct application: Tropical IT order follow-ups, multi-country outreach.

**Actions**:
1. Bring `lib/missions/` into `fde/mission-canvas/src/missions/`
2. Wire into MC CLI: `./mc mission create|status|update|complete`
3. Wire into cron: missions with scheduled steps trigger via scheduler
4. Wire into bridges: mission events can send messages via any bridge
5. Add test: create mission → advance steps → verify state machine enforcement

**Exit criteria**: `./mc mission create "test" --steps "A,B,C"` works. State machine enforced. Tests pass.

---

### Phase 6: @mention + Direct Model Routing

**What**: Complete the `@mention` feature end-to-end.

**Actions**:
1. The frontend parsing is already deployed (docs/index.html)
2. Build hub-side handler: when `direct: true`, skip resolver, route to specified provider
3. Verify governance still fires (sanitizer + store) even on direct routes
4. Test: `@claude hello` → streams from Claude → governance chips show DIRECT + STORED
5. Push to GitHub Pages (deploys live site)

**Exit criteria**: `@claude`, `@mistral`, `@perplexity` work in the browser UI. Governance records every direct call.

---

### Phase 7: Deploy Story (Docker Compose + Instance Config)

**What**: By this point docker-compose.yml already exists from Phases 1-6. This phase adds the instance factory — `mc instance create client.yaml`.

**Actions**:
1. Finalize docker-compose.yml (sanitizer + server + hub + nginx)
2. Build `mc instance create` command — reads client YAML, generates .env + compose override
3. Test: create Tropical IT instance config → `docker compose up -d` → system runs
4. Document the 10-minute deploy path

**Exit criteria**: One YAML file + one command = running MC instance. Tested locally with docker compose.

---

## Iteration Protocol (Per Phase)

```
1. Implement phase
2. Run all tests (python + node)
3. Run ./mc health
4. If regression: fix before proceeding
5. Report results to human
6. Human gets feedback from Claude/others
7. Human relays feedback to Kiro
8. Kiro iterates (max 3 passes per phase)
9. If stable: move to next phase
10. If risk of regression from more iteration: stop, move on
```

---

## Current State Snapshot

| Metric | Value |
|--------|-------|
| `fde/mission-canvas/` files | ~289 |
| Python tests | 72 + 6 + 2 = 80 |
| Node.js tests | ~8 |
| MC health | 94% (16/17) |
| Classification accuracy | 55% (53/97) |
| Bridges available | 1 (telegram) → will be 7 |
| Sanitizer implementations | 3 → will be 1 |

---

## Ready to start Phase 0 on your go.
