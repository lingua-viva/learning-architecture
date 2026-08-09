"""
Perplexity research gateway — teacher-initiated ONLY, fail-closed.

Zero-egress contract:
  - This module is NEVER imported or invoked from src/pipeline.py. The legacy
    pipeline RESEARCH step remains hard-disabled (needs_external → False);
    external research happens only when a teacher explicitly runs
    `lv research "<query>"` or calls POST /api/library/research.
  - Disabled unless BOTH `PERPLEXITY_API_KEY` is set AND `LV_ALLOW_RESEARCH=1`.
    Anything else refuses with a clear message (ResearchDisabledError).
  - The outbound query passes through the full sanitization stack before any
    byte leaves the machine:
        1. roster scrub  — known student display names (StudentLensStore)
                           replaced with [STUDENT]
        2. privacy.redact_runtime_text — student/parent/PII runtime patterns
        3. injection_guard.redact_injection — machine-directed instructions
        4. sanitizer.app.sanitize — unified PII tokenizer (education context,
           nothing suppressed); a blocked verdict aborts the call
        5. final contains_private_runtime_data assertion (fail-closed)
  - Results are written INTO the library (source="perplexity"), classified
    like any other ingest. They flow nowhere else.
  - `dry_run=True` (or an injected `transport`) makes the gateway fully
    testable offline — the socket guard / hermetic suite never sees a real
    network call.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

PERPLEXITY_ENDPOINT = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"
STUDENT_TOKEN = "[STUDENT]"

DISABLED_HELP = (
    "External research is disabled by default (zero-egress). To enable it, a "
    "teacher must set BOTH the PERPLEXITY_API_KEY environment variable AND "
    "LV_ALLOW_RESEARCH=1."
)

# transport(query) -> (content, citations)
Transport = Callable[[str], tuple[str, list[str]]]


class ResearchDisabledError(RuntimeError):
    """Raised when the gateway is invoked without both enable conditions."""


class ResearchBlockedError(RuntimeError):
    """Raised when the sanitizer blocks the outbound query."""


def is_enabled() -> tuple[bool, str]:
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    flag = os.environ.get("LV_ALLOW_RESEARCH", "").strip()
    if not key and flag != "1":
        return False, f"research disabled: PERPLEXITY_API_KEY not set and LV_ALLOW_RESEARCH!=1. {DISABLED_HELP}"
    if not key:
        return False, f"research disabled: PERPLEXITY_API_KEY not set. {DISABLED_HELP}"
    if flag != "1":
        return False, f"research disabled: LV_ALLOW_RESEARCH!=1. {DISABLED_HELP}"
    return True, "enabled"


# ── sanitization stack ──────────────────────────────────────────────────────

def _known_student_names() -> list[str]:
    """Display names from the local student lens roster (best-effort; an
    empty/absent roster is not an error)."""
    names: list[str] = []
    try:
        from src.education.student_lens import StudentLensStore

        store = StudentLensStore()
        try:
            for lens in store.list_lenses():
                display = str(lens.get("display_name") or "").strip()
                if display:
                    names.append(display)
        finally:
            store.close()
    except Exception:
        pass
    return names


def _scrub_roster_names(text: str) -> tuple[str, list[str]]:
    import re

    scrubbed: list[str] = []
    for name in sorted(_known_student_names(), key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        # Also scrub each name token (>=3 chars) so "Nora Rossi" in the roster
        # covers a query that says just "Nora".
        if pattern.search(text):
            text = pattern.sub(STUDENT_TOKEN, text)
            scrubbed.append(name)
        for token in name.split():
            if len(token) < 3:
                continue
            token_re = re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)
            if token_re.search(text):
                text = token_re.sub(STUDENT_TOKEN, text)
                if name not in scrubbed:
                    scrubbed.append(name)
    return text, scrubbed


def sanitize_outbound_query(query: str) -> dict[str, Any]:
    """Run the full sanitization stack. Returns {"text", "scrubbed_students",
    "redactions"}. Raises ResearchBlockedError on a blocked verdict."""
    from src.lingua_viva.injection_guard import redact_injection
    from src.lingua_viva.privacy import contains_private_runtime_data, redact_runtime_text

    text, scrubbed = _scrub_roster_names(query)
    stack_redactions: list[dict] = []
    before_privacy = text
    text = redact_runtime_text(text)
    if text != before_privacy:
        stack_redactions.append({"layer": "privacy", "type": "runtime_redaction"})
    text, injection_redactions = redact_injection(text)
    stack_redactions.extend(injection_redactions)

    # Unified sanitizer (education context: nothing suppressed). Direct import
    # is the sanctioned dev-mode path of sanitizer/client.py — no HTTP hop,
    # so the zero-egress suite never sees a socket for a localhost check.
    from sanitizer.app import sanitize

    result = sanitize(text, context="education", block_signals=[], namespace="lingua-viva")
    if result.get("blocked") or not result.get("ok", False):
        raise ResearchBlockedError(f"sanitizer blocked outbound query: {result.get('reason')}")
    text = result.get("text", "")

    if contains_private_runtime_data(text):
        raise ResearchBlockedError("outbound query still contains private runtime data after sanitization")

    return {
        "text": text,
        "scrubbed_students": scrubbed,
        "redactions": list(result.get("redactions", [])) + stack_redactions,
    }


# ── transport ───────────────────────────────────────────────────────────────

def _http_transport(query: str) -> tuple[str, list[str]]:
    """Real network call. Reached ONLY after is_enabled() passed and the
    query was sanitized."""
    from urllib.request import Request, urlopen

    payload = json.dumps({
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a research assistant for an IB primary-school teacher. Cite sources.",
            },
            {"role": "user", "content": query},
        ],
    }).encode("utf-8")
    req = Request(
        PERPLEXITY_ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('PERPLEXITY_API_KEY', '').strip()}",
        },
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    content = ""
    choices = data.get("choices") or []
    if choices:
        content = str(((choices[0] or {}).get("message") or {}).get("content") or "")
    citations = [str(c) for c in (data.get("citations") or [])]
    return content, citations


def _mock_transport(query: str) -> tuple[str, list[str]]:
    return (
        f"[dry-run] No network call was made. The sanitized query that WOULD "
        f"have been sent: {query}",
        [],
    )


# ── entry point ─────────────────────────────────────────────────────────────

def research(
    query: str,
    *,
    dry_run: bool = False,
    transport: Optional[Transport] = None,
) -> dict[str, Any]:
    """Teacher-initiated research. Fail-closed gate → sanitize → (dry-run |
    transport) → store result in the library.

    Raises ResearchDisabledError unless PERPLEXITY_API_KEY and
    LV_ALLOW_RESEARCH=1 are BOTH set — including in dry-run mode, so the gate
    itself is what tests exercise, not a bypass of it.
    """
    if not query or not query.strip():
        raise ValueError("empty research query")
    enabled, reason = is_enabled()
    if not enabled:
        raise ResearchDisabledError(reason)

    sanitized = sanitize_outbound_query(query.strip())
    outbound = sanitized["text"]

    if dry_run:
        content, citations = _mock_transport(outbound)
    else:
        content, citations = (transport or _http_transport)(outbound)

    from src.lingua_viva import library

    doc = library.add_research_result(outbound, content, citations=citations)
    return {
        "status": "ok",
        "dry_run": bool(dry_run),
        "query_sent": outbound,
        "scrubbed_students": sanitized["scrubbed_students"],
        "redaction_count": len(sanitized["redactions"]),
        "doc": doc,
    }
