"""Voice §1 (SPEC_LV_VOICE_SCOPE_NARROWED_2026-08-08) — surface grounding lock.

Class rule: no surface may render an answer while dropping its grounding
verdict. The backend computes GIR + tone on every teacher query (pipeline
Step 6.25). This suite locks the surface side:

1. The single frontend safety gate mirrors ``resolve_voice_tone``'s
   thresholds and prefixes VERBATIM — string drift between voice_tone.py and
   static/index.html fails here.
2. Every Ask answer path (bubble, /api/ask, spoken) consumes the shared gate;
   no inline per-path GIR logic survives.
3. ``_build_query_response`` carries the exact ``resolve_voice_tone`` prefix
   for its GIR score — the golden "what would Marco need with no data" case
   must always surface the boundary prefix.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.lingua_viva.voice_tone import (
    CLARIFY_THRESHOLD,
    PLAIN_THRESHOLD,
    resolve_voice_tone,
)

REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


# --- 1. Threshold + prefix parity: voice_tone.py is the single source -------

def test_frontend_thresholds_match_resolve_voice_tone_exactly():
    assert f"score >= {PLAIN_THRESHOLD}" in HTML
    assert f"score >= {CLARIFY_THRESHOLD}" in HTML
    # The pre-Voice-§1 gate used 0.5 — that threshold class is closed.
    assert "score < 0.5" not in HTML


def test_frontend_fallback_prefixes_match_voice_tone_verbatim():
    clarify_prefix = resolve_voice_tone((PLAIN_THRESHOLD + CLARIFY_THRESHOLD) / 2)["prefix"]
    boundary_prefix = resolve_voice_tone(0.0)["prefix"]
    assert clarify_prefix.strip()
    assert boundary_prefix.strip()
    assert clarify_prefix in HTML
    assert boundary_prefix in HTML


# --- 2. One gate, every consumer --------------------------------------------

def test_gate_accepts_every_backend_gir_field_shape():
    # grounding.gir.score, gir_score, and bare numeric gir must all count as
    # a signal — a field-name mismatch must never read as "fully grounded".
    assert "meta && meta.gir_score" in HTML
    assert "meta && meta.gir]" in HTML


def test_ask_external_path_has_no_inline_gir_logic():
    # The /api/ask bubble + speech previously carried their own `< 0.8`
    # check; both must route through renderAnswerSafety instead.
    assert "data.gir !== undefined && data.gir < 0.8" not in HTML
    assert "girWarning" not in HTML
    assert "renderAnswerSafety(data).speechPrefix" in HTML


def test_ask_answer_meta_carries_the_verdict():
    # appendAskAnswer must persist gir + tone_prefix into message meta so the
    # shared renderer shows the verdict on re-render, not just once.
    assert "gir: data.gir," in HTML
    assert "tone_prefix: data.tone_prefix," in HTML


def test_every_answer_with_signal_shows_grounding_badge():
    # Visible grounding state on every answer that has a GIR signal, even
    # when no full grounding object is attached.
    assert "safety.hasSignal ? safety.girBadgeHtml" in HTML


# --- 3. Backend response carries the exact prefix ----------------------------

def _fake_result(gir_score, with_grounding=True):
    grounding = None
    if with_grounding:
        grounding = SimpleNamespace(
            as_dict=lambda: {"gir": {"score": gir_score, "method": "test"}, "tier_used": "none"},
        )
    tone = resolve_voice_tone(gir_score)["tone"]
    return SimpleNamespace(
        synthesis=SimpleNamespace(
            citations=[], model_used="ollama/test", content="answer", confidence=0.5,
        ),
        classification=SimpleNamespace(riu_id="RIU-1", name="n", domain="d", confidence=0.5),
        path_record=SimpleNamespace(voice_tone=tone, gir_score=gir_score, gir_method="test"),
        duration_ms=1,
        steps_executed=["CLASSIFY"],
        gap_signals=[],
        grounding=grounding,
    )


def test_empty_source_answer_carries_boundary_prefix():
    from src.web import _build_query_response

    response = _build_query_response(_fake_result(0.0), "what would Marco need", "s1", True)
    assert response["gir_score"] == 0.0
    assert response["tone_prefix"] == resolve_voice_tone(0.0)["prefix"]
    assert response["voice_tone"] == "name_boundary"


def test_clarify_tier_answer_carries_clarify_prefix():
    from src.web import _build_query_response

    response = _build_query_response(_fake_result(0.6), "question", "s1", True)
    assert response["tone_prefix"] == resolve_voice_tone(0.6)["prefix"]
    assert response["voice_tone"] == "clarify"


def test_grounded_answer_carries_no_prefix():
    from src.web import _build_query_response

    response = _build_query_response(_fake_result(0.95), "question", "s1", True)
    assert response["tone_prefix"] == ""
    assert response["voice_tone"] == "plain"


# --- TTS locale: English text never gets the Italian voice -------------------

def test_tts_defaults_to_english_not_italian():
    assert "const looksItalian" in HTML
    assert "const looksEnglish = !looksItalian" in HTML
