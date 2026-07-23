"""
Student Lens Tests — Product A core data model.

Test: lens create/append/get/export/delete work as specified
Test: observations are append-only (history never shrinks, never mutates)
Test: RTI tier changes are logged, never silently overwritten
Test: CEFR snapshot updates per-dimension from latest observation
Test: RTI escalation rules (A-E) trigger on the conditions they specify
Test: soft delete hides from get_lens but export/hard-delete still work
"""

import json
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


def test_new_lens_contains_support_profile_with_all_categories(store):
    sid = store.create_lens(display_name="Claudia")
    lens = store.get_lens(sid)
    assert "support_profile" in lens
    sp = lens["support_profile"]
    assert sp["schema_version"] == 2
    cats = sp["categories"]
    expected_ids = {
        "learning_and_cognition",
        "communication_and_language",
        "executive_functioning",
        "social_skills",
        "emotional_regulation",
        "physical_sensory_needs",
        "attendance_and_engagement",
        "advanced_enrichment",
    }
    assert set(cats.keys()) == expected_ids
    for cat_id, data in cats.items():
        assert data["needs"] == []
        assert data["strengths"] == []
        assert data["strategies_worked"] == []
        assert data["strategies_not_worked"] == []
        assert data["evidence"] == []
        assert data["open_questions"] == []


