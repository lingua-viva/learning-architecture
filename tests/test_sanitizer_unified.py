"""Tests for the unified sanitizer service."""
from pathlib import Path

import pytest
from sanitizer.app import _data_dir, sanitize


def test_data_dir_redirects_out_of_bundle_in_electron_desktop_context(monkeypatch, tmp_path):
    """Chip 0.2.42 QA, check #11 (P0): in the Electron-packaged app, sys.frozen
    never fires (it's not a PyInstaller onefile binary), so _data_dir() fell
    through to Path(__file__).parent / "data" -- writing firewall_log.ndjson
    live inside the signed .app bundle on every ordinary sanitizer call and
    breaking `codesign --verify`. LV_DESKTOP/ELECTRON_RUN_AS_NODE must be
    detected and redirected to LV_STATE_HOME, same as every other bundle-write
    path in this repo (improvement_audit.py, teacher_readiness.py,
    ontology/learned_weights.py)."""
    monkeypatch.delenv("LV_SANITIZER_DATA_DIR", raising=False)
    monkeypatch.setenv("LV_DESKTOP", "1")
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))

    data_dir = _data_dir()

    repo_data_dir = Path(__file__).resolve().parent.parent / "sanitizer" / "data"
    assert data_dir != repo_data_dir
    assert repo_data_dir not in data_dir.parents and data_dir != repo_data_dir
    assert data_dir == tmp_path / "runtime" / "sanitizer"


def test_data_dir_never_defaults_to_stale_still_i_rise_home(monkeypatch, tmp_path):
    """Companion to the check #11 fix: the old frozen-path fallback pointed at
    STILL_I_RISE_HOME (~/.still-i-rise), a leftover from the product's prior
    name -- a mismatch Chip's report flagged as a "bonus" finding alongside
    the main bundle-write bug. No code path should ever reference it again."""
    import inspect
    import sanitizer.app as sanitizer_app

    source = inspect.getsource(sanitizer_app._data_dir)
    assert "STILL_I_RISE_HOME" not in source
    assert ".still-i-rise" not in source


def test_firewall_log_honors_hermeticity_override(monkeypatch, tmp_path):
    """MC-lessons §1 gap found during the §9 desktop-build dirty-tree check:
    DATA_DIR/FIREWALL_LOG used to be module-level constants computed once at
    import time, so a test's monkeypatch.setenv("LV_SANITIZER_DATA_DIR", ...)
    had no effect and every sanitizer-touching test appended real lines to
    the tracked sanitizer/data/firewall_log.ndjson. _data_dir() now resolves
    the override lazily on every call, same seam pattern as
    traces.trace_path()."""
    override_dir = tmp_path / "sanitizer-state"
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(override_dir))

    sanitize("SSN 123-45-6789", block_signals=[])

    log = override_dir / "firewall_log.ndjson"
    assert log.is_file(), "firewall log should be written under the override dir"

    repo_log = Path(__file__).resolve().parent.parent / "sanitizer" / "data" / "firewall_log.ndjson"
    before = repo_log.read_text(encoding="utf-8") if repo_log.exists() else ""
    sanitize("SSN 123-45-6789", block_signals=[])
    after = repo_log.read_text(encoding="utf-8") if repo_log.exists() else ""
    assert before == after, "tracked sanitizer/data/firewall_log.ndjson must not change under the override"


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
