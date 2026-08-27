# BUILD PROMPT: Lingua Viva — End-to-End Gauntlet

You are building a comprehensive gauntlet that proves every LV subsystem works
together with realistic data — from file import through student detection through
lesson plan generation through parent report through print. The synthetic corpus
already exists (`tests/fixtures/docpipe/synthetic-corpus/`) with labeled expectations.
The anonymized real-student data exists (`tests/fixtures/docpipe/real_anon/`). The
5-layer eval framework exists (`tests/evals/`). You are tying them all together into
one end-to-end gauntlet that a teacher could trust.

## Context — Read All of These Before Writing Any Code

**The data you have:**
- `tests/fixtures/docpipe/synthetic-corpus/labels.json` — read this FIRST. It defines
  the expected outcomes for each synthetic file (19 expected students, file shapes,
  sealed/unsealed status)
- `tests/fixtures/docpipe/synthetic-corpus/synthetic_class_list.xlsx` — 19 students
- `tests/fixtures/docpipe/synthetic-corpus/synthetic_support_3v.xlsx` — support data
- `tests/fixtures/docpipe/synthetic-corpus/synthetic_support_k5.xlsx` — K-5 support data
- `tests/fixtures/docpipe/synthetic-corpus/synthetic_curriculum.xlsx` — curriculum (0 students)
- `tests/fixtures/docpipe/synthetic-corpus/synthetic_calendar.xlsx` — calendar (0 students)
- `tests/fixtures/docpipe/real_anon/` — anonymized real-student data (Aron, Jerry)
- `tests/fixtures/docpipe/real_anon/README.md` — anonymization key and purpose
- `references/` — real IB curriculum PDFs (Italian curriculum, CEFR)

**The systems to test:**
- `src/lingua_viva/docpipe/extract.py` — document extraction + student detection
- `src/lingua_viva/docpipe/identity.py` — student identity resolution
- `src/lingua_viva/docpipe/lens.py` — student lens building from documents
- `src/lingua_viva/lesson_materials.py` — lesson plan generation + revision
- `src/education/parent_report.py` — parent report generation
- `src/education/student_lens.py` — student profiles + observations
- `src/education/content_differentiator.py` — tiered content differentiation
- `src/lingua_viva/safeguarding.py` — safeguarding pipeline
- `src/lingua_viva/grounding/` — GIR computation
- `knowledge/education/` — all knowledge entries (curriculum, ATL, learner profile, Italian L2)
- `templates/lesson_plan.html` — lesson plan template
- `templates/parent_report.html` — parent report template
- `src/web.py` + `src/lingua_viva/routers/` — API endpoints

