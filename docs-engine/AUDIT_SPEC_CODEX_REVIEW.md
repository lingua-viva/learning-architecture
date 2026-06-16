# Audit Specification: Codex Implementation Review
## Iterative, Artifact-by-Artifact, Full-System Impact Assessment

**Auditor**: claude.analysis
**Subject**: All Codex Phase 0/1 changes
**Method**: One change at a time → system impact → holistic assessment → improvement → deploy → reflect → diagnose

---

## Protocol

For EACH artifact/change Codex produces, run this 7-step cycle:

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: ISOLATE                                                │
│  Read the single artifact. What exactly changed?                │
│  Lines added/removed. Functions created. Imports added.         │
│  Pure observation. No judgment yet.                             │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: IMPACT MAP                                             │
│  What parts of the system does this change touch?               │
│  - Direct: files that import/call the changed code              │
│  - Indirect: surfaces that route through the changed path       │
│  - Governance: does this affect any trust boundary?             │
│  - Memory: does this change what gets stored in path records?   │
│  - Performance: does this add latency to any hot path?          │
│  - Test coverage: is this change tested? Are existing tests     │
│    affected?                                                    │
│                                                                 │
│  Output: dependency graph showing blast radius                  │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: HOLISTIC ASSESSMENT                                    │
│  Is this change holistically positive? Score on 5 axes:         │
│                                                                 │
│  1. Correctness — Does it do what it claims? Edge cases?        │
│  2. Governance — Does it strengthen or weaken the boundary?     │
│  3. Simplicity — Is this the simplest solution that works?      │
│  4. Composability — Can other surfaces/agents use this?         │
│  5. Client-readiness — Would this work for Komodo/Tropical/     │
│     Still I Rise as-is, or does it need per-client config?      │
│                                                                 │
│  Score: each axis 1-5. Minimum passing: 3/5 on all axes.       │
│  If any axis scores 1-2: flag for revision before proceeding.   │
│                                                                 │
│  Output: 5-axis score card with reasoning                       │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: IMPROVEMENT                                            │
│  How could this be better? And WHY would that be better?        │
│                                                                 │
│  For each improvement suggestion:                               │
│  - What specifically would change                               │
│  - Which axis score it improves (and by how much)               │
│  - What it costs (complexity, time, risk)                       │
│  - Whether it's Phase 0 (do now) or Phase N (later)             │
│                                                                 │
│  Rule: If the improvement is Phase 0 and costs <30 min,         │
│  it goes back to Codex before we proceed. Otherwise note it     │
│  and move on.                                                   │
│                                                                 │
│  Output: prioritized improvement list with cost/benefit         │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: MC CREATE                                              │
│  Deploy the change into the live system.                        │
│                                                                 │
│  Run: mc create "Deploy <artifact> — <one-line description>"    │
│                                                                 │
│  MC classifies the deployment, checks boundaries, logs the      │
│  path record. If MC blocks: investigate why. If MC allows:      │
│  proceed.                                                       │
│                                                                 │
│  Verification:                                                  │
│  - node --check on all changed .mjs files                       │
│  - python3 -c "import ..." on all changed .py files             │
│  - Run relevant test suite                                      │
│  - Smoke test the affected surface (curl, browser, CLI)         │
│                                                                 │
│  Output: deploy log with pass/fail for each verification        │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: MC REFLECT                                             │
│  Run: mc reflect "What changed with <artifact> deployment?"     │
│                                                                 │
│  MC reviews the path record from Step 5, compares to prior      │
│  state, identifies patterns.                                    │
│                                                                 │
│  Questions to answer:                                           │
│  - Did the governance surface area increase or decrease?        │
│  - Did the change compound (build on prior paths) or diverge?   │
│  - Are there new gap signals (unmet knowledge needs)?           │
│  - Does confidence on related RIUs improve?                     │
│  - Would the golden dataset score change? (estimate or run)     │
│                                                                 │
│  Output: reflection record appended to audit trail              │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: MC DIAGNOSE                                            │
│  Run: mc diagnose "Are there problems after <artifact>?"        │
│                                                                 │
│  MC performs root-cause analysis on the system post-change:     │
│  - Any new failures in tests?                                   │
│  - Any regression in golden dataset scores?                     │
│  - Any governance boundary that weakened?                       │
│  - Any surface that now behaves differently (intentional or     │
│    not)?                                                        │
│  - Any performance degradation?                                 │
│  - Any conflict with other pending changes?                     │
│                                                                 │
│  If problems found: create a task envelope for Codex to fix     │
│  before proceeding to next artifact.                            │
│                                                                 │
│  If clean: proceed to next artifact.                            │
│                                                                 │
│  Output: diagnosis record with PASS or ISSUES_FOUND             │
└───────────────────────────────┬─────────────────────────────────┘
                                ↓
                    [Next artifact → Step 1]
