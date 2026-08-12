"""Test 02 — Document Pipeline: Lesson Plan → Student Lens

Scenario: A teacher feeds a lesson plan through docpipe. The system
extracts student references, builds evidence-backed lens profiles,
and verifies grounding (no claim without a source).

Claudia: replace SAMPLE_LESSON_PLAN with a real lesson plan or student
work sample. The pipeline handles markdown, plain text, or extracted PDF text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.lingua_viva.docpipe import lens, vault
from src.lingua_viva.docpipe.contracts import ExtractionRecord, ObservationRecord


# ── Sample lesson plan (replace with real material!) ────────────────

SAMPLE_EXTRACTION = {
    "schema_version": "docpipe.extraction.v1",
    "source_id": "SRC-DEMO-LESSON-001",
    "source_sha256": "demo",
    "extracted_at": "2026-08-11T20:00:00Z",
    "extractor": {"name": "docpipe.demo", "version": "1.0", "model": None},
    "mime": "text/markdown",
    "language": "en",
    "normalized_text": (
        "# MYP3 English — Persuasive Writing Unit\n\n"
        "## Student Work: Amina\n\n"
        "Amina wrote a strong persuasive paragraph using the claim-evidence-reasoning "
        "structure. She selected a relevant quotation from the source text and explained "
        "how repetition creates emphasis. Her vocabulary is strong and her inference "
        "careful. Next step: organize the final paragraph with a clearer topic sentence "
        "before adding the second quotation.\n\n"
        "## Student Work: David\n\n"
        "David's argument shows improving vocabulary — he used 'compelling' and "
        "'furthermore' correctly. His paragraph organization needs work; he tends to "
        "place his strongest point last rather than leading with it.\n"
    ),
    "spans": [
        {"span_id": "SPN-D01", "char_start": 0, "char_end": 45,
         "text": "# MYP3 English — Persuasive Writing Unit"},
        {"span_id": "SPN-D02", "char_start": 49, "char_end": 68,
         "text": "## Student Work: Amina"},
        {"span_id": "SPN-D03", "char_start": 70, "char_end": 380,
         "text": "Amina wrote a strong persuasive paragraph using the claim-evidence-reasoning "
                 "structure. She selected a relevant quotation from the source text and explained "
                 "how repetition creates emphasis. Her vocabulary is strong and her inference "
                 "careful. Next step: organize the final paragraph with a clearer topic sentence "
                 "before adding the second quotation."},
        {"span_id": "SPN-D04", "char_start": 383, "char_end": 405,
         "text": "## Student Work: David"},
        {"span_id": "SPN-D05", "char_start": 407, "char_end": 600,
         "text": "David's argument shows improving vocabulary — he used 'compelling' and "
                 "'furthermore' correctly. His paragraph organization needs work; he tends to "
                 "place his strongest point last rather than leading with it."},
    ],
    "structure": {
        "title": "MYP3 English — Persuasive Writing Unit",
        "document_type": "lesson_plan_review",
        "sections": [
            {"section_id": "amina", "heading": "Student Work: Amina", "span_ids": ["SPN-D03"]},
            {"section_id": "david", "heading": "Student Work: David", "span_ids": ["SPN-D05"]},
        ],
        "students_detected": [
            {"student_id": "student-amina", "display_name": "Amina",
             "confidence": 0.95, "span_ids": ["SPN-D02", "SPN-D03"]},
            {"student_id": "student-david", "display_name": "David",
             "confidence": 0.93, "span_ids": ["SPN-D04", "SPN-D05"]},
        ],
    },
    "warnings": [],
}

SAMPLE_OBSERVATION = {
    "schema_version": "docpipe.observation.v1",
    "obs_id": "OBS-DEMO-AMINA-001",
    "student_id": "student-amina",
    "created_at": "2026-08-11T20:30:00Z",
    "created_by": "teacher:claudia",
    "raw_transcript": (
        "Amina encouraged David to reorganize his paragraph. "
        "She used the sentence starter card to structure her second quotation."
    ),
    "teacher_edited_text": (
        "Amina encouraged David to reorganize his paragraph. "
        "Sentence starter card helped her structure the second quotation."
    ),
    "claims": [
        {"field_id": "personal_strengths",
         "value": "Encouraged a peer to reorganize their paragraph.",
         "confidence": 0.9},
        {"field_id": "strategies_trialed",
         "value": {"strategy": "Sentence starter card",
                   "outcome": "worked",
                   "evidence": "Helped structure the second quotation."},
         "confidence": 0.88},
    ],
}


def test_create_lens_from_lesson_plan(tmp_path: Path) -> None:
    """Docpipe extracts student references → builds a grounded lens."""
    extraction = ExtractionRecord(SAMPLE_EXTRACTION)

    record = lens.create_from_extraction(
        extraction,
        student_id="student-amina",
        student_name="Amina",
        added_by="teacher:claudia",
        root=tmp_path,
    )

    assert record.data["display_name"] == "Amina"
    profile = record.data["profile"]

    # At least one field populated from the lesson plan
    populated = [k for k, v in profile.items() if v.get("value") is not None]
    assert len(populated) >= 1, f"Expected populated fields, got: {populated}"

    # Evidence chains are intact
    for field_id in populated:
        evidence = profile[field_id].get("evidence", [])
        assert len(evidence) > 0, f"Field {field_id} has value but no evidence"
        for e in evidence:
            assert e.get("source_ref", {}).get("type") == "DOCUMENT"
            assert e.get("added_by") == "teacher:claudia"

    # _assert_grounded passes
    lens._assert_grounded(record.data)


def test_merge_observation_accumulates(tmp_path: Path) -> None:
    """An observation adds to the lens without losing existing data."""
    extraction = ExtractionRecord(SAMPLE_EXTRACTION)
    record = lens.create_from_extraction(
        extraction,
        student_id="student-amina",
        student_name="Amina",
        added_by="teacher:claudia",
        root=tmp_path,
    )

    initial_fields = {k for k, v in record.data["profile"].items()
                      if v.get("value") is not None}

    obs = ObservationRecord(SAMPLE_OBSERVATION)
    record2 = lens.merge_observation(
        record, obs, added_by="teacher:claudia", root=tmp_path,
    )

    # Original fields still present
    for f in initial_fields:
        assert record2.data["profile"][f].get("value") is not None

    # New fields from the observation
    assert record2.data["profile"]["personal_strengths"].get("value") is not None
    assert record2.data["profile"]["strategies_trialed"].get("value") is not None

    # merge_events tracked
    assert len(record2.data["metadata"]["merge_events"]) == 2

    # Still grounded
    lens._assert_grounded(record2.data)


def test_evidence_chain_traces_to_source(tmp_path: Path) -> None:
    """Every lens claim traces back to the original document or observation."""
    extraction = ExtractionRecord(SAMPLE_EXTRACTION)
    record = lens.create_from_extraction(
        extraction,
        student_id="student-amina",
        student_name="Amina",
        added_by="teacher:claudia",
        root=tmp_path,
    )

    obs = ObservationRecord(SAMPLE_OBSERVATION)
    record = lens.merge_observation(
        record, obs, added_by="teacher:claudia", root=tmp_path,
    )

    for field_id, field_data in record.data["profile"].items():
        if field_data.get("value") is None:
            continue
        for evidence in field_data.get("evidence", []):
            src = evidence["source_ref"]
            assert src["type"] in ("DOCUMENT", "OBSERVATION"), \
                f"Unknown source type in {field_id}: {src['type']}"
            if src["type"] == "DOCUMENT":
                assert "source_id" in src
                assert "span_id" in evidence
            elif src["type"] == "OBSERVATION":
                assert "obs_id" in evidence
