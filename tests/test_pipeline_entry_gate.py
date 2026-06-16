"""
Pipeline entry-gate regression tests.

If the entry gate blocks a query, RESEARCH must not fire even when the
classifier lands on a node whose default intent would normally research.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

from src.pipeline import Pipeline


class RecordingGateway:
    def __init__(self):
        self.needs_external_called = False
        self.sanitize_called = False
        self.query_external_called = False

    async def needs_external(self, classification, local_confidence, user_intent=None):
        self.needs_external_called = True
        return True

    async def sanitize_query(self, query, classification):
        self.sanitize_called = True
        return query

    async def query_external(self, query, classification, knowledge_context):
        self.query_external_called = True
        raise AssertionError("query_external must not be called after entry gate block")


def test_entry_gate_block_short_circuits_research():
    gateway = RecordingGateway()
    pipeline = Pipeline(gateway=gateway)

    result = asyncio.run(pipeline.run(
        "My patient John Smith SSN 123-45-6789 has stage 4 cancer",
        intent="RESEARCH",
        eval_mode=True,
    ))

    assert result.external_called is False
    assert "RESEARCH" not in result.steps_executed
    assert "entry_gate_blocked:privileged" in result.gap_signals
    assert "research_blocked_by_entry_gate" in result.gap_signals
    assert gateway.needs_external_called is False
    assert gateway.sanitize_called is False
    assert gateway.query_external_called is False


def test_reflect_intent_short_circuits_research():
    gateway = RecordingGateway()
    pipeline = Pipeline(gateway=gateway)

    result = asyncio.run(pipeline.run(
        "what has codex done this week?",
        intent="REFLECT",
        eval_mode=True,
    ))

    assert result.external_called is False
    assert "RESEARCH" not in result.steps_executed
    assert "research_skipped_by_intent:REFLECT" in result.gap_signals
    assert gateway.needs_external_called is False
    assert gateway.sanitize_called is False
    assert gateway.query_external_called is False