```

---

## Artifact Queue (Phase 0 + Phase 1)

Review in this order (each gets the full 7-step cycle):

### Phase 0: Governance Fix

| # | Artifact | File(s) | What It Does |
|---|----------|---------|--------------|
| 1 | Sanitizer functions | `data_boundary.mjs:129+` | `sanitizeForExternal()` + `sanitizePayloadForExternal()` |
| 2 | Server outbound wrappers | `server.mjs:207+` | `sanitizeOutboundText()` + `sanitizeOutboundPayload()` + firewall logging |
| 3 | OpenAI/Perplexity sanitization | `server.mjs:915+` | History + message sanitized before external fetch |
| 4 | OpenClaw proxy sanitization | `server.mjs:1064+` | Recursive payload sanitization before proxy |
| 5 | Tests | `test_external_sanitizer.mjs` | 4 test cases covering PII, block signals, classification, payload |
| 6 | **Voice Hub patch** (pending) | `peers/hub/server.mjs` | Same pattern applied to the Voice Hub surface |
| 7 | **Gate leak fix** (pending) | `src/pipeline.py` or `server.mjs` | entry_gate_blocked → RESEARCH must not fire |

### Phase 1: Codex Adapter

| # | Artifact | File(s) | What It Does |
|---|----------|---------|--------------|
| 8 | Task envelope schema | `docs/` or `config/` | YAML schema defining what Codex receives |
| 9 | Result envelope schema | `docs/` or `config/` | YAML schema defining what Codex returns |
| 10 | Envelope generator | TBD | MC pipeline output → task envelope file |
| 11 | Result ingester | TBD | Result envelope → MC path record |
| 12 | First governed execution | N/A | End-to-end: mc decide → envelope → Codex → result → mc reflect |

---

## Scoring Rubric

### Axis 1: Correctness
| Score | Meaning |
|-------|---------|
| 5 | Handles all edge cases, tested, no false positives/negatives |
| 4 | Handles common cases, minor edge cases untested |
| 3 | Works for the happy path, edge cases need attention |
| 2 | Partial — misses a known case |
| 1 | Broken or untested |

### Axis 2: Governance
| Score | Meaning |
|-------|---------|
| 5 | Strengthens boundary with zero bypass paths |
| 4 | Closes a gap, no new gaps introduced |
| 3 | Neutral — doesn't weaken or strengthen |
| 2 | Introduces a conditional bypass (even if intentional) |
| 1 | Weakens a boundary or creates a new bypass |

### Axis 3: Simplicity
| Score | Meaning |
|-------|---------|
| 5 | Minimal code, obvious logic, no unnecessary abstraction |
| 4 | Clean but could be slightly simpler |
| 3 | Reasonable complexity for what it does |
| 2 | Over-engineered for the current need |
| 1 | Unnecessarily complex, hard to follow |

### Axis 4: Composability
| Score | Meaning |
|-------|---------|
| 5 | Any surface/agent can use this with zero modification |
| 4 | Reusable with minor adaptation |
| 3 | Works for its specific surface, would need refactor for others |
| 2 | Tightly coupled to one context |
| 1 | Single-use, not extractable |

### Axis 5: Client-Readiness
| Score | Meaning |
|-------|---------|
| 5 | Works for all three clients (Komodo/Tropical/Still I Rise) as-is |
| 4 | Works for 2/3, needs config for the third |
| 3 | Works for the default case, needs per-client config for production |
| 2 | Only works for one client context |
| 1 | Not deployable to any client without significant changes |

---

## Cumulative Assessment

After all artifacts are reviewed, produce a summary:

### System Health Delta
```
Before Codex changes:
  PII enforcement: 50% (Python pipeline only)
  Classification accuracy: 29% RIU / 73% classification
  Governance bypass paths: 3 (Voice Hub, @mention, OpenClaw proxy)
  Test coverage: sanitizer only (12 tests)
  Client deployability: 0/3

