"""
Orchestrator Agent

Coordinates multi-agent work on complex queries. When a query spans
multiple intents or domains, the orchestrator:
1. Fans out to relevant intent agents in parallel
2. Collects results via HandoffPackets
3. Runs convergence to detect contradictions, overlaps, and gaps
4. Merges into a single coherent response

This is the relay model: parallel exploration, serial synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memory.handoff import HandoffPacket


@dataclass
class OrchestratorResult:
    """Result of orchestrated multi-agent execution."""
    content: str
    confidence: float
    agents_used: list[str]
    handoffs: list[dict] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)


class Orchestrator:
    """
    Coordinates multi-agent work. The convergence engine.

    When a complex query hits multiple ontology nodes, the orchestrator
    determines which agents handle which parts and merges the results.
    """

    INTENT = "ORCHESTRATE"

    async def execute(
        self,
        query: str,
        context: dict,
        co_occurring_nodes: list[str],
    ) -> OrchestratorResult:
        """
        Execute orchestrated multi-agent query.
        Fans out to intent agents, collects results, converges.
        """
        agents_needed = self._determine_agents(co_occurring_nodes, context)

        # In production: parallel fan-out to each agent
        # For now: structured placeholder
        return OrchestratorResult(
            content=f"[Orchestrator: would fan out to {', '.join(agents_needed)}]",
            confidence=0.7,
            agents_used=agents_needed,
        )

    def _determine_agents(self, nodes: list[str], context: dict) -> list[str]:
        """Map ontology nodes to intent agents."""
        agents = set()
        intent_map = {
            "PROTECT": "protect",
            "RESEARCH": "research",
            "DECIDE": "decide",
            "CREATE": "create",
            "DIAGNOSE": "diagnose",
            "REFLECT": "reflect",
        }
        primary_intent = context.get("default_intent", "RESEARCH")
        agents.add(intent_map.get(primary_intent, "research"))

        # Add agents for co-occurring nodes based on their default intents
        for node_id in nodes:
            # Would look up the node's default_intent from ontology
            # For now, add research as default
            agents.add("research")

        return sorted(agents)
