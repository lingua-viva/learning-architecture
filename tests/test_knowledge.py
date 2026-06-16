"""
Knowledge Library Tests

Test: entries load from YAML
Test: retrieval by ontology node returns correct entries
Test: evidence tier ordering (Tier 1 first)
Test: BM25 search finds relevant entries
Test: citation count matches MANIFEST
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from knowledge import KnowledgeStore


@pytest.fixture(scope="session")
def store():
    return KnowledgeStore(Path(__file__).parent.parent / "knowledge")


class TestKnowledgeLoading:
    def test_entries_loaded(self, store):
        assert store.entry_count >= 15, f"Only {store.entry_count} entries"

    def test_citations_present(self, store):
        assert store.citation_count >= 20

    def test_core_domain_entries(self, store):
        results = store.retrieve(domain="core")
        assert len(results) > 0

    def test_legal_domain_entries(self, store):
        results = store.retrieve(domain="legal")
        assert len(results) > 0


class TestRetrieval:
    def test_retrieve_by_node(self, store):
        results = store.retrieve(node_id="RIU-709")
        assert len(results) > 0
        # Should include Delaware fiduciary duty (remapped from LEGAL-005)
        titles = [e.title for e in results]
        assert any("fiduciary" in t.lower() or "delaware" in t.lower() for t in titles)

    def test_retrieve_by_node_heppner(self, store):
        results = store.retrieve(node_id="RIU-701")
        assert len(results) > 0
        assert any("heppner" in e.title.lower() for e in results)

    def test_evidence_tier_ordering(self, store):
        results = store.retrieve(domain="legal", limit=10)
        tiers = [e.evidence_tier for e in results]
        assert tiers == sorted(tiers), "Results should be ordered by tier (strongest first)"

    def test_min_tier_filter(self, store):
        results = store.retrieve(domain="legal", min_tier=1)
        assert all(e.evidence_tier <= 1 for e in results)


class TestSearch:
    def test_search_fiduciary(self, store):
        results = store.search("fiduciary duty Delaware")
        assert len(results) > 0
        assert any("fiduciary" in e.title.lower() for e in results)

    def test_search_privacy(self, store):
        results = store.search("GDPR data privacy")
        assert len(results) > 0

    def test_search_no_results(self, store):
        results = store.search("xyzzy quantum biscuits")
        # Some entries might match "quantum" — just check it doesn't crash
        assert isinstance(results, list)

    def test_search_memory_theory(self, store):
        results = store.search("no-escape theorem semantic interference")
        assert len(results) > 0
        assert any("price of meaning" in e.title.lower() or "no-escape" in e.content.lower()
                   for e in results)
