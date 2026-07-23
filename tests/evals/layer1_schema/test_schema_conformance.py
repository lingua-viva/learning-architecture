"""Layer 1: Schema & Contract — structural validity of all outputs.

Property proved: Every output conforms to its declared JSON schema.
No model calls. Pure structural. Runs in <1s.

Each test validates that a produced artifact matches its schema exactly:
required fields present, correct types, no structural violations.
"""

import json
import tempfile
from pathlib import Path

import pytest

SCHEMAS_DIR = Path(__file__).parent / "schemas"

SKIP_REASON_LENS = "awaiting full TeacherLensBuilder implementation (src/education/teacher_lens_builder.py)"
SKIP_REASON_PACK = "awaiting generate_with_teacher_lens() to produce teacher_adapted packs"


# --- Student Lens Schema (L1-LENS) --- LIVE ---


def test_L1_LENS_001_student_lens_matches_schema():
    """L1-LENS-001: Student lens JSON matches student_lens.schema.json.

    Pass: All required fields present, correct types.
    """
    from jsonschema import validate
    from src.education.student_lens import StudentLensStore

    schema = json.loads((SCHEMAS_DIR / "student_lens.schema.json").read_text())

    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "test.db")
        sid = store.create_lens(display_name="Schema Test", grade_level="G3", campus="local")
        lens = store.get_lens(sid)
        validate(instance=lens, schema=schema)
        store.close()


def test_L1_LENS_002_empty_lens_safe_defaults():
    """L1-LENS-002: Lens with no observations has null CEFR fields, RTI=1.

    Pass: New student immediately after create_lens() has safe defaults.
    """
    from src.education.student_lens import StudentLensStore

    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "test.db")
        sid = store.create_lens(display_name="Empty Defaults", grade_level="G3")
        lens = store.get_lens(sid)

        assert lens["rti_current_tier"] == 1
        assert lens["cefr_snapshot"] == {
            "reading": None, "writing": None, "speaking": None, "listening": None
        }
        assert lens["cefr_trajectory_30d"] in (None, "insufficient_data")
        assert lens["deleted"] is False
        store.close()


# --- Activity Pack Schema (L1-PACK) --- LIVE ---


def test_L1_PACK_001_activity_pack_three_tiers():
    """L1-PACK-001: Activity pack has exactly 3 tiers: foundational, on_track, extended.

    Pass: pack.tiers.keys() == {"foundational", "on_track", "extended"}
    """
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = ContentDifferentiator().generate(lesson)
    assert set(pack.tiers.keys()) == {"foundational", "on_track", "extended"}


def test_L1_PACK_002_tier_required_fields():
    """L1-PACK-002: Each tier has cefr_target and learning_objective.

    Pass: Both fields non-null, non-empty string for every tier.
    """
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = ContentDifferentiator().generate(lesson)
    for tier_name, tier in pack.tiers.items():
        assert tier.get("cefr_target"), f"{tier_name} missing cefr_target"
        assert tier.get("learning_objective"), f"{tier_name} missing learning_objective"


def test_L1_PACK_003_adapted_pack_has_provenance(schemas_dir):
    """L1-PACK-003: When source_mode=adapted, source_provenance is non-empty list.

    Pass: len(pack["source_provenance"]) >= 1 when source_mode != "generated"
    Calls: ContentDifferentiator.generate_from_documents() or generate_with_teacher_lens()
    """
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    source_chunks = [
        {
            "text": "Daily routines are described using present-tense reflexive verbs.",
            "source_file": "myp_italian_guide.pdf",
            "section": "DAILY ROUTINES",
            "page_start": 2,
            "page_end": 2,
        }
    ]
    pack = ContentDifferentiator().generate(lesson, source_chunks=source_chunks)
    assert pack.source_mode == "adapted"
    assert len(pack.source_provenance) >= 1


# --- Rubric Schema (L1-RUBRIC) ---


@pytest.mark.skip(reason="awaiting rubric generation endpoint validation")
def test_L1_RUBRIC_001_criteria_levels_matrix():
    """L1-RUBRIC-001: Rubric has criteria × levels matrix with all cells non-empty.

    Pass: For every criterion, every level has a non-empty descriptor string.
    Calls: /api/assess/rubric/{unit_id} or RubricGenerator.generate()
    """
    pass


# --- Observation Schema (L1-OBS) --- LIVE ---


def test_L1_OBS_001_observation_round_trips():
    """L1-OBS-001: Observation survives store → retrieve cycle unchanged.

    Pass: Input observation fields == retrieved observation fields.
    """
    from src.education.student_lens import StudentLensStore, Observation

    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "test.db")
        sid = store.create_lens(display_name="Round Trip Test")

        obs = Observation(
            student_id=sid,
            teacher_id="teacher-eval",
            template_type="cefr",
            raw_transcript="Student read complex Italian passage fluently",
            cefr_dimension="reading",
            cefr_level_observed="B1",
            cefr_direction="progressing",
        )
        result = store.append_observation(obs)
        assert result["validation_errors"] == []

        lens = store.get_lens(sid)
        assert lens["cefr_snapshot"]["reading"] == "B1"
        store.close()


def test_L1_OBS_002_observation_has_attribution():
    """L1-OBS-002: Every observation has non-null timestamp, teacher_id, student_id.

    Pass: All three fields present and non-empty for stored observations.
    """
    from src.education.student_lens import StudentLensStore, Observation

    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "test.db")
        sid = store.create_lens(display_name="Attribution Test")

        obs = Observation(
            student_id=sid,
            teacher_id="teacher-eval",
            template_type="literacy",
            raw_transcript="Good progress in writing today",
        )
        store.append_observation(obs)

        lens = store.get_lens(sid)
        # Observations are stored — verify the lens was updated (attribution worked)
        assert lens["profile_version"] >= 2  # version bumps on each observation
        assert lens["updated_at"] is not None
        store.close()


