"""
Assessment Generator Tests — Product B extension.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.content_differentiator import ContentDifferentiator, LessonInput, TIERS
from src.education.assessment_generator import AssessmentGenerator, IB_COMPLIANCE_NOTE


def make_pack():
    engine = ContentDifferentiator()
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
    return engine.generate(lesson)


def test_generates_four_criteria():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    assert len(assessment.criteria) == 4
    assert set(assessment.criteria.keys()) == {"A", "B", "C", "D"}


def test_generates_all_three_tiers():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    assert set(assessment.tier_assessments.keys()) == set(TIERS)


def test_band_descriptors_use_0_to_8_scale_not_1_to_8():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    assert "0" in assessment.band_descriptors
    assert "1-2" in assessment.band_descriptors
    assert "7-8" in assessment.band_descriptors


def test_tier_target_bands_increase_with_tier():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    foundational_band = assessment.tier_assessments["foundational"].target_band
    on_track_band = assessment.tier_assessments["on_track"].target_band
    extended_band = assessment.tier_assessments["extended"].target_band
    assert foundational_band == "1-2"
    assert on_track_band == "3-4"
    assert extended_band == "5-6"


def test_task_reused_from_content_pack_not_invented():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    for tier in TIERS:
        expected_task = pack.tiers[tier]["tasks"][-1]
        assert assessment.tier_assessments[tier].task_prompt == expected_task["prompt"]


def test_opt_out_flag_preserved_for_reflection_tasks():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    # on_track and extended tiers' last task is reflection/extended_writing,
    # both opt-out-offered per content_differentiator.py's design.
    assert assessment.tier_assessments["on_track"].opt_out_offered is True
    assert assessment.tier_assessments["extended"].opt_out_offered is True


def test_compliance_note_present_and_honest():
    pack = make_pack()
    assessment = AssessmentGenerator().generate(pack)
    assert assessment.ib_compliance_note == IB_COMPLIANCE_NOTE
    assert "NOT verified subject-specific" in assessment.ib_compliance_note


def test_assessment_id_stable_for_same_pack():
    pack = make_pack()
    a1 = AssessmentGenerator().generate(pack)
    a2 = AssessmentGenerator().generate(pack)
    assert a1.assessment_id == a2.assessment_id


def test_to_markdown_contains_key_sections():
    pack = make_pack()
    md = AssessmentGenerator().generate(pack).to_markdown()
    assert "# Assessment:" in md
    assert "## Criteria" in md
    assert "## Achievement Bands" in md
    assert "## Differentiated Tasks" in md
    assert "compliance" not in md.lower() or "official" in md.lower()
