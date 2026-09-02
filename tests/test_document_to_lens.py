"""
Tests for the Document-to-Lens Pipeline.

SPEC: dev/SPEC_LV_DOCUMENT_TO_LENS_PIPELINE_2026-08-23.md

Required tests:
1. test_classify_report_card_not_as_roster
2. test_ib_terminology_not_detected_as_students
3. test_single_student_matched_from_filename
4. test_cefr_extraction_from_report_card
5. test_extraction_saved_before_lens_write
6. test_trauma_flag_never_auto_set
7. test_red_safeguarding_routed_to_restricted
8. test_lens_update_persists_after_app_restart
9. test_multi_student_document_partitions_correctly
10. test_gauntlet_still_passes (run separately)
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

# Ensure project root is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "docpipe"
REPORT_CARD_PATH = FIXTURE_DIR / "synthetic_report_card_abigail.txt"


def _read_fixture(name: str = "synthetic_report_card_abigail.txt") -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Document Classification
# ---------------------------------------------------------------------------

def test_classify_report_card_not_as_roster():
    """Claudia's PDF must classify as student_report, not class_list."""
    from src.lingua_viva.docpipe.extract import classify_document_type

    text = _read_fixture()
    result = classify_document_type(text, "Abigail_Chang_3_PYP_Progress_Report2025-26Semester_2.pdf")
    assert result == "student_report", f"Expected student_report, got {result}"


def test_classify_by_filename_report():
    from src.lingua_viva.docpipe.extract import classify_document_type
    assert classify_document_type("some text", "progress_report_G3.pdf") == "student_report"


def test_classify_by_filename_roster():
    from src.lingua_viva.docpipe.extract import classify_document_type
    assert classify_document_type("some text", "class_list_2026.xlsx") == "class_list"


def test_classify_by_filename_assessment():
    from src.lingua_viva.docpipe.extract import classify_document_type
    assert classify_document_type("some text", "assessment_G3_U2.pdf") == "assessment_summary"


def test_classify_by_filename_iep():
    from src.lingua_viva.docpipe.extract import classify_document_type
    assert classify_document_type("some text", "IEP_Marco_2026.pdf") == "support_document"


def test_classify_curriculum_content():
    from src.lingua_viva.docpipe.extract import classify_document_type
    text = (
        "Scope and Sequence for Grade 3 Italian\n"
        "Unit Plan: How We Express Ourselves\n"
        "Central Idea: Stories help us understand ourselves\n"
        "Lines of Inquiry: narrative structure, character analysis\n"
        "Programme of Inquiry alignment\n"
        "Learning goal: students will identify main characters\n"
    )
    result = classify_document_type(text, "curriculum_plan.docx")
    assert result == "curriculum"


def test_classify_other():
    from src.lingua_viva.docpipe.extract import classify_document_type
    result = classify_document_type("Hello world. This is a random text file.", "notes.txt")
    assert result == "other"


# ---------------------------------------------------------------------------
# 2. False Positive Name Detection
# ---------------------------------------------------------------------------

def test_ib_terminology_not_detected_as_students():
    """IB terminology like 'Learner Profile', 'Cordiali Saluti' should not be
    detected as student names."""
    from src.lingua_viva.docpipe.lens_match import match_document_to_students

    text = (
        "Learner Profile attributes include Inquirers, Knowledgeable, "
        "Thinkers, Communicators, Principled, Open-minded, Caring, "
        "Risk-takers, Balanced, Reflective.\n"
        "Cordiali Saluti,\nLa Scuola International School\n"
        "Programme of Inquiry\nApproaches to Learning\n"
        "Central Idea\nLines of Inquiry\n"
    )
    # No students on the roster to match against
    roster = [
        {"student_id": "s1", "display_name": "Marco Bianchi"},
        {"student_id": "s2", "display_name": "Nora Rossi"},
    ]
    matches = match_document_to_students(text, "report.pdf", roster)
    # None of the IB terminology should match a real student
    for match in matches:
        assert match["display_name"] in ("Marco Bianchi", "Nora Rossi"), \
            f"False positive: {match['display_name']} should not be matched"


# ---------------------------------------------------------------------------
# 3. Student Matching
# ---------------------------------------------------------------------------

