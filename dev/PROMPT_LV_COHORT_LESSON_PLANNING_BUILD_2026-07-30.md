# Build Prompt - Lingua Viva Cohort Lesson-Planning & Differentiation Workflow

You are implementing the next high-impact Lingua Viva education product slice after Teacher Decision Flywheel Completion.

Read first:

```text
dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md
dev/SPEC_LV_COHORT_LESSON_PLANNING_WORKFLOW_2026-07-30.md
src/education/content_differentiator.py
src/education/teacher_guide.py
src/education/student_lens.py
src/education/trend_analysis.py
src/education/weekly_recommendation.py
src/education/help_artifacts.py
src/lingua_viva/deliverables/schema.py
src/lingua_viva/deliverables/store.py
src/lingua_viva/audit_receipts/
src/lingua_viva/access_roles.py
src/lingua_viva/exit_gates.py
src/web.py
tests/test_content_differentiator.py
tests/test_teacher_guide.py
tests/test_weekly_recommendation.py
tests/test_teacher_api_phase2.py
tests/test_teacher_decision_flywheel.py
tests/test_server_side_auth_role_gate.py
```

## Objective

Build this deterministic local workflow:

```text
teacher lesson intent + effective teacher roster
  -> cohort summary
  -> tier assignments
  -> differentiated content pack
  -> teacher guide with conflict-aware groups
  -> teacher approval
  -> local deliverable + audit receipt
```

This is not an open-ended AI lesson planner. It is a governed cohort-planning workflow built from existing deterministic modules and real student lenses.

## Hard Rules

1. **Do not commit.**
2. **Do not call external LLMs or any network service.**
3. **Do not auto-send anything to parents, Drive, Slack, or public surfaces.**
4. **Do not mutate student lenses during preview or approval.**
5. **Do not change RTI tiers automatically.**
6. **Do not copy raw observation transcripts into generated plans.**
7. **Do not include diagnoses, clinical labels, refugee/trauma labels, or AI attribution in generated text.**
8. **Student-facing tier content must not include individual student names.**
9. **Use `effective_teacher_id()` for teacher-owned routes.**
10. **Preserve existing `/api/prepare/activity` and `/api/prepare/tier-assignments` behavior.**

## Step 0: Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_content_differentiator.py tests/test_teacher_guide.py tests/test_weekly_recommendation.py tests/test_teacher_api_phase2.py tests/test_teacher_decision_flywheel.py tests/test_server_side_auth_role_gate.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

The working tree is expected to contain uncommitted work from previous July 30 builds. Do not revert unrelated changes.

## Step 1: Add Cohort Planning Module

Create:

```text
src/education/cohort_planning.py
```

Implement dataclasses:

- `CohortStudentAssignment`
- `CohortPlanningSummary`
- `CohortLessonPlanRecord`

Implement helpers:

- `generate_cohort_plan(store, teacher_id, lesson, student_ids=None, teacher_notes=None, retriever=None)`
- `approve_cohort_plan(record_or_payload, teacher_edits=None)`
- `save_cohort_plan(record)`
- `read_cohort_plans(teacher_id="", limit=50)`
- `content_hash(record)` if useful for deliverables

Implementation requirements:

- Build roster from `StudentLensStore.list_lenses_for_teacher(teacher_id)`.
- If `student_ids` is supplied, include only those IDs if they are in the effective roster; reject unauthorized/unknown IDs.
- Use `ContentDifferentiator.assign_tier_for_student()` for every included student.
- Generate the content pack with `ContentDifferentiator.generate()` or `generate_from_documents()` if a retriever is available.
- Generate teacher guide with `TeacherGuideGenerator.generate(pack, roster, assignments)`.
- Include `TrendAnalyzer.analyze_class(teacher_id)` or equivalent roster summary where useful.
- Add manual-review notes for missing CEFR, active RTI escalation, no observations, and grouping conflicts/unplaced students.
- Store records under `LV_STATE_HOME/cohort_plans/records.ndjson` with atomic writes.
- Keep preview generation non-mutating.

## Step 2: Extend Deliverable Types

Update:

```text
src/lingua_viva/deliverables/schema.py
```

Add:

```text
cohort_lesson_plan
```

