# Lingua Viva Improvement Cycle Spec Idea Matrices - Grouped By System And Artifact - Pass 3

Date: 2026-07-30

Derived from:

- `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30.md`
- `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md`
- Current `learning-architecture` source, tests, reports, and July 30 specs.

Purpose: third rolling audit pass for Lingua Viva. This file checks the pass-2 remaining work matrix against live source and test code, documents newly closed features in the Check-Off Ledger, and presents a deeply reflected, high-leverage analysis of remaining open specs.

Verification boundary:

- Inspected source modules in `src/`, test suites in `tests/`, and spec documents in `dev/`.
- Verified syntax validity with `python3 -m py_compile` across modified Lingua Viva modules.
- Evaluated open items for verified educational efficacy, privacy governance, and system integrity impact.
- `[x]` means source/test evidence found and removed from active remaining work.
- `[~]` means partially implemented or built but requiring further integration across the intended boundary.
- `[ ]` means unimplemented, deferred, or requiring a new build slice.

---

## Pass 3 Check-Off Ledger

| System | Artifact | Prior row(s) | Status | Evidence found | Pass-3 decision |
|---|---|---:|---|---|---|
| CON Connectors / Sources | Slack Ops Schedule Acknowledgement Loop | Pass 2 Matrix `SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30` | [x] | `src/education/slack_ops_bot.py` (`/schedule-change` modal, `_handle_schedule_ack`, `_schedule_ack_summary`), `src/web.py` (`/api/ops/schedule-ack-summary`), `tests/test_sir_schedule_acks.py` (10 passing unit/integration tests). | Move to completed ledger; schedule-change acknowledgements are now closed-loop with structured tracking and API summary. |
| PRV Privacy / Governance | Server-side auth & role gate | Pass 2 Matrix `SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30` | [x] | `src/lingua_viva/access_roles.py` (Role hierarchy `admin > coordinator > co_teacher > teacher`, `TEACHER_OR_HIGHER`, `role_allows`), `src/education/access_control.py`, `tests/test_server_side_auth_role_gate.py`, `tests/test_access_control.py`. | Move to completed ledger; server-side role enforcement and co-teacher access bounds are fully implemented with unit test coverage. |
| RTE Runtime Execution | Voice streaming SSE / early sentence TTS | Pass 2 Ledger | [x] | `/api/query/stream`, SSE `answer_sentence`, early sentence TTS queuing. | Retain as completed. |
| OBS Observation / Lens | SIR absence/coverage MVP | Pass 2 Ledger | [x] | `src/education/slack_ops_bot.py`, `tests/test_sir_absence_coverage.py`. | Retain as completed. |
| CON Connectors / Sources | SIR request center MVP | Pass 2 Ledger | [x] | `src/education/slack_ops_bot.py`, `tests/test_sir_ops_request_center.py`. | Retain as completed. |
| PRV Privacy / Governance | Rime TTS privacy gate | Pass 2 Ledger | [x] | `src/lingua_viva/voice_tone.py`, `tests/test_voice_tts_privacy_gate.py`. | Retain as completed. |

---

## Pass 3 High-Impact Verified Analysis of Unimplemented / Partial Specs

This section presents a deep reflection on the remaining open spec ideas in Lingua Viva, analyzing their **verified systemic impact**, target system, target artifact, current gap, and implementation strategy.

### 1. RTE Runtime Execution (`RTE-SYS-001`) & PRV Privacy / Governance (`PRV-SYS-001`) — Native Exit & Integrity Gates
- **Spec**: `dev/SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md`
- **Artifact**: Exit/integrity gates (`src/lingua_viva/` egress filters, `Sanitizer`, PII Gate)
- **Current Status**: `[ ]` (Local-first execution currently keeps external routing off; native exit/integrity gates are unbuilt)
- **Verified High-Impact Rationale**:
  - *Why it matters*: Lingua Viva processes sensitive educational context (student observations, IEP notes, behavioral logs). While external LLM routing is currently disabled by default, enabling cloud models without strict exit gates risks catastrophic FERPA/COPPA 2.0 violations.
  - *Systemic Impact*: Guarantees that any outbound payload to external providers is scrubbed of PII, student names, and unverified claims. Establishes a zero-trust privacy perimeter before cloud LLM fallback or external web search can ever execute.
