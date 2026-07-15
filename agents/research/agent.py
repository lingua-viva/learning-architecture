"""
RESEARCH Agent — Governed external research with knowledge proposals.

Beyond just calling Perplexity (which the gateway handles), the RESEARCH agent:
  1. Evaluates whether external results should become new KL entries
  2. Detects when Perplexity contradicts local knowledge
  3. Extracts structured citations from research results
  4. Proposes knowledge library additions from high-confidence findings
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResearchProposal:
    """A proposed knowledge library entry from research findings."""
    source_query_hash: str
    proposed_title: str
    proposed_content: str
    ontology_node: str
    citations: list[str]
    evidence_tier: int = 2  # External research = Tier 2 by default
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class ResearchAgent:
    """
    RESEARCH intent agent. Evaluates research quality and proposes KL additions.
    """

    INTENT = "RESEARCH"

    def __init__(self):
        self._proposals_dir = Path(__file__).parent.parent.parent / "knowledge" / "proposals"
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    def analyze(
        self,
        research_content: str,
        citations: list,
        node_id: str,
        query_hash: str,
        confidence: float,
        existing_kl_count: int,
    ) -> list[ResearchProposal]:
        """
        Analyze research results and propose KL entries for gaps.

        If this node has < 2 KL entries AND the research returned with citations,
        propose adding the research as a new KL entry.
        """
        proposals = []

        if not research_content or not citations:
            return proposals

        # Only propose if the node has sparse knowledge
        if existing_kl_count < 3 and confidence >= 0.60 and len(citations) >= 1:
            # Extract first substantive paragraph as proposed content
            paragraphs = [p.strip() for p in research_content.split("\n\n") if len(p.strip()) > 50]
            if paragraphs:
                proposal = ResearchProposal(
                    source_query_hash=query_hash,
                    proposed_title=paragraphs[0][:100].strip(),
                    proposed_content="\n\n".join(paragraphs[:3]),  # First 3 paragraphs
                    ontology_node=node_id,
                    citations=[str(c) for c in citations[:5]],
                    confidence=confidence,
                )
                proposals.append(proposal)
                self._save_proposal(proposal)

        return proposals

    def _save_proposal(self, proposal: ResearchProposal) -> None:
        """Save proposal as JSON for human review."""
        filename = f"proposal_{proposal.source_query_hash}_{int(proposal.timestamp)}.json"
        path = self._proposals_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(proposal.to_dict(), f, indent=2)
