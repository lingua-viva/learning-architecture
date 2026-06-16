"""
Ontology Tests — Path consistency, classification accuracy, graph integrity.

Test: same problem type → same ontology node
Test: confidence improves with path history
Test: graph has no cycles, no orphans, no broken edges
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ontology.engine import OntologyEngine, PathRecord
from ontology.integrity.validator import OntologyValidator


@pytest.fixture(scope="session")
def engine():
    return OntologyEngine(Path(__file__).parent.parent / "ontology" / "domains")


@pytest.fixture(scope="session")
def validator(engine):
    return OntologyValidator(engine)


# === Graph Integrity ===

class TestGraphIntegrity:
    def test_nodes_loaded(self, engine):
        assert engine.node_count >= 20, f"Only {engine.node_count} nodes loaded"

    def test_core_domain_exists(self, engine):
        assert "core" in engine.domains

    def test_legal_domain_exists(self, engine):
        assert "legal" in engine.domains

    def test_six_core_intents(self, engine):
        core_nodes = engine.get_domain_nodes("core")
        assert len(core_nodes) == 6
        ids = {n.id for n in core_nodes}
        expected = {"CORE-PROTECT", "CORE-RESEARCH", "CORE-DECIDE",
                   "CORE-CREATE", "CORE-DIAGNOSE", "CORE-REFLECT"}
        assert ids == expected

    def test_no_cycles(self, validator):
        result = validator.validate()
        assert not result.cycle_detected, f"Cycles found: {result.cycle_nodes}"

    def test_no_broken_edges(self, validator):
        result = validator.validate()
        assert len(result.broken_edges) == 0, f"Broken edges: {result.broken_edges}"

    def test_all_parents_exist(self, validator):
        result = validator.validate()
        assert len(result.missing_parents) == 0, f"Missing parents: {result.missing_parents}"

    def test_governance_consistency(self, validator):
        """Nodes with blocks_external should also have requires_local."""
        result = validator.validate()
        gov_issues = [i for i in result.issues if "blocks_external" in i]
        assert len(gov_issues) == 0, f"Governance inconsistencies: {gov_issues}"


# === Classification ===

class TestClassification:
    def test_privilege_query_classifies_to_protect(self, engine):
        result = engine.classify("This is a privileged client communication")
        assert result.blocks_external is True
        assert result.requires_local is True

    def test_public_law_query_allows_external(self, engine):
        result = engine.classify("What does the Delaware DGCL say about mergers?")
        assert result.blocks_external is False

    def test_research_query_classifies_to_research(self, engine):
        result = engine.classify("Find the latest market trends in AI governance")
        # After classification improvements (name auto-indexing), "AI governance"
        # correctly routes to ai-enablement domain (RIU-029) rather than generic CORE
        assert result.domain in ("core", "legal", "ai-enablement")

    def test_decision_query_classifies_to_decide(self, engine):
        result = engine.classify("Should I approve this one-way door decision?")
        assert "DECIDE" in result.riu_id or result.default_intent == "DECIDE"

    def test_same_query_same_classification(self, engine):
        """Path consistency: same query → same node."""
        r1 = engine.classify("Is this privileged attorney-client information?")
        r2 = engine.classify("Is this privileged attorney-client information?")
        assert r1.riu_id == r2.riu_id
        assert r1.confidence == r2.confidence

    def test_confidence_increases_with_path_history(self, engine):
        """Confidence should improve when prior paths exist."""
        r1 = engine.classify("Review this confidential client contract")

        # Create mock prior paths at the same node
        prior_paths = [
            PathRecord(
                session_id="test",
                query_hash="abc",
                domain="legal",
                entry_node=r1.riu_id,
                path=[r1.riu_id, "REASON", "STORE"],
                confidence_at_entry=0.8,
                confidence_at_exit=0.9,
                model_used="test",
                external_called=False,
                outcome="completed",
            )
            for _ in range(5)
        ]

        r2 = engine.classify("Review this confidential client contract", prior_paths=prior_paths)
        assert r2.confidence > r1.confidence, \
            f"Confidence did not improve: {r1.confidence} → {r2.confidence}"

    def test_unknown_query_gets_low_confidence(self, engine):
        result = engine.classify("xyzzy foobar quantum entanglement biscuits")
        assert result.confidence < 0.5

    def test_query_hash_deterministic(self, engine):
        h1 = engine.hash_query("test query")
        h2 = engine.hash_query("test query")
        assert h1 == h2

    def test_query_hash_case_insensitive(self, engine):
        h1 = engine.hash_query("Test Query")
        h2 = engine.hash_query("test query")
        assert h1 == h2


def test_governance_queries_classify_to_governance_domain(engine):
    """Golden cases: governance/safety queries must route to governance nodes (RIU-029 or MC-GOV-*)."""
    GOVERNANCE_NODES = {"RIU-029", "MC-GOV-001", "MC-GOV-002", "MC-GOV-003", "MC-GOV-004", "MC-GOV-005"}
    cases = [
        "governed Codex execution adapter",
        "tool-calling safety envelope",
        "result envelope validation",
        "Codex inside MC governed execution",
    ]
    for query in cases:
        result = engine.classify(query)
        assert result.riu_id in GOVERNANCE_NODES, (
            f'"{query}" classified to {result.riu_id} ({result.name}), expected governance node'
        )
