# Lingua Viva System Improvement Matrix - Grouped By System & Artifact

Date: 2026-07-30

Purpose: Single authoritative matrix for Lingua Viva system improvements, grouped by system and artifact. For every open improvement concept derived from the spec corpus and July 30 handoffs, this matrix defines:
1. **System Being Improved** (RTE, EON, CUR, OBS, EDU, PRV, CON, ACT, EVA, AGV, HTH, SRF, AGT, MEM taxonomy)
2. **Artifact Being Improved** (exact module, surface, schema, or endpoint)
3. **How It Will Be Improved** (concrete technical implementation changes)
4. **Why It Should Be Prioritized** (educational efficacy, FERPA/COPPA compliance, administrative time-savings, system integrity)
5. **Work Gauge** (estimated effort: Small, Medium, High, with effort drivers)
6. **Risk of Regression** (Low, Medium, High, with mitigation strategy)

---

## Executive Summary & Priority Ranking

Based on educational impact, FERPA/COPPA 2.0 privacy compliance, and teacher workflow optimization, the recommended execution sequence for Lingua Viva is:

1. **`SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md`** (PRV Privacy / RTE Exit Gates) — *Critical Safety / Med Effort / Low Risk*
2. **`SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md`** (OBS Student Lens / Help-Artifact Generator) — *High Impact / High Effort / Low Risk*
3. **Cohort Lesson-Planning & Differentiation Workflow** (EDU Product Modules / Planning Surface) — *High Impact / High Effort / Low Risk*
4. **`SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md`** (EON Education Ontology / Defect Triage Engine) — *Med Impact / Med Effort / Low Risk*
5. **`SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`** (AGV Artifact Governance / Spec Validator) — *Med Impact / Small Effort / Low Risk*

---

## Unified System Improvement Matrix (Grouped by System)

### System RTE — Runtime Execution (`RTE-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| RTE Runtime Execution | Native Exit & Integrity Gates (`SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md`) | Replace no-op egress gates with active PII scrubbing, student record anonymization, and external routing validation before cloud LLM calls execute. | **Critical FERPA/COPPA 2.0 Requirement**: Prevents student PII from leaking to external cloud LLMs when cloud fallback is enabled. | **Medium** (~200 lines, PII scrubbing & egress validation middleware) | **Low**: Protects outbound calls; local-first query handling remains unaffected. |
| RTE Runtime Execution | Lazy Config Resolution (`src/lingua_viva/config.py`) | Sweep import-time environment constants into lazy call-time getters. | Guarantees hermetic test execution and prevents stale configuration state between source checkout and desktop bundle runtime. | **Small** (~90 lines across config helpers) | **Low**: Preserves default parameter signatures. |
| RTE Runtime Execution | True Provider-Token Streaming (`src/web.py`) | Connect LLM provider token streaming directly to SSE `/api/query/stream` endpoint rather than waiting for full turn completion. | Substantially reduces time-to-first-token audio/text latency for real-time voice and chat interfaces. | **Medium/High** (~250 lines across pipeline and web routes) | **Medium**: Requires async token queue management and SSE error handling. |

---

### System EON — Education Ontology (`EON-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| EON Education Ontology | Education Defect Source Triage (`SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md`) | Build `src/lingua_viva/defect_triage.py` to classify evaluation failures into distinct layers: Curriculum vs Checker vs Ontology vs Live Layer. | Prevents developers and automated agents from fixing the wrong layer when student evaluations or golden workflows fail. | **Medium** (~160 lines, triage classifier module) | **Low**: Read-only failure classification tool. |
| EON Education Ontology | Learned-Weight Utility Auditor (`src/lingua_viva/gap_audit.py`) | Audit learned-weight effectiveness across student domain classifications and demote unverified self-tuning weights. | Prevents false confidence from unverified automated weight adjustments in student classification. | **Small** (~80 lines, audit module) | **Low**: Read-only audit tool. |

---

### System CUR — Curriculum / Knowledge (`CUR-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| CUR Curriculum / Knowledge | Drive Metadata-Only Freshness Scanner (`src/lingua_viva/sources.py`) | Add metadata-only delta detection for Google Drive curriculum sources, reporting modified files in daily status without auto-importing content. | Gives teachers awareness of updated curriculum materials while strictly preserving explicit-import privacy bounds. | **Small/Medium** (~110 lines) | **Low**: Read-only metadata check. |
| CUR Curriculum / Knowledge | Teacher Curriculum Proposal Queue (`src/education/curriculum_proposals.py`) | Add a proposal queue where teachers can suggest curriculum edits and IB alignment adjustments under an owner-approval gate. | Enables crowdsourced curriculum refinement while preventing unauthorized edits to authoritative teaching standards. | **Medium** (~150 lines, proposal queue & review endpoint) | **Low**: Proposals remain pending until explicit approval. |

---

### System OBS — Observation / Student Lens (`OBS-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| OBS Observation / Student Lens | Teacher Decision Flywheel Completion (`SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md`) | Extend observe -> decide -> artifact loop beyond RTI confirmation to auto-generate differentiated practice materials (`HelpArtifactRecord`) and portfolio entries. | **Core Pedagogical Feedback Loop**: Turns student skill observations into instant, reviewable learning artifacts ready for teacher approval. | **High** (~300 lines across `src/web.py` and education handlers) | **Low**: Generates draft artifacts requiring teacher confirmation before publication. |
| OBS Observation / Student Lens | Gap-Driven Recommendation Queue (`src/education/recommendations.py`) | Automatically convert observed student skill gap clusters into a reviewable queue of next-step teaching actions. | Directs teacher focus to high-priority student learning needs and intervention triggers. | **Medium** (~160 lines, recommendation engine) | **Low**: Read-only queue recommendation engine. |

