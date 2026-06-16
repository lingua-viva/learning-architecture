"""
Unified Memory Store

The single interface for all memory operations in Mission Canvas.
Wraps Redis (hot) and NDJSON (cold) into one coherent API.

The memory interface is simple:
  memory.write_path(path_record)        — store a path
  memory.find_paths(entry_node, ...)    — retrieve relevant paths
  memory.compact_session(session_id)    — compact a long session

The model receives relevant paths in its context before reasoning.
It is not reading a transcript. It is reading a navigation record:
"previous queries classified as LEGAL-001 took this path and produced
these outcomes." That is useful, non-interfering, path-structured memory.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from .schema import PathRecord, SessionRecord
from .redis_adapter import RedisAdapter
from .ndjson_adapter import NDJSONAdapter


class MemoryStore:
    """
    Unified memory interface. Hot (Redis) + Cold (NDJSON).

    Every write goes to both stores:
    - Redis for fast recent lookups (TTL-based expiry)
    - NDJSON for permanent cold storage (append-only, never deletes)

    Reads prefer Redis (hot) and fall back to NDJSON (cold) for older records.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        data_dir: Optional[Path] = None,
    ):
        self.hot = RedisAdapter(redis_url=redis_url)
        self.cold = NDJSONAdapter(data_dir=data_dir)

    # --- Path Records ---

    def write_path(self, record: PathRecord) -> None:
        """
        Store a path record. Goes to both hot and cold storage.
        This is mandatory for every completed query. Memory compounds with every use.
        """
        self.hot.store_path(record)
        self.cold.write_path(record)

        # If there are gap signals, also write them to the gap store
        if record.gap_signals:
            self.cold.write_gap_signal({
                "entry_node": record.entry_node,
                "domain": record.domain,
                "gap_signals": record.gap_signals,
                "timestamp": record.timestamp,
                "session_id": record.session_id,
            })

    def find_paths(
        self,
        entry_node: Optional[str] = None,
        domain: Optional[str] = None,
        intent: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 5,
    ) -> list[PathRecord]:
        """
        Find relevant paths. Checks hot first, falls back to cold.

        NOT semantic search — structural search: find paths that entered
        at similar ontology nodes.
        """
        # Try hot first
        if entry_node:
            hot_results = self.hot.find_recent_paths(entry_node, limit=limit)
            if hot_results:
                filtered = [p for p in hot_results if p.confidence_at_exit >= min_confidence]
                if len(filtered) >= limit:
                    return filtered[:limit]

        # Fall back to cold
        cold_results = self.cold.find_paths(
            entry_node=entry_node,
            domain=domain,
            intent=intent,
            min_confidence=min_confidence,
            limit=limit,
        )
        return cold_results

    def search_paths(self, query: str, limit: int = 10) -> list[PathRecord]:
        """BM25 search over cold path records."""
        return self.cold.bm25_search(query, field="all", limit=limit)

    # --- Sessions ---

    def create_session(self) -> SessionRecord:
        session = SessionRecord(session_id=str(uuid.uuid4()))
        self.hot.set_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        return self.hot.get_session(session_id)

    def update_session(self, session: SessionRecord) -> None:
        self.hot.set_session(session)

    def end_session(self, session: SessionRecord) -> None:
        session.ended_at = time.time()
        self.hot.set_session(session)
        self.cold.write_session(session)

    # --- Statistics ---

    def total_path_count(self) -> int:
        return self.cold.path_count()

    def gap_signal_count(self) -> int:
        return self.cold.gap_signal_count()

    def redis_connected(self) -> bool:
        return self.hot.is_connected
