"""
GraphQuery — Queryable Relationship Graph

Derived from ontology edge fields at load time. No manual YAML maintenance.
Replaces Palette's manual 1,800+ quad RELATIONSHIP_GRAPH.yaml with structural guarantees.

Usage:
    graph = OntologyGraph(engine)
    graph.neighbors("RIU-709")        → {parent_of: [...], escalates_to: [...], ...}
    graph.path_between("CORE-PROTECT", "RIU-700")  → ["CORE-PROTECT", "RIU-700"]
    graph.all_edges()                  → [(subject, predicate, object), ...]
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from .engine import OntologyEngine


class OntologyGraph:
    """Queryable graph derived from ontology edge fields."""

    def __init__(self, engine: OntologyEngine):
        self._engine = engine
        self._outgoing: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._incoming: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._all_edges: list[tuple[str, str, str]] = []
        self._build(engine)

    def _build(self, engine: OntologyEngine) -> None:
        """Build graph from all edge fields on every node."""
        for node_id, node in engine.nodes.items():
            if node.parent:
                self._add_edge(node.parent, "parent_of", node_id)
            for target in node.escalates_to:
                self._add_edge(node_id, "escalates_to", target)
            for target in node.resolves_to:
                self._add_edge(node_id, "resolves_to", target)
            for target in node.contradicts:
                self._add_edge(node_id, "contradicts", target)
            for target in node.co_occurs_with:
                self._add_edge(node_id, "co_occurs_with", target)

    def _add_edge(self, subject: str, predicate: str, obj: str) -> None:
        self._outgoing[subject][predicate].append(obj)
        self._incoming[obj][predicate].append(subject)
        self._all_edges.append((subject, predicate, obj))

    @property
    def edge_count(self) -> int:
        return len(self._all_edges)

    def neighbors(self, node_id: str) -> dict[str, list[str]]:
        """Get all outgoing edges from a node, grouped by predicate."""
        return dict(self._outgoing.get(node_id, {}))

    def incoming(self, node_id: str) -> dict[str, list[str]]:
        """Get all incoming edges to a node, grouped by predicate."""
        return dict(self._incoming.get(node_id, {}))

    def path_between(self, src: str, dst: str, max_depth: int = 6) -> Optional[list[str]]:
        """BFS shortest path between two nodes (follows all edge types)."""
        if src == dst:
            return [src]
        if src not in self._engine.nodes or dst not in self._engine.nodes:
            return None

        visited = {src}
        queue = deque([(src, [src])])

        while queue:
            current, path = queue.popleft()
            if len(path) > max_depth:
                continue
            for predicate, targets in self._outgoing.get(current, {}).items():
                for target in targets:
                    if target == dst:
                        return path + [target]
                    if target not in visited and target in self._engine.nodes:
                        visited.add(target)
                        queue.append((target, path + [target]))
        return None

    def all_edges(self) -> list[tuple[str, str, str]]:
        """All edges as (subject, predicate, object) triples."""
        return list(self._all_edges)

    def subgraph(self, node_id: str, depth: int = 2) -> list[tuple[str, str, str]]:
        """Get all edges within N hops of a node."""
        visited = {node_id}
        frontier = {node_id}
        edges = []

        for _ in range(depth):
            next_frontier = set()
            for nid in frontier:
                for pred, targets in self._outgoing.get(nid, {}).items():
                    for target in targets:
                        edges.append((nid, pred, target))
                        if target not in visited:
                            visited.add(target)
                            next_frontier.add(target)
                for pred, sources in self._incoming.get(nid, {}).items():
                    for source in sources:
                        edges.append((source, pred, nid))
                        if source not in visited:
                            visited.add(source)
                            next_frontier.add(source)
            frontier = next_frontier

        return edges
