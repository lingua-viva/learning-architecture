# SPEC — Roster Split Review & Override Surface — 2026-08-08

**Priority: P1 — one specific piece, taken all the way to perfect.**
Operator ruling 2026-08-08: no more whole-system improvements. This spec covers
exactly one UX piece: *the teacher sees the roster split and can change it before
anything is generated.* Nothing else.

## The gap (verified against disk at `137a002`)

The backend is complete; the surface does not exist.

- `assign_roster_split()` (`src/lingua_viva/lesson_materials.py`) accepts
  `overrides={student_id: tier}` including `"individual_support"`, may move a student
  into or out of INDIVIDUAL SUPPORT (`reason="teacher_override"`), and appends a dated
  teacher-attributed NDJSON record via `record_roster_overrides()` (shipped `e7580cc`,
  locked by `test_tier_overrides_applied_and_recorded`).
- All three routes (`/api/lesson-materials/generate|packet/preview|packet/approve`)
  accept `tier_overrides`; generate returns `"tier_overrides": split.overrides`.
- **But**: `grep -c "tier_overrides" static/index.html` → 0. The strings
  "Foundational", "On Track", "Extended" appear nowhere in the UI. The teacher never
  sees who landed in which group and has no way to move anyone. The split is applied
  silently inside packet generation — a teacher-facing decision made invisibly.

This is the committed-but-unmounted class at the UX level: capability with no surface.

## What to build

### 1. Split preview endpoint (store-only, no LLM)

`POST /api/lesson-materials/roster-split` — body: `{teacher_id?, student_ids?,
tier_overrides?}`. Runs `assign_roster_split` via `_with_student_store` (same seeded
store as the cohort endpoints) and returns:

```json
{
  "groups": {"foundational": [...], "on_track": [...], "extended": [...]},
  "individual_support": [{"student_id", "display_name", "reason"}],
  "overrides": {"student_id": "tier"},
  "roster_names": {"student_id": "display_name"}
}
```

Each group member: `{student_id, display_name, source: "rti"|"cefr"|"default"|
"teacher_override"}` so the teacher can see *why* a student is where they are.
If `assign_roster_split` does not currently expose per-student placement reasons,
add them there (one chokepoint), not in the route.

**No LLM call, no Drive call, no writes** — EXCEPT: overrides passed here are
previewed only, NOT recorded. `record_roster_overrides()` must fire only from the
generate/preview/approve routes where the override actually takes effect. Add a
`record=False` path (or a separate pure function) so the preview endpoint cannot
create ledger entries for splits that were never used. This matters: the override
ledger is the audit trail of what was actually taught.

### 2. Prepare UI: the split panel

In the Prepare view, before the "generate materials" action:

- A "Class groups for this lesson" panel listing the three tier columns + a visually
  separate INDIVIDUAL SUPPORT section (spec Pair 2 G2: kept apart, never a fourth
  tier column).
- Each student row: name, current group, a small select with the four placements.
  Changing the select updates a local `state.tierOverrides` map and re-fetches the
  split preview so the teacher sees the result immediately.
- Overridden students show a "teacher override" badge; a "reset" control per student
  clears the override.
- Generate/preview/approve calls pass `state.tierOverrides` as `tier_overrides`
  (all three — they already accept it).
- After generate, render the returned `tier_overrides` so the teacher sees which
  overrides were applied and recorded.
- Empty roster: the panel says so plainly and generation proceeds as today.

### 3. Ceremony

- New route classified in `contracts/ROUTE_REACHABILITY.yaml` (reachable).
- `static/index.html` + `src/web.py` change → UI contract bump with log line.

## Class-locking tests

1. Route test: split preview returns groups + reasons and **writes no override
   record** even when `tier_overrides` is passed (assert the NDJSON file absent /
   unchanged). Locks the class "preview endpoints never write ledgers."
2. Surface lock (pattern of `test_ask_grounding_surface.py`): `static/index.html`
   contains the individual-support section markup distinct from the tier columns,
   and every lesson-materials POST body in the file carries `tier_overrides` — no
   generation path may drop the teacher's overrides.
3. Existing `test_tier_overrides_applied_and_recorded` already locks the recording
   side; do not duplicate it.

## Acceptance

1. Teacher opens Prepare, sees all roster students in three groups + separate
   individual support, each with a placement reason.
2. Moving a student updates the preview instantly; the packet generated afterwards
   reflects the move; the override is recorded once, dated, teacher-attributed.
3. Preview never writes; generate/preview/approve always carry the overrides.
4. Contract v-bump + route classification green; suite green.

## Non-goals

Per-day override persistence/expiry ("per student per day" beyond the dated record),
drag-and-drop, bulk overrides, any change to the split rule itself, any Drive or
share-back behavior. One panel, one endpoint, done.
