"""Stakeholder sharing matrix — who may see what, declaratively.

W2 slice (2026-08-09). The matrix is data (a module-level constant kept
deliberately small and readable) so Claudia can review every cell without
reading code. Views:

  * ``full``    — the stakeholder may see the full record
  * ``summary`` — only an explicit summary (never a truncation of the
                  full text — truncation leaks; absence of a prepared
                  summary means the content is withheld)
  * ``none``    — nothing through this system

Fail-closed rules baked in:
  * Unknown info_type -> "none". Unknown role -> "none".
  * The safeguarding row is "none" for every role below coordinator.
  * Parents NEVER receive safeguarding material via this system — that
    is a human process led by the school's designated safeguarding
    staff, not a software payload. The row is data, but
    ``allowed_view`` also enforces this pair in code so a mis-edited
    matrix cannot fail open.
"""

from __future__ import annotations

from typing import Any

FULL = "full"
SUMMARY = "summary"
NONE = "none"

VALID_VIEWS = (FULL, SUMMARY, NONE)

ROLES = ("teacher", "co_teacher", "coordinator", "admin", "parent")

# info_type -> role -> view. Reviewable data; keep alphabetical by row.
SHARING_MATRIX: dict[str, dict[str, str]] = {
    "academic_progress": {
        "teacher": FULL,
        "co_teacher": FULL,
        "coordinator": FULL,
        "admin": FULL,
        "parent": SUMMARY,  # parents get progress summaries, not raw notes
    },
    "attendance": {
        "teacher": FULL,
        "co_teacher": FULL,
        "coordinator": FULL,
        "admin": FULL,
        "parent": SUMMARY,
    },
    "behavior": {
        "teacher": FULL,
        "co_teacher": FULL,
        "coordinator": FULL,
        "admin": SUMMARY,  # admin oversight needs the shape, not the narrative
        "parent": SUMMARY,
    },
    "logistics": {
        "teacher": FULL,
        "co_teacher": FULL,
        "coordinator": FULL,
        "admin": FULL,
        "parent": SUMMARY,
    },
    "medical": {
        "teacher": SUMMARY,   # need-to-know: what affects the classroom
        "co_teacher": SUMMARY,
        "coordinator": FULL,
        "admin": FULL,
        "parent": SUMMARY,    # the family's own copy lives with the family/school office, not this app
    },
    "safeguarding": {
        "teacher": NONE,      # below coordinator: none, per fail-closed policy
        "co_teacher": NONE,
        "coordinator": FULL,
        "admin": FULL,
        "parent": NONE,       # NEVER via this system — human process only
    },
    "wellbeing": {
        "teacher": FULL,
        "co_teacher": SUMMARY,
        "coordinator": FULL,
        "admin": SUMMARY,
        "parent": NONE,       # wellbeing concerns reach parents through conversation
    },
}


def allowed_view(info_type: str, role: str) -> str:
    """Look up the allowed view. Fail closed on anything unknown, and
    hard-enforce the safeguarding floor even if the matrix data were
    mis-edited."""
    info = str(info_type or "").strip().lower()
    who = str(role or "").strip().lower()
    view = SHARING_MATRIX.get(info, {}).get(who, NONE)
    if view not in VALID_VIEWS:
        return NONE
    if info == "safeguarding":
        # Code-level floor independent of the data: only coordinator and
        # admin may ever see safeguarding through this system, and
        # parents never do.
        if who not in ("coordinator", "admin"):
            return NONE
    return view


def _summarize(value: Any) -> dict:
    """Summary view: only an explicitly prepared summary passes. No
    truncation of full content — a prefix of a sensitive note is still
    the sensitive note."""
    if isinstance(value, dict) and "summary" in value:
        return {"view": SUMMARY, "summary": value["summary"]}
    return {
        "view": SUMMARY,
        "summary": None,
        "note": "No prepared summary — details withheld (fail closed).",
    }


def filter_payload(payload: dict, role: str) -> dict:
    """Apply the matrix to a payload keyed by info_type.

    Keys that are not known info_types are DROPPED (fail closed) — an
    unclassified field cannot be shared because we cannot know its row.
    """
    filtered: dict[str, Any] = {}
    for info_type, value in dict(payload or {}).items():
        view = allowed_view(info_type, role)
        if view == FULL:
            filtered[info_type] = value
        elif view == SUMMARY:
            filtered[info_type] = _summarize(value)
        # NONE (and unknown keys, which resolve to NONE): dropped.
    return filtered
