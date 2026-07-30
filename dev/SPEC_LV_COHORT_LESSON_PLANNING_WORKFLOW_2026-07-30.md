# SPEC: Lingua Viva Cohort Lesson-Planning & Differentiation Workflow

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Source matrix**: `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
**Systems**: EDU Product Modules / OBS Student Lens / ACT Action Approval
**Primary surfaces**: cohort planning engine, Prepare backend routes, student-lens roster reads, differentiated content packs, teacher guides, deliverables
**Selection rationale**: Native Exit Gates and Teacher Decision Flywheel are now either complete or queued. The matrix ranks cohort lesson planning as the next highest-impact slice because it turns stored student-lens evidence into a usable class plan, reducing teacher planning time while preserving teacher approval and privacy boundaries.

---

## Goal

Build the missing cohort planning workflow:

```text
teacher lesson intent + real roster lenses
  -> cohort distribution summary
  -> three-tier differentiated lesson plan
  -> conflict-aware grouping and facilitation guide
  -> teacher approval
  -> durable local deliverable + audit receipt
```

Lingua Viva already has strong pieces:

- `src/education/content_differentiator.py` creates deterministic three-tier `ContentPack`s from `LessonInput`.
- `ContentDifferentiator.assign_tier_for_student()` maps a real student lens to `foundational`, `on_track`, or `extended`.
- `src/education/teacher_guide.py` creates teacher-facing distribution notes and conflict-aware groups from a roster.
- `StudentLensStore.list_lenses_for_teacher()` provides a teacher-owned cohort based on observation history.
- `TrendAnalyzer.analyze_class()` and `WeeklyRecommendationGenerator` already summarize class patterns.
- The Teacher Decision Flywheel pattern now establishes preview -> approve -> deliverable + audit receipt for education artifacts.

The missing product workflow is not another single lesson generator. It is a planner that joins the lesson, roster, tier distribution, group suggestions, accommodations, and teacher guide into one reviewable cohort plan.

## Product Shape

Add a deterministic, local-only planning module:

```text
src/education/cohort_planning.py
```

It should generate a draft `CohortLessonPlanRecord` from:

- a `LessonInput` payload;
- the effective teacher roster from `StudentLensStore`;
- optional explicit `student_ids` to plan for a subset of the roster;
- optional teacher planning notes.

The record remains a draft until explicitly approved.

No external LLMs. No network. No automatic publication. No student-lens mutation. No automatic RTI changes.

## Existing Capabilities To Reuse

| Capability | Current implementation | Required use |
|---|---|---|
| Lesson schema and differentiated content | `LessonInput`, `ContentDifferentiator.generate()` / `generate_from_documents()` | Generate the three-tier lesson body. |
| Tier assignment | `ContentDifferentiator.assign_tier_for_student()` | Assign each roster student to a differentiation tier. |
| Roster source | `StudentLensStore.list_lenses_for_teacher()` | Default cohort for the effective teacher. |
| Lens details | `StudentLensStore.get_lens()` / `export_lens()` | Read RTI, CEFR, support, and conflict fields without mutating. |
| Conflict-aware grouping | `TeacherGuideGenerator.generate()` / `build_cross_level_groups()` | Create teacher guide and groups. |
| Class trend summary | `TrendAnalyzer.analyze_class()` | Include class-level context. |
| Weekly recommendation patterns | `weekly_recommendation.py` | Reuse clear "known gap" phrasing; do not invent curriculum calendar data. |
| Deliverable records | `src/lingua_viva/deliverables/*` | Approved plans become local deliverables. |
| Audit receipts | `src/lingua_viva/audit_receipts/*` | Approval creates an audit receipt. |
| Role gate | `src/lingua_viva/access_roles.py` + `src/web.py` middleware | Teacher-owned planning routes must use `effective_teacher_id()`. |
| Exit/publication gates | `src/lingua_viva/exit_gates.py`, `src.lingua_viva.governance.check_publication_safety` | Keep output local and structurally safe. |

## Data Model

Recommended dataclasses in `cohort_planning.py`:

```python
@dataclass
class CohortStudentAssignment:
    student_id: str
    display_name: str
    assigned_tier: str              # foundational | on_track | extended
    rti_tier: int
    cefr_snapshot: dict
    support_flags: list[str]
    grouping_notes: list[str]

@dataclass
class CohortPlanningSummary:
    total_students: int
    tier_counts: dict
    cefr_distribution: dict
    support_focus_counts: dict
    flagged_student_count: int
    manual_review_student_ids: list[str]

@dataclass
class CohortLessonPlanRecord:
    plan_id: str
    teacher_id: str
    created_at: str
    status: str                    # draft | approved | rejected
    lesson: dict                   # asdict(LessonInput)
    cohort_summary: CohortPlanningSummary
    student_assignments: list[CohortStudentAssignment]
    content_pack: dict             # ContentPack.to_dict()
    teacher_guide_markdown: str
    source_mode: str               # generated | adapted | teacher_adapted
    source_provenance: list[dict]
    teacher_notes: list[str]
    safety_notes: list[str]
```

Storage can be append-only NDJSON under:

```text
LV_STATE_HOME/cohort_plans/records.ndjson
```

Use atomic writes, permissions consistent with existing deliverable/local stores, and helpers such as:

- `generate_cohort_plan(store, teacher_id, lesson, student_ids=None, teacher_notes=None, retriever=None)`
- `approve_cohort_plan(record_or_payload, teacher_edits=None)`
- `save_cohort_plan(record)`
- `read_cohort_plans(teacher_id="", limit=50)`

## Route Scope

Add backend routes in `src/web.py`.

### Preview

```text
POST /api/cohort-plans/preview
```

Payload:

```json
{
  "teacher_id": "local-teacher",
  "student_ids": ["optional", "subset"],
  "lesson": {
    "ib_programme": "PYP",
    "subject": "Italian",
    "unit_title": "Migration Stories",
    "topic": "describing journeys and reasons",
    "atl_skills": ["communication", "self-management"],
    "cefr_target": "A2",
    "duration_minutes": 45,
    "language_of_instruction": "it"
  },
  "teacher_notes": ["optional planning note"]
}
```

Behavior:

- Require teacher-or-higher through existing route gate.
- Use `effective_teacher_id(request, payload["teacher_id"])`.
- Build `LessonInput` with existing validation.
- Load the effective teacher roster.
- If `student_ids` is provided, include only students from that teacher's roster; reject unknown/unauthorized IDs.
- Generate content pack and teacher guide locally.
- Return `plan`, `requires_teacher_approval: true`, and `writes: {"deliverables": 0, "audit_receipts": 0}`.
- Do not mutate student lenses or write deliverables/audit receipts during preview.

### Approval

```text
POST /api/cohort-plans/approve
```

Behavior:

- Require teacher-or-higher.
- Use `effective_teacher_id()`.
- Accept a draft plan plus optional teacher edits.
- Re-run safety checks on student-facing and teacher-facing text.
- Save approved plan locally.
- Create `DeliverableRecord` with type `cohort_lesson_plan`.
- Create `AuditReceipt`.
- Return approved record, deliverable, and receipt.

### List

```text
GET /api/cohort-plans
```

Behavior:

- Teacher-level caller sees only their effective teacher plans.
- Coordinator/admin may pass `teacher_id` to inspect a specific teacher's approved/draft plan list.
- Default `limit=50`.

Classify these as backend-only in route reachability unless a visible UI calls them in the same build.

## Generation Rules

### Cohort Summary

The planner should summarize real roster structure:

- total students;
- tier counts by `foundational`, `on_track`, `extended`;
- CEFR distribution across observed dimensions;
- support focus counts from lens support entries where available;
- manual review list for students with missing CEFR, missing observations, unresolved conflict grouping, or active escalation rules.

Do not fabricate a curriculum calendar, upcoming unit, attendance state, or operational constraint that is not present in the payload/store.

### Differentiated Plan

Use the existing `ContentDifferentiator` output as the core lesson body. Do not reimplement tier task generation.

The cohort plan may add wrapper sections:

- "Before class": materials and setup by tier.
- "During class": circulation priorities and check-ins.
- "After class": observation prompts for students needing review.
- "Manual review": students or groups the teacher should adjust.

These sections must be deterministic and based on tier counts, active support flags, grouping failures, and teacher notes.

### Student Privacy

The record is teacher-facing and may include student IDs/display names for classroom planning, but must not:

- include raw observation transcripts;
- include diagnoses or clinical labels;
- call a child a refugee, trauma survivor, traumatized, or similar;
- expose student names in audit receipts;
- be sent to Drive, Slack, parents, or public surfaces automatically.

Student-facing content inside the pack must remain generic by tier and must not include individual student names.

### Approval

Approval means:

- the teacher accepted the local plan;
- the plan is stored as an approved local record;
- a deliverable and audit receipt are created.

Approval does not mean:

- it was exported;
- it was shared;
- student lenses were updated;
- RTI tiers changed;
- parents were notified.

## Deliverables

Extend `src/lingua_viva/deliverables/schema.py` to accept:

```text
cohort_lesson_plan
```

Approved cohort plans should appear through existing deliverable listing/export paths as local records.

Use `DeliverableLocation(kind="none")` unless a separate explicit export action is added later.

## Tests

Add:

```text
tests/test_cohort_lesson_planning.py
```

Minimum coverage:

1. Preview builds a plan from the effective teacher roster.
2. Preview returns `requires_teacher_approval` and writes no deliverable/audit receipt.
3. Tier assignment calls/reuses `ContentDifferentiator.assign_tier_for_student()`.
4. Unknown `student_ids` outside the teacher roster are rejected.
5. Empty roster returns a stable empty-plan response, not a crash.
6. Teacher guide includes conflict-aware grouping and unplaced/manual-review students.
7. Student-facing tier content contains no individual student display names.
8. Raw observation transcript does not appear in the generated plan.
9. Approval creates a deliverable with type `cohort_lesson_plan`.
10. Approval creates an audit receipt that does not expose student names.
11. Unsafe teacher edits are rejected.
12. `LV_AUTH_MODE=local_header` prevents teacher-id impersonation.
13. Existing `/api/prepare/activity` and `/api/prepare/tier-assignments` behavior remains intact.

Focused verification:

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
pytest -q
```

## Acceptance Criteria

- A teacher can preview a cohort lesson plan using real roster lenses.
- The plan includes tier assignments, a three-tier content pack, cohort summary, teacher guide, and manual-review notes.
- Preview is non-mutating.
- Approval creates a local `cohort_lesson_plan` deliverable and audit receipt.
- Unauthorized roster subset requests are rejected.
- Student-facing tier content contains no student names or raw observation transcript.
- No external network/LLM calls are introduced.
- Existing Prepare/activity, teacher-guide, content-differentiation, and teacher-decision-flywheel tests still pass.
- Full suite and preflight pass.
- Working tree remains uncommitted.