Do not disturb existing deliverable types including `help_artifact` and `portfolio_entry`.

## Step 3: Add Routes

In `src/web.py`, add:

```text
POST /api/cohort-plans/preview
POST /api/cohort-plans/approve
GET /api/cohort-plans
```

Route requirements:

- Accept `Request` and call `effective_teacher_id(request, payload_teacher_id)`.
- Preview returns `plan`, `requires_teacher_approval: true`, and `writes: {"deliverables": 0, "audit_receipts": 0}`.
- Preview must not save a deliverable or audit receipt.
- Approval accepts draft plan plus optional teacher edits.
- Approval re-runs safety checks on final text.
- Approval saves an approved local plan.
- Approval creates a `DeliverableRecord(type="cohort_lesson_plan", location.kind="none")`.
- Approval creates an `AuditReceipt`.
- Listing returns only the effective teacher's plans unless coordinator/admin access is explicitly allowed by existing role helpers.

If adding routes affects contract files, update them honestly.

## Step 4: Safety Checks

Reject unsafe teacher edits or generated text containing:

- raw observation transcript copied into plan text;
- `diagnosis`, `disorder`, or similar clinical labels;
- `refugee`, `trauma survivor`, `traumatized`, or similar labels;
- `AI`, `generated by AI`, or attribution wording;
- individual student display names inside student-facing tier prompts/tasks.

Use existing helpers where appropriate:

- `src.education.content_differentiator._check_trauma_safety`
- `src.lingua_viva.governance.check_publication_safety`
- safety patterns from `src/education/help_artifacts.py` and `src/education/parent_report.py`

Teacher-facing roster sections may include student names for classroom planning. Audit receipts must not expose student names.

Return `400` or `422` with a stable error such as `unsafe_teacher_edit` or `unauthorized_student_ids`.

## Step 5: Tests

Add:

```text
tests/test_cohort_lesson_planning.py
```

Cover:

- preview builds from effective teacher roster;
- preview returns approval requirement and writes no deliverable/audit receipt;
- tier assignment uses `ContentDifferentiator.assign_tier_for_student()`;
- subset planning rejects student IDs outside the teacher roster;
- empty roster returns a stable empty-plan response;
- teacher guide includes conflict-aware grouping and manual-review/unplaced students;
- student-facing tier content contains no individual student display names;
- raw observation transcript does not appear in generated plan text;
- approval creates deliverable type `cohort_lesson_plan`;
- approval creates audit receipt without student names;
- teacher edits are preserved when safe;
- unsafe teacher edits are rejected;
- teacher-id impersonation is prevented in `LV_AUTH_MODE=local_header`;
- existing `/api/prepare/activity` and `/api/prepare/tier-assignments` tests still pass.

Use isolated env paths:

```text
LV_STUDENT_DB_PATH
LV_STATE_HOME
LV_PRIVACY_LOG_PATH
LV_REVISION_LOG_PATH
```

No network.

## Step 6: Contracts

If `src/web.py` changes, run:

```bash
python3 scripts/check_ui_contract.py --bump
```

Then:

- add a bump-log line to `contracts/UI_CONTRACT.yaml`;
- sync `EXPECTED_VERSION` in `tests/test_ui_contract.py`.

Update:

```text
contracts/ROUTE_REACHABILITY.yaml
```

Classify new routes as backend-only unless this build also wires a visible UI.

## Step 7: Verification

Run focused:

```bash
pytest -q \
  tests/test_cohort_lesson_planning.py \
  tests/test_content_differentiator.py \
  tests/test_teacher_guide.py \
  tests/test_weekly_recommendation.py \
  tests/test_teacher_api_phase2.py \
  tests/test_teacher_decision_flywheel.py \
  tests/test_server_side_auth_role_gate.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

Fix real regressions. If a failure is inherited, document exact evidence before finalizing.

## Final Report

Report:

- files changed;
- new routes;
- preview vs approval behavior;
- cohort summary fields;
- how tier assignments and teacher guide are built;
- deliverable/audit receipt behavior;
- safety checks;
- focused test result;
- preflight result;
- full suite result;
- any intentionally deferred UI surface.

Do not claim plans are exported, shared, parent-visible, or Drive-backed. They are local teacher-approved cohort planning deliverables only.
