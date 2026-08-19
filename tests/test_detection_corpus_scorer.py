"""Corpus-scorer tests — Phase 0B of SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.

Locks the MEASUREMENT INSTRUMENT, not the detection quality: scoring math,
sealed-holdout skipping, report privacy (counts only by default), and that
the scorer runs the real extraction pipeline over the committed synthetic
corpus with internally consistent numbers. Detection-quality gates (0 FP on
curriculum, 6/6 recall on 3V, ...) belong to the STEP tests, not here —
asserting them now would just paint the baseline red forever.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lingua_viva.docpipe import corpus_scorer

SYNTHETIC_CORPUS = Path(__file__).parent / "fixtures" / "docpipe" / "synthetic-corpus"


# ---------------------------------------------------------------------------
# score_names — pure math
# ---------------------------------------------------------------------------

def test_score_names_math():
    result = corpus_scorer.score_names(
        expected=["Marco Bianchi", "Nora Rossi", "Sara Conti"],
        detected=["Marco Bianchi", "Luca Verdi"],
    )
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 2
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(1 / 3)
    assert result["false_positive_names"] == ["Luca Verdi"]
    assert sorted(result["false_negative_names"]) == ["Nora Rossi", "Sara Conti"]


def test_score_names_normalizes_whitespace_and_case_only():
    result = corpus_scorer.score_names(
        expected=["Marco  Bianchi"],
        detected=["  marco bianchi "],
    )
    assert result["true_positives"] == 1
    # spelling differences are NOT forgiven (identity resolution's job)
    result = corpus_scorer.score_names(expected=["Marco Bianchi"], detected=["Marco Bianci"])
    assert result["true_positives"] == 0


def test_score_names_zero_denominators_are_none_not_zero():
    # zero expected, zero detected: both undefined — never fake a 1.0 or 0.0
    result = corpus_scorer.score_names(expected=[], detected=[])
    assert result["precision"] is None
    assert result["recall"] is None
    # zero expected, some detected: precision 0.0 is real, recall undefined
    result = corpus_scorer.score_names(expected=[], detected=["Unità Uno"])
    assert result["precision"] == 0.0
    assert result["recall"] is None
    assert result["false_positives"] == 1


def test_score_names_ignores_blank_entries():
    result = corpus_scorer.score_names(expected=["", "  ", "Marco Bianchi"], detected=["", "Marco Bianchi"])
    assert result["expected_count"] == 1
    assert result["detected_count"] == 1
    assert result["true_positives"] == 1


# ---------------------------------------------------------------------------
# score_corpus — sealed holdout, missing files, labels lookup
# ---------------------------------------------------------------------------

def test_sealed_files_are_skipped_unless_holdout_opened(tmp_path, monkeypatch):
    (tmp_path / "labels.json").write_text(json.dumps({"files": [
        {"file": "open.xlsx", "shape": "s", "expected_students": ["A B"], "sealed": False},
        {"file": "held.xlsx", "shape": "s", "expected_students": ["C D"], "sealed": True},
    ]}), encoding="utf-8")
    (tmp_path / "open.xlsx").write_bytes(b"x")
    (tmp_path / "held.xlsx").write_bytes(b"x")
    monkeypatch.setattr(corpus_scorer, "detect_names", lambda path: ["A B"])

    records = corpus_scorer.score_corpus(tmp_path)
    by_file = {r["file"]: r for r in records}
    assert by_file["open.xlsx"]["status"] == "scored"
    assert by_file["held.xlsx"]["status"].startswith("SEALED")
    assert "true_positives" not in by_file["held.xlsx"]  # never scored, not even silently

    records = corpus_scorer.score_corpus(tmp_path, open_holdout=True)
    by_file = {r["file"]: r for r in records}
    assert by_file["held.xlsx"]["status"] == "scored"


def test_missing_file_is_reported_not_crashed(tmp_path):
    (tmp_path / "labels.json").write_text(json.dumps({"files": [
        {"file": "gone.xlsx", "shape": "s", "expected_students": [], "sealed": False},
    ]}), encoding="utf-8")
    records = corpus_scorer.score_corpus(tmp_path)
    assert records[0]["status"] == "MISSING FILE"


def test_labels_can_live_in_corpus_subdir(tmp_path, monkeypatch):
    # real-corpus layout: files at the top, labels in corpus/labels.json
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "labels.json").write_text(json.dumps({"files": [
        {"file": "f.xlsx", "shape": "s", "expected_students": ["A B"], "sealed": False},
    ]}), encoding="utf-8")
    (tmp_path / "f.xlsx").write_bytes(b"x")
    monkeypatch.setattr(corpus_scorer, "detect_names", lambda path: ["A B"])
    records = corpus_scorer.score_corpus(tmp_path)
    assert records[0]["status"] == "scored"
    assert records[0]["true_positives"] == 1


def test_missing_labels_raises():
    with pytest.raises(FileNotFoundError):
        corpus_scorer.score_corpus(Path("/nonexistent-corpus-dir"))


# ---------------------------------------------------------------------------
# format_report — privacy: counts only unless --show-names
# ---------------------------------------------------------------------------

def test_report_hides_names_by_default():
    records = [{
        "file": "f.xlsx", "shape": "s", "sealed": False, "status": "scored",
        "expected_count": 1, "detected_count": 1, "true_positives": 0,
        "false_positives": 1, "false_negatives": 1, "precision": 0.0, "recall": 0.0,
        "false_positive_names": ["Wrong Name"], "false_negative_names": ["Missed Name"],
    }]
    report = corpus_scorer.format_report(records)
    assert "Wrong Name" not in report
    assert "Missed Name" not in report
    report = corpus_scorer.format_report(records, show_names=True)
    assert "Wrong Name" in report
    assert "Missed Name" in report


# ---------------------------------------------------------------------------
# The committed synthetic corpus, scored by the REAL extraction pipeline
# ---------------------------------------------------------------------------

def test_synthetic_corpus_is_committed_and_labelled():
    labels = json.loads((SYNTHETIC_CORPUS / "labels.json").read_text(encoding="utf-8"))
    shapes = {entry["shape"] for entry in labels["files"]}
    assert shapes == {
        "grade_sheet_class_list", "single_sheet_support",
        "per_class_sheet_support", "curriculum_mapping", "cycle_calendar",
    }
    for entry in labels["files"]:
        assert (SYNTHETIC_CORPUS / entry["file"]).exists(), entry["file"]
        assert entry["sealed"] is False  # holdout sealing is a real-corpus concern
    # zero-student files really carry zero expected students
    by_shape = {e["shape"]: e for e in labels["files"]}
    assert by_shape["curriculum_mapping"]["expected_students"] == []
    assert by_shape["cycle_calendar"]["expected_students"] == []
    assert len(by_shape["single_sheet_support"]["expected_students"]) == 6


def test_scorer_runs_real_pipeline_over_synthetic_corpus():
    records = corpus_scorer.score_corpus(SYNTHETIC_CORPUS)
    assert len(records) == 5
    for record in records:
        assert record["status"] == "scored", record
        # internal consistency of the math on real pipeline output
        assert record["true_positives"] + record["false_negatives"] == record["expected_count"]
        assert record["true_positives"] + record["false_positives"] == record["detected_count"]
        if record["detected_count"]:
            assert record["precision"] == pytest.approx(
                record["true_positives"] / record["detected_count"])
        if record["expected_count"]:
            assert record["recall"] == pytest.approx(
                record["true_positives"] / record["expected_count"])
    # and the report renders every file
    report = corpus_scorer.format_report(records)
    for record in records:
        assert record["file"][:44] in report
