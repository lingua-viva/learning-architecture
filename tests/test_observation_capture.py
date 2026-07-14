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
