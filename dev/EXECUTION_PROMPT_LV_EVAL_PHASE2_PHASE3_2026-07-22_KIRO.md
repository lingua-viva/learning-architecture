# Execution Prompt: Lingua Viva Eval Phase 2 + Phase 3 + App Wiring

**Author**: kiro.design  
**Date**: 2026-07-22  
**Purpose**: Build the implementations that make all 104 evals pass, then wire them into the running app  
**Context**: Phase 1 (eval scaffolding) is DONE — 104 tests, 45 passing, 55 skipped, 4 xfail  
**This window**: Builds implementation, unskips tests, hardens, wires into app  

---

## Current State (confirmed 2026-07-22 23:00)

```
tests/evals/ — 104 tests
  45 PASSING (running against existing code)
  55 SKIPPED (awaiting implementation you will build)
   4 XFAIL  (known gaps you will fix)
   0 BROKEN

Existing suite: 475 pass, 4 pre-existing UI contract failures (not your problem)
```

---

## YOUR JOB (in order)

### PHASE 2: Build the Implementations

Build the code that makes skipped evals pass. Do NOT modify any test in `tests/evals/` — the evals define "correct." You build to them.

#### Step 1: Fix the 4 Known Gaps (smallest changes first)

These are xfail tests that document bugs in existing code. Fix the code, then change xfail → regular test.

| Gap | File | Fix |
|-----|------|-----|
| RTI 1 + CEFR null → should be `foundational` | `src/education/content_differentiator.py` | In `assign_tier_for_student()`, when `weakest` is None, return `"foundational"` instead of falling through to on_track |
| Pre-A1 crashes | `src/education/content_differentiator.py` | Add `"Pre-A1"` to `CEFR_ORDER` at index 0. Or handle it gracefully in `assign_tier_for_student()` by treating unknown levels as below A1 |
| Future timestamps accepted | `src/education/student_lens.py` | Add `validate_observation_timestamp()` method. Call it in `append_observation()`. Add error to `validation_errors` list if future |
| Invalid CEFR dimensions accepted | `src/education/student_lens.py` | In `append_observation()`, validate `cefr_dimension` is in `{"reading", "writing", "speaking", "listening"}` |

**After each fix**: run `pytest tests/evals/ -x --tb=short` and verify the xfail becomes a pass.

#### Step 2: Build `update_rti_tier()` (StudentLensStore)

```python
def update_rti_tier(self, student_id: str, new_tier: int, trigger: str) -> None:
    """Manually change a student's RTI tier with audit trail.
    
    Must:
    - Update rti_current_tier in the DB
    - Close the previous tier entry in rti_tier_history (set "to" timestamp)
    - Append new entry: {"tier": new_tier, "from": now, "to": None, "trigger": trigger}
    - Bump profile_version
    - NOT change cefr_snapshot or observations
    - Raise LensNotFoundError if student doesn't exist
    - Raise ValueError if new_tier not in {1, 2, 3}
    """
```

**After building**: unskip the 4 tests in `test_gauntlet_rti_change.py` and run them.

#### Step 3: Build `get_lens_as_of()` (StudentLensStore)

```python
def get_lens_as_of(self, student_id: str, as_of: str) -> dict:
    """Return lens state as it was at a specific timestamp.
    
    Must:
    - Only include observations with recorded_at <= as_of
    - Recalculate cefr_snapshot from only those observations
    - RTI tier = the tier active at that time (check rti_tier_history)
    - Same dict shape as get_lens()
    - Raise LensNotFoundError if student doesn't exist
    - Raise ValueError if as_of is not valid ISO8601
    """
```

**After building**: unskip `test_L3_TIME_001` and `test_L3_TIME_002` in `test_temporal_integrity.py`.

#### Step 4: Build `TeacherLensBuilder` (NEW file: `src/education/teacher_lens_builder.py`)

This is the biggest piece. Read `tests/evals/CONTRACTS.md` for the full behavioral spec. Summary:

```python
class TeacherLensBuilder:
    def __init__(self, teacher_id: str, storage_path: Path): ...
    def ingest(self, file_path: Path, doc_type: str = "auto") -> IngestResult: ...
    def classify(self, file_path: Path) -> DocClassification: ...
    def build_lens(self) -> TeacherLens: ...
    def holdout_score(self, test_artifact: Path, artifact_type: str) -> HoldoutResult: ...
```

