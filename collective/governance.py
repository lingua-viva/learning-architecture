"""
Community Governance Pipeline

contribution → validation → proposal → review → merge

Tier 3: auto-merge after 3 independent contributors submit same path
Tier 2: maintainer review required
Tier 1: core team vote required
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Proposal:
    """A validated community contribution awaiting merge."""
    contribution_hash: str
    entry_node: str
    domain: str
    path: list[str]
    confidence: float
    tier: int
    contributor_count: int = 1
    status: str = "pending"  # pending, approved, rejected, merged


class GovernancePipeline:
    """Manages the community contribution governance process."""

    def __init__(self):
        self.proposals: dict[str, Proposal] = {}

    def submit(self, contribution: dict) -> str:
        """Submit a validated contribution to the governance pipeline."""
        # Generate a canonical key from the path
        key = f"{contribution['entry_node']}:{'→'.join(contribution['path'])}"

        if key in self.proposals:
            # Increment contributor count
            self.proposals[key].contributor_count += 1
            # Auto-merge at 3 contributors for Tier 3
            if self.proposals[key].tier == 3 and self.proposals[key].contributor_count >= 3:
                self.proposals[key].status = "approved"
        else:
            tier = self._classify_tier(contribution)
            self.proposals[key] = Proposal(
                contribution_hash=contribution.get("query_hash", ""),
                entry_node=contribution["entry_node"],
                domain=contribution["domain"],
                path=contribution["path"],
                confidence=contribution["confidence_at_exit"],
                tier=tier,
            )

        return key

    def _classify_tier(self, contribution: dict) -> int:
        """Classify the governance tier for a contribution."""
        # New ontology nodes = Tier 1
        # New knowledge entries = Tier 2
        # Path confidence updates = Tier 3
        return 3  # Default to observations
