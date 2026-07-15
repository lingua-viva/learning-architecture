"""
NDJSON Cold Memory Adapter

Why NDJSON and not a vector database:
The "Price of Meaning" paper (2603.27116) proves vector databases organize by
semantic meaning and therefore suffer interference. Mission Canvas's memory
does NOT organize by meaning — it organizes by path through a symbolic ontology.

NDJSON stores the cold record: every path ever taken, queryable by BM25 keyword
matching. BM25 achieves zero forgetting and zero false recall (b=0, FA=0) at the
cost of semantic generalization. Because the ontology provides the semantic
structure, BM25 over path records gives exact recall without false positives.

This is the mathematically proven escape from the No-Escape Theorem.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from .schema import PathRecord, SessionRecord


class NDJSONAdapter:
    """
    Append-only NDJSON storage with BM25 path search.
    Files: paths.ndjson, sessions.ndjson, gap_signals.ndjson
    """

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths_file = self.data_dir / "paths.ndjson"
        self.sessions_file = self.data_dir / "sessions.ndjson"
        self.gaps_file = self.data_dir / "gap_signals.ndjson"

    # --- Write ---

    def write_path(self, record: PathRecord) -> None:
        """Append a path record. Append-only. Never deletes."""
        with open(self.paths_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

    def write_session(self, record: SessionRecord) -> None:
        with open(self.sessions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

    def write_gap_signal(self, signal: dict) -> None:
        with open(self.gaps_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal) + "\n")

    # --- Read ---

    def read_all_paths(self) -> list[PathRecord]:
        """Read all path records from cold storage. Skips malformed lines."""
        if not self.paths_file.exists():
            return []
        records = []
        with open(self.paths_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(PathRecord.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue  # Skip corrupted lines — don't break all reads
        return records

    def read_all_sessions(self) -> list[SessionRecord]:
        if not self.sessions_file.exists():
            return []
        records = []
        with open(self.sessions_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(SessionRecord.from_dict(json.loads(line)))
        return records

    def read_gap_signals(self) -> list[dict]:
        if not self.gaps_file.exists():
            return []
        signals = []
        with open(self.gaps_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    signals.append(json.loads(line))
        return signals

    # --- Search ---

    def find_paths(
        self,
        entry_node: Optional[str] = None,
        domain: Optional[str] = None,
        intent: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> list[PathRecord]:
        """
        Structural search — find paths by ontology position, not by semantic similarity.
        This is BM25-style exact matching: zero forgetting, zero false recall.
        """
        all_paths = self.read_all_paths()
        filtered = []
        for p in all_paths:
            if entry_node and p.entry_node != entry_node:
                continue
            if domain and p.domain != domain:
                continue
            if intent and p.intent != intent:
                continue
            if p.confidence_at_exit < min_confidence:
                continue
            filtered.append(p)

        # Sort by timestamp descending (most recent first)
        filtered.sort(key=lambda p: p.timestamp, reverse=True)
        return filtered[:limit]

    def bm25_search(
        self,
        query: str,
        field: str = "entry_node",
        limit: int = 10,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[PathRecord]:
        """
        BM25 keyword search over path records.

        From the paper: "BM25 produces b=0.000, FA=0.000, no spacing effect,
        yielding complete immunity. But semantic retrieval agreement is 15.5%."

        That's fine. The ontology provides the semantic structure. BM25 provides
        the exact recall. Together: best of both worlds.
        """
        all_paths = self.read_all_paths()
        if not all_paths:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return all_paths[:limit]

        # Build document corpus from the specified field
        docs = []
        for p in all_paths:
            text = self._get_searchable_text(p, field)
            tokens = self._tokenize(text)
            docs.append(tokens)

        # Compute IDF
        N = len(docs)
        df = Counter()
        for doc_tokens in docs:
            for token in set(doc_tokens):
                df[token] += 1

        avgdl = sum(len(d) for d in docs) / max(N, 1)

        # Score each document
        scores = []
        for i, doc_tokens in enumerate(docs):
            score = 0.0
            dl = len(doc_tokens)
            tf_counter = Counter(doc_tokens)
            for term in query_tokens:
                if term not in df:
                    continue
                tf = tf_counter.get(term, 0)
                idf = math.log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / max(avgdl, 1))
                score += idf * numerator / denominator
            scores.append((i, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scores[:limit]:
            if score > 0:
                results.append(all_paths[idx])
        return results

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r'\w+', text.lower())

    def _get_searchable_text(self, p: PathRecord, field: str) -> str:
        if field == "entry_node":
            return p.entry_node
        elif field == "path":
            return " ".join(p.path)
        elif field == "domain":
            return p.domain
        elif field == "outcome":
            return p.outcome
        elif field == "all":
            parts = [p.entry_node, p.domain, p.outcome, p.intent or ""]
            parts.extend(p.path)
            parts.extend(p.gap_signals)
            return " ".join(parts)
        return p.entry_node

    # --- Stats ---

    def path_count(self) -> int:
        if not self.paths_file.exists():
            return 0
        count = 0
        with open(self.paths_file, encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count

    def gap_signal_count(self) -> int:
        if not self.gaps_file.exists():
            return 0
        count = 0
        with open(self.gaps_file, encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count
