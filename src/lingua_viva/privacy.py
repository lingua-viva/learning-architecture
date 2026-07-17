from __future__ import annotations

import re
from pathlib import Path

from doctor.support_loop.privacy import matches_private_path, path_risk_reason, redact_text as _doctor_redact_text

PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone_us": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    "dob": re.compile(r"\b(?:born|DOB|date of birth)[:\s]*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", re.IGNORECASE),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    "case_number": re.compile(r"\b\d{1,2}[-:]\w{2,4}[-:]\d{4,8}\b"),
    "account_number": re.compile(r"\b(?:account|acct)[#:\s]*\d{6,12}\b", re.IGNORECASE),
    "passport": re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
    "medical_record": re.compile(r"\b(?:MRN|medical record)[#:\s]*\d{6,12}\b", re.IGNORECASE),
}

NAME_PREFIXES = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Judge|Justice|Attorney|Counsel|Director|CEO|CFO|CTO)\.\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
)
CLIENT_REFS = re.compile(
    r"\b(?:client|patient|matter|case|file|docket)\s*(?:#|number|no\.?|:)\s*\S+\b",
    re.IGNORECASE,
)
ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b",
    re.IGNORECASE,
)

BLOCK_SIGNALS = {
    "privileged", "confidential", "secret", "nda", "trade secret",
    "proprietary", "internal only", "off the record", "not for sharing",
    "client", "patient", "matter",
}


PRIVATE_RUNTIME_PATTERNS = [
    re.compile(r"(?i)\b(student name|student|learner|child)\s*[:=]\s*[A-Z][A-Za-z' -]{1,60}"),
    re.compile(r"(?i)\b(parent|guardian)\s*[:=]\s*[A-Z][A-Za-z' -]{1,60}"),
    re.compile(r"(?i)\b(grade|class)\s*[:=]\s*[A-Za-z0-9 -]{1,20}\b.*\b(student|learner|child)\b"),
    re.compile(r"(?i)\b(IEP|parent report|progress report|student observation|individual score)\b"),
]


def is_private_path(path: Path | str) -> bool:
    return matches_private_path(path)


def private_path_reason(path: Path | str) -> str | None:
    return path_risk_reason(path)


def contains_private_runtime_data(text: str) -> bool:
    redacted = _doctor_redact_text(text)
    if redacted != text:
        return True
    return any(pattern.search(text) for pattern in PRIVATE_RUNTIME_PATTERNS)


def redact_runtime_text(text: str) -> str:
    redacted = _doctor_redact_text(text)
    for pattern in PRIVATE_RUNTIME_PATTERNS:
        redacted = pattern.sub("[REDACTED_PRIVATE_CONTEXT]", redacted)
    return redacted


def assert_safe_for_external_output(text: str) -> str:
    if contains_private_runtime_data(text):
        raise ValueError("private student or family data cannot leave the local machine")
    return text
