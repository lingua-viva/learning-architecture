"""A report card written in Italian must give up its CEFR levels.

Witnessed by Claudia on PC-23, 2026-09-05 03:08Z, desktop-v0.2.91: she uploaded
demo-data/pagella_abigail_chang.txt ("Ascolto: A2 / Parlato: A1+ / Lettura: A2 /
Scrittura: A1"), clicked Update all lenses, and Abigail's CEFR snapshot stayed
empty — the level reader knew only reading / writing / speaking / listening.
Last night's chain ran on the English fixture, so it never saw this. For a
La Scuola teacher every report card is Italian; this is the ordinary input.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.lingua_viva.extraction_engine import _deterministic_cefr  # noqa: E402

ITALIAN_BLOCK = "--- Valutazione CEFR ---\n\nAscolto: A2\nParlato: A1+\nLettura: A2\nScrittura: A1\n"


def test_italian_skill_labels_map_to_the_four_dimensions():
    found = _deterministic_cefr(ITALIAN_BLOCK)
    assert found == {"listening": "A2", "speaking": "A1+", "reading": "A2", "writing": "A1"}, found


@pytest.mark.parametrize("text,expected", [
    ("Comprensione orale: B1\nProduzione orale: A2+", {"listening": "B1", "speaking": "A2+"}),
    ("Comprensione scritta B1+\nProduzione scritta A2", {"reading": "B1+", "writing": "A2"}),
    ("Listening: A2, Speaking: A1", {"listening": "A2", "speaking": "A1"}),
])
def test_other_italian_and_english_forms(text, expected):
    assert _deterministic_cefr(text) == expected


def test_prose_mentioning_a_skill_without_a_level_invents_nothing():
    text = "Abigail mostra buona comprensione nella lettura e sa riassumere storie. La sua scrittura è in fase di sviluppo."
    assert _deterministic_cefr(text) == {}


def test_the_demo_pagella_yields_all_four_levels_through_the_real_extractor(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config"))
    from src.lingua_viva.docpipe.extract import classify_document_type
    from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update
    from src.lingua_viva.docpipe.lens_match import match_document_to_students

    content = (REPO / "demo-data" / "pagella_abigail_chang.txt").read_bytes()
    text = content.decode("utf-8")
    roster = [{"student_id": "s1", "display_name": "Chang Abigail"}]  # surname first, as classe-3B.csv has it
    matched = match_document_to_students(text, "pagella_abigail_chang.txt", roster)
    assert matched and matched[0]["student_id"] == "s1"
    results = asyncio.run(extract_for_lens_update(
        document_bytes=content, document_type=classify_document_type(text, "pagella_abigail_chang.txt"),
        matched_students=matched, lens_store=None, engine=None,
    ))
    levels = {f.field_path.split(".")[-1]: f.value for f in results["s1"].fields if f.field_path.startswith("cefr_snapshot.")}
    assert levels == {"listening": "A2", "speaking": "A1+", "reading": "A2", "writing": "A1"}, levels
