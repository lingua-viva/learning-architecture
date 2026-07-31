# SPEC: Lingua Viva Final Governance, Readiness, and Product-Polish Sweep

**Date**: 2026-07-30
**Status**: BACKLOG SWEEP - not a single build slice
**Purpose**: Consolidate the remaining non-critical Lingua Viva improvement backlog after the July 30 build run.
**Source artifacts**:

- `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
- `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_3.md`
- July 30 completed builds: native exit gates, teacher decision flywheel, cohort planning, defect triage, spec-status drift checker
- Current source/test/contract state as of the final July 30 sweep

---

## Executive Assessment

Lingua Viva has made it through the foundation-risk phase.

The urgent safety and core workflow gaps have been addressed or have concrete specs/builds in place:

- native exit/integrity gates;
- server-side role gates;
- voice/GIR/golden-loop hardening;
- teacher decision flywheel;
- cohort lesson planning;
- SIR Slack absence/ops/schedule workflows;
- defect source triage;
- spec-status drift checker.

The remaining work is mostly governance, launch readiness, operator visibility, and product polish. These items matter, but they are no longer "the app is unsafe or structurally incomplete" blockers.

Recommended next posture:

1. Commit/push current in-flight hardening and spec-status files cleanly.
2. Run one launch-readiness pass before any external/public deployment.
3. Pick only one medium slice at a time; avoid another broad parallel build night unless there is a concrete release deadline.

## Current Verification Baseline

Latest verified state from the final sweep:

```text
preflight: 6/6
full suite: 1685 passed, 20 skipped
```

Treat these numbers as a snapshot, not a permanent guarantee. Re-run before any release.

## Priority 0 - Commit Hygiene

Before further product work, keep the working tree clean.

Expected next commit groups:

1. **Defect triage hardening**
   - `src/lingua_viva/defect_triage.py`
   - `tests/test_defect_triage.py`

2. **Spec status drift checker**
   - `dev/SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`
   - `dev/PROMPT_LV_SPEC_STATUS_DRIFT_CHECKER_BUILD_2026-07-30.md`
   - `src/lingua_viva/spec_status.py`
   - `tests/test_spec_status.py`

Do not mix unrelated runtime/evaluation proposal drift into these commits.

## Priority 1 - Launch Readiness / External Boundary

### 1. Publication Readiness Repass

**System**: PRV / AGV  
**Likely artifact**: `SPEC_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md`  
**Impact**: Medium/high before any public rollout  
**Risk**: Low

Run a publication readiness audit before:

- public site updates;
- demo packages;
- parent-visible artifacts;
- Still I Rise external review;
- any public portfolio examples.

Check:

- public copy does not overclaim what the app can do;
- parent/student examples are anonymized;
- AI attribution and safety language remain accurate;
- consent assumptions are explicit;
- "local-only" claims match actual external connector behavior;
- evidence registers support product claims;
- publication copy distinguishes internal teacher/admin tools from public-facing outputs.

Acceptance:

- report under `dev/reports/`;
- clear go/no-go summary;
- list of exact copy/files changed if any;
- full suite and preflight still pass.

### 2. Citation-Gated Policy Retrieval

**System**: CON / CUR / PRV  
**Likely artifact**: `src/education/policy_retrieval.py`  
**Impact**: Medium  
**Risk**: Low/medium

Build only when policy/procedure assistant becomes a real workflow.

Required behavior:

- retrieval-only from approved school docs;
- every answer must cite source document, section, version/date;
- no answer if no exact source;
- escalation path for safeguarding/HR/medical/legal topics;
- no freeform AI answer without citation.

This is the correct foundation for SlackBot policy/procedure questions.

## Priority 2 - Operator Visibility

### 3. Ops Records Review Dashboard

**System**: CON / SIR Ops  
**Likely artifacts**: `static/admin.html`, `src/web.py`, `/api/ops/records`  
**Impact**: Medium  
**Risk**: Low

The backend ops workflows exist. Leadership still needs a visual review surface.

Build:

- filterable history for absences, coverage, ops requests, and schedule changes;
- status and owner columns;
- reopened/needs-review indicators;
- campus/date/type filters;
- read-only first;
- CSV or local export only if already governed.

Do not add new Slack behavior in this slice. This is visibility over existing records.

### 4. Daily File Section Ownership Contracts

**System**: EDU / PRV  
**Likely artifact**: `src/education/daily_file.py`  
**Impact**: Medium/small  
**Risk**: Low

Prevent daily files from mixing operational reminders, student PII, curriculum items, and private notes in the wrong sections.

Build:

- explicit section schema;
- section ownership tags: ops, student, curriculum, private, reminder;
- validator that fails or warns on cross-section leakage;
- tests with student names/private notes in wrong sections;
- no UI needed unless existing daily view should show validation warnings.

## Priority 3 - Teaching Intelligence Polish

### 5. Gap-Driven Recommendation Queue

**System**: OBS / ACT  
**Likely artifact**: `src/education/recommendations.py`  
**Impact**: Medium  
**Risk**: Low

Teacher decision flywheel and cohort planning now produce artifacts. The next useful layer is a reviewable queue of "what to do next" from observed skill gaps.

Build:

- read-only recommendations from student lens/gap clusters;
- priority score with reasons;
- action suggestions: observe again, generate help artifact, include in cohort plan, review RTI proposal;
- teacher approve/defer/dismiss states;
- no automatic tier change;
- no parent communication;
- no hidden lens mutation.

Acceptance:

- queue is inspectable and auditable;
- recommendations cite underlying observations/gaps by local IDs;
- low-confidence recommendations are labeled as such.

### 6. Teacher Curriculum Proposal Queue

**System**: CUR / ACT  
**Likely artifact**: `src/education/curriculum_proposals.py`  
**Impact**: Medium  
**Risk**: Low

Teachers should be able to propose curriculum adjustments without altering authoritative curriculum directly.

Build:

- proposal record: unit, grade, subject, suggested change, rationale, source/citation;
- statuses: draft, submitted, approved, rejected, needs_changes;
- owner approval gate;
- no automatic curriculum mutation;
- proposal list endpoint;
- optional governance dashboard later.

This complements spec-status and ontology candidate governance.

### 7. Drive Metadata-Only Freshness Scanner

**System**: CUR / CON  
**Likely artifact**: `src/lingua_viva/sources.py` or Drive integration module  
**Impact**: Small/medium  
**Risk**: Low

Teachers need to know when Drive curriculum materials changed, without auto-importing content.

Build:

- metadata-only scan: file id, name, modified time, size, mime type;
- compare against last-seen metadata;
- daily file/source status summary;
- "new/changed source available" indicator;
- explicit import remains required;
- no content download or automatic indexing.

## Priority 4 - Evaluation and Developer Discipline

### 8. Repeatable Live P0 Experience Sweep

**System**: EVA / SRF  
**Likely artifact**: `src/lingua_viva/p0_sweep.py`  
**Impact**: Medium  
**Risk**: Low/medium

The test suite is strong, but a teacher-facing app still needs a repeatable journey sweep.

Build:

- command that exercises core teacher journeys against a running server;
- route/UI reachability checks;
- critical text/state assertions;
- optional Playwright if already in repo; otherwise HTTP/static checks first;
- report artifact under `dev/reports/artifacts/`;
- no external credentials required by default.

Suggested journeys:

- open app;
- ask local question;
- observe student;
- generate help artifact preview;
- approve local artifact;
- cohort plan preview;
- view deliverables/audit receipts;
- inspect governance/trust status.

### 9. Stable Producer and Session Tags for Gap Signals

**System**: EVA / EON  
**Likely artifact**: `src/lingua_viva/gap_audit.py`, signal writers  
**Impact**: Small/medium  
**Risk**: Low

Gap signals should identify whether they came from:

- real user session;
- golden workflow;
- hardening harness;
- live connector test;
- synthetic eval.

Build:

- fields: `origin`, `producer`, `session_id`;
- backward-compatible reader;
- audit report separates real use from harness bursts;
- tests for legacy records.

### 10. Learned-Weight Utility Auditor

**System**: EON  
**Likely artifact**: `src/lingua_viva/gap_audit.py` or new module  
**Impact**: Small/medium  
**Risk**: Low

If learned ontology weights exist, audit whether they actually improve classification.

Build:

- compare learned-weight classification against baseline classification on a small fixture set;
- flag weights with no observed improvement;
- never auto-delete weights;
- report recommended demotion.

## Priority 5 - Action Governance Polish

### 11. Teacher Confirmation Uniformity Auditor

**System**: ACT  
**Likely artifact**: `src/lingua_viva/action_audit.py`  
**Impact**: Small/medium  
**Risk**: Low

Audit all action-producing surfaces for the same principle:

```text
system proposes -> teacher reviews -> teacher approves -> durable record
```

Check:

- parent reports;
- help artifacts;
- portfolio entries;
- cohort plans;
- RTI tier updates;
- Slack ops assignments;
- schedule changes;
- Drive uploads;
- curriculum proposals.

Report any route that writes, sends, shares, exports, assigns, or changes status without explicit human approval.

### 12. Admin Copy and Deferred-State Honesty Pass

**System**: SRF / AGV  
**Impact**: Small/medium  
**Risk**: Low

As backend routes become real, admin/coordinator UI copy can drift.

Review:

- any "coming soon" copy for features now built;
- any "ready" copy for backend-only routes with no UI;
- dashboard panels that imply live external status when only local fixtures exist;
- counts that are stale/hardcoded;
- route reachability backend-only reasons that are no longer accurate.

## Priority 6 - Runtime Polish and Performance

### 13. Lazy Config Resolution Sweep

**System**: RTE  
**Impact**: Small  
**Risk**: Low

Most critical environment behavior is now good, but a final sweep should remove remaining import-time env capture.

Build:

- scan for module constants reading `os.environ` at import;
- convert to lazy getters where tests need env isolation;
- add targeted regression tests.

### 14. True Provider-Token Streaming

**System**: RTE / Voice  
**Impact**: Medium/high for voice UX  
**Risk**: Medium

Current SSE sentence streaming is valuable. True provider-token streaming would reduce latency further, but it is not a safety blocker.

Only build after:

- current voice/golden workflows remain stable;
- provider-specific streaming semantics are understood;
- cancellation/error handling is specified;
- no student data can flow to external providers without exit gate approval.

## Strategic Deferrals

These are not tonight's work:

- student-facing UI;
- automatic parent sending;
- automatic Drive sharing;
- automatic curriculum mutation;
- automatic RTI tier changes;
- open-ended AI policy assistant without citation gate;
- real production OAuth/session auth beyond local-header scaffold;
- broad Slack message surveillance.

Revisit only after teacher/admin adoption signals and launch-readiness review.

## Recommended Next Three Build Slices

If continuing tomorrow, the most rational order is:

1. **Spec Status Drift Checker review/commit**
   - Finish the already-started AGV checker.
   - Keeps the repo honest after the long build night.

2. **Publication Readiness Repass**
   - Required before external demos/public launch/Still I Rise stakeholder package.
   - Low regression risk.

3. **Citation-Gated Policy Retrieval or Ops Records Dashboard**
   - Choose based on immediate stakeholder need:
     - policy assistant if SlackBot workflows are next;
     - ops dashboard if school leadership needs visibility over the new Slack workflows.

## Do Not Do Next

Avoid another large multi-feature build before commit hygiene and readiness are clean.

Specifically do not start with:

- true provider-token streaming;
- student-facing UI;
- live external policy assistant;
- production auth;
- broad app redesign.

Those are valuable later but have higher ambiguity or release risk.

## Acceptance Criteria for This Sweep

This file is complete if it gives the next developer/operator:

- a clear statement that the foundation-risk phase is mostly closed;
- a ranked list of remaining medium-impact improvements;
- clear boundaries for what is deferred;
- enough specificity to convert any listed item into a focused spec/prompt pair later.

