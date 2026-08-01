# Build Prompt — Differentiated Lesson Materials Generator

You are implementing `dev/SPEC_LV_LESSON_MATERIALS_2026-08-01.md` end to end.

Read first:

```text
dev/SPEC_LV_LESSON_MATERIALS_2026-08-01.md
src/education/content_differentiator.py   (ContentDifferentiator, ContentPack, LessonInput, CEFR_ORDER)
src/education/help_artifacts.py           (generate_help_artifact — pattern to follow for safety checks)
src/education/cohort_planning.py          (generate_cohort_plan — pattern for roster loading + tier assignment)
src/lingua_viva/reasoning.py              (ReasoningEngine.reason() — how to call the LLM)
src/lingua_viva/drive_sync.py             (trigger_sync, upload_text_to_folder — how to push to Drive)
src/web.py                                (grep for cohort-plans/preview — pattern for the endpoint)
```

## Objective

Build `POST /api/lesson-materials/generate` that takes a lesson description + student IDs,
groups students by differentiation tier, calls the reasoning engine to produce student-facing
exercise content for each tier, and optionally pushes the results to Drive.

## Hard Rules

1. **No student names in generated materials.** The LLM prompt must never include student names.
   Tier assignments reference student_ids only in the response metadata, never in the content
   the LLM generates.
2. **No sensitive data in prompts.** Do not send RTI tiers, trauma flags, support profile details,
   or observation transcripts to the LLM. The only context the LLM gets is: tier name, CEFR level,
   subject, topic, duration.
3. **Safety validation.** Apply the same `UNSAFE_STUDENT_COPY` check from `help_artifacts.py` to
   all generated text before returning it.
4. **Do not commit.** Leave changes as modified/untracked files for the operator.
5. **Hermetic tests.** Mock the LLM call in unit tests — do not require Ollama running for pytest.

## Step 1: Create `src/lingua_viva/lesson_materials.py`

Core module. Contains:

```python
@dataclass
class TierMaterial:
    tier: str                        # "foundational" | "on_track" | "extended"
    student_ids: list[str]           # which students are assigned here
    title: str
    instructions_for_student: str
    exercise_body: str
    scaffolding: list[str]
    teacher_note: str

@dataclass
class LessonMaterialsResult:
    materials: list[TierMaterial]
    lesson_summary: str
    sync_status: str                 # "pushed_to_drive" | "drive_not_configured" | "push_failed" | "not_requested"

async def generate_lesson_materials(
    lesson: LessonInput,
    student_ids: list[str] | None = None,
    teacher_id: str = "local-teacher",
    push_to_drive: bool = True,
) -> LessonMaterialsResult:
    ...
```

Logic:
1. Open StudentLensStore, load teacher's roster (same pattern as `generate_cohort_plan`)
2. Assign tiers using `ContentDifferentiator().assign_tier_for_student(lens)`
3. Group student_ids by tier
4. For each tier with students (or all 3 if no students specified):
   - Build an LLM prompt (see spec for template)
   - Call `ReasoningEngine().reason(prompt, context={}, model=<default>, system_prompt=SYSTEM_PROMPT)`
   - Parse the response into TierMaterial fields
5. Validate all generated text with the UNSAFE_STUDENT_COPY check
6. If `push_to_drive` and sync folder is configured: format all materials as one markdown file,
   push via `upload_text_to_folder()`
7. Return LessonMaterialsResult

The SYSTEM_PROMPT for the LLM:
```
You are a curriculum materials writer for an international school. You produce
student-facing exercises — clear, age-appropriate, and scaffolded to the
specified CEFR level. Never mention student names, RTI tiers, AI, or diagnostic
information. Write in the language of instruction unless the exercise specifically
practices the target language.
```

The per-tier USER prompt:
```
Create a {tier_name}-tier worksheet for this lesson:
- Subject: {subject}
- Topic: {topic}
- CEFR target for this tier: {cefr_for_tier}
- Duration: {duration} minutes
- Scaffolding level: {scaffolding_description}

Output exactly this format:
TITLE: (a short, student-friendly title)
INSTRUCTIONS: (1-3 sentences telling the student what to do)
EXERCISE:
(the main activity — 5-15 lines of actual exercise content)
SCAFFOLDING NOTES: (comma-separated list of supports included)
```

