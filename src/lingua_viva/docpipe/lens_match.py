"""
Student Matcher — match document names against existing roster (R2).

SPEC: dev/SPEC_LV_DOCUMENT_TO_LENS_PIPELINE_2026-08-23.md

Given a student document (report card, progress report, etc.), matches
student names found in the document against the EXISTING lens roster.
NEVER creates new lenses — only updates existing ones.
"""

from __future__ import annotations

import re
from typing import Any

from src.lingua_viva.docpipe.identity import normalize_name, resolve


def _extract_name_from_filename(filename: str) -> str | None:
    """Extract a student name from a filename like 'Abigail_Chang_3_PYP_...'."""
    if not filename:
        return None
    # Strip extension
    stem = re.sub(r"\.[^.]+$", "", filename)
    # Replace underscores/dashes with spaces
    stem = re.sub(r"[_\-]+", " ", stem)
    # Try to find a First Last pattern at the start
    match = re.match(r"([A-ZÀ-Þ][a-zà-ÿ]+)\s+([A-ZÀ-Þ][a-zà-ÿ]+)", stem)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None


def _extract_names_from_header(text: str, max_chars: int = 500) -> list[str]:
    """Extract candidate student names from the document header."""
    header = text[:max_chars]
    # Look for First Last patterns (capitalized bigrams)
    names = []
    for match in re.finditer(r"\b([A-ZÀ-Þ][a-zà-ÿ]+)\s+([A-ZÀ-Þ][a-zà-ÿ]+)\b", header):
        first, last = match.group(1), match.group(2)
        # Skip common non-name bigrams
        blocklist = {
            "learner", "profile", "progress", "report", "school",
            "international", "grade", "term", "semester", "unit",
            "inquiry", "teacher", "student", "learning", "programme",
        }
        if first.lower() not in blocklist and last.lower() not in blocklist:
            names.append(f"{first} {last}")
    return names


def match_document_to_students(
    text: str,
    filename: str,
    roster: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match a student document against existing roster lenses (R2).

    Args:
        text: Full document text content
        filename: Original filename
        roster: List of dicts with at least {student_id, display_name}

    Returns:
        List of matches: [{student_id, display_name, match_source, confidence}]
        For single-student docs, returns one match.
        For multi-student docs, returns all matched.
    """
    if not roster:
        return []

    matches: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 1. Check filename for a student name
    filename_name = _extract_name_from_filename(filename)
    if filename_name:
        result = resolve(filename_name, roster)
        if result["status"] == "exact":
            student_id = result["student_id"]
            display_name = next(
                (r["display_name"] for r in roster if r["student_id"] == student_id),
                filename_name,
            )
            matches.append({
                "student_id": student_id,
                "display_name": display_name,
                "match_source": "filename",
                "confidence": 0.95,
            })
            seen_ids.add(student_id)
        elif result["status"] == "queue":
            # Plausible match from filename — include top candidate
            for candidate in result["candidates"][:1]:
                if candidate["student_id"] not in seen_ids:
                    matches.append({
                        "student_id": candidate["student_id"],
                        "display_name": candidate["display_name"],
                        "match_source": "filename",
                        "confidence": 0.75,
                    })
                    seen_ids.add(candidate["student_id"])

    # 2. Check document header for roster name matches
    header_names = _extract_names_from_header(text)
    for name in header_names:
        result = resolve(name, roster)
        if result["status"] == "exact" and result["student_id"] not in seen_ids:
            student_id = result["student_id"]
            display_name = next(
                (r["display_name"] for r in roster if r["student_id"] == student_id),
                name,
            )
            matches.append({
                "student_id": student_id,
                "display_name": display_name,
                "match_source": "content",
                "confidence": 0.9,
            })
            seen_ids.add(student_id)
        elif result["status"] == "queue":
            for candidate in result["candidates"]:
                if candidate["student_id"] not in seen_ids:
                    matches.append({
                        "student_id": candidate["student_id"],
                        "display_name": candidate["display_name"],
                        "match_source": "content",
                        "confidence": 0.7,
                    })
                    seen_ids.add(candidate["student_id"])

    # 3. For multi-student documents, scan full text for roster names
    if not matches or len(header_names) > 2:
        for entry in roster:
            if entry["student_id"] in seen_ids:
                continue
            display_name = entry.get("display_name", "")
            if not display_name:
                continue
            # Also try reversed name order ("Chang Abigail" ↔ "Abigail Chang")
            parts = display_name.split()
            reversed_name = " ".join(parts[1:]) + " " + parts[0] if len(parts) >= 2 else ""
            # Check if full name or reversed name appears in document
            if display_name in text or (reversed_name and reversed_name in text):
                matches.append({
                    "student_id": entry["student_id"],
                    "display_name": display_name,
                    "match_source": "content",
                    "confidence": 0.85,
                })
                seen_ids.add(entry["student_id"])
            else:
                # Check normalized match (both orders)
                norm = normalize_name(display_name)
                norm_rev = normalize_name(reversed_name) if reversed_name else ""
                norm_text = normalize_name(text)
                if norm and (norm in norm_text or (norm_rev and norm_rev in norm_text)):
                    matches.append({
                        "student_id": entry["student_id"],
                        "display_name": display_name,
                        "match_source": "content",
                        "confidence": 0.7,
                    })
                    seen_ids.add(entry["student_id"])

    # Sort by confidence descending
    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches
