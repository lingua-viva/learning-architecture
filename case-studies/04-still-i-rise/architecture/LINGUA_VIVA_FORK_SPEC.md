# Lingua Viva — Education Fork of Mission Canvas
## Full Specification

**Status**: `designed`
**Date**: June 19, 2026
**Method**: Generated through MC pipeline (RESEARCH → DIAGNOSE → DECIDE → CREATE → REFLECT), refined with architectural synthesis

---

## 1. What This Is

Lingua Viva is Mission Canvas for schools. Same engine, education-only surface. The general-purpose MC workbench has 174 nodes across governance, work, data, deployment, and legal domains. Lingua Viva replaces the domain layer with education-specific components while keeping the governed engine unchanged.

**Analogy**: MC is the OS. Lingua Viva is the education app that runs on it.

---

## 2. What to Keep from MC Core (Unchanged Engine)

These components are the platform. They don't change between MC and Lingua Viva.

| Component | Path | Why It's Unchanged |
|-----------|------|-------------------|
| **Pipeline** | `src/pipeline.py` | SCAN → CLASSIFY → RETRIEVE → REASON → SYNTHESIZE → STORE. Same 8-step flow. |
| **Ontology engine** | `ontology/engine.py` | Two-pass classification, signal index, learned weights. Same engine, different nodes. |
| **Governance** | `config/core.md` | Tier 1 immutable rules, Tier 2 reviewed, Tier 3 automated. Same tiers, education-specific rules. |
| **PII sanitizer** | `sanitizer/` | Student data is even MORE sensitive than professional data. Same sanitizer, stricter defaults. |
| **Path records** | `memory/` | Every decision tracked. Same schema, education-tagged. |
| **LLM proxy** | `src/llm_proxy.py` | Multi-provider routing. Same proxy. |
| **API server** | `src/api_server.py` | /api/chat, /api/config, SSE streaming. Same server. |
| **Intent agents** | `agents/` | 6 intents (PROTECT, RESEARCH, DECIDE, CREATE, DIAGNOSE, REFLECT). Same agents. |
| **CLI** | `src/mc_cli.py` | Shell, health, status, eval. Same CLI. |

**The contract**: Lingua Viva is a DOMAIN PACK, not a fork of the engine. The engine exposes stable interfaces. The domain pack implements them.

---

## 3. What to Replace (Education-Specific Domain Pack)

### 3A. Ontology — Replace Generic Nodes with Education Nodes

**Remove**: 137 legacy RIU nodes (enterprise AI, business planning, financial modeling, etc.)
**Keep**: 31 MC-native core nodes (MC-GOV, MC-WORK, MC-DATA, MC-DEPLOY, MC-LEGAL) + 6 intents
**Add**: ~40-50 education-specific nodes

#### New Education Ontology Domains

```yaml
# LV-CURRICULUM — Curriculum Architecture
LV-CUR-001: Scope Definition (IB unit planning)
LV-CUR-002: Vertical Alignment (grade-to-grade continuity)
LV-CUR-003: CEFR Language Mapping (A1→B1 targets per grade)
LV-CUR-004: Content Differentiation (3-level pack generation)
LV-CUR-005: Assessment Design (portfolio, rubric, formative)
LV-CUR-006: IB Programme of Inquiry (transdisciplinary themes)
LV-CUR-007: Lesson Plan Generation

# LV-STUDENT — Student Lens & Profiling
LV-STU-001: Student Intake Assessment (interrupted education profiling)
LV-STU-002: Learning Lens Update (observation → profile)
LV-STU-003: CEFR Progression Tracking (per-student language level)
LV-STU-004: RTI Tier Classification (Tier 1/2/3 assignment)
LV-STU-005: RTI Escalation Gate (trigger conditions)
LV-STU-006: RTI De-escalation Gate (progress monitoring)
LV-STU-007: Social-Emotional Note (conflict, grouping, wellbeing)

# LV-TEACHER — Teacher Workflow & Empowerment
LV-TCH-001: Observation Capture (speech-to-text → structured tag)
LV-TCH-002: Classroom Grouping (3-level + social-emotional constraints)
LV-TCH-003: Weekly Routine Design (conjugation practice, etc.)
LV-TCH-004: Help Artifact Generation (checklist, timer, visual scaffold)
LV-TCH-005: Institutional Memory Query (what worked before for this profile)
LV-TCH-006: Teacher Onboarding (new teacher inherits path records)

# LV-PARENT — Parent Communication (AI-opaque)
LV-PAR-001: Recommendation Generation (AI-suggested, teacher-approved)
LV-PAR-002: Progress Summary (no AI attribution, teacher voice)
LV-PAR-003: Home Support Guidance (workspace, routines, reading)

# LV-ASSESS — Assessment & Portfolio
LV-ASS-001: Portfolio Entry Creation (writing sample, oral recording, project)
LV-ASS-002: CEFR Rubric Application (can-do statements per level)
LV-ASS-003: Mastery Check (concept-level, not grade-level)
LV-ASS-004: Gap Detection (what's next, not what's missing)
LV-ASS-005: Inter-rater Calibration (teacher consistency)

# LV-INFRA — School Infrastructure
LV-INF-001: Offline Sync Status (device → cloud reconciliation)
LV-INF-002: Content Pack Versioning (integrity check on sync)
LV-INF-003: Device Fleet Management (what's available per campus)
```

