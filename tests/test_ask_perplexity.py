"""T8 — Ask = voice-first Perplexity (SPEC_T8_ASK_2026-08-04).

The hard requirement: no personal data ever leaves the machine on any Ask
call. These tests assert the refusal at the egress layer — urlopen is
patched to fail the test if anything tries the network — not just at the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva.messages import (
    ask_not_configured_message,
    ask_offline_message,
    ask_personal_data_refusal_message,
)

REPO = Path(__file__).resolve().parents[1]
client = TestClient(web.app)

ROSTER = ["Nora Rossi", "Marco Bianchi"]


@pytest.fixture()
def no_egress(monkeypatch):
    """Any network attempt fails the test."""
    def boom(*args, **kwargs):
        raise AssertionError("outbound network call attempted during Ask test")

    monkeypatch.setattr("urllib.request.urlopen", boom)


@pytest.fixture()
def roster(monkeypatch):
    monkeypatch.setattr(web, "_active_student_names", lambda: list(ROSTER))


@pytest.fixture()
def privacy_log(tmp_path, monkeypatch):
    path = tmp_path / "privacy_events.ndjson"
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(path))
    return path


@pytest.fixture()
def perplexity_key(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")


@pytest.fixture()
def no_perplexity_key(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.setattr(web, "_perplexity_api_key", lambda: "")


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- The PII egress gate -------------------------------------------------------


def test_roster_name_query_is_refused_with_zero_egress(no_egress, roster, privacy_log, perplexity_key):
    response = client.post("/api/ask", json={"question": "What should I do about Nora Rossi's reading?"})
    assert response.status_code == 200
    body = response.json()
    # F3: student-named queries route locally (grounded pipeline), never external.
    # The privacy gate prevents egress but answers from local observations.
    assert body["type"] == "ask_result"
    assert body["external_calls"] == 0
    assert body.get("local_only") is True
    assert any(event["event_type"] == "student_query_routed_local" for event in _events(privacy_log))


def test_fuzzy_roster_name_is_refused(no_egress, roster, privacy_log, perplexity_key):
    response = client.post("/api/ask", json={"question": "Any advice for helping Marko with focus?"})
    body = response.json()
    # Fuzzy match → routes locally too
    assert body["type"] == "ask_result"
    assert body["external_calls"] == 0
    assert body.get("local_only") is True


def test_first_name_only_is_refused(no_egress, roster, privacy_log, perplexity_key):
    response = client.post("/api/ask", json={"question": "How can I help Nora concentrate?"})
    body = response.json()
    assert body["type"] == "ask_result"
    assert body["external_calls"] == 0
    assert body.get("local_only") is True


def test_pattern_pii_without_roster_hit_is_refused(no_egress, roster, privacy_log, perplexity_key):
    response = client.post("/api/ask", json={"question": "Draft an IEP progress report for student: G3"})
    body = response.json()
    assert body["type"] == "ask_refused"
    assert body["external_calls"] == 0


def test_unreadable_roster_fails_closed(no_egress, privacy_log, perplexity_key, monkeypatch):
    def broken():
        raise RuntimeError("lens store unavailable")

    monkeypatch.setattr(web, "_active_student_names", broken)
    response = client.post("/api/ask", json={"question": "What are fun Italian number games?"})
    body = response.json()
    assert body["type"] == "ask_refused"
    assert body["external_calls"] == 0


def test_history_is_gated_too(no_egress, roster, privacy_log, perplexity_key):
    response = client.post("/api/ask", json={
        "question": "tell me more",
        "mode": "more",
        "history": [
            {"role": "user", "content": "How is Marco Bianchi doing in class?"},
            {"role": "assistant", "content": "..."},
        ],
    })
    body = response.json()
    # Student name in history → route locally, zero egress
    assert body["type"] == "ask_result"
    assert body["external_calls"] == 0
    assert body.get("local_only") is True


# --- The happy path ------------------------------------------------------------


@pytest.fixture()
def recorded_perplexity(monkeypatch):
    calls: list[dict] = []

    def fake(messages, max_tokens, key):
        calls.append({"messages": messages, "max_tokens": max_tokens, "key": key})
        return {
            "choices": [{"message": {"content": "Use visual schedules and short task chunks."}}],
            "citations": ["https://example.org/add-strategies"],
        }

    monkeypatch.setattr(web, "_request_perplexity", fake)
    return calls


def test_clean_question_returns_summary_with_citations(roster, privacy_log, perplexity_key, recorded_perplexity):
    response = client.post("/api/ask", json={
        "question": "What are strategies for a student with ADD in a language immersion classroom?",
    })
    body = response.json()
    assert body["type"] == "ask_result"
    assert body["content"] == "Use visual schedules and short task chunks."
    assert body["citations"] == ["https://example.org/add-strategies"]
    assert body["model_used"] == "perplexity/sonar-pro"
    assert body["route"] == "external"
    assert body["more_available"] is True
    assert body["external_calls"] == 1
    # brief §5.2: one-paragraph cap at the API level
    assert recorded_perplexity[0]["max_tokens"] == web.ASK_SUMMARY_MAX_TOKENS
    assert any(event["event_type"] == "external_call_made" for event in _events(privacy_log))


def test_hear_more_uses_larger_cap_and_history(roster, privacy_log, perplexity_key, recorded_perplexity):
    response = client.post("/api/ask", json={
        "question": "What are good dyslexia reading strategies?",
        "mode": "more",
        "history": [
            {"role": "user", "content": "What are good dyslexia reading strategies?"},
            {"role": "assistant", "content": "Multisensory phonics helps."},
        ],
    })
    body = response.json()
    assert body["type"] == "ask_result"
    assert body["more_available"] is False
    call = recorded_perplexity[0]
    assert call["max_tokens"] == web.ASK_MORE_MAX_TOKENS
    contents = [m["content"] for m in call["messages"]]
    assert "Multisensory phonics helps." in contents
    assert "Please continue with more detail." in contents


# --- Honest degraded states ----------------------------------------------------


def test_missing_key_is_honest_and_makes_no_call(no_egress, roster, privacy_log, no_perplexity_key):
    response = client.post("/api/ask", json={"question": "What are fun Italian number games?"})
    body = response.json()
    assert body["type"] == "ask_unavailable"
    assert body["configured"] is False
    assert body["message"] == ask_not_configured_message()
    assert body["external_calls"] == 0


def test_rejected_key_reads_as_setup_problem_not_connectivity(roster, privacy_log, perplexity_key, monkeypatch):
    import urllib.error

    def unauthorized(messages, max_tokens, key):
        raise urllib.error.HTTPError("https://api.perplexity.ai", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(web, "_request_perplexity", unauthorized)
    response = client.post("/api/ask", json={"question": "What are fun Italian number games?"})
    body = response.json()
    assert body["type"] == "ask_unavailable"
    assert body["configured"] is False
    assert body["message"] == ask_not_configured_message()


def test_network_failure_is_honest(roster, privacy_log, perplexity_key, monkeypatch):
    def down(messages, max_tokens, key):
        raise OSError("network unreachable")

    monkeypatch.setattr(web, "_request_perplexity", down)
    response = client.post("/api/ask", json={"question": "What are fun Italian number games?"})
    body = response.json()
    assert body["type"] == "ask_unavailable"
    assert body["configured"] is True
    assert body["message"] == ask_offline_message()


def test_empty_question_is_a_400(roster):
    response = client.post("/api/ask", json={"question": "   "})
    assert response.status_code == 400


def test_oversized_question_is_a_400(no_egress, roster):
    response = client.post("/api/ask", json={"question": "a" * (web.ASK_QUESTION_MAX_CHARS + 1)})
    assert response.status_code == 400


def test_failed_attempt_still_counts_as_egress(roster, privacy_log, perplexity_key, monkeypatch):
    """external_call_made is logged BEFORE the call (reasoning.py semantics):
    a post-gate attempt that errors still left the machine."""
    def down(messages, max_tokens, key):
        raise OSError("network unreachable")

    monkeypatch.setattr(web, "_request_perplexity", down)
    response = client.post("/api/ask", json={"question": "What are fun Italian number games?"})
    body = response.json()
    assert body["external_calls"] == 1
    assert any(event["event_type"] == "external_call_made" for event in _events(privacy_log))


def test_messages_are_plain_prose_no_brackets():
    for message in (
        ask_personal_data_refusal_message(),
        ask_not_configured_message(),
        ask_offline_message(),
    ):
        assert "[" not in message and "]" not in message
        assert message.strip()


# --- Frontend wiring (repo pattern: string asserts on the served HTML) ---------

HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_ask_button_and_examples_present():
    assert 'id="ask-button"' in HTML
    assert ">Ask</button>" in HTML
    assert "ASK_EXAMPLES" in HTML
    assert "language immersion classroom" in HTML


def test_ask_tab_posts_to_api_ask():
    assert '"/api/ask"' in HTML
    assert '"mode": "more"' in HTML.replace("mode: \"more\"", '"mode": "more"') or 'mode: "more"' in HTML


def test_no_auto_switch_to_ask_remains():
    assert 'switchView("ask")' not in HTML


def test_stop_and_more_intercepts_present():
    assert "ASK_STOP_WORDS" in HTML
    assert "ASK_MORE_WORDS" in HTML
    assert "Would you like to hear more?" in HTML
    assert "data-ask-more" in HTML


def test_ask_copy_no_longer_claims_local_governed_reasoning():
    assert "governed local app runtime" not in HTML
    assert "answers come from the web" in HTML
