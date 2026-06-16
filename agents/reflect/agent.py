"""
REFLECT Agent — Self-audit, pattern analysis, improvement proposals.

Analyzes path records to find:
  1. Which nodes are improving (convergence signal)
  2. Which nodes are stuck (gap signal)
  3. Which knowledge entries are most/least used
  4. What improvement proposals should be generated

Reflection feeds the self-improvement loop (Total Health).
Every REFLECT query produces actionable output, not just observation.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from memory.schema.path import PathRecord


@dataclass
class ReflectionReport:
    """Structured output from a reflection analysis."""
    timestamp: float = field(default_factory=time.time)
    total_paths: int = 0
    improving_nodes: list[dict] = field(default_factory=list)
    stuck_nodes: list[dict] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    top_knowledge: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    convergence_score: float = 0.0

    def to_context_block(self) -> str:
        """Format for injection into the model's context."""
        lines = [f"[REFLECTION — {self.total_paths} paths analyzed]"]
        lines.append(f"Convergence: {self.convergence_score:.0%}")

        if self.improving_nodes:
            lines.append(f"\nImproving ({len(self.improving_nodes)}):")
            for n in self.improving_nodes[:5]:
                lines.append(f"  {n['node']}: {n['trend']}")

        if self.stuck_nodes:
            lines.append(f"\nStuck ({len(self.stuck_nodes)}):")
            for n in self.stuck_nodes[:5]:
                lines.append(f"  {n['node']}: {n['reason']}")

        if self.knowledge_gaps:
            lines.append(f"\nKnowledge gaps ({len(self.knowledge_gaps)}):")
            for g in self.knowledge_gaps[:5]:
                lines.append(f"  - {g}")

        if self.proposals:
            lines.append(f"\nProposals ({len(self.proposals)}):")
            for p in self.proposals[:5]:
                lines.append(f"  [{p.get('tier', '?')}] {p.get('action', '?')}")

        lines.append("[END REFLECTION]")
        return "\n".join(lines)


class ReflectAgent:
    """
    REFLECT intent agent. Analyzes system behavior for improvement.
    """

    INTENT = "REFLECT"

    def analyze(self, paths: list[PathRecord]) -> ReflectionReport:
        """Analyze path records and produce a reflection report."""
        report = ReflectionReport(total_paths=len(paths))

        if not paths:
            return report

        # Group by node
        node_paths = defaultdict(list)
        for p in paths:
            node_paths[p.entry_node].append(p)

        improving = 0
        total_repeat = 0

        for node_id, node_records in node_paths.items():
            if len(node_records) < 2:
                continue
            total_repeat += 1

            # Confidence trend
            entries = [r.confidence_at_entry for r in node_records]
            if entries[-1] > entries[0]:
                improving += 1
                report.improving_nodes.append({
                    "node": node_id,
                    "queries": len(node_records),
                    "trend": f"{entries[0]:.2f} → {entries[-1]:.2f} (improving)",
                })
            elif entries[-1] == entries[0]:
                report.stuck_nodes.append({
                    "node": node_id,
                    "queries": len(node_records),
                    "reason": f"Flat at {entries[0]:.2f}",
                })

        report.convergence_score = improving / max(total_repeat, 1)

        # Knowledge usage analysis
        kl_usage = defaultdict(int)
        no_kl_nodes = set()
        for p in paths:
            if p.knowledge_entries_used:
                for kl_id in p.knowledge_entries_used:
                    kl_usage[kl_id] += 1
            else:
                no_kl_nodes.add(p.entry_node)

        report.top_knowledge = [
            {"id": kl_id, "uses": count}
            for kl_id, count in sorted(kl_usage.items(), key=lambda x: -x[1])[:5]
        ]

        for node in no_kl_nodes:
            report.knowledge_gaps.append(f"No KL entries used at {node}")

        # Gap signals
        all_gaps = set()
        for p in paths:
            all_gaps.update(p.gap_signals)

        # Generate proposals
        if no_kl_nodes:
            report.proposals.append({
                "tier": 2,
                "action": f"Add KL entries for {len(no_kl_nodes)} nodes with zero knowledge coverage",
                "nodes": list(no_kl_nodes)[:10],
            })

        if report.stuck_nodes:
            report.proposals.append({
                "tier": 3,
                "action": f"Investigate {len(report.stuck_nodes)} nodes with flat confidence",
                "nodes": [n["node"] for n in report.stuck_nodes],
            })

        return report
