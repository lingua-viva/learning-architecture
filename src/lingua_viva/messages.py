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
DEFAULT_LOCAL_MODEL = "qwen3:8b"


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


def blocked_provider_message(provider: str) -> str:
    """A configured AI provider is not on Lingua Viva's supported list.
    The request is refused on this machine — the wording must say "blocked"
    plainly so teachers (and the readiness harness) can see nothing left."""
    return (
        f"The configured AI provider {provider} is not one Lingua Viva "
        "supports, so this request was blocked before anything left this "
        "computer. Lingua Viva only talks to Ollama running locally, or to "
        "OpenAI, Groq, or Mistral when you set them up in Settings. Nothing "
        "was sent externally."
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


def ask_personal_data_refusal_message() -> str:
    """Ask (T8) detected a student name or personal identifier in a question
    bound for the external web search. The refusal is the feature: personal
    questions are never sanitized-and-sent, they are answered from the lens."""
    return (
        "The Ask section answers general teaching questions using web search. "
        "Questions about your students stay on this machine — their information "
        "lives in their lens and is never sent externally."
    )


def ask_not_configured_message() -> str:
    """Ask (T8) has no Perplexity key configured. Offline-first rule: say so
    plainly, never fake an answer."""
    return (
        "Ask searches the web for general teaching questions, and the web "
        "search service is not set up on this computer yet. Ask needs a "
        "Perplexity key before it can answer. Everything else in Lingua "
        "Viva works without it."
    )


def ask_offline_message() -> str:
    """Ask (T8) is configured but the web search call failed. Offline is a
    supported state, not an error state."""
    return (
        "I could not reach the web search service. Check the internet "
        "connection and try again. Your question is still in the box."
    )
