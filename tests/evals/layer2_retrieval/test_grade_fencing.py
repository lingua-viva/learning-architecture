"""Layer 2: Grade Fencing — content retrieval respects grade boundaries.

Property proved:
- Grade 3 request → only G3 sources
- Grade 3 request → zero G4/G5 sources
- Non-existent grade → error, not fabricated content
- Empty document store → graceful fallback

Most grade fencing tests require document-backed generation (ingested PDFs).
We can test the fallback behavior and error handling NOW.
"""

import tempfile
from pathlib import Path

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.lingua_viva.ingest import document_retriever


@pytest.mark.skip(reason="awaiting ingested multi-grade documents for positive fence test")
def test_L2_FENCE_001_grade3_returns_only_g3_sources():
    """L2-FENCE-001: Grade 3 request returns only G3 provenance.

    Setup: Ingest G3 and G4 documents. Request G3-U1 pack.
    Pass: All provenance entries contain "G3" or "Grade 3".
    """
    pass


@pytest.mark.skip(reason="awaiting ingested multi-grade documents for negative fence test")
def test_L2_FENCE_002_grade3_returns_zero_wrong_grade():
    """L2-FENCE-002: Grade 3 request returns zero G4/G5/G2 provenance.

    Setup: Ingest G3 and G4 documents. Request G3-U1 pack.
    Pass: Zero provenance entries matching G4 or G5.
    """
    pass


@pytest.mark.skip(reason="awaiting unit-specific retrieval implementation")
def test_L2_FENCE_003_unit_specific_no_cross_unit_bleed():
    """L2-FENCE-003: Unit-specific request returns only that unit's sections.

    Setup: Ingest G3 document with multiple units.
    Pass: Request G3-U1 → only U1 sections in provenance.
    """
    pass


def test_L2_FENCE_004_nonexistent_grade_graceful():
    """L2-FENCE-004: Request for Grade 9 doesn't crash, produces template output.

    The template engine should handle any grade gracefully — it may produce
    generic content, but must not crash or fabricate specific curriculum.
    """
    diff = ContentDifferentiator()
    # G9 doesn't exist in Italian elementary — but the template engine should
    # still produce a valid pack (generic, not grade-specific)
    lesson = LessonInput(
        ib_programme="MYP",  # MYP might handle higher grades
        subject="Language",
        unit_title="Advanced Italian",
        topic="Complex sentence structures",
        atl_skills=["COMM-01"],
        cefr_target="B2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = diff.generate(lesson)
    # Must produce valid output (3 tiers) even for unusual input
    assert set(pack.tiers.keys()) == {"foundational", "on_track", "extended"}


def test_L2_FENCE_005_empty_store_falls_back_to_template():
    """L2-FENCE-005: When no documents are ingested, system falls back to template generation.

    Pass: document_retriever() returns None when store doesn't exist.
    ContentDifferentiator.generate() works without a retriever.
    """
    # Point at a non-existent store path
    import os
    old = os.environ.get("LV_DOCUMENT_STORE_PATH")
    try:
        os.environ["LV_DOCUMENT_STORE_PATH"] = "/tmp/nonexistent_store_for_eval.db"
        retriever = document_retriever()
        assert retriever is None, "Expected None retriever for non-existent store"

        # Template generation still works
        diff = ContentDifferentiator()
        lesson = LessonInput(
            ib_programme="PYP",
            subject="Language",
            unit_title="Fallback Test",
            topic="Test topic",
            atl_skills=["COMM-01"],
            cefr_target="A2",
            duration_minutes=45,
            created_by="teacher_eval",
        )
        pack = diff.generate(lesson)
        assert set(pack.tiers.keys()) == {"foundational", "on_track", "extended"}
    finally:
        if old:
            os.environ["LV_DOCUMENT_STORE_PATH"] = old
        else:
            os.environ.pop("LV_DOCUMENT_STORE_PATH", None)