After Codex changes:
  PII enforcement: [measure]
  Classification accuracy: [re-run golden dataset]
  Governance bypass paths: [count remaining]
  Test coverage: [count tests]
  Client deployability: [assess per client]
```

### Compound Value Assessment
- Did each artifact build on the prior one?
- Is the system more coherent after all changes, or more fragmented?
- Did the changes create new architectural debt?
- Is the governance story stronger for interviews and client pitches?

### Golden Dataset Re-Run
After all Phase 0 changes are deployed and verified:
```bash
cd /home/mical/fde/mission-canvas
python3 tests/validate_golden.py
```

Compare to baseline:
- RIU Accuracy: 29% → ?
- Classification Accuracy: 73% → ?
- Knowledge Hit Rate: 5.4% → ?
- Gateway Block: 0% → ? (this should improve with the gate leak fix)

---

## Audit Trail Format

Each artifact review produces one record appended to:
```
mission-canvas/docs/AUDIT_TRAIL_PHASE_0_1.ndjson
```

Record schema:
```json
{
  "artifact_id": 1,
  "artifact_name": "sanitizeForExternal",
  "file": "data_boundary.mjs:129",
  "timestamp": "2026-06-14T...",
  "scores": {
    "correctness": 4,
    "governance": 4,
    "simplicity": 5,
    "composability": 4,
    "client_readiness": 3
  },
  "impact_map": ["server.mjs", "hub/server.mjs (pending)"],
  "holistic_positive": true,
  "improvements_suggested": [...],
  "mc_create_result": "deployed, all checks pass",
  "mc_reflect_result": "governance surface increased, no regression",
  "mc_diagnose_result": "PASS — no problems found",
  "proceed_to_next": true
}
```

---

## Execution Triggers

**When to run this audit**:
1. After Codex reports Phase 0 complete (all 7 artifacts shipped)
2. After Codex reports Phase 1 complete (envelopes + first execution)
3. Before any client deployment (mandatory gate)
4. After any change to `data_boundary.mjs`, `server.mjs`, or `pipeline.py`

**Who runs it**: claude.analysis (me). Not Codex auditing itself.

**How long per artifact**: ~5-10 minutes (read + classify + assess + MC calls)

**Total for Phase 0 (7 artifacts)**: ~45-60 minutes

---

## The Meta-Point

This audit is itself a governed activity. It should be classifiable by MC:
- **RIU**: RIU-029 (Tool-Calling Safety Envelope) — we're auditing the safety implementation
- **Intent**: REFLECT (pattern extraction from implementation)
- **Governance**: Internal only (audit findings are privileged)
- **Path record**: Every audit cycle stores a path, compounding knowledge about what good governance implementation looks like

When we audit Codex's work using MC's own pipeline, we're proving that the system can govern its own development. That's the deepest dogfood possible — and it's the story you tell Encord, Tropical IT, and Still I Rise: "The system governs its own evolution."

---

*Spec created: 2026-06-14 by claude.analysis*
*Classification: RIU-029 | Intent: DECIDE | Confidence: 0.75*
*Path record: stored*