Key behaviors:
- `classify()` reads JSON fixtures from `tests/evals/fixtures/synthetic_teacher_history/`
- Each fixture has a `"doc_type"` field at the top level — use that for classification when in `auto` mode
- Pattern extraction: for exams, extract criteria + scoring patterns. For parent updates, extract vocabulary + tone. For lesson plans, extract scaffolding patterns.
- `build_lens()` must be deterministic
- `holdout_score()` compares a held-out doc against the lens patterns

The synthetic fixtures define the expected format. Read them:
```
tests/evals/fixtures/synthetic_teacher_history/
├── graded_exam_g3_u1.json
├── graded_exam_g3_u2.json
├── parent_update_marco.json
├── parent_update_nora.json
├── lesson_plan_g3_u1.json
└── student_evaluation_q1.json
```

**After building**: unskip ALL Layer 2 extraction tests + Layer 4 holdout tests.

#### Step 5: Build `generate_with_teacher_lens()` (ContentDifferentiator)

```python
def generate_with_teacher_lens(self, lesson, teacher_lens, retriever=None, domain="curriculum"):
    """Generate a pack influenced by the teacher's demonstrated patterns.
    
    Must:
    - Set source_mode = "teacher_adapted"
    - Use teacher_lens.differentiation_style for scaffolding choices
    - Use teacher_lens.communication_voice for language register
    - Fall back gracefully if teacher_lens is None
    """
```

**After building**: unskip L1-PACK-003, Layer 5 lesson prep gauntlet tests.

#### Step 6: Update `ALLOWED_DOC_TYPES` in `src/lingua_viva/ingest.py`

Add the TeacherLensBuilder types:
```python
ALLOWED_DOC_TYPES = {"curriculum", "organizational", "exam", "parent_update", "evaluation", "lesson_plan", "rubric"}
```

**After**: unskip L2-CLASS-006.

---

### PHASE 3: Unskip and Run

After all implementations land:

```bash
# Run full eval suite — target: zero skips, zero failures
pytest tests/evals/ -v --tb=short 2>&1 | tail -20

# Expected perfect state:
# 104 passed, 0 skipped, 0 xfailed
```

For each remaining skip:
1. Remove `@pytest.mark.skip`
2. Run the single test: `pytest tests/evals/path/to/test.py::test_name -v --tb=long`
3. If it fails → fix the implementation (not the test)
4. If the test is genuinely wrong (spec error) → note it, ask operator before changing

---

### PHASE 4: Hardening Passes (3 rounds)

After all 104 pass, do 3 hardening rounds:

#### Round 1: Edge Cases
- Run each layer with `pytest -x` (stop on first failure) — ensures no hidden ordering dependencies
- Run with `pytest --randomly-seed=42` if pytest-randomly is installed
- Add one more test per layer targeting the boundary you're least confident in

#### Round 2: Integration with Existing Suite
```bash
# Full suite including evals — nothing breaks
pytest tests/ -q --tb=no 2>&1 | tail -3
# Target: 579+ passed (475 existing + 104 evals)
```

#### Round 3: Performance
```bash
# Eval suite must complete in <5s (no model calls in live tests)
pytest tests/evals/ -q --tb=no 2>&1 | grep "in "
# Target: <5s
```

---

### PHASE 5: Wire into the App

The evals prove correctness in isolation. Now wire the new code into the running app.

#### 5A: API Endpoints

| Endpoint | Method | Wires To |
|----------|--------|----------|
| `/api/prepare/tier-assignments` | GET | `ContentDifferentiator.assign_tier_for_student()` per student in roster |
| `/api/teacher/lens` | GET | `TeacherLensBuilder.build_lens()` for current teacher |
| `/api/teacher/ingest` | POST | `TeacherLensBuilder.ingest()` — accepts JSON files |
| `/api/teacher/holdout` | POST | `TeacherLensBuilder.holdout_score()` — score a held-out artifact |
| `/api/students/{id}/rti` | PUT | `StudentLensStore.update_rti_tier()` |
| `/api/students/{id}/lens-as-of` | GET | `StudentLensStore.get_lens_as_of()` with `?as_of=` param |

#### 5B: UI Surface

The tier-assignments endpoint feeds the "Differentiated Groups" card in the teacher view.
The teacher lens endpoint feeds a new "My Teaching Style" card (shows what the system learned).
The holdout score feeds a "Confidence" badge (how well does the system match your style?).

#### 5C: Verification

After wiring, restart the server and run:

```bash
# Server smoke
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool | head -5

# Tier assignments (existing students)
curl -s http://127.0.0.1:8787/api/prepare/tier-assignments | python3 -m json.tool

# RTI change
curl -s -X PUT http://127.0.0.1:8787/api/students/student-marco/rti \
  -H "Content-Type: application/json" \
  -d '{"new_tier": 2, "trigger": "teacher_concern"}' | python3 -m json.tool

# Teacher lens (after ingest)
curl -s http://127.0.0.1:8787/api/teacher/lens | python3 -m json.tool
```

