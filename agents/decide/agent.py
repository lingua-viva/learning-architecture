"""
DECIDE Agent — Reversibility analysis, one-way door enforcement.

Parses model output for decision + reversibility classification.
If one-way door detected, flags for human confirmation.
Persists DecisionRecord for the judgment trail.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DecisionRecord:
    """A persistent record of a decision made through the system."""
    session_id: str
    query_hash: str
    decision: str
    reversibility: str  # one_way, two_way, unknown
    evidence_basis: list[str] = field(default_factory=list)
    confidence: float = 0.0
    requires_confirmation: bool = False
    confirmed: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# Patterns that indicate one-way door decisions
ONE_WAY_SIGNALS = [
    "irreversible", "cannot be undone", "one-way door", "permanent",
    "cannot reverse", "binding", "final", "non-revocable",
    "point of no return", "once done", "cannot be taken back",
]

TWO_WAY_SIGNALS = [
    "reversible", "can be undone", "two-way door", "temporary",
    "can reverse", "rollback", "revert", "trial", "pilot",
]


class DecideAgent:
    """
    DECIDE intent agent. Enforces reversibility analysis.

    Parses model output for:
    - Decision statement
    - Reversibility classification (one-way / two-way / unknown)
    - Evidence basis (which KL entries / paths informed it)

    One-way doors get flagged: requires_confirmation = True.
    """

    INTENT = "DECIDE"

    def __init__(self):
        self._decisions_file = Path(__file__).parent.parent.parent / "memory" / "data" / "decisions.ndjson"
        self._decisions_file.parent.mkdir(parents=True, exist_ok=True)

    def analyze(self, content: str, session_id: str, query_hash: str, confidence: float) -> DecisionRecord:
        """Analyze model output for decision + reversibility."""
        reversibility = self._classify_reversibility(content)
        decision = self._extract_decision(content)

        record = DecisionRecord(
            session_id=session_id,
            query_hash=query_hash,
            decision=decision,
            reversibility=reversibility,
            confidence=confidence,
            requires_confirmation=(reversibility == "one_way"),
        )

        self._persist(record)
        return record

    def _classify_reversibility(self, content: str) -> str:
        """Classify the decision as one-way or two-way door."""
        content_lower = content.lower()
        one_way_count = sum(1 for s in ONE_WAY_SIGNALS if s in content_lower)
        two_way_count = sum(1 for s in TWO_WAY_SIGNALS if s in content_lower)

        if one_way_count > two_way_count:
            return "one_way"
        elif two_way_count > one_way_count:
            return "two_way"
        return "unknown"

    def _extract_decision(self, content: str) -> str:
        """Extract the decision statement from model output."""
        # Look for explicit decision markers
        for marker in ["Decision:", "Recommendation:", "I recommend", "The decision is"]:
            idx = content.find(marker)
            if idx >= 0:
                # Get the rest of the sentence/paragraph
                end = content.find("\n\n", idx)
                if end == -1:
                    end = min(idx + 300, len(content))
                return content[idx:end].strip()
        # Fallback: first 200 chars
        return content[:200].strip()

    def _persist(self, record: DecisionRecord) -> None:
        """Append to decisions NDJSON."""
        with open(self._decisions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
