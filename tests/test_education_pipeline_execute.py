"""
Education EXECUTE step tests — Gap 4, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Covers all 4 wired nodes (LV-CUR-002, LV-TCH-002, LV-STU-003, LV-ASS-001)
in both their "ok" (real data present) and "missing_data" (honest fallback)
paths, plus the specific `source_mode == "generated"` guard that stops a
templated ContentPack from ever being presented as grounded.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.pipeline_execute import (
    EducationExecutor,
    NO_CURRICULUM_MESSAGE,
    NO_STUDENTS_MESSAGE,
    NO_STUDENT_IDENTIFIED_MESSAGE,
)
from src.education.student_lens import Observation, StudentLensStore


@pytest.fixture
def lens_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "test.db"


@pytest.fixture
def store_factory(lens_db_path):
    def factory():
        return StudentLensStore(db_path=lens_db_path)
    return factory


class FakeRetriever:
    """Duck-typed document_retriever: .retrieve(query, domain, k) -> list[dict]."""

    def __init__(self, chunks=None):
        self._chunks = chunks or []

    def retrieve(self, query, domain, k=5):
        return self._chunks


REAL_CHUNK = {
    "text": (
        "Photosynthesis converts light energy into chemical energy. "
        "Plants use sunlight, water, and carbon dioxide to produce glucose "
        "and oxygen. This process occurs in the chloroplasts of plant cells. "
        "The light-dependent reactions occur in the thylakoid membrane."
    ),
    "source_file": "biology_unit_3.pdf",
    "section": "3.2 Photosynthesis",
    "page_start": 12,
    "page_end": 13,
}


# -- LV-CUR-002: differentiation -----------------------------------------


def test_differentiation_missing_data_when_no_retriever(store_factory):
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-CUR-002", "photosynthesis lesson")
    assert result.status == "missing_data"
    assert result.markdown == NO_CURRICULUM_MESSAGE


def test_differentiation_missing_data_when_nothing_retrieved(store_factory):
    executor = EducationExecutor(
        document_retriever=FakeRetriever(chunks=[]),
        student_lens_store_factory=store_factory,
    )
    result = executor.execute("LV-CUR-002", "photosynthesis lesson")
    # generate_from_documents() silently falls back to the template path
    # (source_mode == "generated") when nothing was retrieved — this must
    # be intercepted as missing_data, never presented as grounded.
    assert result.status == "missing_data"
    assert result.markdown == NO_CURRICULUM_MESSAGE


def test_differentiation_ok_when_real_chunks_retrieved(store_factory):
    executor = EducationExecutor(
        document_retriever=FakeRetriever(chunks=[REAL_CHUNK]),
        student_lens_store_factory=store_factory,
    )
    result = executor.execute("LV-CUR-002", "photosynthesis lesson")
    assert result.status == "ok"
    assert "# Differentiated Content:" in result.markdown
    assert "Foundational" in result.markdown
    assert "On Track" in result.markdown
    assert "Extended" in result.markdown
    assert "## Source Material" in result.markdown
    assert "biology_unit_3.pdf p.12-13" in result.markdown


# -- LV-TCH-002: grouping --------------------------------------------------


def test_grouping_missing_data_when_no_roster(store_factory):
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-TCH-002", "group my class")
    assert result.status == "missing_data"
    assert result.markdown == NO_STUDENTS_MESSAGE


def test_grouping_ok_with_roster(store_factory):
    store = store_factory()
    store.create_lens(student_id="s1", display_name="Amina", rti_current_tier=1)
    store.create_lens(student_id="s2", display_name="Karim", rti_current_tier=3)
    store.close()

    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-TCH-002", "group my class for tomorrow")
    assert result.status == "ok"
    assert "Amina" in result.markdown
    assert "Karim" in result.markdown


# -- LV-STU-003: RTI --------------------------------------------------------


def test_rti_missing_data_when_no_roster(store_factory):
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-STU-003", "how is Amina doing")
    assert result.status == "missing_data"
    assert result.markdown == NO_STUDENT_IDENTIFIED_MESSAGE


def test_rti_missing_data_when_student_not_identified(store_factory):
    store = store_factory()
    store.create_lens(student_id="s1", display_name="Amina")
    store.close()

    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-STU-003", "how are my students doing")
    assert result.status == "missing_data"
    assert result.markdown == NO_STUDENT_IDENTIFIED_MESSAGE


def test_rti_fresh_lens_shows_honest_no_observations_not_literal_none(store_factory):
    store = store_factory()
    store.create_lens(student_id="s1", display_name="Amina")
    store.close()

    # create_lens() seeds an initial (tier 1, no trigger) history entry, so
    # this renders "ok" — but its cefr_snapshot is {dim: None, ...}, which
    # must render as the honest "no observations" line, never "reading: None".
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-STU-003", "what is Amina's RTI status")
    assert result.status == "ok"
    assert "No CEFR observations recorded yet." in result.markdown
    assert "None" not in result.markdown


def test_rti_ok_after_observation_logged(store_factory):
    store = store_factory()
    store.create_lens(student_id="s1", display_name="Amina")
    store.append_observation(Observation(
        student_id="s1",
        teacher_id="t1",
        template_type="cefr",
        raw_transcript="Amina read a paragraph aloud fluently today.",
        cefr_dimension="reading",
        cefr_level_observed="B1",
        cefr_direction="progressing",
    ))
    store.close()

    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-STU-003", "what is Amina's RTI status")
    assert result.status == "ok"
    assert "# RTI Status: Amina" in result.markdown
    assert "Tier movement is always a human decision" in result.markdown


# -- LV-ASS-001: assessment --------------------------------------------------


def test_assessment_missing_data_when_no_retriever(store_factory):
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    result = executor.execute("LV-ASS-001", "assess photosynthesis unit")
    assert result.status == "missing_data"
    assert result.markdown == NO_CURRICULUM_MESSAGE


def test_assessment_missing_data_when_nothing_retrieved(store_factory):
    executor = EducationExecutor(
        document_retriever=FakeRetriever(chunks=[]),
        student_lens_store_factory=store_factory,
    )
    result = executor.execute("LV-ASS-001", "assess photosynthesis unit")
    assert result.status == "missing_data"
    assert result.markdown == NO_CURRICULUM_MESSAGE


def test_assessment_ok_when_real_chunks_retrieved(store_factory):
    executor = EducationExecutor(
        document_retriever=FakeRetriever(chunks=[REAL_CHUNK]),
        student_lens_store_factory=store_factory,
    )
    result = executor.execute("LV-ASS-001", "assess photosynthesis unit")
    assert result.status == "ok"
    assert result.markdown.strip()


# -- Node routing -------------------------------------------------------


def test_unwired_node_returns_none(store_factory):
    executor = EducationExecutor(document_retriever=None, student_lens_store_factory=store_factory)
    assert executor.execute("LV-SOMETHING-ELSE", "irrelevant query") is None