#### 5D: Final Integration Test

```bash
# Everything together
pytest tests/ -q --tb=no 2>&1 | tail -3
python3 -m src.lingua_viva.cli preflight
python3 -m src.lingua_viva.cli health --full --json
```

All must pass. Health must show no new warnings.

---

## Execution Rules

1. **Do NOT modify tests in `tests/evals/`** except to remove `@pytest.mark.skip` or `@pytest.mark.xfail`
2. **Run evals after EVERY implementation step** — not at the end
3. **If a test fails after unskipping, the implementation is wrong** — fix the code, not the test
4. **If you genuinely believe a test spec is wrong**, document why and flag for operator — do not silently change it
5. **Commit after each step passes** — small, verifiable increments
6. **Do not break existing 475 tests** — run the full suite periodically
7. **The truth table is the source of truth for tier assignment** — see `tests/evals/layer4_golden/tier_assignment_truth_table.yaml`
8. **The CONTRACTS.md is the source of truth for interfaces** — see `tests/evals/CONTRACTS.md`

---

## Success Criteria

```bash
# Phase 2 complete:
pytest tests/evals/ -q --tb=no 2>&1 | tail -1
# → "104 passed in Xs"

# Phase 3 complete:
pytest tests/evals/ -q --tb=no 2>&1 | grep "passed"
# → 104 passed, 0 skipped, 0 xfailed

# Phase 4 complete:
pytest tests/ -q --tb=no 2>&1 | tail -1
# → "579 passed" (or close — 475 existing + 104 evals)
# Time: <5s for evals alone

# Phase 5 complete:
curl -s http://127.0.0.1:8787/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
# → "WARN" (pre-existing) or "OK"
curl -s http://127.0.0.1:8787/api/prepare/tier-assignments | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['assignments']), 'students assigned')"
# → "3 students assigned" (or more)
```

---

## Commit Strategy

```
git add -A && git commit -m "fix(edu): RTI 1 + null CEFR → foundational (eval gap 1/4)"
git add -A && git commit -m "fix(edu): Pre-A1 in CEFR_ORDER (eval gap 2/4)"
git add -A && git commit -m "feat(edu): validate_observation_timestamp (eval gap 3/4)"
git add -A && git commit -m "feat(edu): validate CEFR dimension in append_observation (eval gap 4/4)"
git add -A && git commit -m "feat(edu): update_rti_tier with audit trail"
git add -A && git commit -m "feat(edu): get_lens_as_of temporal queries"
git add -A && git commit -m "feat(edu): TeacherLensBuilder — adaptive learning from teacher history"
git add -A && git commit -m "feat(edu): generate_with_teacher_lens — style-matched generation"
git add -A && git commit -m "feat(api): wire tier-assignments, RTI, teacher-lens endpoints"
git add -A && git commit -m "test(evals): unskip all 104 evals — full pass"
```

---

## File Map (what you'll create/modify)

```
MODIFY: src/education/content_differentiator.py  (gaps 1-2, generate_with_teacher_lens)
MODIFY: src/education/student_lens.py            (gaps 3-4, update_rti_tier, get_lens_as_of)
MODIFY: src/lingua_viva/ingest.py                (ALLOWED_DOC_TYPES expansion)
MODIFY: src/web.py                               (new endpoints)
CREATE: src/education/teacher_lens_builder.py     (TeacherLensBuilder)
MODIFY: tests/evals/ (remove skip/xfail markers only — NO assertion changes)
```

---

## Read These Before Starting

1. `tests/evals/CONTRACTS.md` — full interface spec (your Bible)
2. `tests/evals/layer4_golden/tier_assignment_truth_table.yaml` — tier logic source of truth
3. `tests/evals/fixtures/synthetic_teacher_history/` — the format your TeacherLensBuilder must parse
4. `tests/evals/fixtures/synthetic_students.yaml` — roster + canary values
5. `tests/evals/fixtures/synthetic_observations.yaml` — 55 observations with timestamps and canaries
6. `src/education/content_differentiator.py` — existing code you're extending
7. `src/education/student_lens.py` — existing code you're extending

---

## Start

Begin with Step 1 (fix the 4 gaps). They're the smallest changes and will immediately convert 4 xfail into 4 pass. Then proceed sequentially.

Good luck. The evals are the spec. Build to them.
