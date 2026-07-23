"""Layer 4: CEFR Progression — tier targets maintain monotonic ordering.

Property proved: foundational.cefr_target <= on_track.cefr_target <= extended.cefr_target always.
No model calls. Uses ContentDifferentiator's deterministic logic.
"""

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput, CEFR_ORDER


def _make_lesson(cefr_target: str) -> LessonInput:
    return LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="Test Unit",
        topic="Test topic for CEFR eval",
        atl_skills=["COMM-01"],
        cefr_target=cefr_target,
        duration_minutes=45,
        created_by="teacher_eval",
    )


def test_L4_CEFR_001_monotonic_ordering():
    """L4-CEFR-001: CEFR target monotonicity across tiers.

    Pass: CEFR_ORDER.index(foundational) <= on_track <= extended for every valid target.
    """
    diff = ContentDifferentiator()

    for target in CEFR_ORDER:
        pack = diff.generate(_make_lesson(target))
        f_idx = CEFR_ORDER.index(pack.tiers["foundational"]["cefr_target"])
        o_idx = CEFR_ORDER.index(pack.tiers["on_track"]["cefr_target"])
        e_idx = CEFR_ORDER.index(pack.tiers["extended"]["cefr_target"])
        assert f_idx <= o_idx <= e_idx, (
            f"For target={target}: foundational={pack.tiers['foundational']['cefr_target']} "
            f"({f_idx}), on_track={pack.tiers['on_track']['cefr_target']} ({o_idx}), "
            f"extended={pack.tiers['extended']['cefr_target']} ({e_idx})"
        )


def test_L4_CEFR_002_floor_clamp():
    """L4-CEFR-002: When target is A1, foundational cannot go below A1.

    Pass: foundational.cefr_target is A1 (the floor) when input target is A1.
    """
    diff = ContentDifferentiator()
    pack = diff.generate(_make_lesson("A1"))
    assert pack.tiers["foundational"]["cefr_target"] == "A1"


def test_L4_CEFR_003_ceiling_clamp():
    """L4-CEFR-003: When target is C2, extended cannot go above C2.

    Pass: extended.cefr_target is C2 (the ceiling) when input target is C2.
    """
    diff = ContentDifferentiator()
    pack = diff.generate(_make_lesson("C2"))
    assert pack.tiers["extended"]["cefr_target"] == "C2"
