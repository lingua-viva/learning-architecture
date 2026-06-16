"""
Session Record Schema

A session is a continuous interaction period. It accumulates path records,
decisions, and notes. When the context window fills, the session gets
compacted — but decisions and paths are NEVER lost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionRecord:
    """Tracks one continuous interaction session."""
    session_id: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    path_count: int = 0
    decision_count: int = 0
    external_call_count: int = 0
    domains_touched: list[str] = field(default_factory=list)
    intents_used: list[str] = field(default_factory=list)
    compaction_count: int = 0
    total_tokens_estimated: int = 0
    notes: dict = field(default_factory=dict)  # Working memory

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> SessionRecord:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in valid_fields})
