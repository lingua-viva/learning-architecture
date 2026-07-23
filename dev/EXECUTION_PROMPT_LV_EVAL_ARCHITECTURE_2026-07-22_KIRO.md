# Execution Prompt: Lingua Viva Unified Eval Architecture V1

**Author**: kiro.design (eval designer)  
**Date**: 2026-07-22  
**Target**: The window with full Lingua Viva context (the stalled improvement cycle)  
**Scope**: Design and spec ALL evals. Do NOT implement the functions they test — a separate system builds those.  
**Output**: `tests/evals/` directory with spec files + skeleton test files  

---

## Context You Already Have

You have full context on:
- `src/education/content_differentiator.py` (template + document-backed differentiation)
- `src/education/student_lens.py` (StudentLensStore, observations, CEFR, RTI)
- `src/lingua_viva/ingest.py` + `src/education/document_store.py` + `document_retrieval.py`
- `src/lingua_viva/filemap.py` (file scanning, grade/domain inference)
- `src/web.py` (all API endpoints)
- `ontology/engine.py` (111-node ontology routing)
- `tests/golden_education_v1.yaml` (golden query suite for routing)
- All existing tests in `tests/` (479 passing)

You also know the system's fundamental promise: **a teacher drops their existing documents in, and the system produces differentiated artifacts grounded in those documents, routed to the right students, with zero hallucination and full privacy isolation.**

---

## The Problem This Solves

The existing 479 tests verify the system's _mechanisms_ work (does the parser parse? does the store store? does the endpoint return 200?). What's missing is verification that the system's _promises_ hold:

1. When I ask for Grade 3 content, do I get Grade 3 content and NEVER Grade 4?
2. When I look at Marco's lens, does it contain ONLY Marco's data?
3. When I generate a lesson, does every sentence trace back to a real source document?
4. When the system assigns a student to "foundational" tier, is that assignment deterministically correct per the rules?
5. When a teacher ingests their past work, does the system learn their patterns and produce artifacts that match their style?

These are the properties we must PROVE, not just hope.

---

## Architecture: Five Layers, Zero Overlap

Each layer tests a DIFFERENT property. No two layers test the same thing. If a test could fit in two layers, it goes in the LOWER layer (closer to the data).

```
Layer 5: GAUNTLETS (end-to-end workflow correctness)
  └─ "Does the full teacher story produce correct results?"
  └─ Depends on: Layers 1-4 all passing

Layer 4: GOLDEN ARTIFACTS (output quality & style match)
  └─ "Is this generated artifact actually right/good/matching teacher style?"
  └─ Tests: holdout prediction, CEFR logic, Bloom's taxonomy, bilingual balance

Layer 3: ISOLATION & CONTAMINATION (safety boundaries)
  └─ "Did anything leak where it shouldn't?"
  └─ Tests: student isolation, teacher isolation, temporal integrity, PII boundaries

Layer 2: ADAPTIVE RETRIEVAL & TEACHER LENS (data routing fidelity)
  └─ "Did we pull the right sources? Did we learn the right patterns?"
  └─ Tests: grade fencing, document classification, pattern extraction, holdout scoring

Layer 1: SCHEMA & CONTRACT (structural validity)
  └─ "Does the output have the right shape?"
  └─ Tests: JSON schema conformance, required fields, type correctness
```

---

## IMPORTANT DESIGN PRINCIPLE: Adaptive Teacher Lens

The "golden retrieval map" is NOT a static document that a human validates once. It is LEARNED from the teacher's own historical artifacts:

- Last year's graded exams → grading calibration
- Last year's parent updates → communication voice
- Last year's student evaluations → assessment patterns
- Last year's lesson plans → differentiation style, pacing

The system builds a **Teacher Lens** from these historical documents. The Teacher Lens encodes how THIS specific teacher grades, differentiates, communicates, and assesses. Generated artifacts must match the Teacher Lens — not a generic ideal.

The eval for this is a **holdout test**: train the Teacher Lens on N-1 historical documents, then ask "can the system predict/reproduce the Nth document?" If yes, the lens is working.

This function (`TeacherLensBuilder`) does NOT exist yet. You are writing the eval spec for it. The implementation team will build to your spec.

---

## Your Deliverables

### 1. Spec file: `dev/specs/SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md`

