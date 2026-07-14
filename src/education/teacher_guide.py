"""
Teacher Guide Generator — Product B output

Takes a generated ContentPack (content_differentiator.py) plus a class
roster (student lens dicts + tier assignments) and produces a structured,
printable guide: how to distribute the three tiers, how to facilitate
cross-level collaboration, and trauma-aware facilitation notes.

Output format: plain Markdown text. This satisfies the "downloadable /
printable, offline classroom use" acceptance criterion without adding a
PDF-generation dependency for the Friday vertical slice — any device can
save/print a .md or plain-text file with no extra tooling. A PDF export
layer can wrap this text later without changing the generation logic.

Trauma-aware notes never name a specific reason a student is flagged
(no "this student is a refugee" or "this student experienced X") — per
the trauma-informed research in content_differentiator.py's docstring
(avoid outing/labeling), notes are phrased as general facilitation
instructions the teacher can act on without the note itself becoming a
label visible to anyone else who sees the guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.education.content_differentiator import ContentPack, TIERS

TIER_LABELS = {
    "foundational": "Foundational",
    "on_track": "On-Track",
    "extended": "Extended",
}

TIER_DISTRIBUTION_TIPS = {
    "foundational": (
        "Seat foundational-tier students where they can see visual supports "
        "clearly. Introduce the task orally first, then hand out materials. "
        "Check in after the first 2-3 minutes to confirm the task is understood."
    ),
    "on_track": (
        "On-track students can generally start independently after the "
        "whole-class introduction. Circulate to support pairs during "
        "discussion tasks."
    ),
    "extended": (
        "Extended-tier students can begin as soon as materials are "
        "distributed. Consider letting them choose their own research "
        "angle within the task rather than assigning one."
    ),
}


@dataclass
class TeacherGuide:
    lesson_title: str
    tier_counts: dict
    distribution_instructions: dict
    cross_level_collaboration: list[str]
    trauma_aware_notes: list[str]
    pack_id: str

    def to_markdown(self) -> str:
        lines = [
            f"# Teacher Guide: {self.lesson_title}",
            "",
            f"Content pack: `{self.pack_id}`",
            "",
            "## Class Breakdown",
            "",
        ]
        for tier in TIERS:
            count = self.tier_counts.get(tier, 0)
            lines.append(f"- **{TIER_LABELS[tier]}**: {count} student(s)")
        lines.append("")
        lines.append("## Distribution Instructions")
        lines.append("")
        for tier in TIERS:
            lines.append(f"### {TIER_LABELS[tier]}")
            lines.append(self.distribution_instructions.get(tier, ""))
            lines.append("")
        lines.append("## Cross-Level Collaboration")
        lines.append("")
        for tip in self.cross_level_collaboration:
            lines.append(f"- {tip}")
        lines.append("")
        if self.trauma_aware_notes:
            lines.append("## Facilitation Notes")
            lines.append("")
            for note in self.trauma_aware_notes:
                lines.append(f"- {note}")
            lines.append("")
        return "\n".join(lines)


class TeacherGuideGenerator:
    def generate(
        self,
        pack: ContentPack,
        roster: list[dict],
        assignments: dict[str, str],
    ) -> TeacherGuide:
        tier_counts = {tier: 0 for tier in TIERS}
        for tier in assignments.values():
            if tier in tier_counts:
                tier_counts[tier] += 1

        distribution_instructions = {
            tier: (
                f"{TIER_DISTRIBUTION_TIPS[tier]}\n\n"
                f"Learning objective: {pack.tiers[tier]['learning_objective']}"
            )
            for tier in TIERS
        }

        cross_level_collaboration = [
            "For the opening discussion, group one foundational, one on-track, "
            "and one extended student together so vocabulary introduced by the "
            "extended group's research supports the foundational group's task.",
            "Close the lesson as a whole class: ask one volunteer per tier to "
            "share one thing they learned, in any language they're most "
            "comfortable using.",
        ]

        trauma_aware_notes = []
        for student in roster:
            if student.get("trauma_flag"):
                trauma_aware_notes.append(
                    "For at least one student in this class, offer a quiet, "
                    "non-verbal way to opt out of any personal-reflection task "
                    "(e.g., a card on the desk) rather than asking them to "
                    "explain their choice aloud. Do not draw class attention "
                    "to who opts out."
                )
                break  # one general instruction covers the whole class; we
                # never enumerate which students triggered it

        return TeacherGuide(
            lesson_title=pack.lesson.get("unit_title", pack.lesson.get("topic", "")),
            tier_counts=tier_counts,
            distribution_instructions=distribution_instructions,
            cross_level_collaboration=cross_level_collaboration,
            trauma_aware_notes=trauma_aware_notes,
            pack_id=pack.pack_id,
        )
