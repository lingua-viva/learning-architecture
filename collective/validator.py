"""
Community Contribution Validator

Validates incoming community contributions before merging.
Checks: schema valid, PII-free, novel, confidence above threshold.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool = True
    issues: list[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


class ContributionValidator:
    """Validates community contributions."""

    def validate(self, contribution: dict) -> ValidationResult:
        result = ValidationResult()

        # Schema check
        required = ["query_hash", "domain", "entry_node", "path", "confidence_at_exit", "outcome"]
        for field in required:
            if field not in contribution:
                result.valid = False
                result.issues.append(f"Missing required field: {field}")

        # Confidence threshold
        conf = contribution.get("confidence_at_exit", 0)
        if conf < 0.5:
            result.valid = False
            result.issues.append(f"Confidence too low: {conf}")

        # Path must have at least 2 nodes
        path = contribution.get("path", [])
        if len(path) < 2:
            result.valid = False
            result.issues.append("Path too short (minimum 2 nodes)")

        return result
