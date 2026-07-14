"""
Document Intelligence Tests — Governed RAG regression coverage.

Exercises the full chain built across Turns 16-19: DocumentParser ->
DocumentStore -> DocumentRetriever -> Pipeline, together, the way
`mc ingest` + `mc research` actually run it. Uses a synthetic fixture PDF
(fake placeholder PII — "Dr. Smith", test@example.com, 555-123-4567 — safe
to check in) that intentionally combines a heading, a table, and
Layer-3-style boilerplate ("confidential ... internal school use only") on
the same document — the exact shape that surfaced two real bugs (duplicate
table content flattened into prose, a table header row misdetected as a
section heading) during manual testing in Turn 16.

Store round-trip and retriever tests call the local Ollama embedding
endpoint for real (no mock) — consistent with how test_pipeline_entry_gate.py
already exercises the live local reasoning model rather than mocking it.
This repo mocks external network calls (see test_perplexity.py) but not
local-only Ollama calls.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

from src.education.document_parser import DocumentParser
from src.education.document_store import DocumentStore
from src.education.document_retrieval import DocumentRetriever
from src.pipeline import Pipeline, ReasonResult

FIXTURE = Path(__file__).parent / "fixtures" / "sample_myp_guide.pdf"


class RecordingReasoning:
    """Captures the system_prompt the pipeline actually built, without
    depending on a live chat model being available or deterministic."""

    def __init__(self):
        self.last_system_prompt = None

    async def reason(self, query, context, model=None, system_prompt=None):
        self.last_system_prompt = system_prompt
        return ReasonResult(content="captured", confidence=0.9, model_used="test")


def test_parser_produces_two_correctly_labeled_chunks_no_duplication():
    """Regression test for Turn 16's two bugs: duplicate table content
    flattened into prose, and a table header row misdetected as a new
    section heading that overrode the true page heading."""
    chunks = DocumentParser().parse(FIXTURE)

    assert len(chunks) == 2

    prose = next(c for c in chunks if not c.is_table)
    table = next(c for c in chunks if c.is_table)

    assert prose.section == "CRITERION B: READING"
    assert table.section == "ACHIEVEMENT LEVEL DESCRIPTORS (table 1)"

    # The table's own header row / row data must never leak into the prose
    # chunk — that was the duplication bug.
    assert "Level Descriptor" not in prose.text
    assert "Limited understanding" not in prose.text


def test_parser_redacts_and_flags_review():
    chunks = DocumentParser().parse(FIXTURE)
    prose = next(c for c in chunks if not c.is_table)
    table = next(c for c in chunks if c.is_table)

    # "confidential ... internal school use only" boilerplate triggers
    # needs_review (redact-not-block — see module docstring) without
    # destroying the surrounding legitimate curriculum content.
    assert prose.needs_review is True
    assert len(prose.redactions) == 3  # email, phone, person name
    assert "[REDACTED_" in prose.text
    assert "test@example.com" not in prose.text
    assert "555-123-4567" not in prose.text

    assert table.needs_review is False
    assert table.redactions == []


def test_store_round_trip_ranks_semantically_relevant_chunk_first(tmp_path):
    chunks = DocumentParser().parse(FIXTURE)
    store = DocumentStore(tmp_path / "test.db")
    try:
        added = store.add_chunks(chunks)
        assert added == 2
        assert store.count() == 2

        results = store.search("what are the achievement levels for criterion B?", k=2)
        assert len(results) == 2
        assert results[0]["section"] == "ACHIEVEMENT LEVEL DESCRIPTORS (table 1)"
        assert results[0]["distance"] < results[1]["distance"]
    finally:
        store.close()


def test_retriever_gates_by_ontology_domain(tmp_path):
    chunks = DocumentParser().parse(FIXTURE)
    store = DocumentStore(tmp_path / "test.db")
    try:
        store.add_chunks(chunks)
        retriever = DocumentRetriever(store, domains={"curriculum"})

        # In scope: real search happens.
        in_scope = retriever.retrieve("achievement levels", domain="curriculum", k=2)
        assert len(in_scope) == 2

        # Out of scope: gated off before any embedding call.
        out_of_scope = retriever.retrieve("achievement levels", domain="legal", k=2)
        assert out_of_scope == []
    finally:
        store.close()


def test_pipeline_injects_document_context_for_scoped_domain(tmp_path):
    """The real integration point: a DocumentRetriever wired into Pipeline
    surfaces retrieved chunks in the system prompt the model sees, for a
    query that lands in an in-scope domain."""
    chunks = DocumentParser().parse(FIXTURE)
    store = DocumentStore(tmp_path / "test.db")
    try:
        store.add_chunks(chunks)
        retriever = DocumentRetriever(store, domains={"curriculum"})

        reasoning = RecordingReasoning()
        pipeline = Pipeline(reasoning=reasoning, document_retriever=retriever)

        result = asyncio.run(pipeline.run(
            "what is the central idea for our unit plan on achievement level descriptors?",
            eval_mode=True,
        ))

        assert result.classification.domain == "curriculum"
        assert reasoning.last_system_prompt is not None
        assert "Retrieved Document Excerpts" in reasoning.last_system_prompt
        assert "ACHIEVEMENT LEVEL DESCRIPTORS" in reasoning.last_system_prompt
    finally:
        store.close()


def test_pipeline_skips_document_context_for_out_of_scope_domain(tmp_path):
    chunks = DocumentParser().parse(FIXTURE)
    store = DocumentStore(tmp_path / "test.db")
    try:
        store.add_chunks(chunks)
        retriever = DocumentRetriever(store, domains={"curriculum"})

        reasoning = RecordingReasoning()
        pipeline = Pipeline(reasoning=reasoning, document_retriever=retriever)

        result = asyncio.run(pipeline.run(
            "My patient John Smith SSN 123-45-6789 has stage 4 cancer",
            intent="PROTECT",
            eval_mode=True,
        ))

        assert reasoning.last_system_prompt is not None
        assert "Retrieved Document Excerpts" not in reasoning.last_system_prompt
    finally:
        store.close()


def test_pipeline_with_no_retriever_injected_is_unchanged():
    """Every existing caller of Pipeline() (no document_retriever passed)
    must behave exactly as before this build — zero regression risk."""
    reasoning = RecordingReasoning()
    pipeline = Pipeline(reasoning=reasoning)
    assert pipeline.document_retriever is None

    result = asyncio.run(pipeline.run(
        "what is the central idea for our unit plan?",
        eval_mode=True,
    ))
    assert reasoning.last_system_prompt is not None
    assert "Retrieved Document Excerpts" not in reasoning.last_system_prompt
