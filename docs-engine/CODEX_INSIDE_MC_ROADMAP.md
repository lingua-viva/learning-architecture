# Codex as Governed Mission Canvas Implementation Agent — Roadmap

## MC Classification
- **RIU**: RIU-029 (Tool-Calling Safety Envelope)
- **Intent**: DECIDE
- **Governance**: blocks_external: true, requires_local: true
- **Confidence**: 0.60 → 0.70 (knowledge-boosted)
- **Knowledge Retrieved**: LIB-138 (safety envelope), LIB-160 (threat model), LIB-161 (AuthN/AuthZ), LIB-172 (multi-agent workflows)
- **Co-occurring RIUs**: RIU-510 (multi-agent workflow), RIU-513 (inter-agent comms), RIU-514 (boundary enforcement), RIU-530 (risk classification), RIU-705 (regulatory compliance)

## Dogfood Bug (First Finding)
MC misclassified the initial scoping prompt as **RIU-502 Audio Processing Integration**, then logged `entry_gate_blocked:privileged` but still attempted external research. Two bugs:
1. **Classification miss**: "agent design" signals not strong enough in RIU-502's absence → should route to RIU-029
2. **Gate leak**: entry gate blocked the query BUT the RESEARCH step still fired. The pipeline should short-circuit after block.

Both are acceptance criteria for Phase 1.

---

## Architecture

```
User (Mical / client team)
    ↓
Mission Canvas surface (CLI / Browser / PWA)
    ↓
Entry gate + PII/PHI sanitizer (MUST fire on ALL surfaces)
    ↓
Classification → RIU routing → policy lookup
    ↓
Intent routing → DECIDE / CREATE / RESEARCH / PROTECT / DIAGNOSE / REFLECT
    ↓
Agent selection (architect / builder / orchestrator / validator)
    ↓
┌─────────────────────────────────────────┐
│  Codex Execution Adapter                │
│  ─────────────────────────────────      │
│  Receives: classified task envelope     │
│  Contains: objective, constraints,      │
│            allowed files, boundary,     │
│            policy (internal/external)   │
│  Executes: repo edits, tests, inspect   │
│  Returns: structured result envelope    │
└─────────────────────────────────────────┘
    ↓
MC STORE: path record, decision, artifacts, reflection, gap signals
```

---

## Three Customer Deployments (Why This Matters)

| Customer | Boundary Type | Codex Use Case | Critical Gate |
|----------|---------------|----------------|---------------|
| **Komodo/Mavens** | PHI (HIPAA) | Build AI enablement workflows, generate training content, prototype tools | No patient data reaches Codex. Sanitizer strips PHI before task envelope. |
| **Tropical IT** | Commercial (trade secrets, pricing) | Build CRM logic, order routing, customs classification code | No client pricing/orders reach Codex. Task is architectural, not data-bearing. |
| **Still I Rise** | Child data (COPPA/GDPR-K) | Build adaptive learning modules, configure curriculum AI, test tutoring flows | No student names, scores, or identifiers reach Codex. Ever. |

The Codex adapter MUST enforce: **only the task description and code context reach Codex. Never the data.**

---

## Phases

### Phase 0: Governance Fix (BLOCKER — do first)
**Status**: Critical gap identified
**Owner**: Claude Code (this session) or Codex (first pass)

**Problem**: Voice Hub (`server.mjs`) bypasses all PII/PHI protection. Raw queries go to Perplexity/Claude unsanitized.

**Acceptance Criteria**:
- [ ] Every external model call in `server.mjs` passes through sanitizer logic BEFORE fetch
- [ ] @mention direct routing still fires sanitizer (skips classification, keeps sanitization)
- [ ] Test: POST query with known PII patterns → verify external call has PII stripped
- [ ] Test: entry_gate_blocked → RESEARCH step does NOT fire (fix the gate leak bug)
- [ ] Sanitizer works in Node.js (port from Python or call as subprocess)

