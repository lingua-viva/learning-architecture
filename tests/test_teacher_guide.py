"""
Teacher Guide Generator Tests — Product B output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.education.teacher_guide import TeacherGuideGenerator, build_cross_level_groups


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


# --- Conflict-aware grouping (re-ground audit fix: social-emotional
# grouping, not just academic level) ----------------------------------------

def test_build_groups_pairs_one_per_tier_with_no_conflicts():
    roster = [
        {"student_id": "f1", "display_name": "Foundational One"},
        {"student_id": "o1", "display_name": "OnTrack One"},
        {"student_id": "e1", "display_name": "Extended One"},
    ]
    assignments = {"f1": "foundational", "o1": "on_track", "e1": "extended"}
    groups, unplaced = build_cross_level_groups(roster, assignments)
    assert len(groups) == 1
    assert set(groups[0].student_ids) == {"f1", "o1", "e1"}
    assert unplaced == []


def test_build_groups_respects_avoid_pairing_with():
    roster = [
        {"student_id": "f1", "display_name": "F1", "avoid_pairing_with": ["o1"]},
        {"student_id": "o1", "display_name": "O1"},
        {"student_id": "o2", "display_name": "O2"},
        {"student_id": "e1", "display_name": "E1"},
    ]
    assignments = {"f1": "foundational", "o1": "on_track", "o2": "on_track", "e1": "extended"}
    groups, unplaced = build_cross_level_groups(roster, assignments)
    assert len(groups) == 1
    # f1 must not be grouped with o1 (declared conflict) — should skip to o2
    assert "o1" not in groups[0].student_ids
    assert "o2" in groups[0].student_ids
    # o1 has no remaining tier partners, left unplaced rather than force-paired
    assert "o1" in unplaced


def test_build_groups_conflict_is_symmetric():
    """A conflict declared by the on_track student (not the foundational
    one) still blocks the pairing — it's about the pair, not who reported it."""
    roster = [
        {"student_id": "f1", "display_name": "F1"},
        {"student_id": "o1", "display_name": "O1", "avoid_pairing_with": ["f1"]},
        {"student_id": "e1", "display_name": "E1"},
    ]
    assignments = {"f1": "foundational", "o1": "on_track", "e1": "extended"}
    groups, unplaced = build_cross_level_groups(roster, assignments)
    assert len(groups) == 1
    assert "o1" not in groups[0].student_ids
    assert "o1" in unplaced


def test_build_groups_never_force_pairs_when_all_conflict():
    roster = [
        {"student_id": "f1", "display_name": "F1", "avoid_pairing_with": ["o1"]},
        {"student_id": "o1", "display_name": "O1"},
    ]
    assignments = {"f1": "foundational", "o1": "on_track"}
    groups, unplaced = build_cross_level_groups(roster, assignments)
    assert groups == []
    assert set(unplaced) == {"f1", "o1"}


def test_build_groups_never_silently_drops_a_student_with_missing_tier():
    """A roster student whose assignments entry is missing or names a tier
    outside TIERS never entered by_tier and would previously vanish from
    both `groups` and `unplaced` — silently absent from the printed guide.
    They must now surface in `unplaced` instead."""
    roster = [
        {"student_id": "f1", "display_name": "F1"},
        {"student_id": "o1", "display_name": "O1"},
        {"student_id": "ghost", "display_name": "Ghost"},
    ]
    assignments = {"f1": "foundational", "o1": "on_track"}  # "ghost" has no entry
    groups, unplaced = build_cross_level_groups(roster, assignments)
    all_ids = {sid for g in groups for sid in g.student_ids} | set(unplaced)
    assert "ghost" in all_ids
    assert "ghost" in unplaced


def test_teacher_guide_markdown_includes_groups_section():
    pack = make_pack()
    roster = [
        {"student_id": "f1", "display_name": "F1", "rti_current_tier": 3, "cefr_snapshot": {}},
        {"student_id": "o1", "display_name": "O1", "rti_current_tier": 1, "cefr_snapshot": {}},
        {"student_id": "e1", "display_name": "E1", "rti_current_tier": 1, "cefr_snapshot": {"reading": "B2"}},
    ]
    engine = ContentDifferentiator()
    assignments = engine.assign_packs_for_roster(pack, roster)
    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    md = guide.to_markdown()
    assert "Suggested Groups" in md
    assert len(guide.groups) == 1
