"""Mechanical grounding verification for extractions (T3).

The support rule (SPEC_T3_EXTRACTION_2026-08-04 §5): a claim is supported by
its cited span iff every content token of the claim appears as a whole token
in the cited text. Exact-substring is too strict (spans cite "Nora" without
the surname), semantic similarity is circular (the model would grade itself).
Whole-token overlap is deterministic, mechanical, and explainable to an
auditor in one sentence.

A claim that fails is DROPPED, never demoted — unsupported is not
"less likely true", it does not ship. (`grounding.py`'s lens-level verify
remains T7's file; this module verifies extractions.)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocGroundingReport:
    ok: bool
    checked: int = 0
    dropped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(ch)
    )


def name_tokens(name: str) -> list[str]:
    """Content tokens of a display name: accent-folded, lowercase, >2 chars."""
    return [token for token in re.findall(r"[a-z0-9]+", _fold(name)) if len(token) > 2]


def span_contains_any_token(span_text: str, tokens: list[str]) -> bool:
    folded = _fold(span_text)
    return any(re.search(rf"\b{re.escape(token)}\b", folded) for token in tokens)


def verify_extraction(data: dict[str, Any], *, apply_drops: bool = False) -> DocGroundingReport:
    """Verify an extraction dict in place.

    1. Span integrity: unique ids, valid offsets, text == slice (byte-exact).
    2. Reference integrity: every cited span_id exists.
    3. Support: every students_detected entry's name tokens all appear in the
       union of its cited spans, and each cited span contains >= 1 name token.

    apply_drops=True removes failing students_detected entries and dangling
    section references (recorded in .dropped); span-integrity violations are
    always hard errors (ok=False) — a broken span table means the offsets the
    whole pipeline depends on cannot be trusted.
    """
    report = DocGroundingReport(ok=True)
    text = str(data.get("normalized_text") or "")
    spans = data.get("spans") or []
    span_by_id: dict[str, dict[str, Any]] = {}

    seen_ids: set[str] = set()
    for span in spans:
        report.checked += 1
        span_id = str(span.get("span_id") or "")
        start = span.get("char_start")
        end = span.get("char_end")
        if not span_id or span_id in seen_ids:
            report.errors.append(f"span_integrity:{span_id or '?'}:missing or duplicate span_id")
            continue
        seen_ids.add(span_id)
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(text)):
            report.errors.append(f"span_integrity:{span_id}:offsets out of range")
            continue
        if str(span.get("text")) != text[start:end]:
            report.errors.append(f"span_integrity:{span_id}:text does not match normalized_text slice")
            continue
        span_by_id[span_id] = span

    structure = data.get("structure") or {}

    kept_students = []
    for student in structure.get("students_detected") or []:
        report.checked += 1
        display_name = str(student.get("display_name") or "")
        cited = [str(sid) for sid in (student.get("span_ids") or [])]
        tokens = name_tokens(display_name)
        reason = None
        if not display_name or not tokens:
            reason = "empty display_name"
        elif not cited:
            reason = "no cited spans"
        elif any(sid not in span_by_id for sid in cited):
            missing = next(sid for sid in cited if sid not in span_by_id)
            reason = f"cited span {missing} does not exist"
        else:
            union = " ".join(str(span_by_id[sid]["text"]) for sid in cited)
            if not all(span_contains_any_token(union, [token]) for token in tokens):
                reason = "name tokens not all present in cited spans"
            elif not all(span_contains_any_token(str(span_by_id[sid]["text"]), tokens) for sid in cited):
                reason = "a cited span contains no name token"
        if reason is None:
            kept_students.append(student)
        else:
            report.dropped.append(f"grounding_dropped:student:{display_name or '?'}:{reason}")
    if apply_drops:
        structure["students_detected"] = kept_students
    elif len(kept_students) != len(structure.get("students_detected") or []):
        report.errors.extend(report.dropped)

    kept_sections = []
    for section in structure.get("sections") or []:
        report.checked += 1
        cited = [str(sid) for sid in (section.get("span_ids") or [])]
        dangling = [sid for sid in cited if sid not in span_by_id]
        if dangling:
            report.dropped.append(
                f"grounding_dropped:section:{section.get('section_id') or '?'}:cites missing span {dangling[0]}"
            )
            if not apply_drops:
                report.errors.append(report.dropped[-1])
            continue
        kept_sections.append(section)
    if apply_drops:
        structure["sections"] = kept_sections

    report.ok = not report.errors
    return report
