# SPEC: Differentiated Lesson Materials Generator

**Created**: 2026-08-01
**Status**: READY TO BUILD
**Depends on**: Content differentiator (exists), Reasoning engine (exists), Student lens store (exists)
**Produces**: Tier-specific student-facing worksheets/exercises from a lesson + roster

---

## Problem

The cohort planning system produces a **teacher guide** — instructions for the teacher about how to distribute tiers. It does NOT produce the actual **student-facing materials** (worksheets, exercises, prompts) that differ per group.

A teacher needs:
- A reading exercise for the foundational group (pre-A1 → A1) with heavy scaffolding, visual supports, sentence starters
- A different exercise for on-track (A1+ → A2) with moderate scaffolding, gap-fill, short production
- A different exercise for extended (B1+) with open-ended prompts, peer discussion frames, creative production

All three cover the SAME lesson topic but at different complexity/support levels. All three fit together so the class can work simultaneously on related tasks.

---

## What Exists Already

| Component | Location | What it does |
|---|---|---|
| `ContentDifferentiator.generate()` | `src/education/content_differentiator.py` | Produces a `ContentPack` with 3 tiers of learning objectives + instructions |
| `ContentPack.tiers` | same file | `{foundational: {objective, instructions, ...}, on_track: {...}, extended: {...}}` |
| `generate_help_artifact()` | `src/education/help_artifacts.py` | Produces a single practice artifact for ONE student based on their tier |
| `generate_cohort_plan()` | `src/education/cohort_planning.py` | Groups students by tier, produces teacher guide markdown |
| `ReasoningEngine.reason()` | `src/lingua_viva/reasoning.py` | Calls Ollama/external LLM with a prompt, returns text |
| Drive upload | `src/lingua_viva/google_drive_integration.py` | Can push files to a folder |

**What's missing**: A function that takes a lesson + tier assignments and calls the LLM to produce actual student-facing exercise content per tier, formatted as printable/shareable documents.

---

## Design

### Input
```json
{
  "lesson": {
    "subject": "language",
    "topic": "Describing daily routines in Italian",
    "unit_title": "How we express ourselves",
    "cefr_target": "A2",
    "duration_minutes": 45
  },
  "student_ids": ["student-marco", "student-nora", "student-luca"],
  "artifact_types": ["worksheet"]
}
```

### Output
```json
{
  "materials": [
    {
      "tier": "foundational",
      "student_ids": ["student-nora"],
      "title": "My Daily Routine — Supported Practice",
      "instructions_for_student": "Match the pictures to the Italian words...",
      "exercise_body": "...(the actual worksheet content)...",
      "scaffolding": ["word bank provided", "sentence starters", "visual cues"],
      "teacher_note": "Nora benefits from visual supports. Allow L1 glossing."
    },
    {
      "tier": "on_track",
      "student_ids": ["student-marco", "student-luca"],
      "title": "My Daily Routine — Practice",
      "instructions_for_student": "Write 5 sentences about your morning...",
      "exercise_body": "...",
      "scaffolding": ["verb conjugation reminder"],
      "teacher_note": "Marco and Luca can work as a pair."
    },
    {
      "tier": "extended",
      "student_ids": [],
      "title": "My Daily Routine — Challenge",
      "instructions_for_student": "Write a short paragraph comparing your routine to a partner's...",
      "exercise_body": "...",
      "scaffolding": [],
      "teacher_note": "No students currently at this tier."
    }
  ],
  "lesson_summary": "Describing daily routines in Italian (A2 target, 45min)",
  "sync_status": "pushed_to_drive" | "drive_not_configured" | "push_failed"
}
```

### Endpoint
```
POST /api/lesson-materials/generate
```

### Flow
1. Load student lenses for the given IDs
2. Assign tiers using `ContentDifferentiator.assign_tier_for_student()`
3. Group students by tier
4. For each tier: build an LLM prompt that asks for student-facing exercise content appropriate to that level
5. Call `ReasoningEngine.reason()` for each tier (3 calls, can be parallel)
6. Parse results into structured material objects
7. If Drive sync folder is configured, push materials as markdown files
8. Return the full response

### LLM Prompt Template (per tier)
```
You are creating a {tier_name} worksheet for a {subject} lesson.

Topic: {topic}
CEFR level: {cefr_level_for_tier}
Duration: {duration} minutes
Students at this tier: {count}

Create a student-facing exercise that:
- Is written in clear, simple language appropriate to {cefr_level_for_tier}
- Includes exactly one main activity with {scaffolding_level} scaffolding
- Has a title, clear instructions, and the exercise body
- Can be printed on one page
- For foundational: include word banks, sentence starters, visual cue descriptions
- For on-track: include one model example, then independent practice
- For extended: include an open-ended prompt with peer discussion frame

Output format:
TITLE: ...
INSTRUCTIONS: ...
EXERCISE:
...
SCAFFOLDING NOTES: ...
```

### Safety Rules
- No student names in the generated materials (tier only)
- No RTI/diagnostic language in student-facing text
- No trauma flags or sensitive data referenced
- Materials are always "draft" until teacher approves

---

## Test Plan (Chip can verify without LLM quality being perfect)

### Test 1: Endpoint returns structured response
```bash
curl -X POST http://localhost:8787/api/lesson-materials/generate \
  -H "Content-Type: application/json" \
  -d '{"lesson":{"subject":"language","topic":"Daily routines","cefr_target":"A2","duration_minutes":45},"student_ids":["student-marco","student-nora","student-luca"]}'
```
Expected: 200 with `materials` array containing 3 tier objects

### Test 2: Materials differ by tier
- Foundational material has word bank / sentence starters
- On-track material has model example + independent practice
- Extended material has open-ended prompt

### Test 3: Materials push to Drive (if sync folder configured)
- After generation, check Drive folder for new .md files

### Test 4: No student names in generated text
- Verify `instructions_for_student` and `exercise_body` contain no student names

---

## Files to Create/Modify

| File | Action |
|---|---|
| `src/lingua_viva/lesson_materials.py` | NEW — core generation logic |
| `src/web.py` | ADD — `/api/lesson-materials/generate` route |
| `contracts/ROUTE_REACHABILITY.yaml` | ADD — new route registration |
| `tests/test_lesson_materials.py` | NEW — unit tests (mock LLM) |

---

## Definition of Done

- [ ] Endpoint returns 3 tier-differentiated materials for a given lesson + roster
- [ ] Materials are student-facing (not teacher instructions)
- [ ] No student names or sensitive data in generated content
- [ ] If Drive sync configured, materials auto-push as .md files
- [ ] Chip can hit the endpoint and get readable exercise content
- [ ] All existing tests still pass
