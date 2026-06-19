# Still I Rise — System Architecture

**Status**: `designed` — all artifacts generated through Mission Canvas governed pipeline
**Generated**: June 18-19, 2026
**Method**: Each component designed via a separate MC intent (RESEARCH → DIAGNOSE → DECIDE → CREATE → REFLECT), with Claude Sonnet 4.6 reasoning through MC's ontology, knowledge library, and governance framework.

---

## Architecture Overview

An offline-first AI education system for refugee and vulnerable children across 4 countries (Kenya, Colombia, India, Italy). IB curriculum. Multilingual classrooms. Zero additional teacher burden.

### Build Sequence (fixed by dependency, not preference)

```
1. Offline-First Data Layer        → everything else depends on storage
2. Classroom-as-Unit Data Model    → depends on storage existing  
3. RTI 3-Tier Intervention Gates   → depends on classroom model
4. Differentiated Content Engine   → depends on student lenses + RTI tiers
5. Observation Capture (STT)       → depends on data model to tag into
6. Parent Recommendation Artifacts → depends on all upstream data
```

### Design Principles

1. **Offline-first** — generate at night when connectivity exists, serve from cache always
2. **Zero-sum complexity** — every feature replaces an existing task or is hands-free
3. **Trauma-informed** — low-stakes framing, opt-out prompts, no re-traumatizing content
4. **Teacher-owned** — knowledge compounds in their system, not ours
5. **Open source** — they own the deployment, no vendor dependency

---

## Architecture Documents

| Document | MC Intent | What It Contains |
|----------|-----------|-----------------|
| [data-model.md](data-model.md) | CREATE | Entity schema (11 tables), pipeline spec, data flow diagram, sync architecture |
| [rti-tiers.md](rti-tiers.md) | CREATE | RTI 3-tier system: trigger conditions, escalation logic, progress monitoring, CEFR integration |
| [content-differentiation.md](content-differentiation.md) | CREATE | 3-level content pack engine: foundational/on-track/extended, offline caching, adaptation pipeline |
| [observation-capture.md](observation-capture.md) | CREATE | Speech-to-text observation, structured tagging, parent recommendation artifacts with AI opacity |
| [integration-risks.md](integration-risks.md) | REFLECT | 5 integration risks at component seams, 8 untested assumptions, pilot failure scenarios |

---

## Key Architectural Decisions

| Decision | Classification | Rationale |
|----------|---------------|-----------|
| SQLite local + PostgreSQL cloud | ONE-WAY DOOR | Offline-first is the load-bearing wall; changing post-deployment means schema migration under live data |
| RTI escalation thresholds | ONE-WAY DOOR | Threshold values become irreversible once a child is moved between tiers based on them |
| Classroom-as-unit (not student-centric) | TWO-WAY DOOR | Data modeling choice; can be refactored without affecting live interventions |
| Speech-to-text for observation | TWO-WAY DOOR | Input method is pluggable; fallback to structured forms if STT fails in noisy environments |
| Parent artifacts with AI opacity | TWO-WAY DOOR | Output formatting choice; AI attribution can be toggled without architectural change |

---

## Critical Risks Identified

1. **STT in noisy refugee classrooms** — highest single-component risk. Must be tested in physical environment before pilot launch.
2. **Offline sync + RTI gates** — stale data can trigger tier transitions on ghost data. Timestamp-aware gate logic needed.
3. **Content pack version drift** — partial sync produces worse state than no sync. Pack integrity check needed.
4. **RTI fidelity** — system can surface a gate; cannot ensure teacher acts on it. Fidelity monitoring required.
5. **Parent engagement** — artifacts assume minimum literacy and device access that may not exist in refugee context.

---

## MC Pipeline Trace

All architecture was produced through MC's governed pipeline:

```
STEP 1: RESEARCH  → "What AI education systems exist in refugee contexts?"
         → Found: aprendIA (IRC), messaging-first architecture, gap in IB+refugee AI
         
STEP 2: DIAGNOSE  → "What gaps exist between MC and Still I Rise needs?"
         → Found: classroom-as-unit vs student-centric, RTI as decision gates, offline-first

STEP 3: DECIDE    → "Which components are one-way doors?"
         → Classified: offline architecture + RTI thresholds = irreversible

STEP 4: CREATE    → Data model, RTI system, content engine, observation capture
         → 4 architecture documents produced

STEP 5: REFLECT   → "What integration risks exist?"
         → 5 seam risks, 8 untested assumptions, pilot failure scenarios
```

Each step classified through MC's 174-node ontology, retrieved from 148 knowledge entries, reasoned through Claude Sonnet 4.6, and stored as a path record.
