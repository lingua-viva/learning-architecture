"""
Community Contributor

Strips PII, hashes queries, packages path records for sharing.
Every contribution is opt-in. No data leaves without explicit consent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from memory.schema import PathRecord


@dataclass
class Contribution:
    """A PII-stripped, hashed path record ready for community sharing."""
    query_hash: str       # Already hashed — no raw query ever shared
    domain: str
    entry_node: str
    path: list[str]
    confidence_at_exit: float
    outcome: str
    intent: Optional[str]
    contributor_hash: str  # Hashed user ID — anonymous

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class Contributor:
    """Prepares path records for community contribution."""

    def __init__(self, user_id: str):
        self.user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:12]

    def prepare(self, record: PathRecord) -> Contribution:
        """Strip PII and prepare a path record for sharing."""
        return Contribution(
            query_hash=record.query_hash,  # Already hashed
            domain=record.domain,
            entry_node=record.entry_node,
            path=record.path,
            confidence_at_exit=record.confidence_at_exit,
            outcome=record.outcome,
            intent=record.intent,
            contributor_hash=self.user_hash,
        )

    def is_safe_to_share(self, record: PathRecord) -> bool:
        """Check if a path record is safe to share publicly."""
        # Never share PROTECT paths
        if record.intent == "PROTECT":
            return False
        # Never share if entry node is privilege-related
        if record.entry_node in ("LEGAL-001", "RIU-700"):
            return False
        # Never share gap signals (may contain query fragments)
        if record.gap_signals:
            return False
        return True