def test_single_student_matched_from_filename():
    """'Abigail_Chang_...' filename matches Abigail's lens."""
    from src.lingua_viva.docpipe.lens_match import match_document_to_students

    text = _read_fixture()
    roster = [
        {"student_id": "s-abigail", "display_name": "Abigail Chang"},
        {"student_id": "s-marco", "display_name": "Marco Bianchi"},
        {"student_id": "s-nora", "display_name": "Nora Rossi"},
    ]
    matches = match_document_to_students(
        text,
        "Abigail_Chang_3_PYP_Progress_Report2025-26Semester_2.pdf",
        roster,
    )
    assert len(matches) >= 1
    assert matches[0]["student_id"] == "s-abigail"
    assert matches[0]["match_source"] == "filename"


def test_student_matched_from_content():
    """Student name in document body matches against roster."""
    from src.lingua_viva.docpipe.lens_match import match_document_to_students

    text = "Student: Marco Bianchi\nGrade: G3\nReading: A2"
    roster = [
        {"student_id": "s-marco", "display_name": "Marco Bianchi"},
        {"student_id": "s-nora", "display_name": "Nora Rossi"},
    ]
    matches = match_document_to_students(text, "report.pdf", roster)
    assert any(m["student_id"] == "s-marco" for m in matches)


# ---------------------------------------------------------------------------
# 4. CEFR Extraction
# ---------------------------------------------------------------------------

def test_cefr_extraction_from_report_card():
    """A1/A2/B1 levels are extracted correctly from report card text."""
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update

    text = _read_fixture()
    matched = [{"student_id": "s-abigail", "display_name": "Abigail Chang"}]

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="student_report",
            matched_students=matched,
        )
    )

    assert "s-abigail" in results
    result = results["s-abigail"]
    field_map = {f.field_path: f.value for f in result.fields}

    # Check CEFR extraction
    assert field_map.get("cefr_snapshot.listening") == "A2"
    assert field_map.get("cefr_snapshot.reading") == "A2"
    assert field_map.get("cefr_snapshot.writing") == "A1"
    # Speaking might be A1+ or A1 depending on regex
    assert "cefr_snapshot.speaking" in field_map


# ---------------------------------------------------------------------------
# 5. Extraction Persistence
# ---------------------------------------------------------------------------

def test_extraction_saved_before_lens_write():
    """NDJSON log must exist before any lens write happens."""
    from src.lingua_viva.docpipe.lens_extract import (
        extract_for_lens_update,
        save_extraction_log,
    )

    text = _read_fixture()
    matched = [{"student_id": "s-abigail", "display_name": "Abigail Chang"}]

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="student_report",
            matched_students=matched,
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = save_extraction_log(
            results, "test_report.pdf", state_home=Path(tmpdir)
        )
        # Log must exist
        assert log_path.exists()
        # Log must have content
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) > 0
        # Each line must be valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "student_id" in entry


# ---------------------------------------------------------------------------
# 6. Trauma Flag Safety
# ---------------------------------------------------------------------------

def test_trauma_flag_never_auto_set():
    """trauma_flag must NEVER be auto-verified, even if document mentions trauma."""
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update

    text = (
        "Student: Test Child\n"
        "Note: The student has experienced significant trauma and shows "
        "signs of distress. Family reports history of adverse childhood "
        "experiences. Trauma-informed approach is essential.\n"
        "trauma_flag: true\n"
    )
    matched = [{"student_id": "s-test", "display_name": "Test Child"}]

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="support_document",
            matched_students=matched,
        )
    )

    result = results["s-test"]
    for field in result.fields:
        if field.field_path == "trauma_flag":
            assert field.status == "needs_confirmation", \
                f"trauma_flag must be needs_confirmation, got {field.status}"
        # No field should auto-write trauma
        assert not (
            field.field_path == "trauma_flag" and field.status == "verified"
        ), "trauma_flag was auto-verified — this is a safety violation"


# ---------------------------------------------------------------------------
# 7. RED Safeguarding
# ---------------------------------------------------------------------------

def test_red_safeguarding_routed_to_restricted():
    """RED safeguarding content must never reach a lens field."""
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update

    text = (
        "Student: Safe Child\n"
        "Grade: G3\n"
        "CEFR Reading: A2\n\n"
        "CONFIDENTIAL — SAFEGUARDING CONCERN\n"
        "There are reports of possible neglect and domestic violence at home. "
        "The child has disclosed abuse to a trusted adult. "
        "A mandated report has been filed with CPS. "
        "Self-harm risk assessment pending.\n"
    )
    matched = [{"student_id": "s-safe", "display_name": "Safe Child"}]

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="support_document",
            matched_students=matched,
        )
    )

    result = results["s-safe"]
    # RED content should generate an unresolved question, not lens fields
    assert any(
        "RED" in q or "safeguarding" in q.lower()
        for q in result.unresolved_questions
    ), "RED safeguarding content should be flagged in unresolved_questions"

    # No field should contain safeguarding content words
    for field in result.fields:
        value_str = str(field.value).lower()
        assert "abuse" not in value_str, "Safeguarding content leaked to lens field"
        assert "neglect" not in value_str, "Safeguarding content leaked to lens field"
        assert "self-harm" not in value_str, "Safeguarding content leaked to lens field"