Contains:
- The full 5-layer architecture (as described above)
- Every eval ID, what it tests, pass condition, and which layer it belongs to
- Explicit NON-OVERLAP matrix (which layer owns which property)
- Dependencies between layers
- Required test fixtures (synthetic data needed)
- Required interfaces (what functions/classes the evals will call — these are the contracts the implementation team must satisfy)

### 2. Directory structure: `tests/evals/`

```
tests/evals/
├── __init__.py
├── conftest.py              # Shared fixtures for eval suite
├── README.md                # How to run, what each layer tests
├── layer1_schema/
│   ├── __init__.py
│   ├── schemas/             # JSON Schema files for each artifact type
│   │   ├── student_lens.schema.json
│   │   ├── activity_pack.schema.json
│   │   ├── rubric.schema.json
│   │   ├── observation.schema.json
│   │   ├── privacy_trace.schema.json
│   │   ├── teacher_lens.schema.json
│   │   └── provenance.schema.json
│   └── test_schema_conformance.py
├── layer2_retrieval/
│   ├── __init__.py
│   ├── golden_retrieval_map.yaml    # Expected source → grade/unit mapping
│   ├── test_grade_fencing.py
│   ├── test_document_classification.py
│   ├── test_teacher_lens_extraction.py
│   └── test_retrieval_determinism.py
├── layer3_isolation/
│   ├── __init__.py
│   ├── test_student_isolation.py
│   ├── test_teacher_isolation.py
│   ├── test_temporal_integrity.py
│   └── test_privacy_boundary.py
├── layer4_golden/
│   ├── __init__.py
│   ├── tier_assignment_truth_table.yaml
│   ├── test_tier_logic.py
│   ├── test_cefr_progression.py
│   ├── test_bloom_taxonomy.py
│   ├── test_holdout_prediction.py
│   └── test_bilingual_balance.py
├── layer5_gauntlets/
│   ├── __init__.py
│   ├── test_gauntlet_new_student.py
│   ├── test_gauntlet_lesson_prep.py
│   ├── test_gauntlet_rti_change.py
│   ├── test_gauntlet_contamination_stress.py
│   └── test_gauntlet_wrong_input_rejection.py
└── fixtures/
    ├── synthetic_teacher_history/   # Fake but realistic past-year docs
    │   ├── graded_exam_g3_u1.json
    │   ├── graded_exam_g3_u2.json
    │   ├── parent_update_marco.json
    │   ├── parent_update_nora.json
    │   ├── lesson_plan_g3_u1.json
    │   └── student_evaluation_q1.json
    ├── synthetic_students.yaml      # Test roster (5+ students)
    └── synthetic_observations.yaml  # 50+ observations across students
```

### 3. Each test file as a skeleton

Each test file should contain:
- Module docstring explaining what property this file proves
- All test function signatures with docstrings explaining pass/fail criteria
- `pytest.mark.skip(reason="awaiting implementation of <function>")` on each test
- Comments indicating which interface/function the test will call once implemented
- NO actual assertions yet (those come when implementation ships)

### 4. Interface contracts file: `tests/evals/CONTRACTS.md`

This is what the implementation team reads. It specifies:
- Every function/class the evals expect to exist
- Their signatures (args, return types)
- Their behavioral contracts (what must be true about their outputs)
- Where they should live in the codebase

---

## Layer-by-Layer Eval Specifications

### LAYER 1: Schema & Contract (15 tests)

**Property**: Every output conforms to its declared structure.  
**No model calls. Pure structural. Runs in <1s.**

| Eval ID | Tests | Pass Condition |
|---------|-------|----------------|
| L1-LENS-001 | Student lens JSON matches schema | All required fields, correct types, no extras |
| L1-LENS-002 | Lens with no observations has null CEFR, RTI=1 | Default state is safe |
| L1-PACK-001 | Activity pack has exactly 3 tiers | foundational, on_track, extended — no more, no less |
| L1-PACK-002 | Each tier has required fields | cefr_target, learning_objective, activities[], assessment_criteria |
| L1-PACK-003 | Pack provenance array is non-empty when source_mode=adapted | Grounded generation always has provenance |
| L1-RUBRIC-001 | Rubric has criteria × levels matrix | Every cell non-empty |
| L1-OBS-001 | Observation round-trips through store | Input → store → retrieve is identical |
| L1-OBS-002 | Observation has required timestamp, teacher_id, student_id | No anonymous observations |
| L1-TRACE-001 | Privacy trace has SHA-256 hash, no raw query text | Hash present, query_text field absent or null |
| L1-TRACE-002 | Privacy trace has route_id and external_calls count | Routing + network visibility |
| L1-PROV-001 | Provenance entry has source_file, page_start, section | Minimum grounding metadata |
| L1-PROV-002 | Every referenced source_file exists on disk | No phantom references |
| L1-TLENS-001 | Teacher Lens has grading_calibration, differentiation_style, communication_voice | Core pattern dimensions |
| L1-TLENS-002 | Teacher Lens has ingested_doc_count and last_updated | Metadata for staleness detection |
| L1-TLENS-003 | Teacher Lens pattern entries reference source documents | Patterns trace back to evidence |

