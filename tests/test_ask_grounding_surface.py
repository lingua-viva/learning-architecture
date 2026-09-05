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
import pytest

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
    # Visible grounding state on every answer that has a GIR signal, even when
    # no full grounding object is attached.
    #
    # Widened 2026-08-27. This previously asserted the literal gate
    # "safety.hasSignal ? safety.girBadgeHtml", which suppressed the badge for
    # exactly the case it most needed to show: a local answer about a child
    # carrying NO signal at all. girBadgeHtml is "" when there is nothing to
    # render, so it is consumed directly and the no-signal case now produces
    # its own unverified badge.
    assert ": safety.girBadgeHtml;" in HTML
    assert "safety.hasSignal ? safety.girBadgeHtml" not in HTML


def test_ungrounded_local_answer_is_never_rendered_as_grounded():
    """An answer about a child with no GIR signal and no sources is unverified.

    renderAnswerSafety defaults an absent score to 1, which lands in the
    "plain" tier and renders no warning. For a local answer — one built from a
    child's own lens and observations — arriving with no signal AND no sources,
    that is a false green on the highest-stakes surface in the product: a
    confident paragraph about a student with nothing to check it against.

    Scoped deliberately to local answers with nothing to verify: an external
    answer, or any answer carrying a real score or a source, is unaffected.
    """
    assert "const ungroundedLocalAnswer" in HTML
    assert "!hasSignal && sourceCount === 0" in HTML
    # It must feed the tier decision, not merely be computed.
    assert "fabricated.length > 0 || ungroundedLocalAnswer" in HTML
    # And it must surface its own badge, since there is no score to print.
    assert "unverified · no grounding signal" in HTML


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


# --- 4. The gate is EXECUTED, not just grepped --------------------------------
#
# Everything above asserts that source strings exist. That catches deletion but
# proves nothing about behaviour: a live browser run on 2026-08-27 confirmed
# the unverified badge appeared, but via the GIR path (a real score of 0.00) —
# the !hasSignal branch added the same day never actually ran. String
# assertions cannot tell those two paths apart.
#
# These tests extract renderAnswerSafety from static/index.html and run it in
# node across the cases that matter, so the no-signal branch is exercised for
# real and the narrow scoping is enforced rather than assumed.

import json
import shutil
import subprocess
import tempfile


def _extract_js_function(name: str) -> str:
    """Pull one top-level function out of index.html by brace matching."""
    start = HTML.index(f"function {name}(")
    brace = HTML.index("{", start)
    depth, i = 0, brace
    while i < len(HTML):
        if HTML[i] == "{":
            depth += 1
        elif HTML[i] == "}":
            depth -= 1
            if depth == 0:
                return HTML[start:i + 1]
        i += 1
    raise AssertionError(f"could not brace-match {name}")


def _run_safety_cases(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available to execute the safety gate")
    script = (
        "const escapeHtml = v => String(v ?? '');\n"
        + _extract_js_function("renderAnswerSafety")
        + "\nconst out = "
        + json.dumps(cases)
        + ".map(m => { const r = renderAnswerSafety(m);"
        " return {tier: r.tier, unsafe: r.unsafe, warns: Boolean(r.warningHtml),"
        " badge: r.girBadgeHtml}; });\n"
        "console.log(JSON.stringify(out));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(script)
        path = handle.name
    result = subprocess.run([node, path], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_no_signal_branch_actually_fires_for_an_ungrounded_local_answer():
    """The !hasSignal branch — the one the browser run never reached.

    No gir field at all, no sources, local_only. Before the fix this scored a
    default 1, landed in "plain", and rendered no warning whatsoever.
    """
    (result,) = _run_safety_cases([{"local_only": True, "sources": []}])
    assert result["tier"] == "name_boundary", result
    assert result["unsafe"] is True
    assert result["warns"] is True, "an ungrounded answer about a child rendered no warning"
    assert "no grounding signal" in result["badge"], result["badge"]


def test_the_new_branch_is_narrow_and_adds_no_other_warnings():
    """Conjunctive by construction — everything else must be untouched."""
    cases = [
        {"local_only": True, "sources": ["observation 2026-05-02"]},   # has a source
        {"local_only": True, "sources": [], "gir": 0.91},              # has a score
        {"local_only": False, "sources": []},                          # not local
        {},                                                            # plain chat
    ]
    results = _run_safety_cases(cases)
    for case, result in zip(cases, results):
        assert result["tier"] == "plain", (case, result)
        assert result["warns"] is False, (case, result)
        # None of them may acquire the new no-signal badge. A real score still
        # prints its own "grounded · GIR n" badge — that is pre-existing and
        # correct, and must not be mistaken for the new branch firing.
        assert "no grounding signal" not in result["badge"], (case, result)

    by_case = dict(zip(range(len(cases)), results))
    assert by_case[0]["badge"] == "", "a source alone carries no GIR badge"
    assert "grounded · GIR 0.91" in by_case[1]["badge"], by_case[1]["badge"]
    assert by_case[2]["badge"] == "", "external, no signal — no badge"
    assert by_case[3]["badge"] == "", "plain chat — no badge"


def test_a_real_low_score_still_warns_through_the_gir_path():
    """The path the browser run did exercise — it must keep working."""
    (result,) = _run_safety_cases([{"local_only": True, "sources": [], "gir": 0.0}])
    assert result["tier"] == "name_boundary"
    assert result["warns"] is True
    assert "GIR 0.00" in result["badge"], result["badge"]
