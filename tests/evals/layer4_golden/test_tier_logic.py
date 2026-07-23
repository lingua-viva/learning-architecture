"""Layer 4: Tier Logic — deterministic tier assignment from RTI + CEFR.

Property proved: assign_tier_for_student() is deterministic and matches the truth table exactly.
No model calls. Pure deterministic logic. Runs in <1s.

NOTE: RTI 1 + CEFR null is the known gap — current code returns on_track,
perfect state is foundational. This test documents the gap as xfail so the
implementation team knows exactly what to fix.
"""

import pytest
import yaml
from pathlib import Path

from src.education.content_differentiator import ContentDifferentiator

TRUTH_TABLE_PATH = Path(__file__).parent / "tier_assignment_truth_table.yaml"


def _build_lens(rti_tier: int, weakest_cefr) -> dict:
    """Build a minimal student lens dict for tier assignment testing."""
    cefr_val = weakest_cefr if weakest_cefr else None
    return {
        "rti_current_tier": rti_tier,
        "cefr_snapshot": {
            "reading": cefr_val,
            "writing": cefr_val,
            "speaking": cefr_val,
            "listening": cefr_val,
        },
    }


def test_L4_TIER_001_deterministic_10_runs():
    """L4-TIER-001: Same RTI+CEFR → same tier assignment across 10 runs.

    Pass: 10 calls with identical student lens → 10 identical results.
    """
    diff = ContentDifferentiator()
    lens = _build_lens(1, "B1")
    results = [diff.assign_tier_for_student(lens) for _ in range(10)]
    assert len(set(results)) == 1, f"Non-deterministic: got {set(results)}"


def test_L4_TIER_002_rti1_cefr_b2_extended():
    """L4-TIER-002: RTI 1 + CEFR B2 → extended."""
    diff = ContentDifferentiator()
    lens = _build_lens(1, "B2")
    assert diff.assign_tier_for_student(lens) == "extended"


def test_L4_TIER_003_rti2_cefr_a1_foundational():
    """L4-TIER-003: RTI 2 + CEFR A1 → foundational."""
    diff = ContentDifferentiator()
    lens = _build_lens(2, "A1")
    assert diff.assign_tier_for_student(lens) == "foundational"


def test_L4_TIER_004_rti3_cefr_null_foundational():
    """L4-TIER-004: RTI 3 + CEFR null → foundational (safest default)."""
    diff = ContentDifferentiator()
    lens = _build_lens(3, None)
    assert diff.assign_tier_for_student(lens) == "foundational"


def test_L4_TIER_005_rti1_cefr_a2_on_track():
    """L4-TIER-005: RTI 1 + CEFR A2 → on_track."""
    diff = ContentDifferentiator()
    lens = _build_lens(1, "A2")
    assert diff.assign_tier_for_student(lens) == "on_track"


@pytest.mark.xfail(
    reason="KNOWN GAP: RTI 1 + CEFR null → current code returns on_track; perfect state is foundational",
    strict=True,
)
def test_L4_TIER_NULL_CEFR_perfect_state():
    """PERFECT STATE: RTI 1 + null CEFR → foundational (we don't know yet → scaffold more).

    This test documents the gap. When implementation fixes it, remove the xfail.
    """
    diff = ContentDifferentiator()
    lens = _build_lens(1, None)
    assert diff.assign_tier_for_student(lens) == "foundational"


def test_L4_TIER_006_full_truth_table():
    """L4-TIER-006: Full truth table (all rows the code can handle) pass.

    Loads tier_assignment_truth_table.yaml and asserts every row matches.
    The disputed row (RTI 1 + null) is tested separately as xfail above.
    """
    truth = yaml.safe_load(TRUTH_TABLE_PATH.read_text())
    diff = ContentDifferentiator()

    # CEFR values the implementation currently supports
    SUPPORTED_CEFR = {"A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2", None}

    failures = []
    skipped_unsupported = []
    for row in truth["truth_table"]:
        # Skip the resolved-as-perfect-state row (tested separately as xfail)
        if row.get("rti_tier") == 1 and row.get("weakest_cefr") is None:
            continue

        # Skip CEFR values the implementation doesn't handle yet (Pre-A1)
        if row.get("weakest_cefr") not in SUPPORTED_CEFR:
            skipped_unsupported.append(
                f"RTI {row['rti_tier']} + CEFR {row['weakest_cefr']} (unsupported CEFR value)"
            )
            continue

        lens = _build_lens(row["rti_tier"], row["weakest_cefr"])
        actual = diff.assign_tier_for_student(lens)
        expected = row["expected_tier"]

        if actual != expected:
            failures.append(
                f"RTI {row['rti_tier']} + CEFR {row['weakest_cefr']}: "
                f"expected={expected}, got={actual}"
            )

    assert not failures, f"Truth table failures:\n" + "\n".join(failures)
    # Report skipped rows so we know what's not covered
    if skipped_unsupported:
        pytest.skip(f"Skipped {len(skipped_unsupported)} rows with unsupported CEFR (Pre-A1)")


@pytest.mark.xfail(
    reason="KNOWN GAP: Pre-A1 not in CEFR_ORDER — code crashes with ValueError",
    strict=True,
)
def test_L4_TIER_PRE_A1_handling():
    """PERFECT STATE: Pre-A1 is a valid CEFR level and must not crash.

    Pre-A1 students exist (new arrivals, non-literate in L2). The system must
    handle them gracefully — expected tier is foundational for any RTI.
    """
    diff = ContentDifferentiator()
    lens = _build_lens(2, "Pre-A1")
    result = diff.assign_tier_for_student(lens)
    assert result == "foundational"
