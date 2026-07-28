"""
Shadow suggester (spec SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS §8).

Counts the week's UNMATCHED ops traffic against *disabled* packs'
vocabularies and, at ≥ threshold would-have-matched messages, produces a
panel suggestion ("I found 18 transport-related updates this week —
enable the Bus / Transport pack?"). Suggestion ONLY: the admin enables
the pack through the normal Bot Setup checklist + Save + corpus run.
Nothing here ever changes classification or writes anything.

What counts as unmatched (v1 routing reality):
  - DM traffic no vocabulary matched → category `other`.
  - Ops-channel traffic no vocabulary matched → the POSITIONAL
    `announcement` default bucket (channel_default carries no vocabulary
    by design, so every announcement record is by definition unmatched).

Privacy: the suggestion payload carries pack ids/names and counts only —
never record text, never identifiers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.education import ops_packs

SUGGESTION_THRESHOLD = 3
WINDOW_DAYS = 7

# The categories that mean "no vocabulary matched" (see module docstring).
UNMATCHED_CATEGORIES = ("other", "announcement")


def window_start_iso(*, now: Optional[datetime] = None) -> str:
    reference = now or datetime.now(timezone.utc)
    return (reference - timedelta(days=WINDOW_DAYS)).isoformat()


def shadow_suggestions(
    records,
    *,
    rule_set=None,
    packs: Optional[dict] = None,
    threshold: int = SUGGESTION_THRESHOLD,
) -> list:
    """Would-have-matched counts per DISABLED pack over `records`
    (already window-filtered unmatched traffic). Enabled packs are never
    suggested; below-threshold counts stay silent."""
    rules = rule_set if rule_set is not None else ops_packs.current_rule_set()
    catalog = packs if packs is not None else ops_packs.load_packs()
    enabled = set(rules.enabled_pack_ids)

    suggestions = []
    for pack in sorted(catalog.values(), key=lambda p: p.id):
        if pack.id in enabled:
            continue
        count = 0
        for record in records:
            text = record.text_clean or record.text_raw
            if text and any(
                pattern.search(text)
                for entry in pack.categories
                for pattern in entry.patterns
            ):
                count += 1
        if count >= threshold:
            suggestions.append(
                {
                    "pack_id": pack.id,
                    "pack_name": pack.name,
                    "count": count,
                    "message": (
                        f"I found {count} messages this week that the "
                        f"{pack.name} pack would have filed. Enable it below "
                        "and run the corpus test?"
                    ),
                }
            )
    return suggestions
