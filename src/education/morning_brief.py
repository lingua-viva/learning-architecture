"""
Morning Brief — "Who needs my attention today?"

Research (mandatory, ran before designing this artifact):
  mc research "What does a morning briefing look like for a teacher in a
  differentiated IB classroom? What information do they need before the
  day starts?"
Finding: the literature covers differentiation *principles* well but not
a concrete pre-day checklist. The reconstructed shape (evidence-based,
not verbatim from any single source) centers on: yesterday's data,
today's objectives, group/support structures, and operational
constraints. This module builds the first of those — "yesterday's data,
surfaced as attention items" — since objectives/groups/constraints are
either already covered by Product B's content packs or out of scope for
a data system (room/device logistics aren't stored here).

What this is NOT: an automated tier-change tool. rti-tiers.md is explicit
(Gate 3, both Tier 1->2 and Tier 2->3): tier movement always requires
human educator confirmation, never an automated trigger alone. This
module only *surfaces* — it recomputes StudentLensStore's existing RTI
escalation rules (A-E, already implemented and tested in student_lens.py)
plus a CEFR-regression check, and lists which of a teacher's students
currently carry an open flag. It makes no tier-change decision and writes
nothing back to the store.

Proactive vs. on-query: Product A's Slack bot already surfaces
escalations in real time — the teacher who just recorded the triggering
observation gets ACK_ESCALATION immediately (slack_bot.py). This module
is the complementary "since I last checked" sweep: it catches
escalations that accumulated from a *colleague's* observations of a
shared student, or from SEL/CEFR patterns that only become visible when
several observations are viewed together rather than one at a time.

Local-only: reads StudentLensStore directly, no external call, no PII
leaves the machine. This module produces internal, teacher-facing text
only — never a parent-facing artifact (see parent_report.py for that,
built separately with the stricter AI-opacity rules from
observation-capture.md Stage 7/8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.education.student_lens import StudentLensStore

# Soft "no recent observation" threshold for the morning brief. This is
# deliberately looser than RTI Rule C's 15-day/tier-1-only escalation —
# Rule C is a real escalation with review-queue consequences; this is
# just a gentle proactive nudge so gaps don't silently reach 15 days
# before anyone notices. Not sourced from a specific citation (the RTI
# research call answered "how often should tier decisions be reviewed",
# not "when should a single teacher get nudged") — documented as a
# reasonable default, not a validated threshold.
STALE_OBSERVATION_DAYS = 7

RULE_LABELS = {
    "A": "Persistent regression pattern — consider Tier 2 review",
    "B": "Urgent flag from the most recent observation",
    "C": "Monitoring gap — no observation in 15+ school days",
    "D": "Recurring SEL concerns this week",
    "E": "Manual tier change recorded — pending team review",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_since(iso_timestamp: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return (_now() - ts).total_seconds() / 86400


@dataclass
class AttentionItem:
    student_id: str
    display_name: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class MorningBrief:
    teacher_id: str
    generated_at: str
    total_students: int
    needs_attention: list[AttentionItem]
    no_recent_observation: list[AttentionItem]

    def to_markdown(self) -> str:
        lines = [f"# Morning Brief", "", f"Generated: {self.generated_at}", ""]
        if not self.needs_attention and not self.no_recent_observation:
            lines.append(
                f"No flags across your {self.total_students} student(s) — nothing urgent this morning."
            )
            return "\n".join(lines)

        if self.needs_attention:
            lines.append(f"## Needs Attention ({len(self.needs_attention)})")
            lines.append("")
            for item in self.needs_attention:
                lines.append(f"- **{item.display_name or item.student_id}**")
                for reason in item.reasons:
                    lines.append(f"  - {reason}")
            lines.append("")

        if self.no_recent_observation:
            lines.append(f"## No Recent Observation ({len(self.no_recent_observation)})")
            lines.append("")
            for item in self.no_recent_observation:
                lines.append(f"- {item.display_name or item.student_id}: {item.reasons[0]}")
            lines.append("")

        lines.append(f"_{self.total_students} student(s) total on your roster._")
        return "\n".join(lines)


class MorningBriefGenerator:
    def __init__(self, store: StudentLensStore):
        self.store = store

    def generate(self, teacher_id: str) -> MorningBrief:
        roster = self.store.list_lenses_for_teacher(teacher_id)

        needs_attention: list[AttentionItem] = []
        no_recent: list[AttentionItem] = []

        for lens in roster:
            student_id = lens["student_id"]
            reasons: list[str] = []

            for escalation in self.store.evaluate_rti_rules(student_id):
                label = RULE_LABELS.get(escalation["rule"], escalation["action"])
                reasons.append(label)

            if lens.get("cefr_trajectory_30d") == "regressing":
                reasons.append("CEFR trajectory regressing over the last 30 days")

            if reasons:
                needs_attention.append(
                    AttentionItem(student_id=student_id, display_name=lens.get("display_name", ""), reasons=reasons)
                )

            days_since = _days_since(lens.get("updated_at", ""))
            if days_since >= STALE_OBSERVATION_DAYS:
                no_recent.append(
                    AttentionItem(
                        student_id=student_id,
                        display_name=lens.get("display_name", ""),
                        reasons=[f"{int(days_since)} days since last observation"],
                    )
                )

        return MorningBrief(
            teacher_id=teacher_id,
            generated_at=_now().isoformat(),
            total_students=len(roster),
            needs_attention=needs_attention,
            no_recent_observation=no_recent,
        )
