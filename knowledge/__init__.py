"""
Knowledge Library — Evidence-tiered knowledge store.

Entries are loaded from YAML files, queryable by ontology node and domain.
BM25 keyword search over entry content — same interference-free retrieval
as path records.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from memory.schema.knowledge import KnowledgeEntry


_TOKENIZE = re.compile(r'\w+')


class KnowledgeStore:
    """
    Loads and queries the evidence-tiered knowledge library.

    Entries are YAML files in the knowledge/ directory. Each entry maps
    to one or more ontology nodes. Retrieval is by node ID or BM25 search.
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.entries: dict[str, KnowledgeEntry] = {}
        self._by_node: dict[str, list[str]] = {}  # node_id -> [entry_ids]
        self._by_domain: dict[str, list[str]] = {}  # domain -> [entry_ids]

        if knowledge_dir is None:
            knowledge_dir = Path(__file__).parent
        self._load(knowledge_dir)

    def _load(self, knowledge_dir: Path) -> None:
        yaml_files = list(knowledge_dir.glob("*.yaml"))
        for subdir in ["education"]:
            dir_path = knowledge_dir / subdir
            if dir_path.exists():
                yaml_files.extend(dir_path.glob("*.yaml"))
        for yaml_file in sorted(yaml_files):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if not data or "entries" not in data:
                continue
            domain = data.get("domain", "core")
            for entry_data in data["entries"]:
                entry = KnowledgeEntry(
                    id=entry_data["id"],
                    title=entry_data["title"],
                    content=entry_data["content"],
                    domain=domain,
                    ontology_nodes=entry_data.get("ontology_nodes", []),
                    evidence_tier=entry_data.get("evidence_tier", 3),
                    citations=entry_data.get("citations", []),
                    tags=entry_data.get("tags", []),
                    verified=entry_data.get("verified", False),
                )
                self.entries[entry.id] = entry
                self._by_domain.setdefault(domain, []).append(entry.id)
                for node_id in entry.ontology_nodes:
                    self._by_node.setdefault(node_id, []).append(entry.id)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def citation_count(self) -> int:
        return sum(len(e.citations) for e in self.entries.values())

    def set_ontology(self, ontology) -> None:
        """Wire the ontology engine for hierarchical retrieval."""
        self._ontology = ontology

    def retrieve(
        self,
        node_id: Optional[str] = None,
        domain: Optional[str] = None,
        min_tier: Optional[int] = None,
        limit: int = 5,
    ) -> list[KnowledgeEntry]:
        """
        Retrieve entries by ontology node or domain.

        Hierarchical: if no entries at the exact node, walks UP to parent nodes.
        This is the ontology doing what it's designed to do — multi-directional
        traversal for knowledge retrieval. A query at RIU-709 (Fiduciary Duty)
        that has no direct KL entries will find entries at CORE-RESEARCH (parent).
        """
        ids = []
        if node_id:
            ids = list(self._by_node.get(node_id, []))
            # Walk up parents if no direct entries found
            if not ids and hasattr(self, '_ontology') and self._ontology:
                visited = {node_id}
                current = node_id
                while not ids:
                    parents = self._ontology.traverse(current, "parents")
                    if not parents:
                        break
                    current = parents[0].id
                    if current in visited:
                        break
                    visited.add(current)
                    ids = list(self._by_node.get(current, []))
        elif domain:
            ids = self._by_domain.get(domain, [])
        else:
            ids = list(self.entries.keys())

        results = [self.entries[eid] for eid in ids if eid in self.entries]

        if min_tier:
            results = [e for e in results if e.evidence_tier <= min_tier]

        results.sort(key=lambda e: e.evidence_tier)
        return results[:limit]

    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        """BM25-style keyword search over entry content and tags."""
        tokens = set(_TOKENIZE.findall(query.lower()))
        if not tokens:
            return []

        scored: list[tuple[str, int]] = []
        for eid, entry in self.entries.items():
            searchable = " ".join([
                entry.title, entry.content,
                " ".join(entry.tags), " ".join(entry.ontology_nodes),
            ]).lower()
            entry_tokens = set(_TOKENIZE.findall(searchable))
            overlap = len(tokens & entry_tokens)
            if overlap > 0:
                scored.append((eid, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [self.entries[eid] for eid, _ in scored[:limit]]

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        return self.entries.get(entry_id)