def test_existing_db_without_support_profile_migrates_cleanly(tmp_path):
    db_file = tmp_path / "old.db"
    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE students (
            student_id TEXT PRIMARY KEY,
            display_name TEXT,
            campus TEXT,
            grade_level TEXT,
            home_languages TEXT NOT NULL DEFAULT '[]',
            learning_differences TEXT NOT NULL DEFAULT '[]',
            trauma_flag INTEGER NOT NULL DEFAULT 0,
            avoid_pairing_with TEXT NOT NULL DEFAULT '[]',
            rti_current_tier INTEGER NOT NULL DEFAULT 1,
            rti_tier_history TEXT NOT NULL DEFAULT '[]',
            cefr_snapshot TEXT NOT NULL DEFAULT '{}',
            cefr_trajectory_30d TEXT NOT NULL DEFAULT 'insufficient_data',
            sel_summary TEXT NOT NULL DEFAULT '{}',
            profile_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO students (student_id, display_name, created_at, updated_at)
        VALUES ('s1', 'Old Student', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
    conn.close()

    s = StudentLensStore(db_path=db_file)
    lens = s.get_lens("s1")
    assert lens["display_name"] == "Old Student"
    assert lens["support_profile"]["schema_version"] == 2
    assert len(lens["support_profile"]["categories"]) == 8
    s.close()


def test_malformed_support_json_degrades_to_default(store):
    sid = store.create_lens(display_name="Broken JSON")
    store._conn.execute(
        "UPDATE students SET support_profile = 'NOT_VALID_JSON' WHERE student_id = ?",
        (sid,),
    )
    store._conn.commit()

    lens = store.get_lens(sid)
    assert lens["support_profile"]["schema_version"] == 2
    assert len(lens["support_profile"]["categories"]) == 8
    assert lens["support_profile_warnings"]


def test_malformed_support_bucket_warns_and_defaults(store):
    sid = store.create_lens(display_name="Bad Bucket")
    bad_profile = store.support_profile_default()
    bad_profile["categories"]["social_skills"]["needs"] = "not-a-list"
    store._conn.execute(
        "UPDATE students SET support_profile = ? WHERE student_id = ?",
        (json.dumps(bad_profile), sid),
    )
    store._conn.commit()

    lens = store.get_lens(sid)
    assert lens["support_profile"]["categories"]["social_skills"]["needs"] == []
    assert any("social_skills" in warning for warning in lens["support_profile_warnings"])


def test_add_support_entry_increments_profile_version(store):
    sid = store.create_lens(display_name="Entry Test")
    init_ver = store.get_lens(sid)["profile_version"]

    sp = store.add_support_entry(
        student_id=sid,
        category_id="learning_and_cognition",
        bucket="needs",
        text="Needs visual scaffolds for complex multiset tasks",
        created_by="teacher_1",
        confidence="imported_verified",
    )
    lens = store.get_lens(sid)
    assert lens["profile_version"] == init_ver + 1
    entries = lens["support_profile"]["categories"]["learning_and_cognition"]["needs"]
    assert len(entries) == 1
    assert entries[0]["text"] == "Needs visual scaffolds for complex multiset tasks"
    assert entries[0]["created_by"] == "teacher_1"
    assert entries[0]["confidence"] == "imported_verified"


def test_add_worked_and_not_worked_strategies(store):
    sid = store.create_lens(display_name="Strategy Test")
    store.add_support_entry(
        student_id=sid,
        category_id="communication_and_language",
        bucket="strategies_worked",
        text="Dual-language vocabulary flashcards (IT/EN)",
        created_by="t1",
    )
    store.add_support_entry(
        student_id=sid,
        category_id="communication_and_language",
        bucket="strategies_not_worked",
        text="Fast-paced unscripted audio dictation",
        created_by="t1",
    )

    sp = store.get_support_profile(sid)
    cat = sp["categories"]["communication_and_language"]
    assert len(cat["strategies_worked"]) == 1
    assert cat["strategies_worked"][0]["text"] == "Dual-language vocabulary flashcards (IT/EN)"
    assert len(cat["strategies_not_worked"]) == 1
    assert cat["strategies_not_worked"][0]["text"] == "Fast-paced unscripted audio dictation"


def test_unknown_category_is_rejected(store):
    sid = store.create_lens()
    with pytest.raises(ValueError, match="Unknown category ID"):
        store.add_support_entry(
            student_id=sid,
            category_id="unknown_category_id",
            bucket="needs",
            text="Invalid category test",
            created_by="t1",
        )


def test_advanced_enrichment_present_and_independent(store):
    sid = store.create_lens(display_name="High Potential Student", rti_current_tier=1)
    store.add_support_entry(
        student_id=sid,
        category_id="advanced_enrichment",
        bucket="strengths",
        text="Exhibits advanced mathematical reasoning; ready for G5 logic puzzles",
        created_by="t1",
    )

    lens = store.get_lens(sid)
    assert lens["rti_current_tier"] == 1  # RTI tier remains tier 1
    adv = lens["support_profile"]["categories"]["advanced_enrichment"]["strengths"]
    assert len(adv) == 1
    assert adv[0]["text"] == "Exhibits advanced mathematical reasoning; ready for G5 logic puzzles"


def test_add_support_evidence(store):
    sid = store.create_lens(display_name="Evidence Test")
    store.add_support_evidence(
        student_id=sid,
        category_id="executive_functioning",
        summary="Teacher checklist shows missing binder organization twice this week",
        created_by="t1",
        evidence_type="teacher_note",
    )
    sp = store.get_support_profile(sid)
    ev = sp["categories"]["executive_functioning"]["evidence"]
    assert len(ev) == 1
    assert ev[0]["evidence_type"] == "teacher_note"
    assert ev[0]["summary"] == "Teacher checklist shows missing binder organization twice this week"


def test_store_exposes_support_profile_default_method(store):
    profile = store.support_profile_default()
    assert profile["schema_version"] == 2
    assert "advanced_enrichment" in profile["categories"]


def test_replace_support_profile_rejects_malformed_entry(store):
    sid = store.create_lens()
    profile = store.support_profile_default()
    profile["categories"]["learning_and_cognition"]["needs"].append(
        {"text": "", "confidence": "teacher_confirmed"}
    )
    with pytest.raises(ValueError, match="Entry text"):
        store.replace_support_profile(sid, profile, reviewed_by="t1")


def test_replace_support_profile_rejects_invalid_evidence_type(store):
    sid = store.create_lens()
    profile = store.support_profile_default()
    profile["categories"]["executive_functioning"]["evidence"].append(
        {
            "summary": "Organizer checklist reviewed.",
            "evidence_type": "unsupported_source",
        }
    )
    with pytest.raises(ValueError, match="Invalid evidence_type"):
        store.replace_support_profile(sid, profile, reviewed_by="t1")


def test_add_support_entry_rejects_missing_created_by(store):
    sid = store.create_lens()
    with pytest.raises(ValueError, match="created_by"):
        store.add_support_entry(
            student_id=sid,
            category_id="learning_and_cognition",
            bucket="needs",
            text="Needs manipulatives.",
            created_by="",
        )


def test_add_support_entry_rejects_invalid_source_refs(store):
    sid = store.create_lens()
    with pytest.raises(ValueError, match="source_ref_ids"):
        store.add_support_entry(
            student_id=sid,
            category_id="learning_and_cognition",
            bucket="needs",
            text="Needs manipulatives.",
            created_by="t1",
            source_ref_ids=["valid", ""],
        )
