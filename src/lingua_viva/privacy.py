from __future__ import annotations

import re
from pathlib import Path

from doctor.support_loop.privacy import matches_private_path, path_risk_reason, redact_text as _doctor_redact_text


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