Where:
- foundational → cefr_for_tier = one level below lesson.cefr_target, scaffolding = "heavy (word banks, sentence starters, visual cue placeholders)"
- on_track → cefr_for_tier = lesson.cefr_target, scaffolding = "moderate (one model example, then independent)"
- extended → cefr_for_tier = one level above lesson.cefr_target, scaffolding = "minimal (open-ended, peer discussion)"

## Step 2: Add the endpoint to `src/web.py`

Pattern: follow `/api/cohort-plans/preview` exactly.

```python
@app.post("/api/lesson-materials/generate")
async def lesson_materials_generate(request: Request, payload: dict):
    from src.lingua_viva.lesson_materials import generate_lesson_materials
    from src.education.content_differentiator import LessonInput
    from src.lingua_viva.access_roles import effective_teacher_id

    teacher_id = effective_teacher_id(request, str(payload.get("teacher_id") or "local-teacher"))
    lesson_data = payload.get("lesson") if isinstance(payload.get("lesson"), dict) else {}
    # Build LessonInput (same validation as _cohort_lesson_from_payload)
    lesson = LessonInput(
        ib_programme=str(lesson_data.get("ib_programme") or "PYP"),
        subject=str(lesson_data.get("subject") or ""),
        unit_title=str(lesson_data.get("unit_title") or ""),
        topic=str(lesson_data.get("topic") or ""),
        atl_skills=[str(s) for s in lesson_data.get("atl_skills") or []],
        cefr_target=str(lesson_data.get("cefr_target") or "A2"),
        duration_minutes=int(lesson_data.get("duration_minutes") or 45),
        language_of_instruction=str(lesson_data.get("language_of_instruction") or "en"),
        created_by=teacher_id,
    )
    errors = lesson.validate()
    if errors:
        return JSONResponse({"error": "invalid_lesson", "detail": "; ".join(errors)}, status_code=400)

    student_ids = payload.get("student_ids") if isinstance(payload.get("student_ids"), list) else None
    push_to_drive = bool(payload.get("push_to_drive", True))

    try:
        result = await generate_lesson_materials(
            lesson=lesson,
            student_ids=student_ids,
            teacher_id=teacher_id,
            push_to_drive=push_to_drive,
        )
    except PermissionError as exc:
        return JSONResponse({"error": "unauthorized_student_ids", "detail": str(exc)}, status_code=422)
    except ValueError as exc:
        return JSONResponse({"error": "generation_failed", "detail": str(exc)}, status_code=422)

    return {
        "materials": [asdict(m) for m in result.materials],
        "lesson_summary": result.lesson_summary,
        "sync_status": result.sync_status,
    }
```

## Step 3: Register the route

Add to `contracts/ROUTE_REACHABILITY.yaml` under `intentionally_backend_only`:
```yaml
  - route: "POST /api/lesson-materials/generate"
    status: deferred_undecided
    reason: >-
      MVP sprint Spec 3 (2026-08-01). Generates tier-differentiated student-facing
      materials; UI workbench placement deferred to Spec 4.
```

## Step 4: Write tests

`tests/test_lesson_materials.py`:

1. `test_generate_returns_three_tiers` — mock ReasoningEngine, verify 3 TierMaterial objects returned
2. `test_no_student_names_in_content` — verify student names don't appear in any generated text
3. `test_safety_check_rejects_unsafe` — inject unsafe text, verify it's caught
4. `test_cefr_tier_mapping` — verify foundational gets lower CEFR, extended gets higher
5. `test_empty_roster_still_returns_materials` — no students → still generates 3 generic tiers

Mock pattern:
```python
def mock_reason(query, context, model=None, system_prompt=None):
    return ReasonResult(
        content="TITLE: Test\nINSTRUCTIONS: Do this.\nEXERCISE:\n1. First task\n2. Second task\nSCAFFOLDING NOTES: word bank, sentence starters",
        confidence=0.8,
        model_used="mock",
    )
```

## Step 5: Verify

```bash
pytest -q tests/test_lesson_materials.py
python3 -m src.lingua_viva.cli preflight
```

Then hand back to operator for:
- Real LLM test (needs Ollama running)
- Drive push test (needs OAuth configured)
- Chip's manual test

## Definition of Done

- [ ] `src/lingua_viva/lesson_materials.py` created with all logic
- [ ] Endpoint added to `src/web.py`
- [ ] Route registered in contracts
- [ ] 5+ tests passing with mocked LLM
- [ ] Preflight 6/6
- [ ] Full test suite still passes (1694+ baseline)
