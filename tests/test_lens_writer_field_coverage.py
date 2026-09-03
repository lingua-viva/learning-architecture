"""The lens writer must write what it previews, or say why it did not.

Measured on 2026-09-03, reproducing the operator's demo sequence end to end:

    import preview   cefr_snapshot.reading  = A2   status "verified"  conf 0.95
                     cefr_snapshot.writing  = A1
                     cefr_snapshot.speaking = A1
                     cefr_snapshot.listening= A2

    apply            fields_written: [4 support_profile paths]   <- CEFR absent
                     no error, no warning, HTTP 200

    lens after       cefr_snapshot: {reading: null, writing: null,
                                     speaking: null, listening: null}

The extractor emitted the fields (lens_extract.py:109). `write_student_lens`
had no branch for the path, so they fell off the end of its dispatch loop in
silence. A teacher saw four CEFR levels in the preview, clicked "Update
lenses", got a success message naming four *other* fields, and the lens stayed
empty. That defect survived a week of work on this exact feature because
nothing in the system was obliged to notice.

Two rules are pinned here:

1. CEFR levels extracted from a document reach the lens.
2. A field path the writer cannot handle produces a NAMED REFUSAL, never
   silence. This is the general rule; it is what protects Observe and Assess
   before either is wired, since both will emit new field paths.
"""

from __future__ import annotations

import pytest

from src.education.student_lens import (
    StudentLensStore,
    VALID_CEFR_DIMENSIONS,
)
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
from src.lingua_viva.student_lens_writer import write_student_lens


def _field(path, value, status="verified", chunks=("chunk-1",)):
    return ExtractedField(
        field_path=path,
        value=value,
        confidence=0.95,
        supporting_chunk_ids=list(chunks),
        status=status,
    )


def _result(fields):
    return ExtractionResult(
        target_schema_id="student_lens",
        fields=fields,
        unresolved_questions=[],
        source_files=["report_card.txt"],
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lenses.db"))
    s = StudentLensStore(db_path=tmp_path / "lenses.db")
    s.create_lens(student_id="student-test", display_name="Test Student")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# 1. CEFR reaches the lens
# ---------------------------------------------------------------------------

def test_cefr_levels_from_a_document_reach_the_lens(store):
    """The regression the operator hit. Four dimensions, four different levels."""
    levels = {"reading": "A2", "writing": "A1", "speaking": "A1", "listening": "A2"}
    out = write_student_lens(
        result=_result([_field(f"cefr_snapshot.{d}", v) for d, v in levels.items()]),
        store=store,
        hint={"student_id": "student-test"},
    )

    for dim in levels:
        assert f"cefr_snapshot.{dim}" in out["written_fields"], (
            f"cefr_snapshot.{dim} was previewed and then not written — "
            f"the silent-drop defect has returned"
        )

    lens = store.get_lens("student-test")
    snapshot = lens.get("cefr_snapshot") or {}
    for dim, expected in levels.items():
        assert snapshot.get(dim) == expected, (
            f"lens {dim} is {snapshot.get(dim)!r}, expected {expected!r}"
        )


def test_each_dimension_keeps_its_own_level(store):
    """A report card carries a DIFFERENT level per dimension. set_initial_cefr
    applies one level to all four, so it could not be reused for this path;
    this pins that the per-dimension distinction survives."""
    write_student_lens(
        result=_result([
            _field("cefr_snapshot.reading", "B1"),
            _field("cefr_snapshot.writing", "A1"),
        ]),
        store=store,
        hint={"student_id": "student-test"},
    )
    snap = store.get_lens("student-test").get("cefr_snapshot") or {}
    assert snap.get("reading") == "B1"
    assert snap.get("writing") == "A1"
    assert snap.get("reading") != snap.get("writing"), (
        "both dimensions collapsed to one level — the per-dimension write is gone"
    )


# ---------------------------------------------------------------------------
# 2. Refuse on unknown field path — the general rule
# ---------------------------------------------------------------------------

def test_unknown_field_path_is_refused_by_name_not_dropped(store):
    """The rule that protects Observe and Assess before they are built."""
    out = write_student_lens(
        result=_result([_field("favourite_colour", "blue")]),
        store=store,
        hint={"student_id": "student-test"},
    )
    assert "favourite_colour" not in out["written_fields"]
    assert any("favourite_colour" in q for q in out["unresolved_questions"]), (
        "an unwritable field path vanished without a word — this is exactly the "
        "silence that hid the CEFR defect for a week"
    )


def test_invalid_cefr_dimension_is_refused_by_name(store):
    out = write_student_lens(
        result=_result([_field("cefr_snapshot.telepathy", "A2")]),
        store=store,
        hint={"student_id": "student-test"},
    )
    assert "cefr_snapshot.telepathy" not in out["written_fields"]
    assert any("telepathy" in q for q in out["unresolved_questions"])


def test_invalid_cefr_level_is_refused_by_name(store):
    out = write_student_lens(
        result=_result([_field("cefr_snapshot.reading", "Z9")]),
        store=store,
        hint={"student_id": "student-test"},
    )
    assert "cefr_snapshot.reading" not in out["written_fields"]
    assert any("Z9" in q for q in out["unresolved_questions"])
    snap = store.get_lens("student-test").get("cefr_snapshot") or {}
    assert snap.get("reading") is None, "an invalid level was written to the lens"


def test_cefr_without_source_references_is_refused(store):
    """Same law the support-profile branch already enforces: no source refs,
    no write. A CEFR level is a claim about a child and needs a citation."""
    out = write_student_lens(
        result=_result([_field("cefr_snapshot.reading", "A2", chunks=())]),
        store=store,
        hint={"student_id": "student-test"},
    )
    assert "cefr_snapshot.reading" not in out["written_fields"]
    assert any("source references" in q for q in out["unresolved_questions"])


# ---------------------------------------------------------------------------
# 3. Non-vacuity — the refusal must be reachable and specific
# ---------------------------------------------------------------------------

def test_every_valid_dimension_is_actually_supported(store):
    """Guards a narrowing regression: if someone trims the accepted dimension
    set, this fails rather than silently refusing real report-card data."""
    out = write_student_lens(
        result=_result([_field(f"cefr_snapshot.{d}", "A2") for d in VALID_CEFR_DIMENSIONS]),
        store=store,
        hint={"student_id": "student-test"},
    )
    for dim in VALID_CEFR_DIMENSIONS:
        assert f"cefr_snapshot.{dim}" in out["written_fields"], (
            f"{dim} is a declared CEFR dimension but the writer refused it"
        )


def test_a_good_field_and_a_bad_field_in_one_import(store):
    """The realistic case: one field writes, one refuses, and BOTH are
    reported. Neither silently wins."""
    out = write_student_lens(
        result=_result([
            _field("cefr_snapshot.reading", "A2"),
            _field("not_a_real_field", "x"),
        ]),
        store=store,
        hint={"student_id": "student-test"},
    )
    assert "cefr_snapshot.reading" in out["written_fields"]
    assert any("not_a_real_field" in q for q in out["unresolved_questions"])
