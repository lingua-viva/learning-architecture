"""
Content Differentiation Engine Tests — Product B core.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.content_differentiator import (
    ContentDifferentiator,
    LessonInput,
    PERSONAL_REFLECTION_OPT_OUT,
    TraumaSafetyError,
    _check_trauma_safety,
)


def make_lesson(**overrides) -> LessonInput:
    defaults = dict(
        ib_programme="MYP",
        subject="Individuals & Societies",
        unit_title="Migration and Identity",
        topic="Push and pull factors of forced migration",
        atl_skills=["COMM-01", "CRIT-03"],
        cefr_target="B1",
        duration_minutes=60,
        created_by="teacher_1",
    )
    defaults.update(overrides)
    return LessonInput(**defaults)


def test_lesson_input_validation():
    bad = make_lesson(ib_programme="XX", cefr_target="Z9", duration_minutes=0, subject="")
    errors = bad.validate()
    assert len(errors) == 4


def test_generate_produces_three_tiers():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson())
    assert set(pack.tiers.keys()) == {"foundational", "on_track", "extended"}
    for tier_name, tier in pack.tiers.items():
        assert tier["tier"] == tier_name
        assert tier["learning_objective"]
        assert tier["vocabulary_list"]
        assert tier["tasks"]


def test_cefr_maps_correctly_across_tiers():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson(cefr_target="B1"))
    assert pack.tiers["foundational"]["cefr_target"] == "A2+"
    assert pack.tiers["on_track"]["cefr_target"] == "B1"
    assert pack.tiers["extended"]["cefr_target"] == "B1+"


def test_cefr_target_clamps_at_range_edges():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson(cefr_target="A1"))
    assert pack.tiers["foundational"]["cefr_target"] == "A1"  # can't go below A1
    pack2 = engine.generate(make_lesson(cefr_target="C2"))
    assert pack2.tiers["extended"]["cefr_target"] == "C2"  # can't go above C2


def test_foundational_learning_objective_respects_sentence_length():
    engine = ContentDifferentiator()
    pack = engine.generate(
        make_lesson(topic="Push and pull factors of forced migration across borders and regions")
    )
    words = pack.tiers["foundational"]["learning_objective"].split()
    assert len(words) <= 10


def test_pack_id_is_stable_for_same_lesson():
    engine = ContentDifferentiator()
    lesson_a = make_lesson()
    lesson_b = make_lesson()
    pack_a = engine.generate(lesson_a)
    pack_b = engine.generate(lesson_b)
    assert pack_a.pack_id == pack_b.pack_id


def test_pack_id_differs_for_different_lessons():
    engine = ContentDifferentiator()
    pack_a = engine.generate(make_lesson(topic="Topic A"))
    pack_b = engine.generate(make_lesson(topic="Topic B"))
    assert pack_a.pack_id != pack_b.pack_id


def test_reflection_and_extended_writing_tasks_carry_opt_out():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson())
    personal_tasks = [
        t
        for tier in pack.tiers.values()
        for t in tier["tasks"]
        if t["type"] in ("reflection", "extended_writing")
    ]
    assert personal_tasks
    for task in personal_tasks:
        assert task["opt_out_offered"] is True
        assert PERSONAL_REFLECTION_OPT_OUT in task["prompt"]


def test_no_generated_text_contains_unsafe_labels():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson())
    for tier in pack.tiers.values():
        _check_trauma_safety(tier["learning_objective"])
        for task in tier["tasks"]:
            _check_trauma_safety(task["prompt"])


def test_trauma_safety_check_catches_unsafe_label():
    with pytest.raises(TraumaSafetyError):
        _check_trauma_safety("This lesson is for refugee students only.")


def test_assign_tier_rti3_always_foundational():
    engine = ContentDifferentiator()
    lens = {"rti_current_tier": 3, "cefr_snapshot": {"reading": "C1"}}
    assert engine.assign_tier_for_student(lens) == "foundational"


def test_assign_tier_rti1_high_cefr_gets_extended():
    engine = ContentDifferentiator()
    lens = {"rti_current_tier": 1, "cefr_snapshot": {"reading": "B2", "writing": "B2"}}
    assert engine.assign_tier_for_student(lens) == "extended"


def test_assign_tier_rti1_default_on_track():
    engine = ContentDifferentiator()
    lens = {"rti_current_tier": 1, "cefr_snapshot": {}}
    assert engine.assign_tier_for_student(lens) == "on_track"


def test_assign_tier_rti2_with_strong_cefr_gets_on_track():
    engine = ContentDifferentiator()
    lens = {"rti_current_tier": 2, "cefr_snapshot": {"reading": "B1", "writing": "B1"}}
    assert engine.assign_tier_for_student(lens) == "on_track"


def test_assign_packs_for_roster():
    engine = ContentDifferentiator()
    pack = engine.generate(make_lesson())
    roster = [
        {"student_id": "s1", "rti_current_tier": 3, "cefr_snapshot": {}},
        {"student_id": "s2", "rti_current_tier": 1, "cefr_snapshot": {"reading": "B2"}},
    ]
    assignments = engine.assign_packs_for_roster(pack, roster)
    assert assignments == {"s1": "foundational", "s2": "extended"}