**Implementation options**:
1. **Quick**: Call Python sanitizer as subprocess from Node.js before each external fetch
2. **Clean**: Port the 3-layer sanitizer (regex + NER + ontology blocks) to JavaScript
3. **Hybrid**: Express middleware that calls Python sanitizer via HTTP (localhost:PORT/sanitize)

**Recommendation**: Option 3 (hybrid). Start the Python sanitizer as a tiny Flask/FastAPI service on localhost. Node.js calls it before every external model call. Clean separation, no code duplication, testable independently.

---

### Phase 1: Codex Execution Adapter (Smallest Useful Loop)
**Status**: Design
**Owner**: Codex (first pass)

**The loop**:
```
mc decide/create "<task description>"
    → MC classifies, sanitizes, retrieves knowledge
    → MC produces a TASK ENVELOPE (structured YAML/JSON)
    → Codex receives envelope
    → Codex executes repo work (edits, tests, inspections)
    → Codex writes RESULT ENVELOPE
    → mc reflect stores what happened as path record
```

**Task Envelope Schema**:
```yaml
task_id: "TASK-2026-06-14-001"
source_query: "<original user ask, sanitized>"
classification:
  riu: "RIU-029"
  domain: "ai-enablement"
  intent: "CREATE"
  confidence: 0.70
policy:
  external_allowed: false
  models_allowed: ["codex"]
  data_boundary: "no-phi, no-child-data, no-pricing"
  one_way_door: false
objective: "Implement sanitizer middleware for Voice Hub server.mjs"
constraints:
  - "Must not break existing /api/chat endpoint"
  - "Must sanitize before every external fetch call"
  - "Must log sanitization events to firewall_log.ndjson"
context:
  files_to_read: ["peers/hub/server.mjs", "src/gateway/sanitizer.py"]
  knowledge_entries: ["LIB-138", "LIB-160"]
  prior_paths: ["path-2026-06-14-governance-audit"]
```

**Result Envelope Schema**:
```yaml
task_id: "TASK-2026-06-14-001"
status: "completed" | "blocked" | "partial"
patches:
  - file: "peers/hub/server.mjs"
    diff_summary: "Added sanitize() call before Perplexity fetch at line 534"
    lines_changed: 23
commands_run:
  - "node --check peers/hub/server.mjs"  # syntax check
  - "curl -X POST localhost:7890/api/chat -d '{\"text\":\"SSN 123-45-6789\"}'"  # PII test
test_results:
  passed: 3
  failed: 0
  skipped: 1
decision: "Implemented as Express middleware calling Python sanitizer via subprocess"
reflection:
  confidence: 0.85
  gaps_found: ["No test for email PII pattern in Japanese"]
  suggestions: ["Add i18n PII patterns for LATAM deployment"]
```

**Acceptance Criteria**:
- [ ] Task envelope generated from MC pipeline output
- [ ] Codex receives envelope and produces working code
- [ ] Result envelope written back to MC memory as path record
- [ ] Path record queryable: "what did Codex do on governance tasks?"
- [ ] mc reflect shows the execution history

---

### Phase 2: MC Classification Improvements
**Status**: Identified gaps
**Owner**: Kiro (ontology specialist)

The dogfood run exposed classification gaps. These RIU signals need strengthening:

| Missing Coverage | Proposed RIU | Signals Needed |
|-----------------|--------------|----------------|
| Implementation planning | RIU-029 (extend signals) | "implementation", "adapter", "execution-agent" |
| Agent orchestration | RIU-510 (exists, needs signals) | "codex-adapter", "governed-execution", "agent-as-surface" |
| Repo architecture | NEW or extend RIU-510 | "repo-structure", "standalone-deploy", "codebase-separation" |
| Product deployment | NEW: RIU-540? | "deploy", "vps", "instance", "customer-deploy" |
| Governance architecture | RIU-029 (extend) | "sanitizer", "pii-gate", "boundary-enforcement" |

