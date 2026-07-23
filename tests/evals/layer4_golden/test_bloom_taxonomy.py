"""Layer 4: Bloom's Taxonomy — objectives use tier-appropriate cognitive verbs.

Property proved: Foundational=low Bloom's, On_track=mid, Extended=high.
No model calls. Pattern: "Children [verb] and [verb] [topic]."
"""

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput

LOW_BLOOMS = {"identify", "name", "list", "recognize", "match", "notice", "label", "point"}
MID_BLOOMS = {"explain", "compare", "connect", "describe", "classify", "summarize", "interpret"}
HIGH_BLOOMS = {"analyze", "evaluate", "argue", "investigate", "create", "design", "critique", "justify"}


def _make_lesson(topic: str = "daily routines in Italian") -> LessonInput:
    return LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic=topic,
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )


def _extract_verbs(objective: str) -> set:
    """Extract cognitive verbs from 'Children [verb] and [verb] [topic]' pattern."""
    # Remove "Children " prefix and extract verbs before the topic
    lower = objective.lower()
    if lower.startswith("children "):
        lower = lower[len("children "):]
    # Split on " and " to get verb phrases, take first word of each
    parts = lower.split(" and ")
    verbs = set()
    for part in parts:
        first_word = part.strip().split()[0] if part.strip() else ""
        if first_word:
            verbs.add(first_word)
    return verbs


def test_L4_BLOOM_001_foundational_low_verbs():
    """L4-BLOOM-001: Foundational tier objectives use low Bloom's verbs.

    Pass: Verbs in learning_objective are in LOW_BLOOMS set.
    """
    pack = ContentDifferentiator().generate(_make_lesson())
    verbs = _extract_verbs(pack.tiers["foundational"]["learning_objective"])
    assert verbs, "No verbs extracted from foundational objective"
    unrecognized = verbs - LOW_BLOOMS
    assert not unrecognized, (
        f"Foundational has non-low-Bloom's verbs: {unrecognized}. "
        f"Objective: '{pack.tiers['foundational']['learning_objective']}'"
    )


def test_L4_BLOOM_002_on_track_mid_verbs():
    """L4-BLOOM-002: On_track tier objectives use mid Bloom's verbs.

    Pass: Verbs in learning_objective are in MID_BLOOMS set.
    """
    pack = ContentDifferentiator().generate(_make_lesson())
    verbs = _extract_verbs(pack.tiers["on_track"]["learning_objective"])
    assert verbs, "No verbs extracted from on_track objective"
    unrecognized = verbs - MID_BLOOMS
    assert not unrecognized, (
        f"On_track has non-mid-Bloom's verbs: {unrecognized}. "
        f"Objective: '{pack.tiers['on_track']['learning_objective']}'"
    )


def test_L4_BLOOM_003_extended_high_verbs():
    """L4-BLOOM-003: Extended tier objectives use high Bloom's verbs.

    Pass: Verbs in learning_objective are in HIGH_BLOOMS set.
    """
    pack = ContentDifferentiator().generate(_make_lesson())
    verbs = _extract_verbs(pack.tiers["extended"]["learning_objective"])
    assert verbs, "No verbs extracted from extended objective"
    unrecognized = verbs - HIGH_BLOOMS
    assert not unrecognized, (
        f"Extended has non-high-Bloom's verbs: {unrecognized}. "
        f"Objective: '{pack.tiers['extended']['learning_objective']}'"
    )


def test_L4_BLOOM_multiple_topics():
    """Bloom's verb tiering holds across different topics."""
    topics = [
        "daily routines in Italian",
        "describing weather and seasons",
        "narrative writing for personal experiences",
        "reading comprehension of Italian folk tales",
    ]
    diff = ContentDifferentiator()
    for topic in topics:
        pack = diff.generate(_make_lesson(topic))
        f_verbs = _extract_verbs(pack.tiers["foundational"]["learning_objective"])
        o_verbs = _extract_verbs(pack.tiers["on_track"]["learning_objective"])
        e_verbs = _extract_verbs(pack.tiers["extended"]["learning_objective"])

        # At minimum: no high verbs in foundational, no low verbs in extended
        assert not (f_verbs & HIGH_BLOOMS), f"Topic '{topic}': foundational has high Bloom's {f_verbs & HIGH_BLOOMS}"
        assert not (e_verbs & LOW_BLOOMS), f"Topic '{topic}': extended has low Bloom's {e_verbs & LOW_BLOOMS}"
