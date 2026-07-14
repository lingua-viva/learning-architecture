"""
Student Lens Tests — Product A core data model.

Test: lens create/append/get/export/delete work as specified
Test: observations are append-only (history never shrinks, never mutates)
Test: RTI tier changes are logged, never silently overwritten
Test: CEFR snapshot updates per-dimension from latest observation
Test: RTI escalation rules (A-E) trigger on the conditions they specify
Test: soft delete hides from get_lens but export/hard-delete still work
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.student_lens import (
    LensNotFoundError,
    Observation,
    ObservationValidationError,
    StudentLensStore,
)


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = StudentLensStore(db_path=Path(tmp) / "test.db")
        yield s
        s.close()


def test_create_lens_defaults(store):
    sid = store.create_lens(display_name="Test Student", campus="kenya", grade_level="G3")
    lens = store.get_lens(sid)
    assert lens["rti_current_tier"] == 1
    assert lens["rti_tier_history"] == [
        {"tier": 1, "from": lens["created_at"], "to": None, "trigger": None}
    ]
    assert lens["cefr_snapshot"] == {
        "reading": None, "writing": None, "speaking": None, "listening": None
    }
    assert lens["profile_version"] == 1
    assert lens["deleted"] is False


def test_create_lens_rejects_bad_tier(store):
    with pytest.raises(ObservationValidationError):
        store.create_lens(rti_current_tier=9)


def test_append_observation_updates_cefr_snapshot(store):
    sid = store.create_lens()
    obs = Observation(
        student_id=sid,
        teacher_id="t1",
        template_type="cefr",
        raw_transcript="She read the passage but lost the thread at paragraph 3",
        cefr_dimension="reading",
        cefr_level_observed="A2",
        cefr_direction="progressing",
    )
    result = store.append_observation(obs)
    assert result["validation_errors"] == []
    lens = store.get_lens(sid)
    assert lens["cefr_snapshot"]["reading"] == "A2"
    assert lens["cefr_snapshot"]["writing"] is None
    assert lens["profile_version"] == 2


def test_observations_are_append_only(store):
    sid = store.create_lens()
    for i in range(3):
        store.append_observation(
            Observation(
                student_id=sid, teacher_id="t1", template_type="literacy",
                raw_transcript=f"observation {i}",
            )
        )
    exported = store.export_lens(sid)
    assert len(exported["observations"]) == 3
    # No update path exists that mutates an existing observation row —
    # only append_observation (INSERT) touches the observations table.
    texts = [o["raw_transcript"] for o in exported["observations"]]
    assert texts == ["observation 0", "observation 1", "observation 2"]


def test_manual_rti_tier_change_is_logged_not_overwritten(store):
    sid = store.create_lens(rti_current_tier=1)
    store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="rti_flag",
            raw_transcript="Moving to tier 2 after repeated concern",
            rti_tier=2,
        )
    )
    lens = store.get_lens(sid)
    assert lens["rti_current_tier"] == 2
    history = lens["rti_tier_history"]
    assert len(history) == 2
    assert history[0]["tier"] == 1
    assert history[0]["to"] is not None  # closed out
    assert history[1]["tier"] == 2
    assert history[1]["to"] is None  # currently open


def test_observation_without_tier_defaults_to_current_tier(store):
    sid = store.create_lens(rti_current_tier=2)
    result = store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="literacy",
            raw_transcript="no tier specified",
        )
    )
    assert result["observation"]["rti_tier"] == 2
    assert result["observation"]["rti_tier_changed_this_obs"] is False


def test_rule_b_urgency_flag_triggers_immediate_notification(store):
    sid = store.create_lens()
    result = store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="sel_incident",
            raw_transcript="Safety concern observed", sel_domain="self_regulation",
            sel_valence="concern", urgency_flag=True,
        )
    )
    rules = {e["rule"] for e in result["escalations"]}
    assert "B" in rules


def test_rule_e_manual_tier_change_always_triggers_review(store):
    sid = store.create_lens(rti_current_tier=1)
    result = store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="rti_flag",
            raw_transcript="Escalating", rti_tier=3,
        )
    )
    rules = {e["rule"] for e in result["escalations"]}
    assert "E" in rules


def test_rule_d_sel_concerns_threshold(store):
    sid = store.create_lens()
    for i in range(3):
        store.append_observation(
            Observation(
                student_id=sid, teacher_id="t1", template_type="sel_incident",
                raw_transcript=f"concern {i}", sel_domain="peer_relations",
                sel_valence="concern",
            )
        )
    lens = store.get_lens(sid)
    assert lens["sel_summary"]["recent_concerns"] == 3
    assert lens["sel_summary"]["dominant_domain"] == "peer_relations"


def test_invalid_observation_is_saved_with_errors_not_dropped(store):
    sid = store.create_lens()
    result = store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="cefr",
            raw_transcript="missing cefr fields",
        )
    )
    assert len(result["validation_errors"]) > 0
    # still saved — Stage 2 rule: validation flags, never blocks save
    exported = store.export_lens(sid)
    assert len(exported["observations"]) == 1


def test_append_observation_unknown_student_raises(store):
    with pytest.raises(LensNotFoundError):
        store.append_observation(
            Observation(
                student_id="nonexistent", teacher_id="t1",
                template_type="literacy", raw_transcript="x",
            )
        )


def test_soft_delete_hides_from_get_but_export_still_works(store):
    sid = store.create_lens(display_name="To Delete")
    store.delete_lens(sid)
    with pytest.raises(LensNotFoundError):
        store.get_lens(sid)
    exported = store.export_lens(sid)
    assert exported["deleted"] is True


def test_hard_delete_purges_observations(store):
    sid = store.create_lens()
    store.append_observation(
        Observation(
            student_id=sid, teacher_id="t1", template_type="literacy",
            raw_transcript="will be purged",
        )
    )
    store.delete_lens(sid, hard=True)
    with pytest.raises(LensNotFoundError):
        store.export_lens(sid)


def test_list_lenses_filters_deleted_and_by_campus(store):
    a = store.create_lens(campus="kenya")
    store.create_lens(campus="colombia")
    store.delete_lens(a)
    kenya = store.list_lenses(campus="kenya")
    assert kenya == []
    colombia = store.list_lenses(campus="colombia")
    assert len(colombia) == 1


def test_avoid_pairing_with_defaults_empty(store):
    sid = store.create_lens(display_name="A")
    lens = store.get_lens(sid)
    assert lens["avoid_pairing_with"] == []


def test_create_lens_accepts_avoid_pairing_with(store):
    b = store.create_lens(display_name="B")
    sid = store.create_lens(display_name="A", avoid_pairing_with=[b])
    lens = store.get_lens(sid)
    assert lens["avoid_pairing_with"] == [b]


def test_set_avoid_pairing_with_replaces_not_appends(store):
    b = store.create_lens(display_name="B")
    c = store.create_lens(display_name="C")
    sid = store.create_lens(display_name="A")

    store.set_avoid_pairing_with(sid, [b])
    assert store.get_lens(sid)["avoid_pairing_with"] == [b]

    store.set_avoid_pairing_with(sid, [c])
    assert store.get_lens(sid)["avoid_pairing_with"] == [c]

    store.set_avoid_pairing_with(sid, [])
    assert store.get_lens(sid)["avoid_pairing_with"] == []


def test_set_avoid_pairing_with_unknown_student_raises(store):
    with pytest.raises(LensNotFoundError):
        store.set_avoid_pairing_with("nonexistent", ["x"])