**The eval framework (extend, don't replace):**
- `tests/evals/` — 5 layers (schema, retrieval, isolation, golden, gauntlets)
- `tests/evals/layer5_gauntlets/` — existing gauntlet tests (study the pattern)
- `tests/evals/conftest.py` — shared fixtures
- `tests/evals/CONTRACTS.md` — the eval contracts

**The golden queries:**
- `tests/golden_education_v1.yaml` — 51 goldens (36 original + 10 lesson plan + 5 parent)

Set `export MC_AGENT=1` before any pipeline queries.

## What You Are Building

A 6-phase end-to-end gauntlet in `tests/gauntlet/` that exercises the FULL teacher
workflow: import files → detect students → generate lesson plans → capture observations
→ generate parent reports → verify privacy → verify grounding. All against the
synthetic corpus data (deterministic, labeled, exact assertions possible).

### The Gauntlet Fixture

Create `tests/gauntlet/conftest.py`:

```python
"""Shared gauntlet fixture: a complete LV environment with 19 students imported.

Uses the synthetic corpus (tests/fixtures/docpipe/synthetic-corpus/) which has:
- synthetic_class_list.xlsx: 19 expected students
- synthetic_support_3v.xlsx: 3V support data
- synthetic_support_k5.xlsx: K-5 support data
- synthetic_curriculum.xlsx: curriculum (0 students)
- synthetic_calendar.xlsx: calendar (0 students)
- labels.json: expected outcomes for every file

The fixture imports all files, confirms student detection, and provides
a fully populated environment for all subsequent phases.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / 'fixtures' / 'docpipe' / 'synthetic-corpus'
LABELS = json.loads((CORPUS_DIR / 'labels.json').read_text())
REAL_ANON_DIR = Path(__file__).parent.parent / 'fixtures' / 'docpipe' / 'real_anon'


@pytest.fixture(scope="session")
def gauntlet_env(tmp_path_factory):
    """Full LV environment with synthetic corpus imported."""
    base = tmp_path_factory.mktemp("lv_gauntlet")
    
    # Set up student store, knowledge, ontology in temp dir
    # Import each file from the synthetic corpus
    # Return the populated environment
    
    # You'll need to understand how the ingest pipeline works:
    # Read src/lingua_viva/ingest.py or src/web.py ingest routes
    # The key function is likely ingest_document() or similar
    
    ...
    
    return {
        "base_dir": str(base),
        "student_store": student_store,
        "expected_students": LABELS["files"][0]["expected_students"],  # 19 names
        "corpus_dir": str(CORPUS_DIR),
        "real_anon_dir": str(REAL_ANON_DIR),
        "labels": LABELS,
    }
```

IMPORTANT: Read the actual ingest pipeline to understand how to call it
programmatically. Check `src/lingua_viva/ingest.py`, `src/web.py` ingest
routes, and `tests/test_students_ingest.py` for the correct API.

### Phase 1: Import + Detection

Create `tests/gauntlet/01_import_detection.py`:

```python
"""Phase 1: Import the synthetic corpus and verify student detection.

The synthetic corpus has labeled expectations. Every assertion is EXACT.
"""

class TestClassListImport:
    def test_detect_19_students(self, gauntlet_env):
        """synthetic_class_list.xlsx → exactly 19 students detected."""
        expected = gauntlet_env["expected_students"]
        # Import the class list
        # Assert: detected count == 19
        # Assert: every expected name is found
    
    def test_no_false_positives(self, gauntlet_env):
        """Zero non-student rows detected as students."""
        # The class list has "stacked 1/2-groups tables" that are NOT students
        # Assert: only the 19 labeled names are detected
    
    def test_student_names_exact(self, gauntlet_env):
        """Every detected name matches the expected list exactly."""
        expected = set(gauntlet_env["expected_students"])
        # detected = set of names from the import
        # Assert: detected == expected (set equality)

class TestSupportFileImport:
    def test_3v_support_detection(self, gauntlet_env):
        """synthetic_support_3v.xlsx → support entries linked to students."""
        # Import the 3V support file
        # Assert: support data detected (count > 0)
        # Assert: names match a subset of the 19 class list students
    
    def test_k5_support_detection(self, gauntlet_env):
        """synthetic_support_k5.xlsx → K-5 support entries detected.
        
        This tests the per_class_sheet_support genre (built in Stream 1).
        Expected: precision ≥0.90, recall ≥0.60.
        """
    
    def test_abbreviated_name_resolution(self, gauntlet_env):
        """Abbreviated names from support sheet matched to full names."""
        # K-5 support has abbreviated names ("Sofia M.")
        # These should queue for human confirmation against the class list

class TestNonStudentFiles:
    def test_curriculum_zero_students(self, gauntlet_env):
        """synthetic_curriculum.xlsx → 0 students detected."""
    
    def test_calendar_zero_students(self, gauntlet_env):
        """synthetic_calendar.xlsx → 0 students detected."""
    
    def test_pdf_curriculum_extraction(self, gauntlet_env):
        """references/Criteri_Fondanti_Curricolo_Italiano_K-5.pdf → 
        content extracted, zero students."""
```

### Phase 2: Student Lens + Observations

Create `tests/gauntlet/02_student_lens.py`:

```python
"""Phase 2: Build student lenses and capture observations.

After import, each student should have a lens. Observations should
persist, be queryable, and feed into reports.
"""

class TestStudentLensCreation:
    def test_19_lenses_exist(self, gauntlet_env):
        """After import, 19 student lens records exist."""
    
    def test_lens_has_required_fields(self, gauntlet_env):
        """Each lens has: name, grade, tier (if assigned), observations list."""
    
    def test_lens_with_support_data(self, gauntlet_env):
        """Students who appear in support files have enriched lenses."""

class TestObservationCapture:
    def test_capture_observation(self, gauntlet_env):
        """Capture an observation for Marco → stored in student store."""
        # Simulate: "Marco showed great progress in reading today"
        # Assert: observation persists with timestamp, content, evidence
    
    def test_duplicate_detection(self, gauntlet_env):
        """Same observation within 300 seconds → deduplicated."""
    
    def test_observation_feeds_parent_report(self, gauntlet_env):
        """Captured observations appear in parent report data."""
    
    def test_observation_privacy(self, gauntlet_env):
        """Observation content stays local — never in any log or external call."""

class TestRealAnonData:
    def test_aron_observation_loads(self, gauntlet_env):
        """real_anon/observation_aron.json loads cleanly."""
    
    def test_jerry_observation_loads(self, gauntlet_env):
        """real_anon/observation_jerry.json loads cleanly."""
    
    def test_lesson_plan_fixture_loads(self, gauntlet_env):
        """real_anon/lesson_plan_aron.md is valid lesson content."""
    
    def test_student_work_fixture_loads(self, gauntlet_env):
        """real_anon/student_work_aron.md loads cleanly."""
```

### Phase 3: Lesson Plan Generation

Create `tests/gauntlet/03_lesson_plans.py`:

```python
"""Phase 3: Generate lesson plans and verify the full artifact loop.

Tests: generation → structured output → template rendering → revision → print.
All against the imported 19-student classroom.
"""

class TestLessonPlanGeneration:
    def test_generate_italian_lesson(self, gauntlet_env):
        """Generate a lesson plan for Grade 3 Italian, family vocabulary.
        
        Assert: structured JSON output with all required sections
        (subject, grade, topic, learning_objectives, lesson_structure,
        differentiation, assessment).
        """
    
    def test_plan_has_3_tiers(self, gauntlet_env):
        """Differentiation section has foundation, core, extension tiers."""
    
    def test_plan_cites_curriculum(self, gauntlet_env):
        """Plan references a KL entry (IB PYP, ATL, or Italian L2 pedagogy)."""
    
    def test_plan_references_atl(self, gauntlet_env):
        """When ATL skill is requested, plan cites ATL knowledge entry."""
    
    def test_plan_references_learner_profile(self, gauntlet_env):
        """When Learner Profile attribute is mentioned, plan cites LP entry."""

class TestLessonPlanRendering:
    def test_html_renders(self, gauntlet_env):
        """Lesson plan JSON → HTML via template → valid HTML output."""
    
    def test_html_has_all_sections(self, gauntlet_env):
        """Rendered HTML contains: header, objectives, materials, structure,
        differentiation, assessment, teacher notes."""
    
    def test_html_no_student_names(self, gauntlet_env):
        """Rendered HTML never contains individual student names.
        Differentiation is by tier, not by student."""
    
    def test_print_safe(self, gauntlet_env):
        """Print rendering uses stored artifact, zero model calls."""

class TestLessonPlanRevision:
    def test_add_song_revises_warmup(self, gauntlet_env):
        """'Add a song' → warm-up section mentions song/music."""
    
    def test_harder_extension_revises_extension(self, gauntlet_env):
        """'Make extension harder' → extension tier updated, others unchanged."""
    
    def test_revision_preserves_all_sections(self, gauntlet_env):
        """After revision, every required section still exists."""
    
    def test_three_sequential_revisions(self, gauntlet_env):
        """Three revisions compound without section loss."""
    
    def test_revision_no_student_names(self, gauntlet_env):
        """Revision never introduces student names into the artifact."""

class TestContentDifferentiation:
    def test_3_tiers_produced(self, gauntlet_env):
        """Content differentiator produces 3 tiers for any input."""
    
    def test_cefr_alignment(self, gauntlet_env):
        """Tiers align with CEFR levels (foundation=A1, core=A2, extension=B1)."""
    
    def test_invalid_grade_fallback(self, gauntlet_env):
        """Grade 9 or unusual grade → produces content, never crashes."""
```

### Phase 4: Parent Reports

Create `tests/gauntlet/04_parent_reports.py`:

```python
"""Phase 4: Generate parent reports from observation history.

Tests: observation capture → report generation → template rendering →
privacy verification → print-safe flow.
"""

class TestParentReportGeneration:
    def test_report_for_student_with_observations(self, gauntlet_env):
        """Student with captured observations → report has strengths + growth areas."""
    
    def test_report_for_student_without_observations(self, gauntlet_env):
        """Student with no observations → honest empty sections, not fabricated."""
    
    def test_report_sections_structure(self, gauntlet_env):
        """Report has: student_name, grade, period, strengths, growth_areas, intro."""
    
    def test_report_grounded_in_evidence(self, gauntlet_env):
        """Every strength/growth claim traceable to an observation."""

class TestParentReportRendering:
    def test_html_renders(self, gauntlet_env):
        """Parent report data → HTML via template → valid output."""
    
    def test_html_has_fill_in_line(self, gauntlet_env):
        """Student name has a fill-in line (not pre-filled for privacy)."""
    
    def test_html_signature_line(self, gauntlet_env):
        """Template has teacher signature + date line."""
    
    def test_empty_sections_honest(self, gauntlet_env):
        """Empty sections say 'None noted for this period.' not blank."""

class TestParentReportPrivacy:
    def test_no_other_students_mentioned(self, gauntlet_env):
        """Report for Marco never mentions Sofia, Emma, or any other student."""
    
    def test_publication_safety_gate(self, gauntlet_env):
        """Report passes the publication safety check before rendering."""
    
    def test_no_internal_notes_in_report(self, gauntlet_env):
        """Teacher's private observation notes don't appear in parent report."""
```

### Phase 5: Knowledge Grounding

Create `tests/gauntlet/05_knowledge_grounding.py`:

```python
"""Phase 5: Verify knowledge library grounding across the system.

Every generated artifact should cite real knowledge entries.
No fabricated standards, no hallucinated curriculum references.
"""

class TestKnowledgeAvailability:
    def test_curriculum_ib_entries_load(self, gauntlet_env):
        """curriculum_ib.yaml entries are loadable and valid."""
    
    def test_atl_entries_load(self, gauntlet_env):
        """atl_approaches_to_learning.yaml entries are loadable."""
    
    def test_learner_profile_entries_load(self, gauntlet_env):
        """learner_profile.yaml entries are loadable."""
    
    def test_italian_l2_entries_load(self, gauntlet_env):
        """italian_l2_pedagogy.yaml entries are loadable."""
    
    def test_differentiation_entries_load(self, gauntlet_env):
        """differentiation.yaml entries are loadable."""
    
    def test_total_education_entries(self, gauntlet_env):
        """Total education knowledge entries ≥ 60 (after Day 3 additions)."""
    
    def test_all_entries_have_citations(self, gauntlet_env):
        """Every knowledge entry has at least one citation."""
    
    def test_all_entries_have_ontology_nodes(self, gauntlet_env):
        """Every knowledge entry maps to at least one LV-* ontology node."""
    
    def test_no_duplicate_ids(self, gauntlet_env):
        """No two knowledge entries share the same ID."""

class TestGroundingInArtifacts:
    def test_lesson_plan_cites_real_kl(self, gauntlet_env):
        """Generated lesson plan cites a KL ID that actually exists."""
    
    def test_lesson_plan_no_fabricated_standards(self, gauntlet_env):
        """Lesson plan does not cite standards that don't exist in the KL."""
    
    def test_learner_profile_attributes_valid(self, gauntlet_env):
        """Any Learner Profile attribute in a lesson plan is one of the official 10."""
    
    def test_atl_categories_valid(self, gauntlet_env):
        """Any ATL category in a lesson plan is one of the official 5."""

class TestGIR:
    def test_gir_computation(self, gauntlet_env):
        """GIR is computable for a grounded response."""
    
    def test_ungrounded_certainty_caught(self, gauntlet_env):
        """A certainty claim about curriculum with no source → flagged."""
```

### Phase 6: Privacy + Safeguarding

Create `tests/gauntlet/06_privacy.py`:

```python
"""Phase 6: Privacy and safeguarding gauntlet.

The most important phase. Student data is sacred. This phase verifies
that no student name, no student data, and no sensitive information
leaks through any path in the system.
"""

class TestStudentNameContainment:
    def test_no_names_in_lesson_plan(self, gauntlet_env):
        """Lesson plan HTML never contains any of the 19 student names."""
    
    def test_no_names_in_parent_report_body(self, gauntlet_env):
        """Parent report body doesn't leak OTHER students' names."""
    
    def test_no_names_in_revision_output(self, gauntlet_env):
        """Revised lesson plan doesn't introduce student names."""
    
    def test_no_names_in_observation_logs(self, gauntlet_env):
        """System logs (if any) hash student names, never plaintext."""
    
    def test_no_names_in_error_messages(self, gauntlet_env):
        """Error paths don't include student names in stack traces."""

class TestDataBoundary:
    def test_student_data_never_external(self, gauntlet_env):
        """Queries about students route to LOCAL model only."""
    
    def test_curriculum_data_can_go_external(self, gauntlet_env):
        """Generic curriculum queries can use external model."""
    
    def test_observation_data_local_only(self, gauntlet_env):
        """Observations stored locally, never sent to any external service."""

class TestSafeguarding:
    def test_safeguarding_pipeline_runs(self, gauntlet_env):
        """Safeguarding check runs on observation content."""
    
    def test_red_severity_flagged(self, gauntlet_env):
        """Observation with safeguarding keywords → RED severity flag."""

class TestTTSPrivacy:
    def test_student_name_blocks_tts(self, gauntlet_env):
        """Text containing a student name → TTS blocked, browser fallback."""
    
    def test_curriculum_text_tts_ok(self, gauntlet_env):
        """Generic curriculum text → TTS allowed."""

class TestVoicePrivacy:
    def test_voice_observation_name_detected(self, gauntlet_env):
        """Voice input 'Marco did great today' → 'Marco' matched to roster."""
    
    def test_voice_observation_stays_local(self, gauntlet_env):
        """Voice-captured observation routed to local model."""

class TestDocumentPrivacy:
    def test_imported_xlsx_not_in_repo(self, gauntlet_env):
        """After import, the source XLSX is not copied to any git-tracked path."""
    
    def test_student_data_not_in_knowledge(self, gauntlet_env):
        """No student name appears in any knowledge/*.yaml file."""
```

### The Gauntlet Runner

Create `tests/gauntlet/__init__.py` (empty) and add a CLI hook if desired:

The gauntlet can be run via:
```bash
# Full gauntlet
python3 -m pytest tests/gauntlet/ -q

# Single phase
python3 -m pytest tests/gauntlet/01_import_detection.py -q
python3 -m pytest tests/gauntlet/06_privacy.py -q

# With verbose output
python3 -m pytest tests/gauntlet/ -v
```

## Verification

```bash
# Run the full gauntlet
python3 -m pytest tests/gauntlet/ -q
# Expected: 60-80 tests, all passing

# Run with the rest of the suite
python3 -m pytest tests/ -q
# Expected: 2516+ existing + 60-80 gauntlet = 2576+
# The 8 known baseline failures are still expected

# Verify no gauntlet test requires an LLM
TROP_TEST_MODE=1 python3 -m pytest tests/gauntlet/ -q
# Should still pass — all deterministic

# Verify gauntlet runs in under 2 minutes
time python3 -m pytest tests/gauntlet/ -q
```

## Build Order

1. **Read labels.json** — understand the expected outcomes (15 min)
2. **Read existing ingest tests** — understand how to call the pipeline programmatically (30 min)
3. **Build conftest.py** — the shared fixture that imports the synthetic corpus (1 hour)
4. **Phase 1: Import + Detection** (1 hour)
5. **Phase 2: Student Lens + Observations** (45 min)
6. **Phase 3: Lesson Plans** (1.5 hours)
7. **Phase 4: Parent Reports** (45 min)
8. **Phase 5: Knowledge Grounding** (45 min)
9. **Phase 6: Privacy** (1.5 hours — the most important phase)
10. **Run full suite, verify** (30 min)

Total: 7-9 hours.

## Rules

- ALL assertions are EXACT — the synthetic corpus is deterministic
- No LLM calls in any gauntlet test — test deterministic paths only
- The privacy phase (Phase 6) is the most important — budget extra time for it
- Use the EXISTING synthetic corpus data — do NOT create new test data
- Use the EXISTING real_anon data for the real-data fixture tests
- The gauntlet must run in ISOLATION — temp directories, no modification of real data
- If a test requires a running web server, mock it or use the test client
- Do NOT modify existing tests or eval framework — only ADD new tests
- The 8 known baseline failures are NOT yours — do not fix them
- Every student name in the synthetic corpus (19 names from labels.json) must be
  checked in the privacy tests — hardcode them as the containment list
- Commit when all phases pass. Push to origin.
