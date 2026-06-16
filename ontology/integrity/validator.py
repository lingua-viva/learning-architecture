"""
Ontology Integrity Validator

Validates the ontology graph: detects cycles, orphan nodes, coverage gaps,
and measures path consistency. This is the self-audit for Layer 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..engine import OntologyEngine, PathRecord


@dataclass
class ValidationResult:
    """Result of validating the ontology."""
    total_nodes: int = 0
    total_domains: int = 0
    orphan_nodes: list[str] = field(default_factory=list)
    cycle_detected: bool = False
    cycle_nodes: list[str] = field(default_factory=list)
    missing_parents: list[str] = field(default_factory=list)
    broken_edges: list[dict] = field(default_factory=list)
    coverage_score: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.checks_passed == self.checks_total and not self.cycle_detected


class OntologyValidator:
    """Validates the ontology graph structure and health."""

    def __init__(self, engine: OntologyEngine):
        self.engine = engine

    def validate(self, path_records: Optional[list[PathRecord]] = None) -> ValidationResult:
        result = ValidationResult(
            total_nodes=self.engine.node_count,
            total_domains=self.engine.domain_count,
        )

        checks = [
            self._check_orphan_nodes,
            self._check_cycles,
            self._check_parent_references,
            self._check_edge_targets,
            self._check_signal_coverage,
            self._check_governance_rules,
        ]

        for check in checks:
            result.checks_total += 1
            try:
                passed, issues = check(result)
                if passed:
                    result.checks_passed += 1
                result.issues.extend(issues)
            except Exception as e:
                result.issues.append(f"Check failed with error: {e}")

        # Coverage from path records
        if path_records:
            result.checks_total += 1
            visited_nodes = set()
            for p in path_records:
                visited_nodes.add(p.entry_node)
                visited_nodes.update(p.path)
            total = max(self.engine.node_count, 1)
            result.coverage_score = len(visited_nodes & set(self.engine.nodes.keys())) / total
            if result.coverage_score > 0.3:
                result.checks_passed += 1
            else:
                result.issues.append(
                    f"Low path coverage: {result.coverage_score:.1%} of nodes visited"
                )

        return result

    def _check_orphan_nodes(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """Nodes with no parent and no children are orphans (except root core nodes)."""
        issues = []
        for node_id, node in self.engine.nodes.items():
            if node.parent is None and node.domain != "core":
                children = self.engine.traverse(node_id, "children")
                if not children:
                    result.orphan_nodes.append(node_id)
                    issues.append(f"Orphan node: {node_id}")
        return len(result.orphan_nodes) == 0, issues

    def _check_cycles(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """Detect cycles in parent-child relationships."""
        visited = set()
        path = set()

        def dfs(node_id: str) -> bool:
            if node_id in path:
                result.cycle_detected = True
                result.cycle_nodes.append(node_id)
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            path.add(node_id)
            children = self.engine.traverse(node_id, "children")
            for child in children:
                if dfs(child.id):
                    return True
            path.discard(node_id)
            return False

        for node_id in self.engine.nodes:
            if dfs(node_id):
                break

        issues = [f"Cycle detected involving: {', '.join(result.cycle_nodes)}"] if result.cycle_detected else []
        return not result.cycle_detected, issues

    def _check_parent_references(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """Every node's parent must exist in the graph."""
        issues = []
        for node_id, node in self.engine.nodes.items():
            if node.parent and node.parent not in self.engine.nodes:
                result.missing_parents.append(node_id)
                issues.append(f"Node {node_id} references missing parent: {node.parent}")
        return len(result.missing_parents) == 0, issues

    def _check_edge_targets(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """All edge targets (escalates_to, resolves_to, etc.) must exist."""
        issues = []
        for node_id, node in self.engine.nodes.items():
            for target in node.escalates_to:
                if target not in self.engine.nodes:
                    result.broken_edges.append({"from": node_id, "to": target, "type": "escalates_to"})
                    issues.append(f"Broken edge: {node_id} escalates to missing {target}")
            for target in node.resolves_to:
                if target not in self.engine.nodes:
                    result.broken_edges.append({"from": node_id, "to": target, "type": "resolves_to"})
                    issues.append(f"Broken edge: {node_id} resolves to missing {target}")
        return len(result.broken_edges) == 0, issues

    def _check_signal_coverage(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """Every non-root node should have at least 3 signals."""
        issues = []
        low_signal_count = 0
        for node_id, node in self.engine.nodes.items():
            if len(node.signals) < 3:
                low_signal_count += 1
                issues.append(f"Node {node_id} has only {len(node.signals)} signals (min 3)")
        return low_signal_count == 0, issues

    def _check_governance_rules(self, result: ValidationResult) -> tuple[bool, list[str]]:
        """Nodes with blocks_external=True must also have requires_local=True."""
        issues = []
        mismatches = 0
        for node_id, node in self.engine.nodes.items():
            if node.blocks_external and not node.requires_local:
                mismatches += 1
                issues.append(f"Node {node_id}: blocks_external=True but requires_local=False")
        return mismatches == 0, issues
