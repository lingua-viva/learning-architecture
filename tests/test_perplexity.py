"""
Perplexity Gateway Tests

Tests the governed research gateway WITHOUT making real API calls.
Tests: system prompt targeting, contradiction detection, gap identification,
       graceful fallback when unavailable.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.gateway.perplexity import PerplexityGateway


@pytest.fixture
def gateway(monkeypatch):
    """Gateway without API key — tests everything except actual calls."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    return PerplexityGateway(api_key="")


@pytest.fixture
def gateway_with_key():
    """Gateway with a fake key — for testing call structure."""
    return PerplexityGateway(api_key="test-key")


class TestAvailability:
    def test_unavailable_without_key(self, gateway):
        assert not gateway.available

    def test_available_with_key(self, gateway_with_key):
        assert gateway_with_key.available

    def test_graceful_fallback_no_key(self, gateway):
        result = gateway.research(
            query="What is the fiduciary duty standard?",
            node_name="Fiduciary Duty Analysis",
            domain="legal",
            local_knowledge=[],
        )
        assert "unavailable" in result.content.lower()
        assert result.model_used == "none"
        assert "perplexity_unavailable" in result.gaps_identified


class TestSystemPromptConstruction:
    def test_prompt_includes_node_name(self, gateway_with_key):
        prompt = gateway_with_key._build_system_prompt(
            "Fiduciary Duty Analysis", "legal", []
        )
        assert "Fiduciary Duty Analysis" in prompt
        assert "legal" in prompt

    def test_prompt_includes_local_knowledge(self, gateway_with_key):
        kl = [
            {"title": "Delaware Fiduciary Framework", "content": "..."},
            {"title": "Heppner v. Alyeska", "content": "..."},
        ]
        prompt = gateway_with_key._build_system_prompt(
            "Legal Precedent Research", "legal", kl
        )
        assert "Delaware Fiduciary Framework" in prompt
        assert "Heppner" in prompt
        assert "MISSING" in prompt  # Focus on gaps

    def test_prompt_caps_knowledge_at_3(self, gateway_with_key):
        kl = [{"title": f"Entry {i}", "content": "..."} for i in range(10)]
        prompt = gateway_with_key._build_system_prompt("Test", "core", kl)
        # Should only include first 3
        assert "Entry 0" in prompt
        assert "Entry 2" in prompt
        assert "Entry 3" not in prompt

    def test_prompt_requires_gaps(self, gateway_with_key):
        prompt = gateway_with_key._build_system_prompt("Test", "core", [])
        assert "gaps" in prompt.lower() or "could not verify" in prompt.lower()


class TestContradictionDetection:
    def test_detects_overruled(self, gateway_with_key):
        content = "The prior holding was overruled by the Supreme Court in 2025."
        contradictions = gateway_with_key._detect_contradictions(content, [])
        assert len(contradictions) > 0
        assert any("overruled" in c.lower() for c in contradictions)

    def test_detects_superseded(self, gateway_with_key):
        content = "This regulation has been superseded by the 2026 amendment."
        contradictions = gateway_with_key._detect_contradictions(content, [])
        assert len(contradictions) > 0

    def test_no_false_positives_on_normal_prose(self, gateway_with_key):
        content = "The court held that the duty of care requires directors to make informed decisions. However, the business judgment rule provides protection."
        contradictions = gateway_with_key._detect_contradictions(content, [])
        assert len(contradictions) == 0  # "however" is not a contradiction

    def test_detects_no_longer_good_law(self, gateway_with_key):
        content = "Smith v. Jones is no longer good law after the 2025 revision."
        contradictions = gateway_with_key._detect_contradictions(content, [])
        assert len(contradictions) > 0


class TestGapIdentification:
    def test_identifies_could_not_find(self, gateway_with_key):
        content = "The court's reasoning is clear on duty of care, but I could not find authoritative guidance on the specific question of AI-assisted board decisions."
        gaps = gateway_with_key._identify_gaps(content)
        assert len(gaps) > 0

    def test_identifies_pending(self, gateway_with_key):
        content = "The case is pending before the Delaware Court of Chancery."
        gaps = gateway_with_key._identify_gaps(content)
        assert len(gaps) > 0

    def test_no_false_gaps_on_confident_answer(self, gateway_with_key):
        content = "The Delaware Supreme Court established a clear three-part test in Stone v. Ritter: duty of care, duty of loyalty, and duty of good faith."
        gaps = gateway_with_key._identify_gaps(content)
        assert len(gaps) == 0
