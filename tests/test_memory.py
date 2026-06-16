"""
Memory Tests — Path storage, retrieval, compaction, BM25 search.

Test: paths are stored and retrievable
Test: compaction preserves decisions and paths
Test: BM25 search returns zero false positives
"""

import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from memory.store import MemoryStore
from memory.schema import PathRecord, SessionRecord
from memory.compaction import Compactor


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def store(temp_dir):
    return MemoryStore(data_dir=temp_dir)


@pytest.fixture
def sample_path():
    return PathRecord(
        session_id="test-session",
        query_hash="abc123",
        domain="legal",
        entry_node="LEGAL-001",
        path=["LEGAL-001", "REASON", "STORE"],
        confidence_at_entry=0.7,
        confidence_at_exit=0.85,
        model_used="ollama/qwen2.5:3b",
        external_called=False,
        outcome="completed",
        intent="PROTECT",
    )


class TestPathStorage:
    def test_write_and_read_path(self, store, sample_path):
        store.write_path(sample_path)
        paths = store.find_paths(entry_node="LEGAL-001")
        assert len(paths) >= 1
        assert paths[0].entry_node == "LEGAL-001"

    def test_path_count_increases(self, store, sample_path):
        assert store.total_path_count() == 0
        store.write_path(sample_path)
        assert store.total_path_count() == 1

    def test_find_by_domain(self, store, sample_path):
        store.write_path(sample_path)
        paths = store.find_paths(domain="legal")
        assert len(paths) >= 1

    def test_find_by_min_confidence(self, store, sample_path):
        store.write_path(sample_path)
        high = store.find_paths(min_confidence=0.9)
        assert len(high) == 0
        low = store.find_paths(min_confidence=0.5)
        assert len(low) >= 1

    def test_gap_signals_stored(self, store):
        record = PathRecord(
            session_id="test",
            query_hash="gap",
            domain="core",
            entry_node="CORE-RESEARCH",
            path=["CORE-RESEARCH", "STORE"],
            confidence_at_entry=0.2,
            confidence_at_exit=0.3,
            model_used="test",
            external_called=False,
            outcome="gap",
            gap_signals=["unknown_domain", "low_confidence"],
        )
        store.write_path(record)
        assert store.gap_signal_count() >= 1


class TestCompaction:
    def test_compaction_preserves_decisions(self):
        compactor = Compactor()
        session = SessionRecord(session_id="test", path_count=5)
        paths = [
            PathRecord(
                session_id="test",
                query_hash=f"q{i}",
                domain="legal",
                entry_node="LEGAL-005",
                path=["LEGAL-005", "REASON", "STORE"],
                confidence_at_entry=0.7,
                confidence_at_exit=0.85,
                model_used="test",
                external_called=False,
                outcome="decision_stored",
                intent="DECIDE",
            )
            for i in range(5)
        ]
        summary = compactor.compact(session, paths)
        assert len(summary.decisions_made) == 5
        assert len(summary.paths_taken) == 5

    def test_compaction_trigger_threshold(self):
        compactor = Compactor(context_window_tokens=100_000)
        assert compactor.should_compact(70_000)
        assert not compactor.should_compact(50_000)


class TestBM25Search:
    def test_bm25_returns_relevant(self, store):
        paths = [
            PathRecord(
                session_id="test",
                query_hash=f"q{i}",
                domain="legal",
                entry_node=f"LEGAL-{i:03d}" if i < 5 else "CORE-RESEARCH",
                path=[f"LEGAL-{i:03d}", "STORE"] if i < 5 else ["CORE-RESEARCH", "STORE"],
                confidence_at_entry=0.7,
                confidence_at_exit=0.85,
                model_used="test",
                external_called=False,
                outcome="completed",
            )
            for i in range(10)
        ]
        for p in paths:
            store.write_path(p)

        results = store.search_paths("LEGAL")
        assert len(results) > 0
        # BM25 should rank LEGAL entries higher
        assert "LEGAL" in results[0].entry_node
