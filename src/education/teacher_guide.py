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

Conflict-aware grouping (re-ground audit fix): the meeting notes were
explicit that grouping logic must account for social dynamics, not just
academic/RTI level ("kids cannot work if near a kid with conflict").
`avoid_pairing_with` on a student lens (student_lens.py, teacher-set, not
derived from an observation) now feeds `build_cross_level_groups()`
below: it produces concrete one-per-tier groups from a real roster while
guaranteeing no group ever contains two students with a conflict edge
between them, in either direction. This replaces the previous behavior,
which only printed two generic cross-tier tips with no actual roster
grouping and no conflict awareness at all. If a student can't be placed
without a conflict (small roster, dense conflict graph), they're left
ungrouped and surfaced explicitly on the guide rather than force-paired —
a teacher should decide that case by hand, the system should never guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
class Group:
    group_id: str
    student_ids: list[str] = field(default_factory=list)
    display_names: list[str] = field(default_factory=list)


def _conflicts(a: str, b: str, avoid_map: dict[str, set[str]]) -> bool:
    """Symmetric — a conflict declared by either student blocks the pair,
    regardless of who reported it."""
    return b in avoid_map.get(a, set()) or a in avoid_map.get(b, set())


def build_cross_level_groups(
    roster: list[dict], assignments: dict[str, str]
) -> tuple[list[Group], list[str]]:
    """
    Build concrete one-foundational + one-on_track + one-extended groups
    from a real roster, honoring each student's avoid_pairing_with list
    (teacher-set on the student lens — see student_lens.py). No group is
    ever formed with a conflicting pair, in either direction. Students who
    can't be placed without a conflict (or who have no tier partner left)
    are returned separately as `unplaced` rather than force-paired — a
    teacher resolves that case by hand, the system never guesses.

    Returns (groups, unplaced_student_ids).
    """
    display_names = {s["student_id"]: s.get("display_name", "") for s in roster}
    avoid_map: dict[str, set[str]] = {
        s["student_id"]: set(s.get("avoid_pairing_with") or []) for s in roster
    }

    by_tier: dict[str, list[str]] = {tier: [] for tier in TIERS}
    for student in roster:
        sid = student["student_id"]
        tier = assignments.get(sid)
        if tier in by_tier:
            by_tier[tier].append(sid)

    foundational = list(by_tier["foundational"])
    on_track = list(by_tier["on_track"])
    extended = list(by_tier["extended"])

    groups: list[Group] = []
    unplaced: list[str] = []

    while foundational:
        f = foundational.pop(0)
        members = [f]

        idx = next((i for i, o in enumerate(on_track) if not _conflicts(f, o, avoid_map)), None)
        if idx is not None:
            members.append(on_track.pop(idx))

        idx = next(
            (i for i, e in enumerate(extended)
             if all(not _conflicts(e, m, avoid_map) for m in members)),
            None,
        )
        if idx is not None:
            members.append(extended.pop(idx))

        if len(members) == 1:
            unplaced.append(f)
        else:
            groups.append(Group(
                group_id=f"group-{len(groups) + 1}",
                student_ids=members,
                display_names=[display_names.get(m, m) for m in members],
            ))

    unplaced.extend(on_track)
    unplaced.extend(extended)

    # Guard: any roster student with a missing/invalid tier assignment
    # (assignments.get(sid) not in TIERS) never entered by_tier above and
    # would otherwise vanish from the guide entirely. Surface them as
    # unplaced instead of silently dropping — a teacher should see every
    # roster student accounted for somewhere on the guide.
    accounted = {sid for group in groups for sid in group.student_ids}
    accounted.update(unplaced)
    for student in roster:
        sid = student["student_id"]
        if sid not in accounted:
            unplaced.append(sid)
            accounted.add(sid)

    return groups, unplaced


@dataclass
class TeacherGuide:
    lesson_title: str
    tier_counts: dict
    distribution_instructions: dict
    cross_level_collaboration: list[str]
    trauma_aware_notes: list[str]
    pack_id: str
    groups: list[Group] = field(default_factory=list)
    unplaced_for_grouping: list[str] = field(default_factory=list)
    roster_display_names: dict[str, str] = field(default_factory=dict)

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
        if self.groups:
            lines.append("### Suggested Groups (conflict-checked)")
            lines.append("")
            for group in self.groups:
                names = ", ".join(n or sid for n, sid in zip(group.display_names, group.student_ids))
                lines.append(f"- **{group.group_id}**: {names}")
            lines.append("")
        if self.unplaced_for_grouping:
            lines.append(
                "### Needs Manual Grouping (no conflict-free partner available)"
            )
            lines.append("")
            for sid in self.unplaced_for_grouping:
                name = self.roster_display_names.get(sid) or sid
                lines.append(f"- {name}")
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

        groups, unplaced = build_cross_level_groups(roster, assignments)

        roster_display_names = {s["student_id"]: s.get("display_name", "") for s in roster}

        return TeacherGuide(
            lesson_title=pack.lesson.get("unit_title", pack.lesson.get("topic", "")),
            tier_counts=tier_counts,
            distribution_instructions=distribution_instructions,
            cross_level_collaboration=cross_level_collaboration,
            trauma_aware_notes=trauma_aware_notes,
            pack_id=pack.pack_id,
            groups=groups,
            unplaced_for_grouping=unplaced,
            roster_display_names=roster_display_names,
        )
