"""
Context Compaction System

From the Anthropic context engineering paper: compaction, structured note-taking,
and multi-agent architectures are the three techniques for long-horizon tasks.

Compaction triggers when session token count exceeds 60% of context window.
Extracts: decisions made, paths taken, knowledge retrieved, external calls made.
Discards: intermediate reasoning, repeated context, failed attempts.
Output: a structured SessionSummary that replaces the full transcript.

Invariant: no information loss for decisions and paths.
Lossy compression is acceptable for reasoning steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .schema import PathRecord, SessionRecord


@dataclass
class SessionSummary:
    """
    The compacted representation of a session.
    Replaces the full transcript in context. Decisions and paths preserved.
    """
    session_id: str
    decisions_made: list[dict] = field(default_factory=list)
    paths_taken: list[dict] = field(default_factory=list)
    knowledge_retrieved: list[str] = field(default_factory=list)
    external_calls: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    domains_active: list[str] = field(default_factory=list)
    total_queries: int = 0
    compaction_number: int = 1

    def to_context_block(self) -> str:
        """Format as a context block for injection into the model's prompt."""
        lines = [f"[SESSION SUMMARY — compaction #{self.compaction_number}]"]
        lines.append(f"Session: {self.session_id}")
        lines.append(f"Queries processed: {self.total_queries}")
        lines.append(f"Domains active: {', '.join(self.domains_active)}")

        if self.decisions_made:
            lines.append("\n## Decisions Made")
            for d in self.decisions_made:
                lines.append(f"  - [{d.get('node', '?')}] {d.get('outcome', '?')} "
                           f"(confidence: {d.get('confidence', '?')})")

        if self.paths_taken:
            lines.append(f"\n## Paths Taken ({len(self.paths_taken)} total)")
            for p in self.paths_taken[-5:]:  # Last 5 only
                lines.append(f"  - {' → '.join(p.get('path', []))}")

        if self.knowledge_retrieved:
            lines.append(f"\n## Knowledge Used ({len(self.knowledge_retrieved)} entries)")
            for k in self.knowledge_retrieved[:10]:
                lines.append(f"  - {k}")

        if self.open_questions:
            lines.append("\n## Open Questions")
            for q in self.open_questions:
                lines.append(f"  - {q}")

        lines.append("[END SESSION SUMMARY]")
        return "\n".join(lines)


class Compactor:
    """
    Compacts a session when context fills up.

    Trigger: session token count > 60% of context window.
    Invariant: decisions and paths are NEVER lost.
    """

    def __init__(self, context_window_tokens: int = 128_000):
        self.context_window = context_window_tokens
        self.trigger_threshold = 0.60

    def should_compact(self, estimated_tokens: int) -> bool:
        return estimated_tokens > (self.context_window * self.trigger_threshold)

    def compact(
        self,
        session: SessionRecord,
        paths: list[PathRecord],
        keep_decisions: bool = True,
        keep_paths: bool = True,
    ) -> SessionSummary:
        """
        Compact a session into a summary.
        Decisions and paths always preserved. Reasoning steps compressed.
        """
        summary = SessionSummary(
            session_id=session.session_id,
            total_queries=session.path_count,
            domains_active=list(set(session.domains_touched)),
            compaction_number=session.compaction_count + 1,
        )

        for path in paths:
            # Always keep path records (they ARE the memory)
            path_summary = {
                "entry_node": path.entry_node,
                "path": path.path,
                "confidence_at_exit": path.confidence_at_exit,
                "outcome": path.outcome,
                "intent": path.intent,
            }
            summary.paths_taken.append(path_summary)

            # Extract decisions
            if path.outcome in ("decision_stored", "escalated"):
                summary.decisions_made.append({
                    "node": path.entry_node,
                    "outcome": path.outcome,
                    "confidence": path.confidence_at_exit,
                    "path": path.path,
                })

            # Track knowledge used
            summary.knowledge_retrieved.extend(path.knowledge_entries_used)

            # Track external calls
            if path.external_called:
                summary.external_calls.append({
                    "node": path.entry_node,
                    "model": path.model_used,
                })

            # Track gaps as open questions
            for gap in path.gap_signals:
                summary.open_questions.append(f"Gap at {path.entry_node}: {gap}")

        # Deduplicate knowledge
        summary.knowledge_retrieved = list(set(summary.knowledge_retrieved))

        return summary