### 3B. Knowledge Library — Replace with Education Evidence

**Remove**: 148 enterprise knowledge entries (AWS, cloud adoption, business strategy)
**Add**: ~80-100 education knowledge entries

Sources:
- IB PYP/MYP framework documents
- CEFR Common Reference Levels + Young Learners
- RTI/MTSS research (Vanderbilt IRIS, WIDA)
- Trauma-informed pedagogy research
- Lingua Viva curriculum manual (Claudia's K-5 Italian framework)
- La Scuola structural coherence framework
- Alpha School adaptive learning architecture
- Still I Rise context research

### 3C. Lenses — Education-Specific Interpretive Filters

**Keep**: Core lens types (architect, critique, precision, protection)
**Add**:

```yaml
# Teacher lenses
- learning-architect        # already exists in MC
- curriculum-designer       # IB unit planning lens
- assessment-specialist     # portfolio + CEFR rubric lens
- differentiation-coach     # 3-level content adaptation lens
- rti-monitor              # intervention monitoring lens

# Student-context lenses
- trauma-informed          # safe assessment, low-stakes framing
- multilingual-learner     # CEFR-aware, L1-sensitive
- interrupted-education    # gap-detection, mastery-based

# Institutional lenses
- ib-coordinator           # vertical alignment, programme coherence
- school-leader            # campus-level dashboard, trend detection
```

### 3D. Static UI — Education-Branded Web Interface

**Replace**: MC generic web UI
**With**: Education-branded interface

- Intent chips relabeled: PLAN (lesson planning), OBSERVE (capture), ASSESS (portfolio), DIFFERENTIATE (3-level content), SUPPORT (RTI scaffolds), REFLECT (teacher self-audit)
- Student selector dropdown (per-class roster)
- Observation capture button (speech-to-text)
- Content pack viewer (3-tier tabs: foundational / on-track / extended)
- No "Mission Canvas" branding — "Lingua Viva" branding

---

## 4. New Components to Build

### 4A. Student Lens Engine
- Reads student profile (CEFR level, RTI tier, learning differences, L1, social-emotional notes)
- Generates differentiated artifacts per student
- Updates on every observation capture
- Feeds RTI escalation logic

### 4B. Content Differentiation Pipeline
- Input: teacher lesson topic + class roster with lenses
- Process: cluster students into 3 levels → generate adapted content per level
- Output: 3-level content pack (foundational, on-track, extended)
- Caching: pre-generate at night when connectivity exists, serve from cache always
- Offline: local model (Ollama) as fallback, cloud (Claude) when available

### 4C. RTI 3-Tier Gate System
- Tier assignment based on observation accumulation
- Escalation triggers (configurable thresholds per school)
- De-escalation monitoring (progress over N weeks)
- Teacher notification on tier change (not automated — teacher confirms)
- One-way door flag on threshold values

### 4D. Observation Capture
- Speech-to-text input (Web Speech API or Whisper)
- Structured tagging: student, session, tier, CEFR observation, social-emotional
- <30 seconds per observation
- Offline storage → sync when connected
- Feeds student lens and RTI logic

### 4E. Parent Artifact Generator
- AI generates recommendation drafts
- Teacher reviews and edits
- AI attribution stripped before delivery
- Output formats: PDF, SMS, portal message
- Governance rule: PROTECT intent always — parent artifacts never route to cloud

---

## 5. File Structure

```
lingua-viva/learning-architecture/
├── README.md                          # Lingua Viva — education-specific MC
├── MANIFEST.yaml                      # Version, node counts, knowledge counts
├── CLAUDE.md                          # Project instructions (education-specific)
│
├── case-studies/                      # Claudia's portfolio (unchanged)
│   ├── 01-structural-coherence/
│   ├── 02-ai-classroom/
│   ├── 03-lingua-viva/
│   └── 04-still-i-rise/              # NEW — full architecture
│
├── ontology/
│   ├── engine.py                      # MC core (unchanged)
│   ├── core/                          # MC-native nodes (keep MC-GOV, MC-WORK, etc.)
│   │   ├── intents.yaml
│   │   ├── governance.yaml
│   │   └── work.yaml
│   └── education/                     # NEW — education domain nodes
│       ├── curriculum.yaml            # LV-CUR-001 through LV-CUR-007
│       ├── student.yaml              # LV-STU-001 through LV-STU-007
│       ├── teacher.yaml              # LV-TCH-001 through LV-TCH-006
│       ├── parent.yaml               # LV-PAR-001 through LV-PAR-003
│       ├── assessment.yaml           # LV-ASS-001 through LV-ASS-005
│       └── infrastructure.yaml       # LV-INF-001 through LV-INF-003
│
├── knowledge/                         # Education evidence library
│   ├── curriculum/                    # IB, CEFR, Indicazioni sources
│   ├── assessment/                    # Portfolio, rubric, RTI research
│   ├── multilingual/                  # L2 acquisition, code-switching
│   ├── trauma-informed/              # Safe assessment, PSS integration
│   └── lingua-viva-manual/           # Claudia's K-5 Italian curriculum
│
├── lenses/
│   ├── core/                          # MC core lenses (architect, critique, etc.)
│   └── education/                     # NEW — education lenses
│       ├── learning-architect.yaml
│       ├── curriculum-designer.yaml
│       ├── assessment-specialist.yaml
│       ├── differentiation-coach.yaml
│       ├── rti-monitor.yaml
│       ├── trauma-informed.yaml
│       ├── multilingual-learner.yaml
│       ├── ib-coordinator.yaml
│       └── school-leader.yaml
│
├── src/                               # MC engine (synced from mission-canvas)
│   ├── pipeline.py
│   ├── api_server.py
│   ├── llm_proxy.py
│   ├── mc_cli.py
│   ├── context_builder.py
│   └── education/                     # NEW — education-specific modules
│       ├── student_lens.py            # Per-student profile engine
│       ├── content_differentiator.py  # 3-level pack generator
│       ├── rti_gates.py              # Tier escalation/de-escalation
│       ├── observation_capture.py     # STT → structured tag
│       └── parent_artifacts.py        # AI-opaque recommendation generator
│
├── static/                            # Education-branded web UI
│   └── index.html                     # Lingua Viva interface
│
├── config/
│   ├── core.md                        # Governance (education-adapted)
│   └── providers.json                 # Model routing (same as MC)
│
├── sanitizer/                         # MC PII sanitizer (education defaults)
├── memory/                            # Path records (education-tagged)
├── agents/                            # 6 intent agents (same as MC)
├── methods/                           # Claudia's education methods
├── resume-cv/                         # Claudia's CV
├── tests/                             # MC tests + education tests
└── publication-policy.md              # Privacy rules
```

---

## 6. Migration Path

### Phase 1: Sync Engine (Week 1)
1. Update the bundled MC from v1.0.0 to current (v1.2.0)
2. Copy `src/pipeline.py`, `src/llm_proxy.py`, `src/api_server.py`, `ontology/engine.py` from mission-canvas
3. Verify 136 tests pass in the new repo
4. Keep existing case studies and methods untouched

### Phase 2: Education Ontology (Week 2-3)
1. Remove 137 legacy RIU nodes
2. Keep 31 MC-native core nodes + 6 intents
3. Add `ontology/education/` with LV-* nodes (start with 10-15 highest-priority)
4. Build education knowledge library (start with 20-30 entries from existing research)
5. Add education lenses (start with learning-architect, differentiation-coach, rti-monitor)

### Phase 3: Education Modules (Week 3-5)
1. Build `src/education/student_lens.py`
2. Build `src/education/content_differentiator.py`
3. Build `src/education/rti_gates.py`
4. Build `src/education/observation_capture.py`
5. Build `src/education/parent_artifacts.py`

### Phase 4: Education UI (Week 5-6)
1. Replace generic MC web UI with education-branded Lingua Viva interface
2. Education-specific intent chips
3. Student selector, observation capture button, content pack viewer

### Phase 5: Still I Rise Pilot (Week 7+)
1. Add Still I Rise-specific knowledge entries
2. Configure for Nairobi campus
3. Deploy offline-first with Ollama on local hardware
4. Train 2-3 teachers
5. Measure: teacher time saved, observation capture rate, content quality

---

## 7. The Separation Contract

MC and Lingua Viva stay connected through a clear interface:

```
MC Platform (stable API):
├── Pipeline.run(query, intent) → PipelineResult
├── OntologyEngine.classify(query) → Classification
├── LLMProxy.stream_chat(system, user, provider) → SSE
├── Sanitizer.sanitize(text) → SanitizedText
└── MemoryStore.store_path(record) → PathID

Lingua Viva Domain Pack (implements):
├── ontology/education/*.yaml → nodes loaded by OntologyEngine
├── knowledge/education/ → entries loaded by knowledge library
├── lenses/education/ → filters loaded by lens engine
├── src/education/ → modules called by pipeline hooks
└── static/index.html → UI served by api_server
```

When MC core updates (new pipeline features, new governance rules, new LLM proxy providers), Lingua Viva inherits them by syncing the engine files. The education domain pack is never touched by MC updates.

---

## 8. Success Criteria

1. A teacher at Still I Rise can open Lingua Viva, describe a lesson, and receive a 3-level content pack without added burden
2. Observations captured in <30 seconds, feeding student lenses and RTI logic
3. System works offline at Nairobi campus
4. Parents receive recommendations with zero AI attribution
5. 136+ tests passing (MC core + education-specific)
6. Path records accumulate — institutional memory survives teacher turnover

---

*Generated through Mission Canvas pipeline: RESEARCH → DIAGNOSE → DECIDE → CREATE → REFLECT. Each step classified through MC's 174-node ontology, reasoned through Claude Sonnet 4.6.*
