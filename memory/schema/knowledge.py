"""
Knowledge Entry Schema

Knowledge entries are evidence-tiered facts stored in the knowledge library.
They are NOT path records — they are the facts the system knows.
Path records reference knowledge entries by ID.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeEntry:
    """A single evidence-tiered knowledge entry."""
    id: str
    title: str
    content: str
    domain: str
    ontology_nodes: list[str]               # Which nodes this entry is relevant to
    evidence_tier: int                       # 1=primary, 2=secondary, 3=community
    citations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: Optional[float] = None
    verified: bool = False
    verified_by: Optional[str] = None
    last_verified: Optional[float] = None
    verification_interval_days: int = 180  # Legal: 90, Technical: 180
    superseded_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> KnowledgeEntry:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in valid_fields})
