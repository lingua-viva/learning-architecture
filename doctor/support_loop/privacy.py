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


EXCLUDED_DIR_PARTS = {
    ".venv", "venv", "site-packages", "node_modules", ".git",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
}


# macOS resolves /tmp, /var and /etc to a SYSTEM directory literally named
# "private". That prefix belongs to the OS, not the teacher, so it must not
# trigger the "private*" rules below — otherwise every temp file the app
# writes while processing an upload is refused as student data. The prefix is
# stripped before matching; the remainder of the path and the filename are
# still checked in full, so a real IEP_*.pdf sitting in a temp directory is
# still caught. Same class of false positive that is_student_data_zone() in
# src/lingua_viva/filemap.py already guards against.
_MACOS_SYSTEM_PRIVATE_PREFIXES = ("/private/var", "/private/tmp", "/private/etc")


def matches_private_path(path: Path | str) -> bool:
    normalized = str(path).replace("\\", "/")
    for prefix in _MACOS_SYSTEM_PRIVATE_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len("/private"):]
            break
    # Never flag third-party/vendored directories — they contain files
    # named "private" that are not student data (e.g. numpy test_private.py).
    parts = set(Path(normalized).parts)
    if parts & EXCLUDED_DIR_PARTS:
        return False
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
