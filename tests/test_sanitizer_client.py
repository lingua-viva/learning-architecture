"""Tests for sanitizer client — especially fail-closed behavior."""
import os
import pytest
from unittest.mock import patch
from sanitizer.client import sanitize_text, rehydrate


def test_dev_mode_direct_import():
    """In dev mode, if service is down, falls back to direct import."""
    with patch.dict(os.environ, {"MC_DEV_MODE": "1", "MC_SANITIZER_URL": "http://localhost:99999"}):
        # Service on port 99999 won't exist — should fall back to direct import
        r = sanitize_text("SSN 123-45-6789", block_signals=[])
        assert r["ok"] is True
        assert "123-45-6789" not in r["text"]


def test_fail_closed_production_mode():
    """In production mode, if service is down, BLOCK everything."""
    with patch.dict(os.environ, {"MC_DEV_MODE": "0", "MC_SANITIZER_URL": "http://localhost:99999"}):
        r = sanitize_text("SSN 123-45-6789", block_signals=[])
        assert r["ok"] is False
        assert r["blocked"] is True
        assert r["reason"] == "sanitizer_unavailable"
        assert r["text"] == ""


def test_rehydrate():
    """Exit gate re-hydration restores tokens to original values."""
    reverse_tokens = {
        "<SSN_abc123>": "123-45-6789",
        "<EMAIL_ADDRESS_def456>": "john@test.com",
    }
    text = "The person with <SSN_abc123> emailed from <EMAIL_ADDRESS_def456>"
    result = rehydrate(text, reverse_tokens)
    assert "123-45-6789" in result
    assert "john@test.com" in result
    assert "<SSN_" not in result


def test_empty_block_signals_allows_all():
    """Empty block_signals = PII redaction only, no content blocking."""
    with patch.dict(os.environ, {"MC_DEV_MODE": "1", "MC_SANITIZER_URL": "http://localhost:99999"}):
        r = sanitize_text("The patient discussed their diagnosis", block_signals=[])
        assert r["blocked"] is False
        assert r["ok"] is True


def test_per_client_block_signals():
    """Different clients have different block signals."""
    with patch.dict(os.environ, {"MC_DEV_MODE": "1", "MC_SANITIZER_URL": "http://localhost:99999"}):
        # Tropical IT: block pricing
        r = sanitize_text("The pricing is $500 per unit", block_signals=["pricing"])
        assert r["blocked"] is True

        # Komodo: doesn't block pricing
        r = sanitize_text("The pricing is $500 per unit", block_signals=["ssn", "medical_record"])
        assert r["blocked"] is False
