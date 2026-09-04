"""CEFR plus levels (A1+, A2+, B1+) must survive extraction — found 2026-09-04
by running roster -> report card -> Observe -> lens end to end: "Listening: A2+"
in a teacher's comment landed on the lens as A2. Both deterministic extractors
used `\\b` after the level; "+" is a non-word character so `A2\\+\\b` cannot
match "A2+." and the optional plus backtracked away."""

from __future__ import annotations

import pytest

from src.lingua_viva.docpipe.lens_extract import _extract_cefr
from src.lingua_viva.extraction_engine import _deterministic_cefr


@pytest.mark.parametrize("text,expected", [
    ("Listening: A2+. She was distracted.", {"listening": "A2+"}),
    ("Speaking: A1+\nReading: A2\nWriting: B1+", {"speaking": "A1+", "reading": "A2", "writing": "B1+"}),
    ("Reading - B1+ (end of term)", {"reading": "B1+"}),
    ("Listening: A2", {"listening": "A2"}),
])
def test_lens_extract_keeps_the_plus(text, expected):
    got = {f.field_path.split(".", 1)[1]: f.value for f in _extract_cefr(text)}
    assert got == expected


@pytest.mark.parametrize("text,expected", [
    ("Listening: A2+. She was distracted.", {"listening": "A2+"}),
    # Separate sentences: the engine's level-then-dimension window (25 chars,
    # no period) is a pre-existing heuristic and "A1+ and Writing" would
    # legitimately be read either way — that ambiguity is not under test here.
    ("Speaking: A1+. Writing: B1+.", {"speaking": "A1+", "writing": "B1+"}),
    ("reading level is A2 this term", {"reading": "A2"}),
])
def test_extraction_engine_keeps_the_plus(text, expected):
    assert _deterministic_cefr(text) == expected


def test_plus_level_is_not_confused_with_a_word_starting_with_the_level():
    # "A2x" is not a level; neither extractor may match it.
    assert _extract_cefr("Listening: A2x") == []
    assert _deterministic_cefr("Listening: A2x") == {}
