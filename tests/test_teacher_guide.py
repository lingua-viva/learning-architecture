"""
Teacher Guide Generator Tests — Product B output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.education.teacher_guide import TeacherGuideGenerator


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


def test_guide_has_tier_counts_matching_roster():
    pack = make_pack()
    roster = [
        {"student_id": "s1", "rti_current_tier": 3, "cefr_snapshot": {}},
        {"student_id": "s2", "rti_current_tier": 1, "cefr_snapshot": {"reading": "B2"}},
        {"student_id": "s3", "rti_current_tier": 1, "cefr_snapshot": {}},
    ]
    engine = ContentDifferentiator()
    assignments = engine.assign_packs_for_roster(pack, roster)
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    assert guide.tier_counts["foundational"] == 1
    assert guide.tier_counts["extended"] == 1
    assert guide.tier_counts["on_track"] == 1


def test_guide_distribution_instructions_present_for_all_tiers():
    pack = make_pack()
    roster = [{"student_id": "s1", "rti_current_tier": 1, "cefr_snapshot": {}}]
    assignments = {"s1": "on_track"}
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    for tier in ("foundational", "on_track", "extended"):
        assert tier in guide.distribution_instructions
        assert guide.distribution_instructions[tier]


def test_trauma_flag_produces_general_note_not_student_specific():
    pack = make_pack()
    roster = [
        {"student_id": "s1", "rti_current_tier": 1, "cefr_snapshot": {}, "trauma_flag": True},
        {"student_id": "s2", "rti_current_tier": 1, "cefr_snapshot": {}, "trauma_flag": False},
    ]
    assignments = {"s1": "on_track", "s2": "on_track"}
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    assert len(guide.trauma_aware_notes) == 1
    note = guide.trauma_aware_notes[0]
    assert "s1" not in note
    assert "student_id" not in note


def test_no_trauma_flag_produces_no_notes():
    pack = make_pack()
    roster = [{"student_id": "s1", "rti_current_tier": 1, "cefr_snapshot": {}}]
    assignments = {"s1": "on_track"}
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    assert guide.trauma_aware_notes == []


def test_to_markdown_is_printable_text():
    pack = make_pack()
    roster = [{"student_id": "s1", "rti_current_tier": 1, "cefr_snapshot": {}}]
    assignments = {"s1": "on_track"}
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    md = guide.to_markdown()
    assert md.startswith("# Teacher Guide:")
    assert "## Class Breakdown" in md
    assert "## Distribution Instructions" in md
    assert "## Cross-Level Collaboration" in md
