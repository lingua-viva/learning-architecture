from __future__ import annotations

from scripts.run_lv_voice_gir_hardening import classify_verdict


def test_hardening_harness_blocks_no_model_placeholder_answer():
    verdict = classify_verdict({
        "route_used": "/api/query/stream",
        "answer_preview": "[Local reasoning for LV-PLN-001 - no model available]",
        "bucket": "strong_local",
        "gir_score": 1.0,
        "voice_tone": "plain",
        "tone_prefix": "",
    })

    assert verdict == "BLOCKED"


def test_hardening_harness_blocks_ollama_down_answer():
    verdict = classify_verdict({
        "route_used": "/api/query/stream",
        "answer_preview": "Ollama appears to be down - check if it's running, then try again.",
        "bucket": "followup",
        "gir_score": 1.0,
        "voice_tone": "plain",
        "tone_prefix": "",
    })

    assert verdict == "BLOCKED"


def test_hardening_harness_requires_student_privacy_probe_for_student_bucket():
    verdict = classify_verdict({
        "route_used": "/api/query/stream",
        "answer_preview": "Try a short confidence-building speaking routine.",
        "bucket": "student_support",
        "gir_score": 0.7,
        "voice_tone": "clarify",
        "tone_prefix": "I'm fairly sure, but let's double check this together. ",
        "privacy_probe": "fail",
    })

    assert "privacy_probe_not_refused" in verdict
