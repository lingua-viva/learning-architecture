"""Layer 2: Teacher Lens Extraction — patterns are correctly learned from history.

Property proved: TeacherLensBuilder extracts accurate patterns from ingested teaching artifacts.
"""

import tempfile
from pathlib import Path

import pytest

from src.education.teacher_lens_builder import TeacherLensBuilder


def test_L2_EXTRACT_001_grading_patterns_from_exams(teacher_history_dir):
    """L2-EXTRACT-001: Grading patterns extracted from graded exams.

    Pass: Lens.grading_calibration is non-empty, each criterion cites at least one exam doc_id.
    Fixture: graded_exam_g3_u1.json, graded_exam_g3_u2.json
    Calls: TeacherLensBuilder.ingest(exam) × N → build_lens() → check grading_calibration
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        ids = []
        for name in ("graded_exam_g3_u1.json", "graded_exam_g3_u2.json"):
            result = builder.ingest(teacher_history_dir / name)
            assert result.classified_type == "exam"
            ids.append(result.doc_id)

        lens = builder.build_lens()
        assert lens.grading_calibration
        for criterion, spec in lens.grading_calibration.items():
            assert spec["examples"]
            assert any(any(doc_id in ex for doc_id in ids) for ex in spec["examples"])


def test_L2_EXTRACT_002_communication_voice_from_parents(teacher_history_dir):
    """L2-EXTRACT-002: Communication voice extracted from parent updates.

    Pass: Lens.communication_voice has formality, l1_l2_ratio (float 0-1), focus_areas (non-empty list).
    Fixture: parent_update_marco.json, parent_update_nora.json
    Calls: TeacherLensBuilder.ingest(parent_update) × N → build_lens()
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        for name in ("parent_update_marco.json", "parent_update_nora.json"):
            result = builder.ingest(teacher_history_dir / name)
            assert result.classified_type == "parent_update"

        lens = builder.build_lens()
        voice = lens.communication_voice
        assert voice["formality"]
        assert 0.0 <= voice["l1_l2_ratio"] <= 1.0
        assert voice["focus_areas"]


def test_L2_EXTRACT_003_differentiation_from_lesson_plans(teacher_history_dir):
    """L2-EXTRACT-003: Differentiation style extracted from lesson plans.

    Pass: Lens.differentiation_style has entries for foundational/on_track/extended, each with scaffolding list.
    Fixture: lesson_plan_g3_u1.json
    Calls: TeacherLensBuilder.ingest(lesson_plan) × N → build_lens()
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        result = builder.ingest(teacher_history_dir / "lesson_plan_g3_u1.json")
        assert result.classified_type == "lesson_plan"

        lens = builder.build_lens()
        for tier in ("foundational", "on_track", "extended"):
            assert tier in lens.differentiation_style
            assert lens.differentiation_style[tier]["scaffolding"]


def test_L2_EXTRACT_004_assessment_weighting_from_evaluations(teacher_history_dir):
    """L2-EXTRACT-004: Assessment weighting extracted from evaluations sums to 1.0.

    Pass: sum(Lens.assessment_weighting.values()) == 1.0 ±0.01
    Fixture: student_evaluation_q1.json
    Calls: TeacherLensBuilder.ingest(evaluation) × N → build_lens()
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        result = builder.ingest(teacher_history_dir / "student_evaluation_q1.json")
        assert result.classified_type == "evaluation"

        lens = builder.build_lens()
        assert lens.assessment_weighting
        assert abs(sum(lens.assessment_weighting.values()) - 1.0) <= 0.01


def test_L2_INCR_001_new_doc_superset(teacher_history_dir):
    """L2-INCR-001: Adding a new document updates lens without losing old data.

    Pass: After ingest of doc N+1, lens.source_documents is superset of previous.
    Calls: build_lens() before and after new ingest.
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        builder.ingest(teacher_history_dir / "graded_exam_g3_u1.json")
        lens_before = builder.build_lens()
        ids_before = {d["doc_id"] for d in lens_before.source_documents}

        builder.ingest(teacher_history_dir / "graded_exam_g3_u2.json")
        lens_after = builder.build_lens()
        ids_after = {d["doc_id"] for d in lens_after.source_documents}

        assert ids_before.issubset(ids_after)
        assert len(ids_after) > len(ids_before)


def test_L2_INCR_002_remove_and_rebuild_shrinks(teacher_history_dir):
    """L2-INCR-002: Removing a doc and rebuilding produces smaller lens.

    Pass: Rebuilt lens has fewer source_documents and potentially fewer patterns.
    Calls: Remove a doc from storage → rebuild → compare.
    """
    with tempfile.TemporaryDirectory() as tmp_full, tempfile.TemporaryDirectory() as tmp_partial:
        full_builder = TeacherLensBuilder("teacher-eval", Path(tmp_full))
        full_builder.ingest(teacher_history_dir / "graded_exam_g3_u1.json")
        full_builder.ingest(teacher_history_dir / "graded_exam_g3_u2.json")
        full_lens = full_builder.build_lens()

        # Simulate "one doc removed from storage" via a fresh instance that
        # never ingested the second exam — the builder has no
        # un-ingest primitive (append-only per CONTRACTS.md), so removal
        # happens at the storage layer, not through the builder's API.
        partial_builder = TeacherLensBuilder("teacher-eval", Path(tmp_partial))
        partial_builder.ingest(teacher_history_dir / "graded_exam_g3_u1.json")
        partial_lens = partial_builder.build_lens()

        assert len(partial_lens.source_documents) < len(full_lens.source_documents)
