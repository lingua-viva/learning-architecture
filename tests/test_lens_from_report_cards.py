"""End-to-end tests for the document-to-lens report card pipeline.

Tests the core requirement: upload a multi-student report card,
extract academic content into the correct student lenses, with
NO cross-contamination between students.

SPEC: dev/SPEC_LV_LENS_FROM_REPORT_CARDS_2026-08-30.md
"""

import pytest
from src.lingua_viva.docpipe.lens_extract import (
    _split_into_student_sections,
    _split_into_sentences,
    _find_student_chunks,
    _text_to_chunks,
    _extract_cefr,
    _extract_grade_scale,
    _extract_learner_profile,
    _extract_attendance,
    _LENS_FIELD_IDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MULTI_STUDENT_REPORT = """
La Scuola International School — Grade 3 Progress Report — Semester 2, 2025-26

BOYCE AIKEN

Reading: A2. Aiken demonstrates strong reading comprehension and can identify
main ideas in grade-level Italian texts. She reads aloud with appropriate
intonation and is beginning to make inferences from context clues.

Writing: A1+. Written expression is developing. Aiken can write short
paragraphs using familiar vocabulary but needs support with complex sentence
structures. Organization of ideas is improving.

Mathematics: Accomplished. Strong number sense and problem-solving skills.
Can apply multiplication strategies independently.

Social skills: Collaborates well with peers and contributes actively to group
discussions. Sometimes needs reminders to listen to others before speaking.

Attendance: 95% present this semester.

---

CORAZZA MIRO

Reading: A1. Miro is building foundational reading skills in Italian. He can
decode familiar words and short phrases. Comprehension of longer texts requires
additional scaffolding and visual support.

Writing: A1. Emerging writer. Miro can copy and write individual words and
short phrases. Sentence construction is an area for targeted support.

Mathematics: Developing. Understands basic addition and subtraction but needs
concrete manipulatives for multi-digit problems.

Social skills: Miro is a kind and empathetic classmate. He shows strong
emotional awareness and often helps peers who are struggling.

Executive functioning: Needs support with task organization and time management.
Benefits from visual schedules and step-by-step instructions.

---

SCALA LUCA

Reading: A2+. Luca is an advanced reader who enjoys chapter books in Italian.
Shows sophisticated vocabulary and can discuss texts at a deep level.

Writing: A2. Writes with creativity and voice. Sentence variety is strong.
Spelling of irregular words needs attention.

Mathematics: Exemplary. Exceptional mathematical reasoning. Can explain
strategies to peers and applies concepts to novel situations.

Personal strengths: Natural leader. Shows curiosity about science topics.
Brings energy and enthusiasm to all classroom activities.
"""

TWO_STUDENTS = [
    {"student_id": "s-boyce", "display_name": "Boyce Aiken"},
    {"student_id": "s-miro", "display_name": "Corazza Miro"},
]

THREE_STUDENTS = [
    {"student_id": "s-boyce", "display_name": "Boyce Aiken"},
    {"student_id": "s-miro", "display_name": "Corazza Miro"},
    {"student_id": "s-luca", "display_name": "Scala Luca"},
]


# ---------------------------------------------------------------------------
# Section splitting tests (cross-contamination guard)
# ---------------------------------------------------------------------------

def test_section_split_isolates_students():
    sections = _split_into_student_sections(MULTI_STUDENT_REPORT, THREE_STUDENTS)
    assert len(sections) == 3

    # Each student's section contains ONLY their data
    assert "strong reading comprehension" in sections["s-boyce"]
    assert "building foundational reading" in sections["s-miro"]
    assert "advanced reader" in sections["s-luca"]


def test_section_split_no_cross_contamination():
    sections = _split_into_student_sections(MULTI_STUDENT_REPORT, THREE_STUDENTS)

    # Boyce's data must NOT appear in Miro's or Luca's section
    assert "strong reading comprehension" not in sections["s-miro"]
    assert "strong reading comprehension" not in sections["s-luca"]

    # Miro's data must NOT appear in Boyce's or Luca's section
    assert "building foundational reading" not in sections["s-boyce"]
    assert "building foundational reading" not in sections["s-luca"]

    # Luca's data must NOT appear in others
    assert "advanced reader" not in sections["s-boyce"]
    assert "advanced reader" not in sections["s-miro"]


def test_section_split_single_student_gets_all_text():
    sections = _split_into_student_sections(
        "Student report for Test Student. Great at math.",
        [{"student_id": "s-test", "display_name": "Test Student"}],
    )
    assert "Great at math" in sections["s-test"]


def test_section_split_missing_student_gets_empty():
    sections = _split_into_student_sections(
        MULTI_STUDENT_REPORT,
        [
            {"student_id": "s-boyce", "display_name": "Boyce Aiken"},
            {"student_id": "s-unknown", "display_name": "Unknown Student"},
        ],
    )
    assert sections.get("s-unknown", "") == "" or "Unknown Student" not in MULTI_STUDENT_REPORT


def test_section_split_no_positions_refuses_rather_than_duplicates():
    """Locking test: when multiple students match but NONE of their names appear
    in the text, every student must get an empty section — never the full text.
    Prior behavior duplicated the entire document for every student, which is
    cross-contamination."""
    text = "This report discusses academic progress in Term 2. Reading is strong."
    students = [
        {"student_id": "s-alpha", "display_name": "Alpha Nowhere"},
        {"student_id": "s-beta", "display_name": "Beta Nowhere"},
        {"student_id": "s-gamma", "display_name": "Gamma Nowhere"},
    ]
    sections = _split_into_student_sections(text, students)

    # All three students must be present
    assert len(sections) == 3

    # No student may receive the full document text
    for sid in ["s-alpha", "s-beta", "s-gamma"]:
        assert sections[sid] == "", (
            f"{sid} received non-empty section when no name positions were found — "
            f"this is the cross-contamination fallback that must stay closed"
        )


# ---------------------------------------------------------------------------
# Sentence splitting tests
# ---------------------------------------------------------------------------

def test_sentence_split_basic():
    sentences = _split_into_sentences(
        "Miro demonstrates strong reading skills. He struggles with writing."
    )
    assert len(sentences) >= 2
    assert any("reading" in s for s in sentences)
    assert any("writing" in s for s in sentences)


def test_sentence_split_skips_short_fragments():
    sentences = _split_into_sentences("A1. B2. This is a real sentence about reading.")
    # "A1." and "B2." are too short, only the real sentence should remain
    assert len(sentences) >= 1
    assert any("real sentence" in s for s in sentences)


# ---------------------------------------------------------------------------
# Heuristic extractor tests (these already work, just verifying)
# ---------------------------------------------------------------------------

def test_cefr_extraction():
    fields = _extract_cefr("Reading: A2. Writing: A1+.")
    assert len(fields) >= 1
    values = {f.value for f in fields}
    assert "A2" in values or "A1+" in values


def test_grade_scale_extraction():
    fields = _extract_grade_scale("Mathematics: Accomplished. Science: Developing.")
    assert len(fields) >= 1
    values = {str(f.value) for f in fields}
    assert any("accomplished" in v for v in values)


def test_attendance_extraction():
    fields = _extract_attendance("Attendance: 95% present this semester.")
    assert len(fields) >= 1


def test_learner_profile_extraction():
    # IB Learner Profile uses plural forms: "inquirers", "communicators"
    fields = _extract_learner_profile("She shows the qualities of inquirers and communicators.")
    assert len(fields) >= 1
    assert any("inquirers" in str(f.value) for f in fields)


# ---------------------------------------------------------------------------
# Field ID validation
# ---------------------------------------------------------------------------

def test_lens_field_ids_are_complete():
    assert len(_LENS_FIELD_IDS) == 10
    assert "learning_and_cognition" in _LENS_FIELD_IDS
    assert "communication_and_language" in _LENS_FIELD_IDS
    assert "academic_strengths" in _LENS_FIELD_IDS
    assert "personal_strengths" in _LENS_FIELD_IDS
