"""
Gateway PII Boundary Tests — Minimum 12

These tests verify that the 3-layer PII sanitizer works correctly.
The gateway is the gatekeeper: nothing sensitive leaves the machine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.gateway.sanitizer import Sanitizer


@pytest.fixture
def sanitizer():
    return Sanitizer()


# === Layer 1: Regex Patterns ===

class TestRegexPatterns:
    def test_email_redacted(self, sanitizer):
        result = sanitizer.analyze("Contact john.doe@example.com for details")
        assert any(r["type"] == "email" for r in result.redactions)
        assert "john.doe@example.com" not in result.sanitized

    def test_phone_redacted(self, sanitizer):
        result = sanitizer.analyze("Call me at 415-555-1234")
        assert any(r["type"] == "phone_us" for r in result.redactions)
        assert "415-555-1234" not in result.sanitized

    def test_ssn_redacted(self, sanitizer):
        result = sanitizer.analyze("SSN is 123-45-6789")
        assert any(r["type"] == "ssn" for r in result.redactions)
        assert "123-45-6789" not in result.sanitized

    def test_credit_card_redacted(self, sanitizer):
        result = sanitizer.analyze("Card number 4111-1111-1111-1111")
        assert any(r["type"] == "credit_card" for r in result.redactions)

    def test_ip_address_redacted(self, sanitizer):
        result = sanitizer.analyze("Server at 192.168.1.100")
        assert any(r["type"] == "ip_address" for r in result.redactions)


# === Layer 2: NER Patterns ===

class TestNERPatterns:
    def test_titled_name_redacted(self, sanitizer):
        result = sanitizer.analyze("Contact Dr. Jane Smith for the report")
        assert any(r["type"] == "person_name" for r in result.redactions)

    def test_client_reference_redacted(self, sanitizer):
        result = sanitizer.analyze("Regarding case #12345 and the filing")
        assert any(r["type"] == "client_reference" for r in result.redactions)


# === Layer 3: Ontology-Guided Blocking ===

class TestOntologyBlocking:
    def test_privileged_signal_blocks(self, sanitizer):
        result = sanitizer.analyze("This is privileged attorney-client communication")
        assert result.blocked is True
        assert result.sanitized == ""

    def test_confidential_signal_blocks(self, sanitizer):
        result = sanitizer.analyze("This information is strictly confidential")
        assert result.blocked is True

    def test_nda_signal_blocks(self, sanitizer):
        result = sanitizer.analyze("This is covered by our NDA")
        assert result.blocked is True

    def test_public_query_passes(self, sanitizer):
        result = sanitizer.analyze("What is the Delaware DGCL merger statute?")
        assert result.blocked is False
        assert len(result.redactions) == 0

    def test_blocks_external_classification_blocks(self, sanitizer):
        result = sanitizer.analyze(
            "Tell me about the merger",
            classification={"blocks_external": True}
        )
        assert result.blocked is True


# === Integration ===

class TestSanitizationIntegration:
    def test_sanitize_returns_clean_string(self, sanitizer):
        clean = sanitizer.sanitize("Email john@test.com about the public filing")
        assert "john@test.com" not in clean
        assert "[REDACTED_EMAIL]" in clean

    def test_is_safe_for_external(self, sanitizer):
        assert sanitizer.is_safe_for_external("What is the GDP of France?")
        assert not sanitizer.is_safe_for_external("This is confidential client data")