**Acceptance Criteria**:
- [ ] "Design a governed execution adapter" classifies to RIU-029, not RIU-502
- [ ] "Deploy mission canvas for a new customer" classifies to deployment RIU
- [ ] Golden dataset extended with 10 governance/deployment test cases
- [ ] Baseline re-run shows improvement

---

### Phase 3: Execution Audit Trail
**Status**: Design
**Owner**: Claude Code

Every Codex task stores a full audit record:

```
memory/data/codex_executions.ndjson (append-only)
```

Fields per record:
- `task_id` — unique identifier
- `timestamp` — ISO 8601
- `original_ask` — user's raw query (sanitized)
- `mc_classification` — RIU, domain, intent, confidence
- `external_routing_allowed` — boolean
- `policy_applied` — which boundary rules fired
- `plan` — Codex's stated approach before execution
- `patches` — files changed with diff summaries
- `commands_run` — verification commands and results
- `test_results` — pass/fail/skip counts
- `outcome` — completed/blocked/partial
- `reflection` — confidence, gaps, suggestions
- `duration_ms` — how long Codex took

**Queryable via**: `mc reflect "what has codex done this week?"`

**Acceptance Criteria**:
- [ ] Every Codex execution produces exactly one NDJSON record
- [ ] Records are queryable by RIU, date, outcome
- [ ] Failed executions include diagnosis (why it failed)
- [ ] Reflection agent can identify patterns across executions

---

### Phase 4: Standalone Mission Canvas Repo
**Status**: Approved (TWO-WAY DOOR)
**Owner**: Kiro (scaffolding) + Claude Code (migration)

```
mission-canvas/              (new standalone repo: github.com/pretendhome/mission-canvas)
├── site/                    # Landing page (missioncanvas.ai via GitHub Pages)
├── hub/                     # Voice Hub server + @mention routing + sanitizer
├── server/                  # MC server (pipeline, agents, memory, ontology)
├── resolver/                # Python classifier service
├── bridges/                 # Telegram bots (joseph, rossi)
├── deploy/                  # systemd units, nginx confs, install.sh
│   ├── systemd/
│   ├── nginx/
│   └── install.sh
├── tests/                   # E2E tests including PII enforcement
│   ├── test_sanitizer.py
│   ├── test_e2e_pii.sh
│   └── golden_dataset_v1.yaml
├── .env.example
├── package.json
├── pyproject.toml
└── README.md
```

**What stays in palette**: Taxonomy, Knowledge Library, agents (design specs), SDK, governance wiki, skills, peers broker.

**Interface between them**: Peers bus (port 7899). MC calls broker for agent coordination. Palette agents are consumers on the bus.

**Acceptance Criteria**:
- [ ] Standalone repo runs independently (no palette dependency for core function)
- [ ] VPS can `git pull` and restart (deploy key configured)
- [ ] GitHub Pages serves missioncanvas.ai from repo root or /site
- [ ] `install.sh` stands up a fresh instance in <60 seconds
- [ ] All existing functionality preserved (regression test)

---

### Phase 5: Client Instance Model
**Status**: Design
**Owner**: Claude Code (architecture) + Codex (implementation)

Each customer deployment is a configured MC instance:

```
mission-canvas-instance/
├── config/
│   ├── ontology.yaml        # Client-specific classification nodes
│   ├── knowledge.yaml       # Client-specific knowledge entries
│   ├── boundaries.yaml      # Data boundary rules (PHI/COPPA/trade-secret)
│   ├── agents.yaml          # Which agents are active, their constraints
│   └── surfaces.yaml        # Which surfaces are enabled (CLI/browser/PWA/voice)
├── memory/                   # Client's path records (never shared)
├── .env                      # Client's API keys, model preferences
└── docker-compose.yaml       # Or: systemd units for non-Docker deploys
```

**Per-customer configuration**:

