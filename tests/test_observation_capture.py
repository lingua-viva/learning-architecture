"""
Observation Capture Pipeline Tests — Product A end-to-end (classify ->
govern -> sanitize-audit -> lens update).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from ontology.engine import OntologyEngine
from src.education.observation_capture import (
    ExternalRoutingBlockedError,
    ObservationCapturePipeline,
)
from src.education.student_lens import StudentLensStore


@pytest.fixture(scope="module")
def engine():
    return OntologyEngine()


@pytest.fixture
def pipeline(engine):
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "test.db")
        yield ObservationCapturePipeline(store=store, engine=engine)
        store.close()


def test_capture_classifies_through_education_ontology(pipeline):
    sid = pipeline.store.create_lens()
    result = pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="I noticed a student struggling to follow instructions today",
        template_type="literacy",
    )
    assert result["classification"]["riu_id"].startswith("LV-")
    assert result["classification"]["blocks_external"] is True
    assert result["classification"]["requires_local"] is True
    assert result["governance_note"] is None


def test_capture_runs_sanitizer_audit(pipeline):
    sid = pipeline.store.create_lens()
    result = pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Contact her guardian at 555-123-4567 about the reading gap",
        template_type="literacy",
    )
    assert "sanitizer_report" in result
    assert result["sanitizer_report"]["redaction_count"] >= 1


def test_capture_persists_to_lens(pipeline):
    sid = pipeline.store.create_lens()
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="I noticed she read the passage but lost the thread at paragraph 3",
        template_type="cefr",
        cefr_dimension="reading",
        cefr_level_observed="A2",
        cefr_direction="progressing",
    )
    lens = pipeline.store.get_lens(sid)
    assert lens["cefr_snapshot"]["reading"] == "A2"
    exported = pipeline.store.export_lens(sid)
    assert len(exported["observations"]) == 1
    assert exported["observations"][0]["ontology_node"].startswith("LV-")


def test_capture_persists_even_when_classification_misses_lv_signals(pipeline):
    """Realistic teacher narration without trigger words ('I noticed',
    'observation', etc.) can classify to a non-LV, non-guarded node —
    measured directly (see BUILD_JOURNAL.md Turn 3). The observation
    must still be captured and lens-updated regardless: this pipeline's
    PII protection is structural (no external code path exists here),
    not dependent on classify() landing on an LV- node."""
    sid = pipeline.store.create_lens()
    result = pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="She read the passage but lost the thread at paragraph 3",
        template_type="cefr",
        cefr_dimension="reading",
        cefr_level_observed="A2",
    )
    assert not result["classification"]["riu_id"].startswith("LV-")
    assert result["governance_note"] is not None
    lens = pipeline.store.get_lens(sid)
    assert lens["cefr_snapshot"]["reading"] == "A2"


def test_assert_never_external_raises_on_blocked_node(pipeline, engine):
    classification = engine.classify(
        "I noticed a student struggling to follow instructions today"
    )
    assert classification.blocks_external is True
    with pytest.raises(ExternalRoutingBlockedError):
        pipeline.assert_never_external(classification)


def test_pending_sync_count_grows_with_captures(pipeline):
    sid = pipeline.store.create_lens()
    assert pipeline.pending_sync_count(student_id=sid) == 0
    pipeline.capture(
        student_id=sid, teacher_id="t1", raw_transcript="note one",
        template_type="literacy",
    )
    pipeline.capture(
        student_id=sid, teacher_id="t1", raw_transcript="note two",
        template_type="literacy",
    )
    assert pipeline.pending_sync_count(student_id=sid) == 2


def test_capture_with_need_statement_writes_support_profile_need(pipeline):
    sid = pipeline.store.create_lens(display_name="Need Test")
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Needs structured graphic organizer for writing essays",
        template_type="literacy",
        support_category="learning_and_cognition",
        need_statement="Needs structured graphic organizer for writing essays",
        evidence_summary="Observed during writing workshop",
    )

    lens = pipeline.store.get_lens(sid)
    cat = lens["support_profile"]["categories"]["learning_and_cognition"]
    assert len(cat["needs"]) == 1
    assert cat["needs"][0]["text"] == "Needs structured graphic organizer for writing essays"
    assert cat["needs"][0]["created_by"] == "t1"
    assert len(cat["evidence"]) == 1
    assert cat["evidence"][0]["summary"] == "Observed during writing workshop"


def test_capture_with_worked_and_did_not_work_strategies(pipeline):
    sid = pipeline.store.create_lens(display_name="Strategy Capture Test")

    # Worked strategy
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Chunking instructions into 2-step tasks worked great",
        template_type="literacy",
        support_category="executive_functioning",
        strategy_statement="Chunking instructions into 2-step tasks",
        strategy_outcome="worked",
    )

    # Did not work strategy
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Open-ended silent reading without checklist failed",
        template_type="literacy",
        support_category="executive_functioning",
        strategy_statement="Open-ended silent reading without checklist",
        strategy_outcome="did_not_work",
    )

    # Unknown outcome strategy (should not write to worked or did_not_work buckets)
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Trying color-coded highlighter strategy",
        template_type="literacy",
        support_category="executive_functioning",
        strategy_statement="Color-coded highlighter strategy",
        strategy_outcome="unknown",
        evidence_summary="Introduced today",
    )

    sp = pipeline.store.get_support_profile(sid)
    cat = sp["categories"]["executive_functioning"]
    assert len(cat["strategies_worked"]) == 1
    assert cat["strategies_worked"][0]["text"] == "Chunking instructions into 2-step tasks"
    assert len(cat["strategies_not_worked"]) == 1
    assert cat["strategies_not_worked"][0]["text"] == "Open-ended silent reading without checklist"
    # Unknown outcome only wrote evidence, not worked/not-worked buckets
    assert len(cat["evidence"]) == 1
    assert cat["evidence"][0]["summary"] == "Introduced today"


def test_observation_export_includes_structured_fields(pipeline):
    sid = pipeline.store.create_lens()
    pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Paces when nervous during oral presentations",
        template_type="sel_incident",
        support_category="emotional_regulation",
        need_statement="Needs pre-presentation calm-down protocol",
        source_type="teacher_note",
    )
    exported = pipeline.store.export_lens(sid)
    obs = exported["observations"][0]
    assert obs["support_category"] == "emotional_regulation"
    assert obs["need_statement"] == "Needs pre-presentation calm-down protocol"
    assert obs["source_type"] == "teacher_note"


def test_capture_with_multiple_support_entries_updates_multiple_categories(pipeline):
    sid = pipeline.store.create_lens(display_name="Multi Category Test")
    result = pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Checklist helped in English small group; student explained the idea clearly in Italian.",
        template_type="literacy",
        source_type="observation",
        support_entries=[
            {
                "support_category": "executive_functioning",
                "need_statement": "Needs task sequence checklist",
                "strategy_statement": "Two-step task checklist",
                "strategy_outcome": "worked",
                "evidence_summary": "Checklist helped in English small group",
                "context_tags": {"language": "en", "setting": "small_group"},
                "teacher_confirmed": True,
                "model_suggested": True,
                "teacher_edited": True,
            },
            {
                "support_category": "communication_and_language",
                "strength_statement": "Explains the idea clearly in Italian",
                "evidence_summary": "Oral explanation was stronger in Italian",
                "context_tags": {"language": "it", "setting": "classroom"},
                "teacher_confirmed": True,
                "model_suggested": True,
            },
        ],
    )

    obs_id = result["observation"]["observation_id"]
    sp = pipeline.store.get_support_profile(sid)
    executive = sp["categories"]["executive_functioning"]
    communication = sp["categories"]["communication_and_language"]
    assert executive["needs"][0]["source_observation_id"] == obs_id
    assert communication["strengths"][0]["source_observation_id"] == obs_id
    assert executive["strategies_worked"][0]["confidence"] == "teacher_confirmed"
    assert "context:language:en" in executive["evidence"][0]["source_ref_ids"]
    assert "context:language:it" in communication["evidence"][0]["source_ref_ids"]
    assert result["feedback"]["saved_entries"] == 5
    assert result["feedback"]["categories_updated"] == [
        "executive_functioning",
        "communication_and_language",
    ]


def test_unconfirmed_support_entries_do_not_update_support_profile(pipeline):
    sid = pipeline.store.create_lens(display_name="Unconfirmed Test")
    result = pipeline.capture(
        student_id=sid,
        teacher_id="t1",
        raw_transcript="Model proposed a category but teacher did not confirm.",
        template_type="literacy",
        support_entries=[
            {
                "support_category": "social_skills",
                "need_statement": "Needs turn-taking support",
                "teacher_confirmed": False,
            }
        ],
    )

    sp = pipeline.store.get_support_profile(sid)
    assert sp["categories"]["social_skills"]["needs"] == []
    assert result["feedback"]["saved_entries"] == 0
