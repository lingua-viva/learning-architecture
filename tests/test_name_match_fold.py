"""Locking test for the name-comparison failure class (63d9631 / 972892c family).

The class: any site comparing student names with raw `.lower()` / `==` is
exposed to (a) surname-first vs first-last order, (b) accent sensitivity
(Lucà vs Luca), and silently loses observations. identity.normalize_name()
and identity.fold_text() are the two sanctioned comparators — normalize_name
when only the verdict matters, fold_text when character positions into the
original text must survive folding.

These tests lock every site that carried the bug so it cannot regress:
lens._span_ids_for_student, lens._mentions_student,
lens_extract._split_into_student_sections, lens_extract._find_student_chunks.
"""
from __future__ import annotations

from src.lingua_viva.docpipe.identity import fold_text, normalize_name
from src.lingua_viva.docpipe.lens import _mentions_student, _span_ids_for_student
from src.lingua_viva.docpipe.lens_extract import (
    SourceChunk,
    _find_student_chunks,
    _split_into_student_sections,
)


# ---------------------------------------------------------------------------
# fold_text — the position-preserving comparator
# ---------------------------------------------------------------------------


def test_fold_text_strips_accents_and_lowercases():
    assert fold_text("Lucà") == "luca"
    assert fold_text("Noëmi VILLA") == "noemi villa"


def test_fold_text_preserves_length_and_positions():
    original = "Report for Lucà Rossi — term 2\nHe reads well."
    folded = fold_text(original)
    assert len(folded) == len(original)
    idx = folded.find("luca rossi")
    assert idx == original.find("Lucà Rossi")


def test_fold_text_does_not_collapse_whitespace_unlike_normalize_name():
    text = "Anna   Villa"
    assert len(fold_text(text)) == len(text)
    assert normalize_name(text) == "anna villa"


# ---------------------------------------------------------------------------
# lens.py — span filtering
# ---------------------------------------------------------------------------


def _extraction_data(display_name: str) -> dict:
    return {
        "structure": {
            "students_detected": [
                {"student_id": "stu-1", "display_name": display_name,
                 "span_ids": ["span-1", "span-2"]},
            ],
        },
    }


def test_span_ids_match_reversed_name_order():
    # Roster stores surname-first; caller queries first-last.
    ids = _span_ids_for_student(_extraction_data("Chang Abigail"), "other-id", "Abigail Chang")
    assert ids == {"span-1", "span-2"}


def test_span_ids_match_accented_variant():
    ids = _span_ids_for_student(_extraction_data("Lucà Rossi"), "other-id", "Luca Rossi")
    assert ids == {"span-1", "span-2"}


def test_span_ids_no_match_for_different_child():
    ids = _span_ids_for_student(_extraction_data("Marco Bianchi"), "other-id", "Luca Rossi")
    assert ids == set()


def test_mentions_student_accent_and_order():
    assert _mentions_student("Noëmi has grown as a reader.", "Noemi")
    assert _mentions_student("Chang Abigail excelled this term.", "Abigail Chang")
    assert not _mentions_student("Marco excelled this term.", "Luca Rossi")


# ---------------------------------------------------------------------------
# lens_extract.py — section splitting (positions must survive folding)
# ---------------------------------------------------------------------------


def test_split_sections_finds_accented_names_at_correct_positions():
    text = (
        "Progress Report\n\n"
        "Lucà Rossi\nStrong reader this term.\n\n"
        "Noëmi Villa\nEnjoys mathematics.\n"
    )
    matched = [
        {"student_id": "stu-luca", "display_name": "Luca Rossi"},
        {"student_id": "stu-noemi", "display_name": "Noemi Villa"},
    ]
    sections = _split_into_student_sections(text, matched)
    assert "Strong reader" in sections["stu-luca"]
    assert "Enjoys mathematics" in sections["stu-noemi"]
    # No cross-contamination
    assert "Enjoys mathematics" not in sections["stu-luca"]
    assert "Strong reader" not in sections["stu-noemi"]


def test_split_sections_reversed_order_still_splits():
    text = "Rossi Luca\nReads well.\n\nVilla Noemi\nCounts well.\n"
    matched = [
        {"student_id": "stu-luca", "display_name": "Luca Rossi"},
        {"student_id": "stu-noemi", "display_name": "Noemi Villa"},
    ]
    sections = _split_into_student_sections(text, matched)
    assert "Reads well" in sections["stu-luca"]
    assert "Counts well" in sections["stu-noemi"]


