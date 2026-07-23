"""Layer 4: Bilingual Balance — generated content respects language ratio constraints.

Property proved: Activity packs maintain the specified Italian/English ratio.
"""

import pytest

SKIP = "awaiting bilingual ratio validation against generated content"


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
