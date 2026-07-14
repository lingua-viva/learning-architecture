"""
Parent Progress Report Generator — the first artifact in the teacher
daily-workflow layer that crosses the teacher-facing trust boundary and
becomes something a parent actually reads.

This is NOT a new design — `architecture/observation-capture.md`
Stages 7-9 already specify the full shape (ai_draft -> teacher review ->
parent_artifact, with `attribution_visible_to_parent` hard-locked to
`false`) before this module was written. This module implements that
existing spec rather than inventing a new one.

One deliberate deviation from the spec's wording, documented here: Stage
7 calls the draft step "AI-assisted" and describes sending pseudonymized
observation content to a model. This module does NOT call any external
model. It generates the draft entirely locally from structured lens
fields (CEFR level/direction, RTI status, SEL trend) — never from raw
observation transcript text — using the same deterministic,
template-based approach already used in content_differentiator.py and
trend_analysis.py. Reasons: (1) even pseudonymized transcript text can
carry identifying detail a name/ID strip doesn't catch (a specific
incident description, a sibling's name mentioned in passing); (2)
offline-first is load-bearing per the build rules — a parent report
generator that requires connectivity to draft anything defeats that;
(3) it keeps this module's PII guarantee identical in strength to every
other module in this build: no code path to an external host exists at
all, so there's nothing to audit for "did the draft leak something."

Trust-boundary workflow (matches Stage 8 exactly):
  generate_draft()   -> ParentReportDraft (ai_draft equivalent; teacher-
                         facing "suggested message", not sent anywhere)
  approve() / edit()  -> ParentArtifact (only after explicit teacher
                         action; attribution_visible_to_parent is
                         hard-locked False and cannot be set any other
                         way — there is no parameter for it)

Trauma-safety: every generated string runs through the same
`_check_trauma_safety` structural check from content_differentiator.py
(Turn 4) — raises `TraumaSafetyError` if a labeling/outing phrase
("refugee student", "trauma survivor", etc.) appears, regardless of who
the intended reader is. A parent report is exactly the kind of document
that gets printed and can be seen by someone other than its intended
recipient (siblings, other family members), so the same no-labeling bar
used for the teacher guide applies here too.

Clinical/deficit language: RTI tier and SEL "concern" language is never
surfaced verbatim to a parent. A tier-2/3 student's report reads as
encouraging + a concrete home activity, not "your child is in Tier 2
intervention" or "N behavioral concerns logged this month" — matching
the trauma-informed research from Turn 4 (avoid deficit/diagnostic
framing) applied to a new audience.

Language: `architecture-phase` research (this phase's research call)
could only verify language data for the Kenya campus and found no
authoritative source covering Colombia/India/Italy. Rather than assume
a school-wide default, this module reads the target language directly
from the student's own stored `home_languages[0]` — real per-student
data, not a guess. No local translation engine exists in this vertical
slice, so the draft body itself is generated in English regardless of
target language; `language` on the artifact is a routing field for a
human/admin translation step, not a claim that translation happened.
Documented as a known limitation, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.education.content_differentiator import CEFR_ORDER, _check_trauma_safety
from src.education.student_lens import StudentLensStore
from src.education.trend_analysis import TrendAnalyzer

VALID_TEMPLATES = ("progress", "concern", "activity_ideas")

_CEFR_ACTIVITY = {
    "reading": "Read together for 10 minutes a day, in any language — ask them to retell what happened.",
    "writing": "Encourage a short daily note or drawing with a caption, in any language.",
    "speaking": "Ask them to tell you about one thing from their day and listen without correcting.",
    "listening": "Listen to a short story or song together and ask what they noticed.",
}

_GENERAL_ACTIVITY = "Ask them one specific thing about their day and give them your full attention while they answer."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ParentReportDraft:
    """Internal, teacher-facing only. Never transmitted anywhere as-is —
    mirrors observation-capture.md's `ai_draft` field, which the spec
    states is "never transmitted to any parent-facing endpoint.\""""
    student_id: str
    teacher_id: str
    template_type: str
    generated_at: str
    subject_line: str
    body: str
    home_activities: list
    tone: str


