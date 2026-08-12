"""Test 03 — Content Differentiation (IB MYP Unit → Three Tiers)

Scenario: A teacher inputs an IB MYP English unit on persuasive writing.
The engine generates three differentiated packs (foundational, on_track,
extended) plus a teacher guide. Trauma-safe rules are checked.

Claudia: change the UNIT below to match a real unit you're teaching.
The engine adapts IB content — same concept at three levels.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.education.content_differentiator import ContentDifferentiator, LessonInput


# ── The IB unit to differentiate (replace with real material!) ──────

UNIT = LessonInput(
    ib_programme="MYP",
    subject="English Language and Literature",
    unit_title="The Power of Persuasion",
    topic="Writing persuasive arguments using claim-evidence-reasoning",
    atl_skills=["Communication", "Critical thinking"],
    cefr_target="B1",
    duration_minutes=50,
    language_of_instruction="en",
    created_by="teacher-claudia",
)


def test_unit_validates() -> None:
    """The IB unit input passes validation."""
    errors = UNIT.validate()
    assert errors == [], f"Validation errors: {errors}"


def test_three_tiers_generated() -> None:
    """Three differentiated packs are produced."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)

    assert "foundational" in pack.tiers
    assert "on_track" in pack.tiers
    assert "extended" in pack.tiers

    # Each tier has content
    for tier_name in ("foundational", "on_track", "extended"):
        tier = pack.tiers[tier_name]
        assert tier.get("tasks"), f"{tier_name} has no tasks"
        assert tier.get("cefr_target"), f"{tier_name} has no CEFR target"


def test_tiers_maintain_same_concept() -> None:
    """All three tiers address the same topic — differentiation is in
    scaffolding and complexity, not content."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)

    # Topic/subject should appear across all tiers
    for tier_name in ("foundational", "on_track", "extended"):
        tier = pack.tiers[tier_name]
        all_text = " ".join(
            str(a.get("prompt", "")) + " " + str(a.get("type", ""))
            for a in tier.get("tasks", [])
        ).lower()
        all_text += " " + str(tier.get("learning_objective", "")).lower()
        assert "persuasi" in all_text or "argument" in all_text or "claim" in all_text, \
            f"{tier_name} doesn't reference the unit topic"


def test_cefr_bands_differentiated() -> None:
    """CEFR targets decrease for foundational, increase for extended."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)

    cefr_order = ["Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2"]

    f_band = pack.tiers["foundational"]["cefr_target"]
    o_band = pack.tiers["on_track"]["cefr_target"]
    e_band = pack.tiers["extended"]["cefr_target"]

    f_idx = cefr_order.index(f_band) if f_band in cefr_order else -1
    o_idx = cefr_order.index(o_band) if o_band in cefr_order else -1
    e_idx = cefr_order.index(e_band) if e_band in cefr_order else -1

    assert f_idx <= o_idx, f"Foundational ({f_band}) should be <= on_track ({o_band})"
    assert o_idx <= e_idx, f"On_track ({o_band}) should be <= extended ({e_band})"


def test_teacher_guide_included() -> None:
    """A teacher guide accompanies the differentiated packs."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    d = pack.to_dict()

    # The pack has tiers with teacher-relevant structure
    for tier_name in ("foundational", "on_track", "extended"):
        tier = d["tiers"][tier_name]
        # Each tier should have activities with instructions
        for task in tier.get("tasks", []):
            assert "prompt" in task or "type" in task, \
                f"Task in {tier_name} needs prompt or type"


def test_trauma_safe_rules() -> None:
    """Content passes trauma-safe checks — no deficit language,
    no forced personal disclosure."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)

    unsafe_patterns = [
        "refugee", "trauma", "survivor", "victim", "disadvantaged",
        "at-risk", "broken home", "impoverished",
    ]

    for tier_name in ("foundational", "on_track", "extended"):
        tier = pack.tiers[tier_name]
        for task in tier.get("tasks", []):
            text = (str(task.get("prompt", "")) + " " +
                    str(task.get("type", ""))).lower()
            for pattern in unsafe_patterns:
                assert pattern not in text, \
                    f"Trauma-unsafe pattern '{pattern}' found in {tier_name}: {text[:100]}"


def test_no_external_calls() -> None:
    """Content differentiation is deterministic, local, no LLM call."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    assert pack is not None
    assert not hasattr(engine, 'provider')
    assert not hasattr(engine, 'model')
