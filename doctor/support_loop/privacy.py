from __future__ import annotations

import fnmatch
import re
from pathlib import Path


PRIVATE_PATH_PATTERNS = [
    "**/student_lens*.db",
    "**/still_i_rise.db",
    "**/observations*",
    "**/parent_reports*",
    "**/progress_reports*",
    "**/IEP*",
    "student_lens*.db",
    "still_i_rise.db",
    "observations*",
    "parent_reports*",
    "progress_reports*",
    "IEP*",
    "**/private*",
    "private*",
    "**/*.docx",
    "*.docx",
]

REDACTION_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"hf_[A-Za-z0-9]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"), r"\1=[REDACTED_SECRET]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"(?i)\b(IEP|parent report|progress report|student observation)\b"), "[REDACTED_PRIVATE_CONTEXT]"),
]


def matches_private_path(path: Path | str) -> bool:
    normalized = str(path).replace("\\", "/")
    name = Path(normalized).name
    return any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern) for pattern in PRIVATE_PATH_PATTERNS)


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def path_risk_reason(path: Path | str) -> str | None:
    normalized = str(path).replace("\\", "/")
    if matches_private_path(normalized):
        return "path matches private support-bundle exclusion rule"
    return None