# ---------------------------------------------------------------------------
# lens_extract.py — chunk finding
# ---------------------------------------------------------------------------


def _chunk(i: int, text: str) -> SourceChunk:
    return SourceChunk(
        chunk_id=f"doc-{i:04d}",
        file_path="uploaded-document",
        text=text,
        char_start=0,
        char_end=len(text),
    )


def test_find_student_chunks_accented_mention():
    chunks = [
        _chunk(0, "Lucà has made great progress in reading."),
        _chunk(1, "The class enjoyed the unit of inquiry."),
    ]
    relevant = _find_student_chunks(chunks, "Luca Rossi", "")
    assert [c.chunk_id for c in relevant] == ["doc-0000"]


# ---------------------------------------------------------------------------
# voice_intent.py — surname-first rosters (same class, voice surface)
# ---------------------------------------------------------------------------


def test_voice_detects_spoken_given_name_on_surname_first_roster():
    from src.lingua_viva.voice_intent import detect_student_detailed

    roster = [{"student_id": "stu-abigail", "display_name": "Chang Abigail"}]
    detection = detect_student_detailed("Abigail worked hard on her essay", roster)
    assert detection.student_id == "stu-abigail"
    assert detection.match_quality == "exact"


def test_voice_detects_reversed_full_name():
    from src.lingua_viva.voice_intent import detect_student_detailed

    roster = [{"student_id": "stu-abigail", "display_name": "Chang Abigail"}]
    detection = detect_student_detailed("Abigail Chang finished her essay", roster)
    assert detection.student_id == "stu-abigail"
    assert detection.match_quality == "exact"


def test_voice_siblings_sharing_surname_are_ambiguous_never_silent():
    from src.lingua_viva.voice_intent import detect_student_detailed

    roster = [
        {"student_id": "stu-abigail", "display_name": "Chang Abigail"},
        {"student_id": "stu-marco", "display_name": "Chang Marco"},
    ]
    detection = detect_student_detailed("Chang was very helpful today", roster)
    assert detection.student_id is None
    assert detection.match_quality == "ambiguous"
    assert {c["student_id"] for c in detection.candidates} == {"stu-abigail", "stu-marco"}


# ---------------------------------------------------------------------------
# extract.py — roster detection (same class, 6th surface: BUG-T1.1,
# Claudia QA v0.2.78). A capitalized header word ending one line ("Note\n")
# matched the next line's first name as a bigram, got blocklisted, and the
# already-consumed first name orphaned its surname — dropping the student
# silently. Two-part fix: bigrams never span line breaks; rejected
# candidates never consume the following token.
# ---------------------------------------------------------------------------


def _detect_names(text: str) -> list[str]:
    from src.lingua_viva.docpipe.extract import _build_spans, _detect_students

    return [d["display_name"] for d in _detect_students(_build_spans(text))]


def test_roster_first_row_after_header_is_not_dropped():
    # Claudia's exact fixture: "Note\nLucà Rossi" ate Lucà in v0.2.78.
    csv_text = (
        "Nome,Classe,Note\n"
        "Lucà Rossi,3B,\n"
        "Noëmi Villa,3B,\n"
        "Chang Abigail,3B,\n"
        "Chang Marco,3B,\n"
        "Bianchi Sofia,3B,\n"
        "Giuseppe Esposito,3B,\n"
    )
    assert _detect_names(csv_text) == [
        "Lucà Rossi", "Noëmi Villa", "Chang Abigail",
        "Chang Marco", "Bianchi Sofia", "Giuseppe Esposito",
    ]


def test_bigram_never_spans_line_breaks():
    # A capitalized word ending a line must not pair with the name below it.
    assert _detect_names("Progress Report\nLucà Rossi legge bene.") == ["Lucà Rossi"]


def test_rejected_candidate_does_not_consume_next_name():
    # "Note" (blocklisted) + name on the SAME line: rejection must rescan
    # from the second token, not swallow it.
    assert _detect_names("Note Lucà Rossi ha completato il tema.") == ["Lucà Rossi"]


def test_accepted_pairs_stay_non_overlapping():
    # Guard against over-detection: an accepted pair still consumes both
    # tokens — no phantom "Chang Marco" carved from adjacent names.
    assert _detect_names("Anna Chang Marco Bianchi") == ["Anna Chang", "Marco Bianchi"]
