"""Shared teacher-facing messages for degraded states.

P1-2 (Claudia QA 2026-08-03): when no local model was available, both
reasoning engines returned a bracketed developer placeholder —
"[Local reasoning for LV-STU-002 - no model available]" — which the query
view rendered verbatim and the voice path READ ALOUD. A teacher cannot act
on that. This module is the single source for what we say instead, so every
entry point (typed query, streamed query, voice question, lesson materials,
extraction) tells the same actionable story.

Rules for these messages:
- Plain sentences, no brackets/markdown — they are spoken by TTS as-is.
- Say what the teacher can DO, not what the system lacks.
- Keep the privacy promise explicit: setup keeps everything local.
"""

from __future__ import annotations

# Kept in sync with desktop/electron/bootstrap.ts DEFAULT_MODEL.
DEFAULT_LOCAL_MODEL = "qwen2.5:3b"


def no_model_message() -> str:
    """What the teacher sees/hears when no local model can answer."""
    return (
        "I need a local AI model to answer questions about your students. "
        "To set this up: install Ollama from ollama.com, then open Terminal "
        f"and run: ollama pull {DEFAULT_LOCAL_MODEL} — then restart Lingua "
        "Viva. This keeps all student data on your computer; nothing is "
        "sent externally."
    )


def local_only_no_model_message() -> str:
    """Same situation, but the query contains student/family data, so the
    external route is deliberately closed. Explain both halves."""
    return (
        "This question mentions student or family information, so it can "
        "only be answered by a model running on this computer. No local "
        "model is available right now. To set one up: install Ollama from "
        f"ollama.com, then open Terminal and run: ollama pull "
        f"{DEFAULT_LOCAL_MODEL} — then restart Lingua Viva."
    )


def model_unreachable_message(model: str, reason: str = "connection failed") -> str:
    """What the teacher sees/hears when a configured local model exists but
    cannot be reached right now. Do not imply installation is missing."""
    model_name = model or f"ollama/{DEFAULT_LOCAL_MODEL}"
    return (
        f"I tried to reach {model_name}, but {reason}. Ollama may still be "
        "starting, loading the model, or temporarily unreachable. Check that "
        "Ollama is running, then try again."
    )
