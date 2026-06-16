# Mission Canvas — Tier 3 Working Decisions

Append-only. Never delete. Auto-update allowed for Tier 3 entries.

---

## 2026-06-04: Initial Architecture Decisions

- **Memory architecture**: Redis (hot) + NDJSON (cold). No vector database.
  Rationale: Price of Meaning paper proves semantic memory suffers interference.
  BM25 over path records = zero forgetting, zero false recall.

- **8-step pipeline is obligatory**: SCAN → CLASSIFY → RETRIEVE → RESEARCH → CONTEXT → REASON → SYNTHESIZE → STORE.
  No shortcuts. The pipeline IS the OS.

- **Convergence is the only KPI**: Path consistency, confidence improvement,
  external call reduction, decision reuse.

- **Skills are morphable**: Skill-builder creates skills from user description.
  Not a static library. The system designs its own capabilities.

- **Community governance is tiered**: Tier 3 auto-merge after 3 independent
  contributors. Tier 2 maintainer review. Tier 1 core team vote.
