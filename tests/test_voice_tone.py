"""Tests for GIR → voice delivery tone resolver."""
from __future__ import annotations

from src.lingua_viva.voice_tone import (
    CLARIFY_THRESHOLD,
    PLAIN_THRESHOLD,
    resolve_voice_tone,
)


def test_high_score_returns_plain():
    result = resolve_voice_tone(0.95)
    assert result["tone"] == "plain"
    assert result["prefix"] == ""


def test_exact_plain_threshold():
    result = resolve_voice_tone(PLAIN_THRESHOLD)
    assert result["tone"] == "plain"
    assert result["prefix"] == ""


def test_mid_score_returns_clarify():
    result = resolve_voice_tone(0.6)
    assert result["tone"] == "clarify"
    assert "double check" in result["prefix"]


def test_exact_clarify_threshold():
    result = resolve_voice_tone(CLARIFY_THRESHOLD)
    assert result["tone"] == "clarify"


def test_just_below_plain_threshold():
    result = resolve_voice_tone(PLAIN_THRESHOLD - 0.01)
    assert result["tone"] == "clarify"


def test_low_score_returns_name_boundary():
    result = resolve_voice_tone(0.2)
    assert result["tone"] == "name_boundary"
    assert "starting point" in result["prefix"]


def test_just_below_clarify_threshold():
    result = resolve_voice_tone(CLARIFY_THRESHOLD - 0.01)
    assert result["tone"] == "name_boundary"


def test_zero_score():
    result = resolve_voice_tone(0.0)
    assert result["tone"] == "name_boundary"


def test_perfect_score():
    result = resolve_voice_tone(1.0)
    assert result["tone"] == "plain"
    assert result["prefix"] == ""


def test_path_record_grounding_fields():
    """PathRecord includes gir_score, gir_method, voice_tone with defaults."""
    from memory.schema.path import PathRecord

    p = PathRecord(
        session_id="s", query_hash="q", domain="d", entry_node="e",
        path=[], confidence_at_entry=0.5, confidence_at_exit=0.7,
        model_used="m", external_called=False, outcome="ok",
    )
    assert p.gir_score == 1.0
    assert p.gir_method == ""
    assert p.voice_tone == "plain"


def test_path_record_grounding_fields_roundtrip():
    """PathRecord grounding fields survive to_dict/from_dict."""
    from memory.schema.path import PathRecord

    p = PathRecord(
        session_id="s", query_hash="q", domain="d", entry_node="e",
        path=[], confidence_at_entry=0.5, confidence_at_exit=0.7,
        model_used="m", external_called=False, outcome="ok",
        gir_score=0.35, gir_method="claim_support_v1_heuristic",
        voice_tone="name_boundary",
    )
    d = p.to_dict()
    assert d["gir_score"] == 0.35
    assert d["gir_method"] == "claim_support_v1_heuristic"
    assert d["voice_tone"] == "name_boundary"

    p2 = PathRecord.from_dict(d)
    assert p2.gir_score == 0.35
    assert p2.gir_method == "claim_support_v1_heuristic"
    assert p2.voice_tone == "name_boundary"
