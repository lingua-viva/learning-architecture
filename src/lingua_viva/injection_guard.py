"""
Injection Guard — high-precision prompt-injection redaction for untrusted document text.

Why this exists (Track A item 2, REPORT_LV_EXTERNAL_FEEDBACK_TRANSFER_2026-07-25.md):
teacher-uploaded documents feed the extraction engine, student lenses, and parent
reports. A document carrying prompt-injection text ("ignore previous instructions...")
would steer the local model when it generates content the teacher trusts about her
students. Mission Canvas added pattern-based injection detection to its entry gate
after the c2a9bf5 fork point; Lingua Viva never inherited it.

Why this is NOT a copy of MC's pattern list: MC's patterns are tuned for a
legal/compliance threat surface. K-5 education documents legitimately contain
"You are now a detective!", "Pretend you are a pirate", "Act as a reporter" —
role-play framing is a *teaching technique*, not an attack. Copying MC's
`you are now (a|an|in)` / `pretend you are` / `act as` patterns blind would
false-positive on real classroom material and silently destroy legitimate
content. Only unambiguous machine-directed injection phrasing is matched here.

Behavior contract (teacher-first, deliberately NOT block-and-reject):
  - Matched spans are replaced with [REDACTED_INJECTION] and audit-logged in the
    returned redaction list. The document is never rejected — a teacher on a
    Monday morning must never lose a document to a false positive with no
    explanation. Redact-and-flag, same philosophy as DocumentParser's
    needs_review handling of Layer-3 signal words.
  - Queries the teacher types herself are NOT run through this guard at the app
    boundary — in a local-only app the operator's own words are trusted input.
    The guard runs on *document* text (ingestion + extraction chunking) and on
    the external-egress sanitization seam (GatewayInterface.sanitize_query),
    which is the boundary where untrusted content could leave or loop back.
"""

from __future__ import annotations

import re

# Unambiguous machine-directed injection phrasing ONLY. Every pattern here
# should be something with no plausible K-5 classroom reading. Deliberately
# excluded (kid-content false positives): "you are now a...", "pretend you
# are...", "act as...", "forget everything".
INJECTION_PATTERNS: dict[str, re.Pattern] = {
    "ignore_previous_instructions": re.compile(
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE
    ),
    "disregard_instructions": re.compile(
        r"disregard\s+(?:all\s+)?(?:prior|previous|above)\s+(?:instructions|context|rules)",
        re.IGNORECASE,
    ),
    "reveal_system_prompt": re.compile(
        r"reveal\s+(?:the\s+)?(?:system|developer|hidden)\s+(?:prompt|message|instructions)",
        re.IGNORECASE,
    ),
    "system_prompt_marker": re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    "system_tag": re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    "inst_tag": re.compile(r"\[\s*/?\s*INST\s*\]"),
    "new_instructions_marker": re.compile(r"\bnew\s+instructions?\s*:", re.IGNORECASE),
    "override_rules": re.compile(
        r"override\s+(?:your|all|the)\s+(?:rules|instructions|guidelines|safety)",
        re.IGNORECASE,
    ),
}

REDACTION_TOKEN = "[REDACTED_INJECTION]"


def detect_injection(text: str) -> list[str]:
    """Return the names of injection patterns present in text (empty = clean)."""
    if not text:
        return []
    return [name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text)]


def redact_injection(text: str) -> tuple[str, list[dict]]:
    """Replace injection spans with REDACTION_TOKEN.

    Returns (sanitized_text, redactions) where each redaction is
    {"layer": "injection_guard", "type": <pattern name>, "value": <matched text>}
    — same audit shape as DocumentParser's PII redaction entries, so the two
    lists concatenate cleanly into ChunkRecord.redactions.
    """
    if not text:
        return text, []
    redactions: list[dict] = []
    sanitized = text
    for name, pattern in INJECTION_PATTERNS.items():
        for match in pattern.findall(sanitized):
            redactions.append({"layer": "injection_guard", "type": name, "value": match})
            sanitized = sanitized.replace(match, REDACTION_TOKEN)
    return sanitized, redactions