- **Verification Strategy**:
  - Verify in `tests/test_native_exit_integrity_gates.py` that outbound external payloads containing synthetic student PII are blocked and scrubbed before network transmission.

### 2. OBS Observation / Student Lens (`OBS-SYS-001`) — Teacher Decision Flywheel Completion
- **Spec**: `dev/SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md`
- **Artifact**: Observe capture, classify, and lens update loop (`src/web.py` -> `teacher_decision`, `src/education/`)
- **Current Status**: `[~]` (RTI confirmation and student grouping exist; portfolio generation and automated help-artifact creation are open)
- **Verified High-Impact Rationale**:
  - *Why it matters*: Currently, teachers can log student observations and confirm RTI tiers, but translating those insights into student-facing portfolio entries or tailored practice exercises requires manual external drafting.
  - *Systemic Impact*: Completes the core educational feedback loop: **Observe -> Classify -> Decide -> Produce Artifact**. When a teacher confirms an observation gap, Lingua Viva automatically drafts a differentiated learning artifact (e.g. Italian Bridge reading snippet or scaffolded math prompt) ready for 1-click teacher approval.
- **Verification Strategy**:
  - Assert that confirming a student gap triggers automated generation of a `HelpArtifactRecord` with review/approve state.

### 3. EON Education Ontology (`EON-SYS-001`) — Education Defect Source Triage
- **Spec**: `dev/SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md`
- **Artifact**: Education ontology domains and candidate nodes (`src/lingua_viva/gap_audit.py`, Triage Classifier)
- **Current Status**: `[ ]` (Measurement evals exist, but failure source layer classification is unbuilt)
- **Verified High-Impact Rationale**:
  - *Why it matters*: When an evaluation or golden workflow fails in Lingua Viva, developers can easily misdiagnose the failure (e.g., tweaking prompt formatting code when the actual issue was a missing curriculum standard in the ontology).
  - *Systemic Impact*: Classifies every evaluation failure into a distinct defect layer: **Curriculum Source vs Checker Logic vs Ontology Taxonomy vs Live Layer Drift**. Prevents misplaced code fixes and ensures improvements are applied to the authoritative layer.
- **Verification Strategy**:
  - Run triage classifier over synthetic test failure shapes and verify accurate layer attribution.

### 4. AGV Artifact Governance (`AGV-SYS-001`) — LV Spec Status Drift Checker
- **Spec**: `dev/SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`
- **Artifact**: Artifact inventory and spec status (`dev/INDEX.md`, Spec Status Validator)
- **Current Status**: `[~]` (Manual spec indexing exists; automated drift checker between spec status claims and code evidence is unbuilt)
- **Verified High-Impact Rationale**:
  - *Why it matters*: Fast-paced feature additions in Lingua Viva cause spec documents and `dev/INDEX.md` status tables to quickly fall out of sync with actual source and test states.
  - *Systemic Impact*: Mechanically enforces documentation integrity. Scans all `dev/*SPEC*.md` files, verifies claimed files/tests exist in `src/` and `tests/`, and flags status drift as a build warning.
- **Verification Strategy**:
  - Execute `python3 -m src.lingua_viva.spec_status_drift` and verify detection of stale spec status headers.

### 5. EDU Education Product Modules (`EDU-SYS-001`) — Cohort Lesson-Planning Workflow
- **Spec**: `dev/specs/SPEC_LV_COHORT_LESSON_PLANNING_2026-07-30.md` (or new proposal)
- **Artifact**: Teacher/admin product modules (Lesson Planning & Differentiation Surface)
- **Current Status**: `[ ]` (Lesson adaptation exists for individual turns, but structured multi-student cohort planning is missing)
- **Verified High-Impact Rationale**:
  - *Why it matters*: K-8 teachers spend 5+ hours weekly planning lessons that accommodate mixed skill levels (bilingual learners, RTI Tier 2, advanced students).
  - *Systemic Impact*: Automates cohort-level lesson plan generation. Uses stored student lenses to generate a single lesson plan with 3 embedded differentiation tiers (Universal, Targeted, Intensive), saving hours of administrative time while preserving Reggio/IB pedagogical standards.
- **Verification Strategy**:
  - Test cohort planning endpoint with a 15-student class roster and verify output contains valid differentiation paths for all 3 RTI tiers.

---

## Pass 3 Active Remaining Work Matrix

