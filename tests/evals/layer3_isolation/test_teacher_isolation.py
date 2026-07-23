"""Layer 3: Teacher Isolation — one teacher's lens has zero data from another teacher.

Property proved: Teacher lenses are fully isolated from each other.
"""

import pytest

SKIP = "awaiting TeacherLensBuilder with multi-teacher isolation"


@pytest.mark.skip(reason=SKIP)
def test_L3_TCH_001_teacher_a_lens_zero_teacher_b_data():
    """L3-TCH-001: Teacher A's lens contains zero data from Teacher B's history.

    Setup: Two TeacherLensBuilder instances (teacher-a, teacher-b), each ingests different docs.
    Pass: teacher_a.build_lens().source_documents has zero doc_ids from teacher_b's ingests.
    """
    pass


@pytest.mark.skip(reason=SKIP)
def test_L3_TCH_002_same_source_different_lenses_different_output():
    """L3-TCH-002: Same IB source + different teacher lenses → different generated outputs.

    Setup: Two teachers with different grading_calibration/differentiation_style.
    Pass: generate_with_teacher_lens(same_lesson, lens_a) != generate_with_teacher_lens(same_lesson, lens_b)
    """
    pass