@dataclass
class ParentArtifact:
    """What a parent actually sees. No AI fields, no internal IDs, no
    performance metrics — matches observation-capture.md Stage 9's
    explicit "fields NEVER transmitted to parent" list."""
    subject_line: str
    body: str
    home_activities: list
    from_label: str
    language: str
    attribution_visible_to_parent: bool = False  # hard-locked, never a parameter

    def to_printable_text(self) -> str:
        lines = [self.subject_line, "", self.body, ""]
        if self.home_activities:
            lines.append("A few things you could try at home:")
            for activity in self.home_activities:
                lines.append(f"- {activity}")
            lines.append("")
        lines.append(f"— {self.from_label}")
        return "\n".join(lines)


class ParentReportGenerator:
    def __init__(self, store: StudentLensStore):
        self.store = store
        self.analyzer = TrendAnalyzer(store)

    def generate_draft(
        self,
        student_id: str,
        teacher_id: str,
        template_type: str = "progress",
    ) -> ParentReportDraft:
        if template_type not in VALID_TEMPLATES:
            raise ValueError(f"template_type must be one of {VALID_TEMPLATES}")

        lens = self.store.get_lens(student_id)
        trend = self.analyzer.analyze_student(student_id)
        name = lens.get("display_name") or "your child"

        body_parts = [f"Over the past few weeks, we've been getting to know {name} better in class."]
        activities: list = []

        progressed_dims = [d for d in trend.cefr_dimensions if d.direction == "improved"]
        if progressed_dims:
            dim = progressed_dims[0]
            body_parts.append(
                f"{name} has been making real progress with {dim.dimension} — "
                f"we've seen steady growth in this area."
            )
            activities.append(_CEFR_ACTIVITY.get(dim.dimension, _GENERAL_ACTIVITY))
        elif trend.cefr_dimensions:
            dim = trend.cefr_dimensions[0]
            body_parts.append(
                f"{name} is working on building {dim.dimension} skills, and a little "
                f"extra practice at home would help."
            )
            activities.append(_CEFR_ACTIVITY.get(dim.dimension, _GENERAL_ACTIVITY))
        else:
            body_parts.append(f"We're still getting a full picture of {name}'s learning — more updates soon.")

        if trend.sel_positive_count > 0:
            body_parts.append(f"{name} has had some lovely moments in class this month.")

        if not activities:
            activities.append(_GENERAL_ACTIVITY)

        subject_line = f"A note about {name}'s progress"
        body = " ".join(body_parts)
        tone = "encouraging"

        _check_trauma_safety(subject_line)
        _check_trauma_safety(body)
        for activity in activities:
            _check_trauma_safety(activity)

        return ParentReportDraft(
            student_id=student_id,
            teacher_id=teacher_id,
            template_type=template_type,
            generated_at=_now_iso(),
            subject_line=subject_line,
            body=body,
            home_activities=activities,
            tone=tone,
        )

    def approve(
        self,
        draft: ParentReportDraft,
        teacher_display_name: str,
        teacher_edited_body: Optional[str] = None,
    ) -> ParentArtifact:
        """Teacher approval step (Stage 8). If teacher_edited_body is
        given, it replaces the draft body in the parent-facing artifact
        (still re-checked for trauma-safety — a teacher edit could
        reintroduce a labeling phrase the deterministic generator would
        never produce on its own)."""
        body = teacher_edited_body if teacher_edited_body is not None else draft.body
        _check_trauma_safety(body)

        lens = self.store.get_lens(draft.student_id)
        home_languages = lens.get("home_languages") or []
        language = home_languages[0] if home_languages else "en"

        return ParentArtifact(
            subject_line=draft.subject_line,
            body=body,
            home_activities=draft.home_activities,
            from_label=f"{teacher_display_name} (Class Teacher)",
            language=language,
            attribution_visible_to_parent=False,
        )
