"""
Weekly Recommendation Engine — "What should I focus on next week?"

The end-of-week counterpart to morning_brief.py's "who needs my attention
today?" — same underlying data, different cadence and framing. The
morning brief is a daily sweep of currently-open flags; this module looks
back across the week and forward to what a teacher should prioritize next,
combining three signals already built in this phase rather than inventing
new ones (zero-sum complexity):
  1. Students with an active RTI escalation right now (reuses
     StudentLensStore.evaluate_rti_rules() and morning_brief.py's
     RULE_LABELS — not re-derived).
  2. Students whose 30-day CEFR trajectory is regressing (same signal
     morning_brief.py surfaces daily; carried over here because a single
     day's brief can get missed, a week's recommendation shouldn't).
  3. Students nobody has recorded an observation for in the last 7 days
     (reuses morning_brief.py's `_days_since` helper) — these are the
     students most likely to fall through the cracks going into next
     week, so they're surfaced as a distinct "prioritize observing"
     list rather than folded into the flagged list.
Class-level shape (tier distribution, trajectory distribution, flagged
count) is not recomputed here — `TrendAnalyzer.analyze_class()` (Turn 9)
already produces exactly that, so this module embeds its `ClassSummary`
directly on the recommendation rather than duplicating the aggregation.

Documented scope limitation, not built: the acceptance criteria for this
feature ask for recommendations informed by "upcoming units." This system
has no persisted curriculum calendar — content_differentiator.py generates
a ContentPack on demand from a LessonInput the caller supplies each time;
there is no stored schedule of which unit a teacher is covering next week.
Building a fabricated "you have a Migration unit on Tuesday" recommendation
would be inventing data that doesn't exist in this vertical slice, which
the publication policy's evidence-traceability rule forbids. Instead,
`WeeklyRecommendation.curriculum_note` states this gap explicitly so a
teacher (or future build) knows a real curriculum-calendar integration is
what's missing, not that it was overlooked.

Deterministic, no LLM call, local-only: same pattern as every other module
in this phase — counts and orders real stored values, no external call, no
new PII surface (reads through StudentLensStore only).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.education.morning_brief import RULE_LABELS, _days_since
from src.education.student_lens import StudentLensStore
from src.education.trend_analysis import ClassSummary, TrendAnalyzer

# Weekly-cadence threshold for "hasn't been observed" — distinct from
# morning_brief.py's STALE_OBSERVATION_DAYS (7 days, same value here by
# coincidence of both being "roughly a school week," not a shared
# constant — morning_brief's is a daily nudge threshold, this one is a
# weekly-planning threshold, and they're free to diverge independently).
UNOBSERVED_WEEK_DAYS = 7

CURRICULUM_NOTE = (
    "This recommendation is based on observation history and RTI/CEFR "
    "signals only. It does NOT account for upcoming curriculum units — "
    "this system has no stored curriculum calendar (content packs are "
    "generated on demand per lesson, not scheduled in advance), so "
    "unit-aware planning is a known gap, not a claim this build makes."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RecommendationItem:
    student_id: str
    display_name: str
    reasons: list


@dataclass
class WeeklyRecommendation:
    teacher_id: str
    generated_at: str
    class_summary: ClassSummary
    priority_students: list  # list[RecommendationItem], active flags/regression
    unobserved_this_week: list  # list[RecommendationItem]
    curriculum_note: str = CURRICULUM_NOTE

    def to_markdown(self) -> str:
        lines = [f"# Weekly Recommendation", "", f"Generated: {self.generated_at}", ""]
        lines.append(self.class_summary.to_markdown())
        lines.append("")

        if self.priority_students:
            lines.append(f"## Priority for Next Week ({len(self.priority_students)})")
            lines.append("")
            for item in self.priority_students:
                lines.append(f"- **{item.display_name or item.student_id}**")
                for reason in item.reasons:
                    lines.append(f"  - {reason}")
            lines.append("")

        if self.unobserved_this_week:
            lines.append(f"## Prioritize Observing ({len(self.unobserved_this_week)})")
            lines.append("")
            for item in self.unobserved_this_week:
                lines.append(f"- {item.display_name or item.student_id}: {item.reasons[0]}")
            lines.append("")

        if not self.priority_students and not self.unobserved_this_week:
            lines.append("No open flags and everyone's been observed recently — a quiet week.")
            lines.append("")

        lines.append(f"_{self.curriculum_note}_")
        return "\n".join(lines)


class WeeklyRecommendationGenerator:
    def __init__(self, store: StudentLensStore):
        self.store = store
        self.analyzer = TrendAnalyzer(store)

    def generate(self, teacher_id: str) -> WeeklyRecommendation:
        roster = self.store.list_lenses_for_teacher(teacher_id)
        class_summary = self.analyzer.analyze_class(teacher_id)

        priority: list = []
        unobserved: list = []

        for lens in roster:
            student_id = lens["student_id"]
            reasons: list = []

            for escalation in self.store.evaluate_rti_rules(student_id):
                reasons.append(RULE_LABELS.get(escalation["rule"], escalation["action"]))

            if lens.get("cefr_trajectory_30d") == "regressing":
                reasons.append("CEFR trajectory regressing over the last 30 days — consider a check-in")

            if reasons:
                priority.append(RecommendationItem(
                    student_id=student_id, display_name=lens.get("display_name", ""), reasons=reasons,
                ))

            days_since = _days_since(lens.get("updated_at", ""))
            if days_since >= UNOBSERVED_WEEK_DAYS:
                unobserved.append(RecommendationItem(
                    student_id=student_id,
                    display_name=lens.get("display_name", ""),
                    reasons=[f"{int(days_since)} days since last observation — prioritize next week"],
                ))

        priority.sort(key=lambda item: -len(item.reasons))
        unobserved.sort(key=lambda item: item.display_name or item.student_id)

        return WeeklyRecommendation(
            teacher_id=teacher_id,
            generated_at=_now_iso(),
            class_summary=class_summary,
            priority_students=priority,
            unobserved_this_week=unobserved,
        )
