"""
Path Record Schema

The path record is the fundamental memory unit in Mission Canvas.
Not semantic similarity. Not vector proximity. The path taken through
the ontology — that is the memory.

This is associative memory: the mechanism of human long-term memory.
The path is what becomes long-term memory. The ontology is the map
the path runs through.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PathRecord:
    """
    An episodic memory artifact recording one traversal through the ontology.

    Every completed query produces exactly one PathRecord. This is mandatory.
    The system's memory compounds with every use because every query
    contributes a path record.
    """
    session_id: str
    query_hash: str
    domain: str
    entry_node: str
    path: list[str]                          # Ordered list of node IDs visited
    confidence_at_entry: float               # Confidence when entering the pipeline
    confidence_at_exit: float                # Confidence after synthesis
    model_used: str                          # Which model handled the reasoning
    external_called: bool                    # Whether Perplexity/external was called
    outcome: str                             # "decision_stored", "knowledge_gap", "escalated", etc.
    timestamp: float = field(default_factory=time.time)
    intent: Optional[str] = None             # PROTECT, RESEARCH, DECIDE, CREATE, DIAGNOSE, REFLECT
    lens_applied: Optional[str] = None       # Which lens was active
    knowledge_entries_used: list[str] = field(default_factory=list)
    gap_signals: list[str] = field(default_factory=list)  # What was missing
    duration_ms: Optional[int] = None        # Pipeline execution time

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> PathRecord:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in valid_fields})
