"""
Voice tone resolver — maps GIR score to delivery tone.

A confidently-voiced ungrounded answer is a worse failure than a slow one.
This module is a pure function with no pipeline, web, or I/O dependencies
so it can be unit-tested in isolation.

Thresholds start as MC's (>=0.8 / 0.4-0.8 / <0.4) but LV's GIR method is
`claim_support_v1_heuristic` — a coarse sentence-split + uncertainty-marker
heuristic, not the same computation MC's inline GIR uses. Treat these as a
starting point, not a validated calibration.
"""

from __future__ import annotations

PLAIN_THRESHOLD = 0.8
CLARIFY_THRESHOLD = 0.4


def resolve_voice_tone(gir_score: float) -> dict:
    """Return tone and spoken prefix for the given grounding score."""
    if gir_score >= PLAIN_THRESHOLD:
        return {"tone": "plain", "prefix": ""}
    if gir_score >= CLARIFY_THRESHOLD:
        return {
            "tone": "clarify",
            "prefix": "I'm fairly sure, but let's double check this together. ",
        }
    return {
        "tone": "name_boundary",
        "prefix": "I don't have a solid source for this one, so take it as a starting point, not a final answer. ",
    }
