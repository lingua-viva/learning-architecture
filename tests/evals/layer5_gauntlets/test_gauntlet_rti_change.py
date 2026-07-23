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

def test_gauntlet_rti_change_updates_tier_assignment():
    """RTI 1 → RTI 2: next tier assignment reflects new RTI.

    Expected: store.update_rti_tier(sid, 2, "teacher_concern")
    Then: assign_tier_for_student(lens) changes from on_track to foundational.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_update.db")
        sid = store.create_lens(display_name="Marco", grade_level="G3", rti_current_tier=1)
        store.append_observation(Observation(
            student_id=sid,
            teacher_id="teacher-eval",
            template_type="cefr",
            raw_transcript="Reading at grade level with good comprehension",
            cefr_dimension="reading",
            cefr_level_observed="A2",
            cefr_direction="progressing",
        ))

        engine = ContentDifferentiator()
        lens_before = store.get_lens(sid)
        tier_before = engine.assign_tier_for_student(lens_before)
        assert tier_before == "on_track"

        store.update_rti_tier(sid, 2, "teacher_concern")

        lens_after = store.get_lens(sid)
        assert lens_after["rti_current_tier"] == 2
        tier_after = engine.assign_tier_for_student(lens_after)
        assert tier_after == "foundational"
        store.close()


def test_gauntlet_rti_change_preserves_history():
    """RTI change: historical observations and CEFR data remain unchanged.

    Expected: After tier change, cefr_snapshot is identical.
    rti_tier_history grows by one entry.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_preserve.db")
        sid = store.create_lens(display_name="Marco", grade_level="G3")
        store.append_observation(Observation(
            student_id=sid,
            teacher_id="teacher-eval",
            template_type="cefr",
            raw_transcript="Solid vocabulary use in class discussion",
            cefr_dimension="speaking",
            cefr_level_observed="A2",
            cefr_direction="progressing",
        ))

        lens_before = store.get_lens(sid)
        cefr_before = lens_before["cefr_snapshot"]
        history_len_before = len(lens_before["rti_tier_history"])

        store.update_rti_tier(sid, 2, "team_meeting_decision")

        lens_after = store.get_lens(sid)
        assert lens_after["cefr_snapshot"] == cefr_before
        assert len(lens_after["rti_tier_history"]) == history_len_before + 1
        store.close()


def test_gauntlet_rti_change_no_side_effect_on_others():
    """Changing Marco's RTI doesn't affect Nora's lens or tier.

    Expected: Nora's lens is byte-identical before and after Marco's change.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_isolation.db")
        marco_id = store.create_lens(display_name="Marco", grade_level="G3")
        nora_id = store.create_lens(display_name="Nora", grade_level="G3")

        nora_before = store.get_lens(nora_id)

        store.update_rti_tier(marco_id, 3, "teacher_concern")

        nora_after = store.get_lens(nora_id)
        assert nora_after == nora_before
        store.close()


def test_gauntlet_rti_change_audit_trail():
    """RTI change is logged with timestamp and trigger reason.

    Expected: rti_tier_history[-1] == {"tier": 2, "trigger": "3_missed_targets", "from": <ts>}
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "rti_audit.db")
        sid = store.create_lens(display_name="Marco", grade_level="G3")

        store.update_rti_tier(sid, 2, "3_missed_targets")

        lens = store.get_lens(sid)
        last_entry = lens["rti_tier_history"][-1]
        assert last_entry["tier"] == 2
        assert last_entry["trigger"] == "3_missed_targets"
        assert last_entry["from"] is not None
        assert last_entry["to"] is None

        # Prior entry should be closed off (its "to" is now set)
        prior_entry = lens["rti_tier_history"][-2]
        assert prior_entry["to"] == last_entry["from"]
        store.close()


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
