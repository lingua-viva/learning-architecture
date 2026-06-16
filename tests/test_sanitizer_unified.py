"""Tests for the unified sanitizer service."""
import pytest
from sanitizer.app import sanitize


def test_pii_detection_with_block_signals():
    """Block signals are per-client, passed in request."""
    r = sanitize("My patient John Smith SSN 123-45-6789", block_signals=["patient"])
    assert r["blocked"] is True
    assert "SSN" in r["text"]  # Token contains SSN prefix
    assert "123-45-6789" not in r["text"]
    assert r["reason"] == "block_signal: patient"


def test_no_block_signals_means_redact_only():
    """Without block signals, PII is redacted but not blocked."""
    r = sanitize("My patient John Smith SSN 123-45-6789", block_signals=[])
    assert r["blocked"] is False
    assert r["ok"] is True
    assert "123-45-6789" not in r["text"]  # SSN still redacted


def test_deterministic_token_substitution():
    """Same value in same namespace → same token always."""
    r = sanitize("Call 415-555-1212 then try 415-555-1212 again",
                 block_signals=[], namespace="test_client")
    # Same value → same token (hash-based, stable)
    tokens_used = [red["token"] for red in r["redactions"]]
    assert tokens_used[0] == tokens_used[1]  # Both occurrences get same token
    assert "415-555-1212" not in r["text"]


def test_namespace_stability():
    """Same value + same namespace = same token across calls."""
    r1 = sanitize("SSN 123-45-6789", block_signals=[], namespace="tropical_it")
    r2 = sanitize("SSN 123-45-6789", block_signals=[], namespace="tropical_it")
    assert r1["redactions"][0]["token"] == r2["redactions"][0]["token"]

    # Different namespace → different token
    r3 = sanitize("SSN 123-45-6789", block_signals=[], namespace="komodo")
    assert r3["redactions"][0]["token"] != r1["redactions"][0]["token"]


def test_context_logistics_suppresses_phone():
    r = sanitize("Ship SKU-415-555-1212 to Colombia", context="logistics", block_signals=[])
    assert r["ok"] is True
    assert "415-555-1212" in r["text"]  # NOT redacted in logistics


def test_context_medical_redacts_all():
    r = sanitize("SSN 123-45-6789 phone 415-555-1212", context="medical", block_signals=[])
    assert "123-45-6789" not in r["text"]
    assert "415-555-1212" not in r["text"]


def test_clean_text_passes():
    r = sanitize("What is the weather today?", block_signals=[])
    assert r["ok"] is True
    assert r["blocked"] is False
    assert r["text"] == "What is the weather today?"
    assert len(r["redactions"]) == 0


def test_komodo_can_use_patient():
    """Komodo's block signals don't include 'patient' — they can discuss patients."""
    komodo_signals = ["ssn", "medical_record_number"]
    r = sanitize("What treatment protocols exist for patient with condition X?",
                 block_signals=komodo_signals)
    assert r["blocked"] is False  # "patient" is NOT a block signal for Komodo
    assert r["ok"] is True


def test_reverse_tokens_for_rehydration():
    """Exit gate can use reverse_tokens to restore original values for the user."""
    r = sanitize("Email john@test.com and call 415-555-1212", block_signals=[], namespace="demo")
    assert len(r["reverse_tokens"]) >= 2
    # Each token maps back to original
    for token, original in r["reverse_tokens"].items():
        assert token.startswith("<")
        assert original in ("john@test.com", "415-555-1212")


def test_email_detection():
    r = sanitize("Contact me at john@example.com", block_signals=[])
    assert "john@example.com" not in r["text"]
    assert len(r["redactions"]) >= 1


def test_latency_fast():
    r = sanitize("A quick test with SSN 999-88-7777", block_signals=[])
    assert r["latency_ms"] < 50
