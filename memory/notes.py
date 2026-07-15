"""
Structured Note-Taking System

Every agent maintains structured notes — the working memory.
Not the full session, just what the agent needs to continue.
Updated at the end of every intent execution.

This is the model's scratchpad. It prevents the context window from
filling with repeated context by keeping only the active state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentNotes:
    """Working memory for one agent in one session."""
    agent_id: str
    session_id: str
    active_decisions: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    def to_context_block(self) -> str:
        lines = [f"[NOTES — {self.agent_id}]"]
        if self.active_decisions:
            lines.append("Active decisions:")
            for d in self.active_decisions:
                lines.append(f"  - {d}")
        if self.open_questions:
            lines.append("Open questions:")
            for q in self.open_questions:
                lines.append(f"  - {q}")
        if self.next_steps:
            lines.append("Next steps:")
            for s in self.next_steps:
                lines.append(f"  - {s}")
        lines.append("[END NOTES]")
        return "\n".join(lines)


class NotesManager:
    """Manages structured notes for all agents across sessions."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent / "data" / "notes"
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _notes_path(self, agent_id: str, session_id: str) -> Path:
        return self.data_dir / f"{session_id}_{agent_id}.json"

    def save(self, notes: AgentNotes) -> None:
        path = self._notes_path(notes.agent_id, notes.session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "agent_id": notes.agent_id,
                "session_id": notes.session_id,
                "active_decisions": notes.active_decisions,
                "open_questions": notes.open_questions,
                "knowledge_refs": notes.knowledge_refs,
                "next_steps": notes.next_steps,
                "observations": notes.observations,
            }, f, indent=2)

    def load(self, agent_id: str, session_id: str) -> Optional[AgentNotes]:
        path = self._notes_path(agent_id, session_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return AgentNotes(**data)