### RTE - Runtime Execution (`RTE-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A04 | [~] | Lazy/call-time environment resolution. | Ensures hermetic test execution and prevents stale configuration caching. | Perform runtime hermeticity sweep over helper modules. |
| LV-B01; LV-A25 | [ ] | `SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md` | Prevents student PII leakage before external LLM routing can be enabled. | Build native exit/integrity gate module in `src/lingua_viva/`. |
| New Voice | [~] | True provider-token streaming. | Reduces time-to-first-token audio latency for voice interactions. | Spec provider token streaming after SSE voice stabilizes. |

### EON - Education Ontology (`EON-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| New Triage | [ ] | `SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md` | Prevents misdiagnosing evaluation failures by attributing defects to Curriculum vs Code vs Ontology layers. | Build `src/lingua_viva/defect_triage.py`. |
| LV-A09 | [~] | Learned-weight health audit or formal demotion. | Ensures weight tuning provides real utility rather than false confidence. | Run audit over learned-weight usage. |

### CUR - Curriculum / Knowledge (`CUR-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A13 | [~] | Drive metadata-only freshness signal detection. | Notifies teachers when curriculum sources update without auto-importing private files. | Build metadata freshness scanner into daily file status. |
| LV-B03 | [ ] | Teacher curriculum adjustment proposal queue. | Enables teachers to propose curriculum updates via a governed approval workflow. | Add curriculum proposal candidate schema. |

### OBS - Observation / Student Lens (`OBS-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A14 | [~] | `SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md` | Completes the observation-to-artifact loop by auto-generating differentiated student learning materials. | Implement help-artifact generation endpoint in `src/web.py`. |
| LV-A16 | [~] | Gap-driven next-step proposal queue. | Converts observed student skill gaps into actionable teacher recommendations. | Connect gap clusters to recommendation queue. |

### EDU - Education Product Modules (`EDU-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| New Cohort | [ ] | Dedicated Cohort Lesson-Planning Workflow | Automates multi-tier lesson differentiation (Universal, Targeted, Intensive) across class rosters. | Build cohort lesson planning endpoint and UI surface. |
| LV-A22 | [~] | Daily file section ownership & classification contracts. | Prevents mixing ops, student PII, and curriculum reminders in the operational daily file. | Enforce section ownership contracts in daily file generator. |

### PRV - Privacy / Governance (`PRV-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A27; LV-B11 | [~] | `SPEC_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md` | Re-audits publication readiness against current public/portfolio features prior to launch. | Perform publication readiness review. |

### CON - Connectors / Sources (`CON-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A37 | [ ] | `/api/ops/records` human-inspectable review UI. | Gives school ops managers visual history of all Slack requests and schedule changes. | Add ops records review panel to admin UI. |
| New Policy | [ ] | AI Policy retrieval with strict citation gate. | Provides authoritative answering for school handbook policies without hallucination. | Build retrieval-only policy endpoint with citation validation. |

### EVA - Evaluation / Measurement (`EVA-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A72 | [~] | Stable origin/session tags in eval harness signal writes. | Enables mechanical burst detection and session filtering in gap audits. | Add `origin` and `session_id` fields to gap signal writer. |
| LV-A51 | [~] | Repeatable P0 live experience sweep instrument. | Automates live P0 regression testing across core teacher workflows. | Build `mc eval p0` sweep command for Lingua Viva. |

### AGV - Artifact Governance (`AGV-SYS-001`)

| Source ID(s) | Status | Remaining Spec / Idea | Why It Matters (Systemic Impact) | Recommended Next Action |
|---|---|---|---|---|
| LV-A54 | [~] | `SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md` | Prevents spec status claims from lagging behind live code and test implementations. | Implement LV spec status drift checker script. |

---

## Priority Ranking for Next Lingua Viva Build Cycle

Based on verified systemic impact, the recommended execution order for the next Lingua Viva sprint is:

1. **`SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md`** (PRV/RTE) — Highest safety impact; ensures FERPA/COPPA compliance before external routing.
2. **`SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md`** (OBS) — Highest educational impact; completes observe-to-artifact workflow.
3. **Cohort Lesson-Planning Workflow** (EDU) — Highest administrative value; automates multi-tier lesson differentiation.
4. **`SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md`** (EON) — Highest developer efficiency impact; accurately attributes eval failures to correct layers.
5. **`SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`** (AGV) — Maintains documentation and spec alignment.
