"""Layer 4: Bilingual Balance — generated content respects language ratio constraints.

Property proved: Activity packs maintain the specified Italian/English ratio.
"""

import pytest

SKIP = (
    "OUT OF SCOPE tonight: no italian_percentage_target field on LessonInput "
    "and no Italian-content generation exists anywhere in ContentDifferentiator "
    "(templates and adaptation are English-only). Not in tests/evals/CONTRACTS.md "
    "either — building a real bilingual generator is new-feature work, not a gap "
    "fix. Flagging for a dedicated build, not silently faking a passing assertion."
)


@pytest.mark.skip(reason=SKIP)
def test_L4_BILING_001_italian_ratio_within_tolerance():
    """L4-BILING-001: Unit specifying 70% Italian → activities maintain 60-80% Italian.

    Setup: Generate pack for a lesson with italian_percentage_target=0.70.
    Pass: Measured Italian word percentage is within ±10% of target (0.60-0.80).
    Calls: Generate pack → language detection on each tier's content.
    """
    pass


@pytest.mark.skip(reason=SKIP)
def test_L4_BILING_002_english_scaffolding_only_foundational():
    """L4-BILING-002: English scaffolding appears only in foundational tier.

    Pass: on_track and extended tiers have Italian-only content; foundational may include English bridges.
    Calls: Generate pack → check on_track/extended for English words.
    """
    pass
