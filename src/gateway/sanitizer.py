"""
3-Layer PII Sanitizer

Nothing leaves the machine without passing through all three layers.
This is governance by architecture, not by convention.

Layer 1: Regex patterns (names, emails, phone, SSN, case numbers, dates of birth)
Layer 2: NER patterns (organization names, person names, locations in context)
Layer 3: Ontology-guided (blocks_external signals from the classification)

The sanitizer returns a clean query safe for external APIs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SanitizationResult:
    """Result of sanitizing a query."""
    original: str
    sanitized: str
    redactions: list[dict] = field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None


# === Layer 1: Regex Patterns ===

PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone_us": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),
    "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
    "dob": re.compile(r'\b(?:born|DOB|date of birth)[:\s]*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b', re.IGNORECASE),
    "ip_address": re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    "case_number": re.compile(r'\b\d{1,2}[-:]\w{2,4}[-:]\d{4,8}\b'),
    "account_number": re.compile(r'\b(?:account|acct)[#:\s]*\d{6,12}\b', re.IGNORECASE),
    "passport": re.compile(r'\b[A-Z]{1,2}\d{6,9}\b'),
    "medical_record": re.compile(r'\b(?:MRN|medical record)[#:\s]*\d{6,12}\b', re.IGNORECASE),
}

# === Layer 2: NER-style patterns (lightweight, no spaCy dependency) ===

# Common titles that precede person names
NAME_PREFIXES = re.compile(
    r'\b(?:Mr|Mrs|Ms|Dr|Prof|Judge|Justice|Attorney|Counsel|Director|CEO|CFO|CTO)\.\s+'
    r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b'
)

# Client/matter references — requires a separator (#, number, no., :) after keyword
CLIENT_REFS = re.compile(
    r'\b(?:client|patient|matter|case|file|docket)\s*(?:#|number|no\.?|:)\s*\S+\b',
    re.IGNORECASE
)

# Addresses (US-style)
ADDRESS = re.compile(
    r'\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+'
    r'(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b',
    re.IGNORECASE
)

# === Layer 3: Ontology-guided signals ===

BLOCK_SIGNALS = {
    "privileged", "confidential", "secret", "nda", "trade secret",
    "proprietary", "internal only", "off the record", "not for sharing",
    "client", "patient", "matter",
}


class Sanitizer:
    """
    3-layer PII sanitizer. Governance by architecture.
    """

    def sanitize(self, query: str, classification: Optional[dict] = None) -> str:
        """
        Run all three layers. Returns sanitized query.
        If classification.blocks_external is True, returns empty string.
        """
        result = self.analyze(query, classification)
        if result.blocked:
            return ""
        return result.sanitized

    def analyze(self, query: str, classification: Optional[dict] = None) -> SanitizationResult:
        """Full analysis with redaction details."""
        result = SanitizationResult(original=query, sanitized=query)

        # Layer 3 first (fastest check — if blocked, stop immediately)
        if classification and classification.get("blocks_external"):
            result.blocked = True
            result.block_reason = "Ontology classification blocks external routing"
            result.sanitized = ""
            return result

        # Check for block signals with word boundary matching
        # Prevents "Linux privileged access" from triggering "privileged" block
        query_lower = query.lower()
        for signal in BLOCK_SIGNALS:
            if ' ' in signal:
                # Multi-word: substring match is fine ("trade secret" is specific enough)
                if signal in query_lower:
                    result.blocked = True
                    result.block_reason = f"Block signal detected: '{signal}'"
                    result.sanitized = ""
                    return result
            else:
                # Single-word: require word boundary to avoid false positives
                import re as _re
                if _re.search(r'\b' + _re.escape(signal) + r'\b', query_lower):
                    result.blocked = True
                    result.block_reason = f"Block signal detected: '{signal}'"
                    result.sanitized = ""
                    return result

        # Layer 1: Regex patterns
        sanitized = query
        for pattern_name, pattern in PATTERNS.items():
            matches = pattern.findall(sanitized)
            for match in matches:
                result.redactions.append({
                    "layer": 1,
                    "type": pattern_name,
                    "value": match,
                })
                sanitized = sanitized.replace(match, f"[REDACTED_{pattern_name.upper()}]")

        # Layer 2: NER patterns
        for pattern, label in [
            (NAME_PREFIXES, "person_name"),
            (CLIENT_REFS, "client_reference"),
            (ADDRESS, "address"),
        ]:
            matches = pattern.findall(sanitized)
            for match in matches:
                result.redactions.append({
                    "layer": 2,
                    "type": label,
                    "value": match,
                })
                sanitized = sanitized.replace(match, f"[REDACTED_{label.upper()}]")

        result.sanitized = sanitized
        return result

    def is_safe_for_external(self, query: str, classification: Optional[dict] = None) -> bool:
        """Quick check: is this query safe to send externally?"""
        result = self.analyze(query, classification)
        return not result.blocked and len(result.redactions) == 0