### LAYER 2: Adaptive Retrieval & Teacher Lens (20 tests)

**Property**: The system pulls correct sources for the requested grade/unit, and learns accurate patterns from teacher history.  
**May use local Ollama for embeddings. No external API calls.**

| Eval ID | Tests | Pass Condition |
|---------|-------|----------------|
| L2-FENCE-001 | Grade 3 request returns only G3 sources | All provenance contains "G3" or "Grade 3" |
| L2-FENCE-002 | Grade 3 request returns zero G4/G5/G2/G1 sources | Negative fence |
| L2-FENCE-003 | Unit-specific request returns only that unit's sections | No cross-unit bleed |
| L2-FENCE-004 | Non-existent grade returns error, not fabricated content | G9 → 404/error, never a pack |
| L2-FENCE-005 | Empty document store → graceful fallback to template generation | Never blocks teacher |
| L2-DETERM-001 | Same query 3x → identical provenance sets | No randomness in retrieval |
| L2-DETERM-002 | Same teacher history 2x → identical Teacher Lens | Lens build is deterministic |
| L2-CLASS-001 | System classifies graded exam correctly | doc_type = "exam" |
| L2-CLASS-002 | System classifies parent update correctly | doc_type = "parent_update" |
| L2-CLASS-003 | System classifies lesson plan correctly | doc_type = "lesson_plan" |
| L2-CLASS-004 | System classifies student evaluation correctly | doc_type = "evaluation" |
| L2-CLASS-005 | System rejects student-records (privacy boundary) | Blocked type → error |
| L2-EXTRACT-001 | Grading patterns extracted from graded exams | Lens contains calibration with cited examples |
| L2-EXTRACT-002 | Communication voice extracted from parent updates | Lens contains tone/formality/L1-L2 ratio |
| L2-EXTRACT-003 | Differentiation style extracted from lesson plans | Lens contains scaffolding patterns |
| L2-EXTRACT-004 | Assessment weighting extracted from evaluations | Lens contains skill dimension weights |
| L2-INCR-001 | Adding a new doc updates lens without losing old data | Superset property |
| L2-INCR-002 | Removing a doc and rebuilding produces smaller lens | No ghost patterns |
| L2-PAGE-001 | Page numbers in provenance are within document bounds | page_start ≤ page_end ≤ total_pages |
| L2-FILE-001 | File map correctly identifies grade from folder structure | Teaching/G3/*.pdf → grade=3 |

### LAYER 3: Isolation & Contamination (15 tests)

**Property**: Data never crosses boundaries — between students, between teachers, across time, or into traces.  
**Uses canary injection pattern. No model calls.**

| Eval ID | Tests | Pass Condition |
|---------|-------|----------------|
| L3-STU-001 | Canary in Marco's observation absent from Nora's lens | Zero cross-student leakage |
| L3-STU-002 | Canary in Marco's observation absent from Luca's lens | Zero cross-student leakage |
| L3-STU-003 | Canary IS present in Marco's own lens | Positive control |
| L3-STU-004 | Add observation for Nora, Marco's lens byte-identical before/after | No side effects |
| L3-STU-005 | Each observation has exactly one student_id (no nulls, no lists) | Attribution integrity |
| L3-STU-006 | Bulk generate all lenses simultaneously → no cross-contamination | Concurrency safety |
| L3-TCH-001 | Teacher A's lens contains zero data from Teacher B's history | Teacher isolation |
| L3-TCH-002 | Same IB source + different teacher lenses → different outputs | Lens actually influences generation |
| L3-TIME-001 | Lens at time T contains no observations after T | No future data |
| L3-TIME-002 | Lens at time T contains ALL observations through T | No missing data |
| L3-TIME-003 | Observation with future timestamp is rejected | Temporal boundary enforced |
| L3-PRIV-001 | Trace files contain zero student names | Grep all .ndjson for names → 0 |
| L3-PRIV-002 | Support bundle contains zero student PII | No names, scores, observation text |
| L3-PRIV-003 | Generated activity pack contains zero student names | Content is class-level, not student-specific |
| L3-PRIV-004 | File map scan skips student-data zones entirely | is_student_data_zone() → excluded from scan |

### LAYER 4: Golden Artifacts & Correctness (20 tests)

**Property**: Generated artifacts are pedagogically correct and match the teacher's demonstrated style.  
**Uses holdout test pattern and deterministic truth tables.**

| Eval ID | Tests | Pass Condition |
|---------|-------|----------------|
| L4-TIER-001 | Same RTI+CEFR → same tier assignment, 10 runs | 100% identical (deterministic) |
| L4-TIER-002 | RTI 1 + CEFR B2 → extended | Truth table row |
| L4-TIER-003 | RTI 2 + CEFR A1 → foundational | Truth table row |
| L4-TIER-004 | RTI 3 + CEFR null → foundational (safest default) | Truth table row |
| L4-TIER-005 | RTI 1 + CEFR A2 → on_track | Truth table row |
| L4-TIER-006 | Full truth table (all RTI×CEFR combinations) passes | Exhaustive |
| L4-CEFR-001 | foundational.cefr_target < on_track.cefr_target < extended.cefr_target | Monotonic ordering |
| L4-CEFR-002 | A1 target → foundational cannot go below A1 | Floor clamp |
| L4-CEFR-003 | C2 target → extended cannot go above C2 | Ceiling clamp |
| L4-BLOOM-001 | Foundational objectives use identify/name/list/recognize | Low Bloom's |
| L4-BLOOM-002 | On_track objectives use explain/compare/connect | Mid Bloom's |
| L4-BLOOM-003 | Extended objectives use analyze/evaluate/argue/investigate | High Bloom's |
| L4-HOLD-001 | Train on 9 exams, predict grading on 10th → criteria overlap ≥70% | Holdout: exam |
| L4-HOLD-002 | Train on 4 parent updates, predict 5th → voice match ≥60% vocabulary overlap | Holdout: communication |
| L4-HOLD-003 | Train on 4 lesson plans, predict 5th → same differentiation approach | Holdout: scaffolding |
| L4-HOLD-004 | Train on 4 evaluations, predict 5th → same strengths/growth identified | Holdout: assessment |
| L4-LANG-001 | Foundational tier readability ≤ grade level + 1 | Age-appropriate language |
| L4-LANG-002 | Extended tier readability ≥ grade level | Not dumbed down |
| L4-BILING-001 | Unit specifying 70% Italian → activities maintain 60-80% Italian | Ratio within ±10% |
| L4-BILING-002 | English scaffolding appears only in foundational tier | L1 support is differentiated |

### LAYER 5: End-to-End Gauntlets (5 gauntlets, ~25 assertions)

**Property**: Full teacher workflows produce correct, safe, grounded results across the entire chain.  
**Each gauntlet is a multi-step scenario that exercises all layers together.**

#### Gauntlet 1: New Student Onboarding
- New student added with no data → appears in roster
- Default tier assignment → foundational (safest)
- No hallucinated CEFR before observations justify it
- First observation → lens updates, CEFR starts populating
- After 5 observations → trajectory calculated

#### Gauntlet 2: Adaptive Lesson Preparation
- Teacher ingests 3 past lesson plans for G3
- Teacher Lens builds from those plans
- Request G3-U1 activity pack
- Pack provenance traces only to G3 documents
- Pack differentiation matches teacher's historical style (holdout-like check)
- Zero content from G4/G5 appears anywhere

#### Gauntlet 3: RTI Tier Change Propagation
- Marco at RTI 1 → teacher changes to RTI 2
- Next tier assignment reflects new RTI
- Historical lens preserves old observations unchanged
- Other students' assignments unaffected
- Audit trail shows the change with timestamp

#### Gauntlet 4: Contamination Stress Test
- 10 students, 50 observations each
- Each lens contains exactly that student's observations
- No observation appears in two lenses
- Removing one student doesn't affect others
- Re-running produces identical results

#### Gauntlet 5: Wrong Input Rejection
- G9 request → error, not fabricated content
- Non-existent student → 404, not empty lens
- Future-dated observation → rejected
- Student name in teacher query → redacted in trace
- student-records doc type → blocked at ingest

---

## Interface Contracts (What the Implementation Team Must Build)

The evals will call these interfaces. The implementation team must satisfy these contracts.

### TeacherLensBuilder (NEW — does not exist yet)

```python
class TeacherLensBuilder:
    """Build a Teacher Lens from historical teaching artifacts."""

    def __init__(self, teacher_id: str, storage_path: Path):
        ...

    def ingest(self, file_path: Path, doc_type: str = "auto") -> IngestResult:
        """Ingest one historical document. Returns classification + extraction result.
        
        doc_type: "auto" | "exam" | "parent_update" | "evaluation" | "lesson_plan" | "rubric"
        When "auto", system classifies from content.
        
        Returns: IngestResult with fields:
          - doc_id: str (unique identifier)
          - classified_type: str (detected doc type)
          - patterns_extracted: list[str] (what was learned)
          - confidence: float (0-1, how confident in classification)
        """

    def classify(self, file_path: Path) -> DocClassification:
        """Identify document type without ingesting.
        
        Returns: DocClassification with fields:
          - doc_type: str
          - confidence: float
          - signals: list[str] (what triggered the classification)
        """

    def build_lens(self) -> TeacherLens:
        """Synthesize all ingested patterns into a coherent Teacher Lens.
        
        Returns: TeacherLens with fields:
          - teacher_id: str
          - grading_calibration: dict (criteria → examples from exams)
          - differentiation_style: dict (tier → scaffolding pattern)
          - communication_voice: dict (formality, L1_L2_ratio, focus_areas)
          - assessment_weighting: dict (dimension → weight 0-1)
          - pacing_style: dict (unit → typical_duration)
          - ingested_doc_count: int
          - last_updated: str (ISO8601)
          - source_documents: list[dict] (doc_id, type, ingested_at)
        """

    def holdout_score(self, test_artifact: Path, artifact_type: str) -> HoldoutResult:
        """Score: given the current lens, can we predict/reproduce this artifact?
        
        Returns: HoldoutResult with fields:
          - overall_score: float (0-1)
          - criteria_overlap: float (0-1, for exams/rubrics)
          - vocabulary_overlap: float (0-1, for parent updates)
          - structural_match: float (0-1, for lesson plans)
          - detail: str (human-readable explanation)
        """
```

### ContentDifferentiator Extensions (partially exists)

```python
class ContentDifferentiator:
    # EXISTING: generate(lesson) → template-based pack
    # EXISTING: generate_from_documents(lesson, retriever, domain) → document-backed pack

    def generate_with_teacher_lens(
        self, lesson: LessonInput, teacher_lens: TeacherLens, retriever=None
    ) -> ActivityPack:
        """Generate a pack that matches this teacher's style.
        
        Uses teacher_lens to:
        - Select scaffolding approach (from differentiation_style)
        - Choose vocabulary complexity (from grading_calibration)
        - Apply assessment criteria (from assessment_weighting)
        
        Falls back to generate_from_documents() if teacher_lens is None.
        Falls back to generate() if retriever is also None.
        """

    def assign_tier_for_student(self, student_lens: dict) -> str:
        """Deterministic tier assignment from student's RTI + CEFR data.
        
        Rules (must match tier_assignment_truth_table.yaml exactly):
        - RTI 3 (any CEFR) → "foundational"
        - RTI 2 + CEFR ≤ A2 → "foundational"
        - RTI 2 + CEFR ≥ B1 → "on_track"
        - RTI 1 + CEFR ≤ A2 → "on_track"
        - RTI 1 + CEFR ≥ B1 → "extended"
        - Any RTI + CEFR null → "foundational" (safest default)
        
        Returns: "foundational" | "on_track" | "extended"
        """
```

### StudentLensStore Extensions (partially exists)

```python
class StudentLensStore:
    # EXISTING: create_lens, append_observation, get_lens, list_lenses

    def get_lens_as_of(self, student_id: str, as_of: str) -> dict:
        """Return lens state as it was at a specific point in time.
        
        Only includes observations with timestamp <= as_of.
        CEFR snapshot reflects only those observations.
        RTI tier reflects the tier active at that time.
        """

    def validate_observation_timestamp(self, obs: Observation) -> list[str]:
        """Reject observations with timestamps in the future.
        Returns list of validation errors (empty = valid).
        """
```

---

## Fixture Requirements

### Synthetic Teacher History (`tests/evals/fixtures/synthetic_teacher_history/`)

Create realistic but fake teaching artifacts that exercise the Teacher Lens:

1. **5 graded exams** (G3, Italian language) — each with criteria, student work samples, grades assigned. Must show a consistent grading pattern (e.g., this teacher consistently weighs "grammatical accuracy" over "creative expression").

2. **5 parent updates** — formal, bilingual (Italian/English), focusing on social-emotional growth first then academic. Must show a consistent communication voice.

3. **5 lesson plans** (G3 Italian) — showing differentiation pattern: foundational always gets visual scaffolds + word banks, extended always gets open-ended creative extension.

4. **5 student evaluations** — quarterly, showing how this teacher assesses speaking (40%), writing (30%), reading (30%).

Format: JSON with fields that map to the document types the classifier must recognize. Include enough signal for pattern extraction but keep them synthetic (no real student data).

### Synthetic Student Roster (`tests/evals/fixtures/synthetic_students.yaml`)

5+ students with varying RTI/CEFR profiles:
- Sofia: RTI 1, CEFR B2 all dimensions (should get extended)
- Marco: RTI 1, CEFR A2 reading/A1 writing (should get on_track)
- Nora: RTI 2, CEFR null (should get foundational)
- Luca: RTI 3, CEFR B1 (should get foundational despite B1 — RTI 3 overrides)
- Elena: RTI 1, CEFR null (should get foundational — null is safest)

### Synthetic Observations (`tests/evals/fixtures/synthetic_observations.yaml`)

50+ observations across the 5 students. Must include:
- Canary values (unique strings per student for isolation testing)
- Timestamps spanning a school year (September → June)
- Multiple CEFR dimensions per student
- At least one RTI tier change mid-year

---

## Execution Rules

1. **Write the spec FIRST** (`dev/specs/SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md`)
2. **Then create the directory structure and skeleton test files**
3. **Then create CONTRACTS.md** (the interface spec for implementation team)
4. **Then create fixtures** (synthetic data)
5. **Every test must be `pytest.mark.skip`** with a reason pointing to the unbuilt function
6. **No test may overlap with another** — if you're unsure where a test belongs, put it in the LOWER layer
7. **Run `pytest tests/evals/ --co` at the end** to verify all tests are discoverable (collected but skipped)
8. **Do NOT modify any existing code** in `src/` — you are only creating evals
9. **Do NOT modify existing tests** in `tests/` — the eval suite is additive

---

## Success Criteria

When you're done, this must be true:

```bash
# All evals are discoverable
pytest tests/evals/ --co | grep "test session starts"
# → should show 75+ test items collected

# All evals skip cleanly (nothing crashes on import)
pytest tests/evals/ -v 2>&1 | grep -c "SKIPPED"
# → should equal the number collected above

# Existing tests still pass (you broke nothing)
pytest tests/ -q --ignore=tests/evals/ --tb=no 2>&1 | tail -1
# → 479 passed

# The spec exists and is >3000 words
wc -w dev/specs/SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md
# → >3000

# The contracts file exists
cat tests/evals/CONTRACTS.md | head -5
# → should show the interface spec header
```

---

## What NOT To Do

- Do NOT implement `TeacherLensBuilder` — only spec its interface and write evals against it
- Do NOT implement `assign_tier_for_student` — only spec the truth table and write evals
- Do NOT implement `get_lens_as_of` — only spec the temporal behavior and write evals
- Do NOT implement `generate_with_teacher_lens` — only spec the contract
- Do NOT touch `src/web.py`, `src/education/`, or `src/lingua_viva/` code
- Do NOT modify or refactor existing tests
- Do NOT make any assertions that test current behavior — all tests are forward-looking (skipped)

Your job is to define what "correct" means. Another system will build to that definition.

---

## Final Note

This eval architecture replaces the need for a human expert to manually validate a "golden retrieval map." Instead, the teacher's OWN past work IS the ground truth. The holdout pattern (train on N-1, predict Nth) is how we prove the system learned correctly without requiring a human in the eval loop.

The ultimate proof of "perfect state": a teacher ingests last year's work, generates this year's first lesson, and the holdout score is ≥80%.

Build the evals that prove or disprove that claim.
