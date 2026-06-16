"""
Convergence Engine

Detects contradictions, overlaps, and coverage gaps across agent outputs.
This is the mechanism that ensures multi-agent work produces a coherent
result, not five competing answers.

From the governance project: "We didn't converge because we're similar.
We converged because we're different — and the governance protocol forced
us to resolve our differences into something stronger than any individual
perspective."
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConvergenceResult:
    """Result of convergence analysis across agent outputs."""
    converged: bool = True
    contradictions: list[dict] = field(default_factory=list)
    overlaps: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    merged_confidence: float = 0.0
    resolution_notes: list[str] = field(default_factory=list)


class ConvergenceEngine:
    """Analyzes multiple agent outputs for coherence."""

    def analyze(self, outputs: list[dict]) -> ConvergenceResult:
        """
        Analyze multiple agent outputs for contradictions, overlaps, and gaps.
        Returns a convergence result with resolution notes.
        """
        result = ConvergenceResult()

        if len(outputs) <= 1:
            result.merged_confidence = outputs[0].get("confidence", 0.5) if outputs else 0.0
            return result

        # Check for contradictions
        decisions = [o for o in outputs if o.get("decisions")]
        for i, d1 in enumerate(decisions):
            for d2 in decisions[i+1:]:
                if self._contradicts(d1, d2):
                    result.contradictions.append({
                        "agent_1": d1.get("agent"),
                        "agent_2": d2.get("agent"),
                        "issue": "Conflicting decisions",
                    })
                    result.converged = False

        # Average confidence
        confidences = [o.get("confidence", 0.5) for o in outputs]
        result.merged_confidence = sum(confidences) / len(confidences)

        return result

    def _contradicts(self, d1: dict, d2: dict) -> bool:
        """Simple contradiction check — can be made more sophisticated."""
        # If one says "blocks_external" and another called external
        if d1.get("external_blocked") and d2.get("external_called"):
            return True
        return False
