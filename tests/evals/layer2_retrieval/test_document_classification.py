"""Layer 2: Document Classification — system correctly identifies document types.

Property proved: Historical teaching artifacts are classified by type accurately.
The TeacherLensBuilder.classify() doesn't exist yet, but the existing ingest module
already has blocked/allowed type enforcement that we can test NOW.
"""

import tempfile
from pathlib import Path

import pytest

from src.lingua_viva.ingest import ALLOWED_DOC_TYPES, BLOCKED_DOC_TYPES, ingest_document


SKIP_CLASSIFY = "awaiting TeacherLensBuilder.classify() implementation"


@pytest.mark.skip(reason=SKIP_CLASSIFY)
def test_L2_CLASS_001_graded_exam_classified(teacher_history_dir):
    """L2-CLASS-001: System classifies graded exam correctly.

    Pass: classify(graded_exam_g3_u1.json).doc_type == "exam"
    Calls: TeacherLensBuilder.classify(file_path)
    """
    pass


@pytest.mark.skip(reason=SKIP_CLASSIFY)
def test_L2_CLASS_002_parent_update_classified(teacher_history_dir):
    """L2-CLASS-002: System classifies parent update correctly.

    Pass: classify(parent_update_marco.json).doc_type == "parent_update"
    """
    pass


@pytest.mark.skip(reason=SKIP_CLASSIFY)
def test_L2_CLASS_003_lesson_plan_classified(teacher_history_dir):
    """L2-CLASS-003: System classifies lesson plan correctly.

    Pass: classify(lesson_plan_g3_u1.json).doc_type == "lesson_plan"
    """
    pass


@pytest.mark.skip(reason=SKIP_CLASSIFY)
def test_L2_CLASS_004_evaluation_classified(teacher_history_dir):
    """L2-CLASS-004: System classifies student evaluation correctly.

    Pass: classify(student_evaluation_q1.json).doc_type == "evaluation"
    """
    pass


def test_L2_CLASS_005_student_records_blocked():
    """L2-CLASS-005: System rejects student-records at the ingest boundary.

    Pass: ingest_document(..., doc_type="student-records") returns error.
    This exercises the EXISTING privacy gate in src/lingua_viva/ingest.py.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fake_pdf = Path(tmp) / "fake_records.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake content")

        result = ingest_document(fake_pdf, "student-records")
        assert result["ok"] is False
        assert result["reason"] == "blocked_type"


def test_L2_CLASS_006_allowed_types_are_explicit():
    """The allowed doc types are a known, bounded set."""
    assert "curriculum" in ALLOWED_DOC_TYPES
    assert "organizational" in ALLOWED_DOC_TYPES
    assert "student-records" in BLOCKED_DOC_TYPES
    # Future types the TeacherLensBuilder will need:
    # These should eventually be in ALLOWED_DOC_TYPES
    future_types_needed = {"exam", "parent_update", "evaluation", "lesson_plan", "rubric"}
    missing = future_types_needed - ALLOWED_DOC_TYPES
    if missing:
        pytest.skip(
            f"TeacherLensBuilder doc types not yet in ALLOWED_DOC_TYPES: {missing}. "
            f"Implementation team must add these."
        )
