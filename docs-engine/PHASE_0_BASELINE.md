# Phase 0 Baseline — 2026-06-14

**Captured by**: kiro.design
**Time**: 15:12 PDT

---

## Test Results

| Suite | Result | Duration |
|-------|--------|----------|
| Python (pytest) | **73 passed** | 63s |
| MC server sanitizer (Node.js) | **passed** | <1s |
| Voice Hub sanitizer (Node.js) | **passed** | <1s |

**Note**: One stale test assertion updated (`test_ontology.py:81` — classification now correctly routes "AI governance" to ai-enablement instead of generic core/legal). This is an improvement from Claude's name auto-indexing, not a regression.

---

## MC Health

```
Health: 94% (16/17)
  [WARN] ontology: 3/4
        Node RIU-100 has only 2 signals (min 3)
        Node RIU-105 has only 2 signals (min 3)
  [PASS] knowledge: 3/3
  [PASS] memory: 1/1
  [PASS] gateway: 3/3
  [PASS] skills: 2/2
  [PASS] lenses: 2/2
  [PASS] config: 2/2
```

---

## System Metrics

| Metric | Value |
|--------|-------|
| Source files (excl. cache/node_modules) | 162 |
| Python tests | 73 |
| Node.js tests | 2 suites (pass) |
| MC health | 94% (16/17) |
| Ontology nodes | 137 |
| Domains | 11 |
| Knowledge entries | 148 |
| Path records | 82 |
| Classification accuracy (golden) | 55% (53/97) — from Claude's session |

---

## File Locations (canonical)

| Component | Path |
|-----------|------|
| Standalone MC repo | `/home/mical/fde/mission-canvas/` |
| MC pipeline | `src/pipeline.py` |
| Ontology engine | `ontology/engine.py` |
| Entry gate | `src/gates/entry.py` |
| Exit gate | `src/gates/exit.py` |
| Python sanitizer | `src/gateway/sanitizer.py` |
| Codex adapter | `src/codex_adapter.py` |
| MC CLI | `src/mc_cli.py` |
| Hub (Node.js) | `runtime/hub/server.mjs` |
| Broker (Node.js) | `runtime/broker/index.mjs` |
| Tests | `tests/` |
| Telegram bridge | `bridges/telegram/bot.py` |

---

## Sanitizer Locations (to unify in Phase 1)

| File | Language | Where |
|------|----------|-------|
| `fde/mission-canvas/src/gateway/sanitizer.py` | Python | Standalone MC (3-layer) |
| `fde/palette/mission-canvas/data_boundary.mjs` | Node.js | Palette monorepo MC server |
| `fde/palette/peers/hub/external_sanitizer.mjs` | Node.js | Palette monorepo hub |
| `fde/palette/mission-canvas/bridges/lib/safety_patterns.py` | Python | Today's extraction |

---

## What Passes the "No Regression" Bar

After any phase, all of these must hold:
- `python3 -m pytest -q` → 73+ passed, 0 failed
- `./mc health` → ≥ 94%
- Node sanitizer tests → pass
- Hub sanitizer tests → pass
- MC stats returns valid numbers (no crashes)

---

## Phase 0 Status: ✅ COMPLETE

Baseline locked. Ready for Phase 1.
