"""
Trend Analysis — "What patterns am I seeing with this student?" /
"How is my class doing overall?"

Both queries answer the same underlying teacher need: turn a pile of
individual observations into a pattern a human would otherwise have to
scroll back through weeks of notes to reconstruct by hand. That's the
zero-sum-complexity justification for this module — it replaces manual
re-reading of observation history, it doesn't add a new capability that
invents information.

Deterministic, no LLM call: every sentence here is built from counting,
ordering, and comparing values already stored in StudentLensStore. There
is no free-text generation and therefore no hallucination risk — this
mirrors the design of content_differentiator.py (Turn 4) and
teacher_guide.py (Turn 5), both of which generate structured text from
real data with the same constraint.

Local-only: reads StudentLensStore directly. No external call, no PII
leaves the machine. Output is teacher-facing only (uses raw CEFR/RTI/SEL
values and, for the per-student case, direct references to stored
observation content) — never suitable to hand to a parent as-is. See
parent_report.py for the parent-facing artifact, which redacts and
reframes rather than reusing this module's output directly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from src.education.content_differentiator import CEFR_ORDER
from src.education.student_lens import StudentLensStore, VALID_CEFR_DIMENSIONS


def _cefr_index(level: Optional[str]) -> Optional[int]:
    if level in CEFR_ORDER:
        return CEFR_ORDER.index(level)
    return None


@dataclass
class CefrDimensionTrend:
    dimension: str
    observation_count: int
    first_level: Optional[str]
    latest_level: Optional[str]
    direction: str  # "improved" | "declined" | "stable" | "insufficient_data"


@dataclass
class StudentTrend:
    student_id: str
    display_name: str
    observation_count: int
    date_range: tuple  # (earliest_iso, latest_iso) or (None, None)
    rti_tier_current: int
    rti_tier_changes: int
    cefr_dimensions: list  # list[CefrDimensionTrend]
    sel_concern_count: int
    sel_positive_count: int
    dominant_sel_domain: Optional[str]
    active_escalations: list  # from StudentLensStore.evaluate_rti_rules

    def to_markdown(self) -> str:
        lines = [f"# Trend Summary: {self.display_name or self.student_id}", ""]
        if self.observation_count == 0:
            lines.append("No observations recorded yet.")
            return "\n".join(lines)

        lines.append(f"Based on {self.observation_count} observation(s), "
                      f"{self.date_range[0]} to {self.date_range[1]}.")
        lines.append("")
        lines.append(f"**RTI tier**: {self.rti_tier_current} "
                      f"({self.rti_tier_changes} tier change(s) recorded)")
        lines.append("")
        if self.cefr_dimensions:
            lines.append("**CEFR progress**")
            for dim in self.cefr_dimensions:
                lines.append(
                    f"- {dim.dimension}: {dim.first_level or '—'} -> {dim.latest_level or '—'} "
                    f"({dim.direction}, {dim.observation_count} observation(s))"
                )
            lines.append("")
        lines.append(f"**SEL**: {self.sel_positive_count} positive note(s), "
                      f"{self.sel_concern_count} concern(s)"
                      + (f", most often in {self.dominant_sel_domain}" if self.dominant_sel_domain else ""))
        if self.active_escalations:
            lines.append("")
            lines.append("**Currently flagged**:")
            for esc in self.active_escalations:
                lines.append(f"- Rule {esc['rule']}: {esc['action']}")
        return "\n".join(lines)


@dataclass
class ClassSummary:
    teacher_id: str
    student_count: int
    tier_distribution: dict
    cefr_trajectory_distribution: dict
    students_flagged: int
    avg_observations_per_student: float

    def to_markdown(self) -> str:
        lines = [f"# Class Summary", "", f"{self.student_count} student(s) on roster.", ""]
        if self.student_count == 0:
            return "\n".join(lines)
        lines.append("**RTI tier distribution**")
        for tier in (1, 2, 3):
            lines.append(f"- Tier {tier}: {self.tier_distribution.get(tier, 0)}")
        lines.append("")
        lines.append("**CEFR trajectory distribution**")
        for k, v in self.cefr_trajectory_distribution.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append(f"**Flagged for attention**: {self.students_flagged} student(s)")
        lines.append(f"**Avg observations per student**: {self.avg_observations_per_student:.1f}")
        return "\n".join(lines)


class TrendAnalyzer:
    def __init__(self, store: StudentLensStore):
        self.store = store

    def analyze_student(self, student_id: str) -> StudentTrend:
        lens = self.store.get_lens(student_id)
        export = self.store.export_lens(student_id)
        observations = sorted(export["observations"], key=lambda o: o["recorded_at"])

        date_range = (
            (observations[0]["recorded_at"], observations[-1]["recorded_at"])
            if observations else (None, None)
        )

        rti_tier_changes = sum(1 for o in observations if o["rti_tier_changed_this_obs"])

        cefr_dimensions = []
        for dimension in VALID_CEFR_DIMENSIONS:
            dim_obs = [o for o in observations if o.get("cefr_dimension") == dimension
                       and o.get("cefr_level_observed")]
            if not dim_obs:
                continue
            first_level = dim_obs[0]["cefr_level_observed"]
            latest_level = dim_obs[-1]["cefr_level_observed"]
            first_idx = _cefr_index(first_level)
            latest_idx = _cefr_index(latest_level)
            if len(dim_obs) < 2 or first_idx is None or latest_idx is None:
                direction = "insufficient_data"
            elif latest_idx > first_idx:
                direction = "improved"
            elif latest_idx < first_idx:
                direction = "declined"
            else:
                direction = "stable"
            cefr_dimensions.append(CefrDimensionTrend(
                dimension=dimension, observation_count=len(dim_obs),
                first_level=first_level, latest_level=latest_level, direction=direction,
            ))

        sel_concerns = [o for o in observations if o.get("sel_valence") == "concern"]
        sel_positives = [o for o in observations if o.get("sel_valence") == "positive"]
        sel_domains = Counter(o["sel_domain"] for o in observations if o.get("sel_domain"))
        dominant_domain = sel_domains.most_common(1)[0][0] if sel_domains else None

        return StudentTrend(
            student_id=student_id,
            display_name=lens.get("display_name", ""),
            observation_count=len(observations),
            date_range=date_range,
            rti_tier_current=lens["rti_current_tier"],
            rti_tier_changes=rti_tier_changes,
            cefr_dimensions=cefr_dimensions,
            sel_concern_count=len(sel_concerns),
            sel_positive_count=len(sel_positives),
            dominant_sel_domain=dominant_domain,
            active_escalations=self.store.evaluate_rti_rules(student_id),
        )

    def analyze_class(self, teacher_id: str) -> ClassSummary:
        roster = self.store.list_lenses_for_teacher(teacher_id)
        tier_distribution: dict = Counter(lens["rti_current_tier"] for lens in roster)
        trajectory_distribution: dict = Counter(lens["cefr_trajectory_30d"] for lens in roster)

        total_observations = 0
        flagged = 0
        for lens in roster:
            export = self.store.export_lens(lens["student_id"])
            total_observations += len(export["observations"])
            if self.store.evaluate_rti_rules(lens["student_id"]):
                flagged += 1

        avg_obs = (total_observations / len(roster)) if roster else 0.0

        return ClassSummary(
            teacher_id=teacher_id,
            student_count=len(roster),
            tier_distribution=dict(tier_distribution),
            cefr_trajectory_distribution=dict(trajectory_distribution),
            students_flagged=flagged,
            avg_observations_per_student=avg_obs,
        )