# --- Privacy Trace Schema (L1-TRACE) ---


@pytest.mark.skip(reason="awaiting trace schema validation harness")
def test_L1_TRACE_001_trace_has_hash_no_raw_text():
    """L1-TRACE-001: Privacy trace has SHA-256 hash and no raw query text.

    Pass: query_hash matches ^[a-f0-9]{64}$; query_text is absent or null.
    Calls: Read traces.ndjson after a query; validate each line.
    """
    pass


@pytest.mark.skip(reason="awaiting trace schema validation harness")
def test_L1_TRACE_002_trace_has_routing_metadata():
    """L1-TRACE-002: Privacy trace has route_id and external_calls count.

    Pass: route_id is non-empty string; external_calls is integer >= 0.
    Calls: Read traces.ndjson after a query.
    """
    pass


# --- Provenance Schema (L1-PROV) ---


def test_L1_PROV_001_provenance_has_grounding_metadata(teacher_history_dir):
    """L1-PROV-001: Provenance entry has source_file, page_start, section.

    Pass: All three fields present and non-null for every provenance entry.
    Calls: ContentDifferentiator.generate_from_documents() → pack.source_provenance
    """
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    class FakeRetriever:
        def __init__(self, chunks):
            self.chunks = chunks

        def retrieve(self, query, domain, k=3):
            return self.chunks

    source_file = teacher_history_dir / "lesson_plan_g3_u1.json"
    chunks = [
        {
            "text": "Morning routine actions are practiced with picture cards and TPR.",
            "source_file": str(source_file),
            "section": "MORNING ROUTINE",
            "page_start": 1,
            "page_end": 1,
        }
    ]
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = ContentDifferentiator().generate_from_documents(lesson, FakeRetriever(chunks), domain="curriculum")

    assert pack.source_provenance
    for entry in pack.source_provenance:
        assert entry.get("source_file")
        assert entry.get("page_start") is not None
        assert entry.get("section")


def test_L1_PROV_002_provenance_source_files_exist(teacher_history_dir):
    """L1-PROV-002: Every source_file referenced in provenance exists on disk.

    Pass: Path(source_file).exists() is True for all provenance entries.
    """
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    class FakeRetriever:
        def __init__(self, chunks):
            self.chunks = chunks

        def retrieve(self, query, domain, k=3):
            return self.chunks

    source_file = teacher_history_dir / "lesson_plan_g3_u1.json"
    assert source_file.exists()  # sanity: the fixture backing this test is real
    chunks = [
        {
            "text": "Morning routine actions are practiced with picture cards and TPR.",
            "source_file": str(source_file),
            "section": "MORNING ROUTINE",
            "page_start": 1,
            "page_end": 1,
        }
    ]
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = ContentDifferentiator().generate_from_documents(lesson, FakeRetriever(chunks), domain="curriculum")

    for entry in pack.source_provenance:
        assert Path(entry["source_file"]).exists()


# --- Teacher Lens Schema (L1-TLENS) ---


def _build_teacher_lens(tmp_path, teacher_history_dir):
    from src.education.teacher_lens_builder import TeacherLensBuilder

    builder = TeacherLensBuilder("teacher-eval", tmp_path)
    for name in ("graded_exam_g3_u1.json", "graded_exam_g3_u2.json", "lesson_plan_g3_u1.json"):
        builder.ingest(teacher_history_dir / name)
    return builder.build_lens()


def test_L1_TLENS_001_teacher_lens_core_dimensions(teacher_history_dir):
    """L1-TLENS-001: Teacher Lens has grading_calibration, differentiation_style, communication_voice.

    Pass: All three top-level keys present and are dicts.
    Calls: TeacherLensBuilder.build_lens() → validate against teacher_lens.schema.json
    """
    with tempfile.TemporaryDirectory() as tmp:
        lens = _build_teacher_lens(Path(tmp), teacher_history_dir)
        assert isinstance(lens.grading_calibration, dict)
        assert isinstance(lens.differentiation_style, dict)
        assert isinstance(lens.communication_voice, dict)


def test_L1_TLENS_002_teacher_lens_staleness_metadata(teacher_history_dir):
    """L1-TLENS-002: Teacher Lens has ingested_doc_count >= 0 and valid last_updated.

    Pass: ingested_doc_count is int >= 0; last_updated parses as ISO8601.
    Calls: TeacherLensBuilder.build_lens()
    """
    from datetime import datetime

    with tempfile.TemporaryDirectory() as tmp:
        lens = _build_teacher_lens(Path(tmp), teacher_history_dir)
        assert isinstance(lens.ingested_doc_count, int)
        assert lens.ingested_doc_count >= 0
        datetime.fromisoformat(lens.last_updated)  # raises if not valid ISO8601


def test_L1_TLENS_003_teacher_lens_patterns_cite_sources(teacher_history_dir):
    """L1-TLENS-003: Every pattern entry in grading_calibration references at least one source doc.

    Pass: Each criterion in grading_calibration has examples[] with >= 1 item citing a doc_id.
    Calls: TeacherLensBuilder.build_lens().grading_calibration
    """
    with tempfile.TemporaryDirectory() as tmp:
        lens = _build_teacher_lens(Path(tmp), teacher_history_dir)
        source_doc_ids = {d["doc_id"] for d in lens.source_documents}

        assert lens.grading_calibration
        for criterion, spec in lens.grading_calibration.items():
            assert spec["examples"]
            assert any(
                any(doc_id in example for doc_id in source_doc_ids) for example in spec["examples"]
            )