---

### System EDU — Education Product Modules (`EDU-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| EDU Product Modules | Cohort Lesson-Planning & Differentiation Workflow (`src/education/cohort_planning.py`) | Build a dedicated cohort planning surface that uses stored student lenses to auto-generate lesson plans with 3 differentiation tiers (Universal, Targeted, Intensive). | **Top Administrative Time-Saver**: Saves 5+ hours weekly per teacher while ensuring full IB/Reggio pedagogical differentiation across mixed-ability classes. | **High** (~320 lines, planning engine & web endpoint) | **Low**: Standalone planning workflow; does not alter single-turn query logic. |
| EDU Product Modules | Daily File Section Ownership Contracts (`src/education/daily_file.py`) | Enforce explicit section boundaries in the daily operational file to prevent mixing student PII, ops reminders, and curriculum sources. | Protects student privacy and maintains clear operational focus in the daily teacher dashboard. | **Small/Medium** (~100 lines, schema validator) | **Low**: Formatting & schema isolation contract. |

---

### System PRV — Privacy / Governance (`PRV-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| PRV Privacy / Governance | Publication Readiness & Launch Gate (`SPEC_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md`) | Audit public portfolio copy, consent policies, and evidence registers prior to public deployment. | Guarantees institutional compliance, parental consent checks, and safety before external school rollout. | **Medium** (~140 lines & audit script) | **Low**: Pre-launch audit pass. |

---

### System CON — Connectors / Sources (`CON-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| CON Connectors / Sources | Ops Records Review Dashboard UI (`static/admin.html` & `/api/ops/records`) | Build a visual dashboard UI for school ops managers to view historical Slack requests, absence coverage logs, and schedule change acknowledgements. | Replaces backend-only JSON endpoints with a usable administrative review interface for school leadership. | **Medium** (~180 lines in HTML/JS UI & API endpoints) | **Low**: Read-only dashboard surface. |
| CON Connectors / Sources | Citation-Gated AI Policy Retrieval (`src/education/policy_retrieval.py`) | Implement a retrieval-only endpoint for school handbook policies requiring exact source and section citations for every answer. | Eliminates AI hallucination for critical school safeguarding, attendance, and administrative policies. | **Medium** (~170 lines, retrieval engine with citation gate) | **Low**: Standalone policy lookup module. |

---

### System ACT — Action / Approval (`ACT-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| ACT Action / Approval | Teacher Confirmation Uniformity Auditor (`src/lingua_viva/action_audit.py`) | Audit all action surfaces to enforce the "system proposes, teacher confirms" pattern across all learning and administrative flows. | Ensures teachers retain ultimate governance and oversight over all AI-generated student communications and learning plans. | **Small/Medium** (~110 lines, audit module) | **Low**: Diagnostic audit check. |

---

### System EVA — Evaluation / Measurement (`EVA-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| EVA Evaluation / Measurement | Repeatable Live P0 Experience Sweep (`src/lingua_viva/p0_sweep.py`) | Convert manual P0 user testing steps into an automated command (`python3 -m src.lingua_viva.p0_sweep`) covering core teacher journeys. | Catches UI breakage, route reachability regressions, and contract drifts automatically on every build. | **Medium** (~190 lines, automated sweep runner) | **Low**: Test/eval instrument. |
| EVA Evaluation / Measurement | Stable Producer & Session Tags (`src/lingua_viva/gap_audit.py`) | Extend gap signal schemas with mandatory `origin`, `producer`, and `session_id` metadata. | Enables mechanical detection of evaluation harness bursts vs real user query failures. | **Small** (~70 lines, schema extension) | **Low**: Schema extension; backward-compatible. |

---

### System AGV — Artifact Governance (`AGV-SYS-001`)

| System | Artifact | How It Will Be Improved | Why It Should Be Prioritized | Work Gauge | Risk of Regression |
|---|---|---|---|---|---|
| AGV Artifact Governance | Spec Status Drift Checker (`SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`) | Build an automated status drift validator scanning `dev/*SPEC*.md` files and verifying claimed files/tests exist in `src/` and `tests/`. | Keeps documentation and `dev/INDEX.md` status tables strictly aligned with active source code. | **Small/Medium** (~130 lines, validator script) | **Low**: Read-only documentation check. |

---

## Summary Matrix Distribution

| System Code | System Name | Total Open Items | High Priority Slices | Primary Goal |
|---|---|---:|---|---|
| **RTE** | Runtime Execution | 3 | Native Exit Gates | FERPA/COPPA 2.0 Egress Protection |
| **EON** | Education Ontology | 2 | Education Defect Source Triage | Defect Attribution |
| **CUR** | Curriculum / Knowledge | 2 | Drive Freshness Scanner | Source Awareness |
| **OBS** | Observation / Student Lens | 2 | Teacher Decision Flywheel Completion | Automated Differentiated Materials |
| **EDU** | Education Product Modules | 2 | Cohort Lesson-Planning Workflow | 5+ Hr/Wk Teacher Time Savings |
| **PRV** | Privacy / Governance | 1 | Launch Gate Repass | Institutional Compliance |
| **CON** | Connectors / Sources | 2 | Ops Records Dashboard & Policy Retrieval | Administrative Visibility |
| **ACT** | Action / Approval | 1 | Teacher Confirmation Audit | Human-in-the-Loop Oversight |
| **EVA** | Evaluation / Measurement | 2 | Live P0 Experience Sweep | Automated UI/Route Regression Testing |
| **AGV** | Artifact Governance | 1 | Spec Status Drift Checker | Spec & Source Synchronization |
| **TOTAL** | **All Systems** | **18** | **5 Core Slices** | **Privacy, Efficacy & Time Savings** |
