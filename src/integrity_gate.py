"""
Integrity Gate — Output Validation

Sits between REASON and SYNTHESIZE. Scans model output for:
  - RIU-XXX patterns → verifies they exist in the ontology
  - KL-XXX / LIB-XXX patterns → verifies they exist in knowledge store
  - Hallucinated citations → flags unverifiable references
  - ASSUMPTION labels → logs as gap signals

The model can hallucinate. The gate catches it before the user sees it.
Per Heppner v. Alyeska (SDNY 2026): fabricated citations = professional negligence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Patterns to detect in model output
RIU_PATTERN = re.compile(r'\bRIU-\d{3,4}\b')
KL_PATTERN = re.compile(r'\b(?:KL|LIB)-[A-Z]*-?\d{3,4}\b')
ASSUMPTION_PATTERN = re.compile(r'\b(?:ASSUMPTION|I assume|assuming that|I believe)\b', re.IGNORECASE)


@dataclass
class GateResult:
    """Result of scanning model output through the integrity gate."""
    passed: bool = True
    hallucinated_rius: list[str] = field(default_factory=list)
    hallucinated_kl: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cleaned_content: str = ""


class IntegrityGate:
    """
    Validates model output before it reaches the user.

    The gate does NOT modify content for correctness — that would be
    a black box. It FLAGS issues transparently. The user sees what
    the model said PLUS what the gate found wrong.
    """

    def __init__(self, ontology_nodes: set[str], knowledge_ids: set[str]):
        self._valid_rius = ontology_nodes
        self._valid_kl = knowledge_ids

    def check(self, content: str) -> GateResult:
        result = GateResult(cleaned_content=content)

        # Check for hallucinated RIU references
        for match in RIU_PATTERN.findall(content):
            if match not in self._valid_rius:
                result.hallucinated_rius.append(match)
                result.passed = False

        # Check for hallucinated knowledge references
        for match in KL_PATTERN.findall(content):
            if match not in self._valid_kl:
                result.hallucinated_kl.append(match)
                result.passed = False

        # Check for assumptions
        for match in ASSUMPTION_PATTERN.finditer(content):
            # Get the sentence containing the assumption
            start = content.rfind('.', 0, match.start()) + 1
            end = content.find('.', match.end())
            if end == -1:
                end = min(match.end() + 100, len(content))
            sentence = content[start:end].strip()
            if sentence:
                result.assumptions.append(sentence)

        # Build warnings
        if result.hallucinated_rius:
            result.warnings.append(
                f"Model referenced {len(result.hallucinated_rius)} non-existent RIU(s): "
                f"{', '.join(result.hallucinated_rius)}"
            )
        if result.hallucinated_kl:
            result.warnings.append(
                f"Model cited {len(result.hallucinated_kl)} non-existent knowledge entry(s): "
                f"{', '.join(result.hallucinated_kl)}"
            )
        if result.assumptions:
            result.warnings.append(
                f"Model made {len(result.assumptions)} assumption(s) — verify before acting"
            )

        return result
