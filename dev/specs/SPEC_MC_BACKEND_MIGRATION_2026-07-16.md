# SPEC: MC-Shaped Backend Migration to Lingua Viva Native

**Status**: draft — ready to build  
**Date**: 2026-07-16  
**Repo**: `/home/mical/learning-architecture`  
**Branch**: `LINGUA-VIVA-UPDATE`  
**Author**: kiro (architecture lens)  
**Origin**: Post-separation audit — this repo still carries the full Mission Canvas
pipeline infrastructure from the `feat/mission-canvas-engine` branch merge. The app
works (348 tests pass) but the codebase is 60% MC machinery that Lingua Viva doesn't
need and actively confuses contributors about product boundaries.

---

## 0. Problem

The learning-architecture repo integrated the Mission Canvas engine as its backend
(`feat/mission-canvas-engine` → merged to main). This gave Lingua Viva a working
governed pipeline, but also imported:

- A 12-step pipeline designed for multi-domain routing (Lingua Viva is single-domain: education)
- Exit gate socket firewall (LV has no external API calls except Ollama)
- Entry gate PII scanner (LV handles student data differently — COPPA, not enterprise PII)
- Missions engine (LV doesn't have "missions")
- Provider registry for 6+ cloud LLMs (LV is local-first, single provider)
- Agent adapter / Codex adapter (LV doesn't orchestrate agents)
- Gateway/Perplexity integration (LV doesn't do external research)
- `mc_cli.py` named and branded as Mission Canvas
- Cron daemon (LV doesn't need scheduled jobs yet)

**What LV actually uses from the MC engine:**
- `src/education/` — 16 modules (the real product code)
- `src/pipeline.py` — only the `ReasoningEngine` class (local Ollama calls)
- `src/web.py` — HTTP server + WebSocket (but branded MC, routes could be simpler)
- `src/provider_config.py` — Ollama/OpenRouter config
- `src/session.py` — session management
- `ontology/` — education domain nodes
- `knowledge/` — education knowledge entries

**What LV does NOT use:**
- `src/gates/` — entry/exit gates (LV has its own privacy model via Doctor)
- `src/gateway/` — Perplexity, web search, sanitizer (no external research)
- `src/missions/` — missions engine
- `src/agent_adapter.py`, `src/codex_adapter.py` — agent orchestration
- `src/integrity_gate.py` — hallucination checking (could be useful later, not now)
- `src/cron.py` — scheduled jobs
- `src/integration_onboarding.py` — MC onboarding flow
- `src/mc_cli.py` — MC-branded CLI (LV needs its own `lv` CLI)
- `src/pwa.py` — PWA manifest helpers (already rebranded in static/)

---

## 1. Migration Strategy: Strangler Fig

Do NOT delete MC files in one pass. Instead:

1. Create `src/lingua_viva/` as the new native module
2. Move education-specific logic there
3. Create a thin `lv` CLI that imports from `src/lingua_viva/`
4. Create a thin web server that imports from `src/lingua_viva/`
5. As each MC module loses its last import, archive it
6. Tests migrate one file at a time — old tests still pass throughout

This preserves the 348-test safety net while progressively replacing MC plumbing.

---

## 2. Phase 1 — Native Lingua Viva Module (No deletions)

### Create `src/lingua_viva/`

```
src/lingua_viva/
  __init__.py          — package marker
  app.py               — teacher-facing web app (replaces src/web.py eventually)
  reasoning.py         — thin wrapper around Ollama (extracts ReasoningEngine)
  privacy.py           — student data privacy (imports from doctor/support_loop/privacy.py)
  config.py            — model config (extracts from provider_config.py)
  cli.py               — `lv` CLI entry point
```

### What each module does:

**reasoning.py** — Extract `ReasoningEngine` and `ReasonResult` from `src/pipeline.py` (lines ~750-850). No ontology classify, no traverse, no gates. Just: build prompt → call Ollama → return result. The education executor already does its own prompt assembly.

**privacy.py** — Wrap `doctor/support_loop/privacy.py` patterns for use in the app runtime. Student names, grades, parent info → blocked from any output that leaves the machine. This replaces the MC entry gate's enterprise PII model with LV's education-specific COPPA model.

**config.py** — Model detection (which Ollama models are installed), provider selection. Extract from `src/provider_config.py` the parts that matter: Ollama URL, model preference list, health check.

**app.py** — The teacher web app. Initially just re-exports `src/web.py`'s routes, but becomes the place to add Doctor as a Help/Health affordance (per the unified build spec §5).

**cli.py** — `lv` command. Subcommands: `lv chat`, `lv ingest <pdf>`, `lv health`, `lv doctor`. Replaces `mc` CLI for this repo.

### Tests for Phase 1:

```
tests/test_lingua_viva_reasoning.py   — ReasoningEngine works standalone
tests/test_lingua_viva_privacy.py     — student data blocked
tests/test_lingua_viva_config.py      — model detection
tests/test_lv_cli.py                  — CLI smoke test
```

### Acceptance:
- `python3 -m pytest tests/test_lingua_viva_*.py tests/test_lv_cli.py -q` passes
- `python3 -m pytest tests/ -q` still passes (348+ green — no regressions)
- `python3 -m doctor.support_loop doctor` no longer reports PRIVATE_RISK from MC artifacts

---

## 3. Phase 2 — Route the App Through Native Module

### Changes:
- `src/web.py` imports from `src/lingua_viva/` instead of directly from `src/pipeline.py`
- All "Mission Canvas" strings in `src/web.py` → "Lingua Viva"
- `/api/query` WebSocket handler calls `src/lingua_viva/reasoning.py`
- `/api/upload` calls `src/lingua_viva/` ingest path
- Doctor endpoint added: `GET /api/health` → runs `doctor/support_loop/doctor.py`

### Tests:
- Existing `tests/test_pwa_routes.py` still passes
- New `tests/test_app_doctor_endpoint.py` — Doctor accessible from app

### Acceptance:
- App serves teachers at localhost (same port)
- Doctor is accessible via Help/Health in the app
- No "Mission Canvas" visible in any user-facing surface
- 348+ tests still green

---

## 4. Phase 3 — Archive MC-Only Modules

Once Phase 2 is stable and all tests pass through the native module:

### Move to `archive/mc-engine/`:
- `src/gates/` (entry.py, exit.py, __init__.py)
- `src/gateway/` (perplexity.py, web_search.py, sanitizer.py)
- `src/missions/`
- `src/agent_adapter.py`
- `src/codex_adapter.py`
- `src/cron.py`
- `src/integration_onboarding.py`
- `src/integrity_gate.py`
- `src/integrity/` (health_check.py, total_health.py, regression.py)

### Rename:
- `src/mc_cli.py` → archived (replaced by `src/lingua_viva/cli.py`)

### Keep (shared infrastructure, still used):
- `src/pipeline.py` — until ReasoningEngine is fully extracted
- `src/provider_config.py` — until config.py replaces it
- `src/session.py` — session management (useful)
- `src/education/` — the actual product code (stays)
- `src/web.py` — until app.py replaces it
- `src/pwa.py` — PWA helpers (already rebranded)

### Tests:
- Remove/archive the 9 test files that import MC-only modules
- All remaining tests pass
- Doctor reports clean

### Acceptance:
- `rg "Mission Canvas" src/` returns 0 hits (archive/ excluded)
- `python3 -m pytest tests/ -q` passes (reduced count but 0 failures)
- `python3 -m doctor.support_loop doctor` reports OK or WARN (not PRIVATE_RISK)

---

## 5. Phase 4 — LV-Native Pipeline (Optional, Future)

Replace `src/pipeline.py` entirely with a simpler education-specific pipeline:

```
SCAN (privacy) → CLASSIFY (education domain only) → RETRIEVE (knowledge) → REASON (Ollama) → STORE
```

No traverse, no meta-intent, no candidate RIUs, no governance-only mode, no cloud escalation.
This is a future phase — only worth doing once the app has real teacher users and we
understand what the pipeline actually needs to do for them.

---

## 6. Files That Need Attention Before Phase 1

| File | Issue | Fix |
|------|-------|-----|
| `src/web.py` | Titled "Mission Canvas API Server" | Rename in Phase 2 |
| `src/mc_cli.py` | Named `mc`, branded MC | Replace with `lv` CLI in Phase 1 |
| `src/api_server.py` | Titled "Mission Canvas API Server" | Archive in Phase 3 |
| `CLAUDE.md` | References Mission Canvas governance | Update to LV context |
| `README.md` | May reference MC | Audit after Phase 2 |
| `src/context_builder.py:114` | Fallback says "Mission Canvas" | Fix in Phase 2 |

---

## 7. Test Impact Summary

| Phase | Tests Added | Tests Archived | Net Change |
|-------|------------|----------------|------------|
| Phase 1 | +4 (lingua_viva module) | 0 | +4 |
| Phase 2 | +1 (doctor endpoint) | 0 | +1 |
| Phase 3 | 0 | -9 (MC-only imports) | -9 |
| **Total** | +5 | -9 | -4 |

Expected final count: ~344 tests (down from 348, but all meaningful).

---

## 8. Validation After Each Phase

```bash
# Always run:
python3 -m pytest tests/ -q
python3 -m pytest doctor/support_loop/tests/ -q
python3 -m doctor.support_loop doctor
python3 doctor/lv_artifact_gauntlet.py

# Phase 2+:
python3 -m src.lingua_viva.cli health

# Phase 3+:
rg "Mission Canvas" src/ static/ tests/
```

---

## 9. What NOT To Do

- Do NOT copy MC's 12-step pipeline verbatim into `src/lingua_viva/`
- Do NOT import MC gates/gateway into the LV native module
- Do NOT add Perplexity/external research (LV is local-first)
- Do NOT add agent orchestration (LV serves one teacher at a time)
- Do NOT remove `src/education/` — that IS the product code
- Do NOT break the 348-test baseline at any point during migration

---

## 10. Open Questions (For Operator)

1. **Port number**: Keep 8787 or change? (Current: same as MC default)
2. **`lv` CLI name**: Confirm `lv` vs `lingua-viva` vs `lviva`
3. **Phase 4 timing**: Build the simplified pipeline now or wait for real users?
4. **CLAUDE.md**: Rewrite for LV context or remove entirely?
5. **Onboarding flow**: Keep the integration_onboarding.py wizard (Slack/provider setup) or start fresh?
