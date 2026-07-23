"""Layer 5 Gauntlet: RTI Tier Change — state change propagates correctly without side effects.

Property proved: When a student's RTI tier changes, their future tier assignments
update accordingly, historical data is preserved, and other students are unaffected.

NOTE: StudentLensStore.update_rti_tier() does NOT exist yet.
The store has evaluate_rti_rules() (automated escalation) but no manual tier change method.
These tests document the expected behavior for the implementation team.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.education.student_lens import StudentLensStore, Observation
from src.education.content_differentiator import ContentDifferentiator

SKIP_RTI = "awaiting StudentLensStore.update_rti_tier(student_id, new_tier, trigger) implementation"


@pytest.mark.skip(reason=SKIP_RTI)
def test_gauntlet_rti_change_updates_tier_assignment():
    """RTI 1 → RTI 2: next tier assignment reflects new RTI.

    Expected: store.update_rti_tier(sid, 2, "teacher_concern")
    Then: assign_tier_for_student(lens) changes from on_track to foundational.
    """
    pass


@pytest.mark.skip(reason=SKIP_RTI)
def test_gauntlet_rti_change_preserves_history():
    """RTI change: historical observations and CEFR data remain unchanged.

    Expected: After tier change, cefr_snapshot is identical.
    rti_tier_history grows by one entry.
    """
    pass


@pytest.mark.skip(reason=SKIP_RTI)
def test_gauntlet_rti_change_no_side_effect_on_others():
    """Changing Marco's RTI doesn't affect Nora's lens or tier.

    Expected: Nora's lens is byte-identical before and after Marco's change.
    """
    pass


@pytest.mark.skip(reason=SKIP_RTI)
def test_gauntlet_rti_change_audit_trail():
    """RTI change is logged with timestamp and trigger reason.

    Expected: rti_tier_history[-1] == {"tier": 2, "trigger": "3_missed_targets", "from": <ts>}
    """
    pass


# --- Tests we CAN run against existing code ---


def test_gauntlet_rti_rules_evaluate():
    """evaluate_rti_rules() exists and returns escalation signals."""
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_eval.db")
        sid = store.create_lens(display_name="Rules Test", grade_level="G3")

        # Add multiple observations to trigger rule evaluation
        for _ in range(5):
            store.append_observation(Observation(
                student_id=sid,
                teacher_id="teacher-eval",
                template_type="cefr",
                raw_transcript="Struggling with reading comprehension",
                cefr_dimension="reading",
                cefr_level_observed="A1",
                cefr_direction="stable",
            ))

        # evaluate_rti_rules should return a list of rule results
        rules = store.evaluate_rti_rules(sid)
        assert isinstance(rules, list)
        store.close()


def test_gauntlet_initial_rti_history_has_one_entry():
    """New student has exactly 1 entry in rti_tier_history (the initial tier)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_hist.db")
        sid = store.create_lens(display_name="History Test", grade_level="G3")

        lens = store.get_lens(sid)
        assert len(lens["rti_tier_history"]) == 1
        assert lens["rti_tier_history"][0]["tier"] == 1
        assert lens["rti_tier_history"][0]["to"] is None  # Still current
        store.close()