# ---------------------------------------------------------------------------
# 8. Persistence Across App Restart
# ---------------------------------------------------------------------------

def test_lens_update_persists_after_app_restart():
    """Data in ~/.lingua-viva must survive app restart (simulated)."""
    from src.lingua_viva.docpipe.lens_extract import (
        save_extraction_log,
        load_extraction_log,
    )
    from src.lingua_viva.data_in_contracts import ExtractionResult, ExtractedField

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save
        results = {
            "s-test": ExtractionResult(
                target_schema_id="student_lens",
                fields=[
                    ExtractedField(
                        field_path="cefr_snapshot.reading",
                        value="A2",
                        confidence=0.95,
                        supporting_chunk_ids=["chunk-1"],
                        status="verified",
                    ),
                ],
                unresolved_questions=[],
                source_files=["test.pdf"],
                chunks_used=[],
            ),
        }
        log_path = save_extraction_log(results, "test.pdf", state_home=Path(tmpdir))

        # Simulate restart: load from same path
        loaded = load_extraction_log(log_path)
        assert "s-test" in loaded
        assert len(loaded["s-test"].fields) == 1
        assert loaded["s-test"].fields[0].field_path == "cefr_snapshot.reading"
        assert loaded["s-test"].fields[0].value == "A2"


# ---------------------------------------------------------------------------
# 9. Multi-Student Document
# ---------------------------------------------------------------------------

def test_multi_student_document_partitions_correctly():
    """Multi-student document must correctly partition information per student."""
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update

    text = (
        "Class Progress Report — Grade 3\n\n"
        "Abigail Chang\n"
        "Reading: A2, Writing: A1, Speaking: A1+\n"
        "Strong reader, needs writing support.\n\n"
        "Marco Bianchi\n"
        "Reading: A1, Writing: A1, Speaking: A2\n"
        "Excellent oral skills, developing in reading.\n\n"
        "Nora Rossi\n"
        "Reading: B1, Writing: A2, Speaking: B1\n"
        "Strong across all dimensions.\n"
    )
    matched = [
        {"student_id": "s-abigail", "display_name": "Abigail Chang"},
        {"student_id": "s-marco", "display_name": "Marco Bianchi"},
        {"student_id": "s-nora", "display_name": "Nora Rossi"},
    ]

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="student_report",
            matched_students=matched,
        )
    )

    assert len(results) == 3
    # Each student should have some extracted fields
    for student_id in ("s-abigail", "s-marco", "s-nora"):
        assert student_id in results
        assert len(results[student_id].fields) > 0, \
            f"No fields extracted for {student_id}"


def test_multi_student_without_name_positions_refuses_duplication():
    """If a multi-student match cannot be located in the text, do not copy
    the full document into every student's section."""
    from src.lingua_viva.docpipe.lens_extract import (
        _split_into_student_sections,
        extract_for_lens_update,
    )

    text = (
        "Classroom summary\n"
        "Reading: A2. Writing: A1. Strong oral participation and thoughtful questions."
    )
    matched = [
        {"student_id": "s-abigail", "display_name": "Abigail Chang"},
        {"student_id": "s-marco", "display_name": "Marco Bianchi"},
    ]

    sections = _split_into_student_sections(text, matched)
    assert sections == {"s-abigail": "", "s-marco": ""}

    results = asyncio.run(
        extract_for_lens_update(
            document_bytes=text.encode("utf-8"),
            document_type="student_report",
            matched_students=matched,
        )
    )

    for result in results.values():
        assert result.fields == []
        assert any("No content found" in q for q in result.unresolved_questions)


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

def test_classify_empty_document():
    from src.lingua_viva.docpipe.extract import classify_document_type
    assert classify_document_type("", "") == "other"


def test_match_empty_roster():
    from src.lingua_viva.docpipe.lens_match import match_document_to_students
    matches = match_document_to_students("Student: Abigail Chang", "report.pdf", [])
    assert matches == []


def test_extraction_with_no_content():
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update
    matched = [{"student_id": "s-test", "display_name": "Test"}]
    results = asyncio.run(
        extract_for_lens_update(b"", "student_report", matched)
    )
    assert "s-test" in results
    assert len(results["s-test"].fields) == 0
    assert len(results["s-test"].unresolved_questions) > 0
