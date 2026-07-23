"""Layer 3: Teacher Isolation — one teacher's lens has zero data from another teacher.

Property proved: Teacher lenses are fully isolated from each other.
"""

import tempfile
from pathlib import Path

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.education.teacher_lens_builder import TeacherLensBuilder


def test_L3_TCH_001_teacher_a_lens_zero_teacher_b_data(teacher_history_dir):
    """L3-TCH-001: Teacher A's lens contains zero data from Teacher B's history.

    Setup: Two TeacherLensBuilder instances (teacher-a, teacher-b), each ingests different docs.
    Pass: teacher_a.build_lens().source_documents has zero doc_ids from teacher_b's ingests.
    """
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        teacher_a = TeacherLensBuilder("teacher-a", Path(tmp_a))
        teacher_b = TeacherLensBuilder("teacher-b", Path(tmp_b))

        result_a = teacher_a.ingest(teacher_history_dir / "graded_exam_g3_u1.json")
        result_b = teacher_b.ingest(teacher_history_dir / "parent_update_marco.json")

        lens_a = teacher_a.build_lens()
        lens_b = teacher_b.build_lens()

        ids_a = {d["doc_id"] for d in lens_a.source_documents}
        ids_b = {d["doc_id"] for d in lens_b.source_documents}

        assert result_b.doc_id not in ids_a
        assert result_a.doc_id not in ids_b
        assert ids_a.isdisjoint(ids_b)


def test_L3_TCH_002_same_source_different_lenses_different_output(teacher_history_dir):
    """L3-TCH-002: Same IB source + different teacher lenses → different generated outputs.

    Setup: Two teachers with different grading_calibration/differentiation_style.
    Pass: generate_with_teacher_lens(same_lesson, lens_a) != generate_with_teacher_lens(same_lesson, lens_b)
    """
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        teacher_a = TeacherLensBuilder("teacher-a", Path(tmp_a))
        teacher_a.ingest(teacher_history_dir / "graded_exam_g3_u1.json")
        teacher_a.ingest(teacher_history_dir / "lesson_plan_g3_u1.json")
        lens_a = teacher_a.build_lens()

        teacher_b = TeacherLensBuilder("teacher-b", Path(tmp_b))
        teacher_b.ingest(teacher_history_dir / "graded_exam_g3_u2.json")
        lens_b = teacher_b.build_lens()

        lesson = LessonInput(
            ib_programme="MYP",
            subject="Individuals & Societies",
            unit_title="Migration and Identity",
            topic="Push and pull factors of forced migration",
            atl_skills=["COMM-01"],
            cefr_target="B1",
            duration_minutes=60,
            created_by="teacher_1",
        )

        engine = ContentDifferentiator()
        pack_a = engine.generate_with_teacher_lens(lesson, lens_a)
        pack_b = engine.generate_with_teacher_lens(lesson, lens_b)

        assert pack_a.tiers != pack_b.tiers