| Config | Komodo/Mavens | Tropical IT | Still I Rise |
|--------|---------------|-------------|--------------|
| Ontology | Medical affairs, publications, grants, enablement | Sales, procurement, inventory, logistics, customs, finance | Curriculum, assessment, student progress, teacher tools |
| Boundaries | PHI blocked, HIPAA audit, named-entity redaction | Trade secrets, pricing, customer data redaction | COPPA, child names/scores/identifiers blocked |
| Models allowed | Claude, Mistral (no data to either) | Claude only (self-hosted preferred) | Claude (free tier or sponsored key) |
| Surfaces | Browser primary, PWA secondary | Browser + PWA (mobile critical) | PWA mobile-first, offline-capable |
| Agents | Enablement, Quality, Research | Quote, Logistics, Customs, Inventory, Finance, Customer | Tutor, Curriculum, Assessment, Teacher |

**Acceptance Criteria**:
- [ ] New instance deployable from config files in <10 minutes
- [ ] Zero data leakage between instances (verified by test)
- [ ] Ontology is swappable without code changes
- [ ] Boundary rules are configurable per instance
- [ ] Each instance has its own memory store (path records don't cross)

---

## Priority Order

```
Phase 0 (Governance Fix)     ← BLOCKER, do now
    ↓
Phase 1 (Codex Adapter)      ← smallest useful loop
    ↓
Phase 2 (Classification)     ← fix the dogfood bugs
    ↓
Phase 3 (Audit Trail)        ← compound value
    ↓
Phase 4 (Standalone Repo)    ← deploy infrastructure
    ↓
Phase 5 (Client Instances)   ← customer delivery
```

Phase 0 and Phase 1 can start in parallel (different owners). Phase 4 can start anytime (independent). Phase 5 requires Phase 4.

---

## First Implementation Slice (for Codex)

**Do not start with the full adapter.** Start with the smallest useful loop:

```
1. mc decide "<task>"
2. Pipeline outputs classification + knowledge + policy
3. Save as task_envelope.yaml in /tmp or memory/
4. Codex reads envelope, executes the bounded task
5. Codex writes result_envelope.yaml
6. mc reflect reads result and stores path record
```

**Concrete first task for Codex**:
> "Read task_envelope.yaml. It says: implement a sanitizer middleware for the Voice Hub server.mjs that calls the Python sanitizer before every external model call. The boundary rule is: no PII/PHI reaches any external API. Write the code, run syntax check, report back in result_envelope.yaml format."

This is Phase 0 AND Phase 1 combined — Codex fixes the governance gap AS its first governed task. Dogfooding the dogfood.

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| PII enforcement coverage (surfaces) | 50% (Python only) | 100% (all surfaces) |
| Classification accuracy on governance queries | Misclassified (RIU-502) | Correct (RIU-029) |
| Codex tasks with full audit trail | 0 | 100% |
| Time to deploy new client instance | N/A (manual) | <10 minutes |
| Customer data leakage between instances | Untested | 0 (verified) |

---

## Decision Record

| Decision | Rationale | Reversibility |
|----------|-----------|---------------|
| Sanitizer as localhost HTTP service (not JS port) | Clean separation, testable independently, no code duplication | TWO-WAY DOOR |
| Standalone repo (not monorepo subfolder) | Independent deploy, VPS can pull, clean GitHub Pages | TWO-WAY DOOR |
| Task envelope as YAML (not JSON) | Human-readable, matches MC conventions, diffable | TWO-WAY DOOR |
| Phase 0 before Phase 1 | Can't govern Codex's execution if governance itself has gaps | ONE-WAY DOOR (sequence) |
| PWA over native app | No App Store, same codebase, installs from browser | TWO-WAY DOOR |

---

*Classified: RIU-029 (Tool-Calling Safety Envelope) | Intent: DECIDE | Confidence: 0.70*
*Path record: stored in memory/data/paths.ndjson*
*Generated: 2026-06-14 by claude.analysis via MC pipeline*
