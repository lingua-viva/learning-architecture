"""Gauntlet phase 1 — import + detection against the labeled corpus.

Every assertion here is EXACT against tests/fixtures/docpipe/synthetic-corpus/
labels.json. If detection drifts by even one name, this phase fails and says
which file and which name.
"""

from __future__ import annotations

from src.lingua_viva.docpipe import identity

from .conftest import (
    CORPUS_FILES,
    EXPECTED_STUDENTS,
    LABELS_BY_FILE,
    PDF_MIME,
    REFERENCES_DIR,
    detected_names,
    detected_students,
    extract_document,
    run,
    source_for,
)

# --- class list: all 19, nothing else ---------------------------------------


def test_class_list_detects_exactly_the_19_labeled_students(corpus_extractions):
    record = corpus_extractions["synthetic_class_list.xlsx"]
    names = detected_names(record)
    assert len(names) == 19
    assert set(names) == set(EXPECTED_STUDENTS)


def test_class_list_has_no_duplicates_and_no_false_positives(corpus_extractions):
    """The class list contains teacher rows, class-pair headers, and two
    stacked group tables (labels.json note) — none of those may surface."""
    record = corpus_extractions["synthetic_class_list.xlsx"]
    names = detected_names(record)
    assert len(names) == len(set(names))
    extras = set(names) - set(EXPECTED_STUDENTS)
    assert extras == set(), f"false positives detected: {sorted(extras)}"


def test_class_list_detections_are_verbatim_student_column_hits(corpus_extractions):
    """All 19 come from the roster's student column — verbatim evidence at
    confidence 0.99, never a model guess."""
    record = corpus_extractions["synthetic_class_list.xlsx"]
    for student in detected_students(record):
        assert student["evidence"] == "student_column", student["display_name"]
        assert student["confidence"] == 0.99, student["display_name"]


# --- support 3v: abbreviated names ------------------------------------------


def test_support_3v_detects_exactly_the_6_abbreviated_names(corpus_extractions):
    record = corpus_extractions["synthetic_support_3v.xlsx"]
    expected = LABELS_BY_FILE["synthetic_support_3v.xlsx"]["expected_students"]
    assert set(detected_names(record)) == set(expected)
    assert len(detected_names(record)) == 6


def test_support_3v_abbreviations_resolve_to_queue_with_right_candidate(gauntlet_env):
    """'Marco B-R' must NOT silently merge into Marco Bianchi — identity
    resolution queues it for the teacher, with the right candidate offered."""
    roster = [
        {"student_id": sid, "display_name": name}
        for name, sid in gauntlet_env["student_ids"].items()
    ]
    expected_candidates = {
        "Marco B-R": "Marco Bianchi",
        "Nora R-S": "Nora Rossi",
        "Elisa G-M": "Elisa Greco",
        "Giulia R-V": "Giulia Riva",
        "Matteo B-C": "Matteo Barbieri",
        "Viola P-S": "Viola Pellegrini",
    }
    for abbreviated, full in expected_candidates.items():
        resolution = identity.resolve(abbreviated, roster)
        assert resolution["status"] == "queue", abbreviated
        candidate_names = [c["display_name"] for c in resolution["candidates"]]
        assert full in candidate_names, (abbreviated, candidate_names)


def test_unknown_name_resolves_to_new_not_to_a_roster_student(gauntlet_env):
    roster = [
        {"student_id": sid, "display_name": name}
        for name, sid in gauntlet_env["student_ids"].items()
    ]
    resolution = identity.resolve("Sofia M.", roster)
    # Sofia Caruso is on the roster but "M." is not abbreviation-compatible
    # with "Caruso" — merging would corrupt a real student's record.
    assert resolution["status"] == "new"


# --- support k5: multi-sheet genre ------------------------------------------


def test_support_k5_detects_exactly_the_7_labeled_students(corpus_extractions):
    record = corpus_extractions["synthetic_support_k5.xlsx"]
    expected = LABELS_BY_FILE["synthetic_support_k5.xlsx"]["expected_students"]
    assert set(detected_names(record)) == set(expected)
    assert len(detected_names(record)) == 7


def test_support_k5_is_classified_as_student_support(corpus_extractions):
    record = corpus_extractions["synthetic_support_k5.xlsx"]
    assert record.data["structure"]["document_type"] == "student_support"


def test_support_k5_staff_first_name_block_not_detected(corpus_extractions):
    """The k5 sheets carry a staff first-name block (labels.json note) —
    single first names must never be promoted to students."""
    record = corpus_extractions["synthetic_support_k5.xlsx"]
    for name in detected_names(record):
        assert " " in name, f"bare first name detected as student: {name!r}"


# --- curriculum + calendar: zero students -----------------------------------


def test_curriculum_workbook_detects_zero_students(corpus_extractions):
    record = corpus_extractions["synthetic_curriculum.xlsx"]
    assert detected_students(record) == []


def test_calendar_workbook_detects_zero_students(corpus_extractions):
    record = corpus_extractions["synthetic_calendar.xlsx"]
    assert detected_students(record) == []


def test_no_labeled_student_leaks_into_curriculum_or_calendar(corpus_extractions):
    """Italian capitalized bigrams in curriculum text and month/room names in
    the calendar must not collide with the roster."""
    for name in ("synthetic_curriculum.xlsx", "synthetic_calendar.xlsx"):
        record = corpus_extractions[name]
        assert set(detected_names(record)) & set(EXPECTED_STUDENTS) == set()


# --- curriculum PDF: text yes, students no ----------------------------------


def test_curriculum_pdf_extracts_text_but_no_verbatim_students():
    """references/Criteri_Fondanti... is a curriculum rubric: text extraction
    must work, and no detection may claim student_column (verbatim) evidence.
    NB: the low-confidence bigram fallback DOES propose Italian phrase
    candidates ("La Scuola", ...) — those are model-tier guesses a teacher
    reviews, never auto-created students. The invariant pinned here is that
    none of them is presented as verbatim roster evidence and none matches a
    real student.
    """
    path = REFERENCES_DIR / "Criteri_Fondanti_Curricolo_Italiano_K-5.pdf"
    record = run(extract_document(source_for(path, mime=PDF_MIME), path.read_bytes()))
    text = record.data.get("normalized_text", "")
    assert len(text) > 1000, "PDF text extraction failed"
    verbatim = [s for s in detected_students(record) if s["evidence"] == "student_column"]
    assert verbatim == []
    assert set(detected_names(record)) & set(EXPECTED_STUDENTS) == set()


# --- extraction integrity ----------------------------------------------------


def test_every_corpus_extraction_completed_without_error(corpus_extractions):
    for name in CORPUS_FILES:
        record = corpus_extractions[name]
        assert record.data["structure"] is not None, name
