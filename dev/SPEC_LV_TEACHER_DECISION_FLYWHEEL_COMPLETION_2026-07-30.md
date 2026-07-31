# SPEC: Lingua Viva Teacher Decision Flywheel Completion

**Date**: 2026-07-30
**Status**: SHIPPED - committed `f4d0446`, tested
**Source matrix**: `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
**Systems**: OBS Observation / ACT Action Approval / EDU Product Modules
**Primary surfaces**: student lens, observation decisions, differentiated help artifacts, portfolio entries, deliverables
**Selection rationale**: Native Exit & Integrity Gates are now implemented. The unified matrix ranks this as the next highest-impact slice because it completes the core educational loop: observe -> classify -> decide -> produce a teacher-approved artifact.

---

## Goal

Complete the teacher decision half of Lingua Viva's learning flywheel.

Today Lingua Viva can:

- capture observations into a student lens;
- classify CEFR/SEL/support evidence;
- suggest RTI review proposals;
- let the teacher confirm/defer RTI tier decisions;
- generate differentiated lesson/activity packs and parent-report drafts in separate workflows;
- record deliverables and audit receipts for some exports.

The missing workflow is direct:

```text
student evidence -> teacher decision -> draft help artifact / portfolio entry -> teacher approval -> durable deliverable
```

This build should make observed student gaps actionable without ever auto-sending, auto-publishing, or silently changing student support status.

## Product Shape

Add a deterministic, local-only module, preferably:

```text
src/education/help_artifacts.py
```

It should produce two teacher-facing draft types:

1. **HelpArtifactRecord**: a differentiated practice/support artifact for a student.
2. **PortfolioEntryDraft / PortfolioEntryRecord**: a short learning-story style entry that a teacher can approve for portfolio use.

Both are drafts until the teacher approves them.

Do not call external LLMs. Do not use broad AI generation. Use stored lens facts, CEFR direction, support entries, current RTI tier, and existing deterministic education helpers.

## Existing Capabilities To Reuse

| Capability | Current implementation | Use in this build |
|---|---|---|
| Observation capture | `src/education/observation_capture.py` | Source observations and support evidence. |
| Student lens store | `src/education/student_lens.py` | Read lens, observations, RTI/CEFR/support state. |
| RTI decision routes | `src/web.py` `/api/students/{student_id}/rti/decision`, `PUT /api/students/{student_id}/rti` | Keep existing RTI decision behavior; optionally attach artifact suggestions after decisions. |
| Differentiation tier assignment | `ContentDifferentiator.assign_tier_for_student()` | Choose artifact scaffolding tier from the real lens. |
| Parent report approval pattern | `src/education/parent_report.py` | Mirror draft -> approve separation and safety language style. |
| Deliverable records | `src/lingua_viva/deliverables/*` | Record approved help artifacts / portfolio entries. |
| Audit receipts | `src/lingua_viva/audit_receipts/*` | Create receipt on approval, not preview. |
| Native exit gate | `src/lingua_viva/exit_gates.py` | Ensure drafts remain local and approved exports are structurally safe. |
| Server-side role gate | `src/lingua_viva/access_roles.py`, `src/web.py` middleware | Teacher-owned routes must use effective teacher identity. |

## Data Model

Add dataclasses in the new module.

Recommended `HelpArtifactRecord` fields:

```python
artifact_id: str
student_id: str
teacher_id: str
created_at: str
status: str                  # draft | approved | rejected
artifact_type: str           # practice | scaffold | check_in | review
source_observation_ids: list[str]
source_summary: str          # no raw transcript
target_domain: str           # reading | writing | speaking | listening | support_category id
cefr_level: str
rti_tier: int
differentiation_tier: str    # foundational | on_track | extended
title: str
instructions: str
student_prompt: str
teacher_notes: list[str]
safety_notes: list[str]
```

Recommended `PortfolioEntryRecord` fields:

```python
portfolio_entry_id: str
student_id: str
teacher_id: str
created_at: str
status: str                  # draft | approved | rejected
source_observation_ids: list[str]
title: str
body: str                    # learning-story style, no clinical/deficit labels
evidence_tags: list[str]
safety_notes: list[str]
```

Storage can be append-only NDJSON under `LV_STATE_HOME` or `lv_home()/runtime/teacher_decisions/`.

Do not write generated artifacts into the student lens automatically. The student lens remains evidence/history; approved artifacts are deliverables.

## Route Scope

Add backend routes in `src/web.py`.

### Preview Routes

```text
POST /api/students/{student_id}/help-artifact/preview
POST /api/students/{student_id}/portfolio-entry/preview
```

Behavior:

- Require teacher-or-higher via existing role gate.
- Use `effective_teacher_id(request, payload["teacher_id"])`.
- Load the real student lens.
- Select recent relevant observations, preferably latest 3-5.
- Generate draft locally.
- Do not write a deliverable or audit receipt yet.
- Return draft plus `requires_teacher_approval: true`.

### Approval Routes

```text
POST /api/students/{student_id}/help-artifact/approve
POST /api/students/{student_id}/portfolio-entry/approve
```

Behavior:

- Require teacher-or-higher via existing role gate.
- Accept draft id or draft payload plus optional teacher edits.
- Re-run safety checks on final text.
- Mark artifact approved in local store.
- Create `DeliverableRecord`.
- Create `AuditReceipt`.
- Return approved record, deliverable, and audit receipt.

### Optional Summary Route

If useful, add:

```text
GET /api/students/{student_id}/decision-workbench
```

This should return:

- current RTI proposals;
- latest CEFR/support gaps;
- available actions: help artifact, portfolio entry, RTI decision.

Classify as backend-only in route reachability unless mounted visibly.

## Generation Rules

### Help Artifact

Generate a concrete student-facing support item, for example:

- foundational: short guided practice, sentence frames, checklist, visual cue;
- on_track: independent practice with one scaffold;
- extended: transfer/extension challenge.

Use:

- weakest/recent CEFR dimension;
- support entries if present;
- `ContentDifferentiator.assign_tier_for_student()`;
- safe, non-clinical language.

Do not mention:

- RTI tier numbers in student-facing text;
- diagnoses;
- refugee/trauma labels;
- raw observation transcript;
- AI attribution.

### Portfolio Entry

Generate a short learning-story style entry:

- names the skill, not the deficit;
- describes observed progress or next step;
- cites evidence tags internally;
- avoids clinical labels and raw transcript.

Portfolio entries are still teacher-facing until approved.

## Deliverables

Extend `src/lingua_viva/deliverables/schema.py` to accept:

- `help_artifact`
- `portfolio_entry`

Approved records should appear through existing:

```text
GET /api/deliverables
POST /api/audit-receipts/export
```

Do not add Drive upload/share-back here unless already supported through the deliverables path. Export/share remains a separate explicit action.

## Privacy And Governance

- All generation is local-only and deterministic.
- Preview does not create a deliverable.
- Approval creates an audit trail.
- Raw observation transcript must not appear in generated student-facing artifacts.
- Run publication/trauma safety checks before approval.
- Use native exit gate only as a local structural check if no external action occurs; do not mark preview as external.
- No auto-parent communication.
- No automatic RTI tier change from artifact generation.
- No hidden mutation of student lens state.

## Tests

Add focused tests, preferably:

```text
tests/test_teacher_decision_flywheel.py
```

Minimum coverage:

1. Help artifact preview uses real student lens evidence and returns `requires_teacher_approval`.
2. Preview does not create a deliverable.
3. Help artifact selects a differentiation tier from `ContentDifferentiator.assign_tier_for_student()`.
4. Raw observation transcript is not copied into student-facing artifact text.
5. Help artifact approval creates `DeliverableRecord` with type `help_artifact`.
6. Help artifact approval creates an audit receipt.
7. Portfolio entry preview uses latest observations and avoids RTI/clinical/deficit labels.
8. Portfolio entry approval creates `DeliverableRecord` with type `portfolio_entry`.
9. Teacher edits are preserved after safety checks.
10. Unsafe teacher-edited text is rejected.
11. Teacher-id impersonation is prevented in `LV_AUTH_MODE=local_header`.
12. Existing RTI decision routes still pass.
13. Native exit gate tests still pass.

Run:

```bash
pytest -q \
  tests/test_teacher_decision_flywheel.py \
  tests/test_student_lens.py \
  tests/test_teacher_api_phase2.py \
  tests/test_parent_report.py \
  tests/test_parent_report_safety_gate.py \
  tests/test_native_exit_integrity_gates.py \
  tests/test_server_side_auth_role_gate.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- Teachers can preview a help artifact from a student's real lens evidence.
- Teachers can approve a help artifact into deliverables + audit receipt.
- Teachers can preview and approve a portfolio entry.
- Preview remains non-mutating.
- Approval is explicit, audited, and locally stored.
- No generated student-facing artifact contains raw observation transcript, RTI tier labels, AI attribution, diagnosis, or trauma/refugee labels.
- Existing RTI decision behavior remains intact.
- Full suite and preflight pass.
- Working tree remains uncommitted.
