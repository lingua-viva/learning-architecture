"""
Multi-Agent Handoff System

When a query exceeds one agent's competence, the handoff packet includes
the path record, NOT the conversation history. The receiving agent starts
from the ontology node, not from a conversation summary.

This is the key insight: agents don't need to read each other's transcripts.
They need to know where the problem is on the map and what paths have been tried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .schema import PathRecord


@dataclass
class HandoffPacket:
    """
    Everything an agent needs to continue work started by another agent.
    No conversation history. Just the map position and path records.
    """
    from_agent: str
    to_agent: str
    entry_node: str
    domain: str
    intent: str
    paths_tried: list[PathRecord] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    decisions_made: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    context_notes: str = ""
    confidence: float = 0.5

    def to_context_block(self) -> str:
        """Format for injection into the receiving agent's context."""
        lines = [f"[HANDOFF from {self.from_agent} → {self.to_agent}]"]
        lines.append(f"Node: {self.entry_node} | Domain: {self.domain} | Intent: {self.intent}")
        lines.append(f"Confidence: {self.confidence:.2f}")

        if self.paths_tried:
            lines.append(f"\nPaths tried ({len(self.paths_tried)}):")
            for p in self.paths_tried:
                lines.append(f"  {' → '.join(p.path)} → {p.outcome}")

        if self.decisions_made:
            lines.append("\nDecisions already made:")
            for d in self.decisions_made:
                lines.append(f"  - {d}")

        if self.open_questions:
            lines.append("\nOpen questions:")
            for q in self.open_questions:
                lines.append(f"  - {q}")

        if self.context_notes:
            lines.append(f"\nNotes: {self.context_notes}")

        lines.append("[END HANDOFF]")
        return "\n".join(lines)
