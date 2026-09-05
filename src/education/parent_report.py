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

import html as _html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.education.content_differentiator import CEFR_ORDER, _check_trauma_safety
from src.education.student_lens import (
    REPORT_GRADE_CONFIDENCE,
    StudentLensStore,
    support_profile_for_audience,
)
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
    # Structured sections (P1-DOC-001): the same sentences that make up
    # `body`, kept separately so the print template controls layout.
    intro: str = ""
    strengths: list = field(default_factory=list)
    growth_areas: list = field(default_factory=list)
    student_name: str = ""
    grade_level: str = ""
    reporting_period: str = ""
    # Lens field contract OUT filter (2026-09-04): what this draft read from
    # the lens, what it lacked, and the ids of the support-profile /
    # strengths entries behind its sentences (traceability, like
    # source_observation_ids at the endpoint).
    fields_used: list = field(default_factory=list)
    fields_enriching_missing: list = field(default_factory=list)
    source_entry_ids: list = field(default_factory=list)


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
    # Structured print fields (P1-DOC-001). student_name here is by design:
    # the parent-facing artifact names their own child (same as
    # to_printable_text has always done) — internal IDs stay forbidden.
    student_name: str = ""
    grade_level: str = ""
    reporting_period: str = ""
    intro: str = ""
    strengths: list = field(default_factory=list)
    growth_areas: list = field(default_factory=list)

    def to_print_html(self) -> str:
        return render_parent_report_html(self.__dict__)

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
        include_evidence_summaries: bool = False,
    ) -> ParentReportDraft:
        if template_type not in VALID_TEMPLATES:
            raise ValueError(f"template_type must be one of {VALID_TEMPLATES}")

        lens = self.store.get_lens(student_id)
        # OUT filter (lens_field_contract.requires("parent_report")): read the
        # declared fields, and know what was missing. display_name is essential.
        from src.lingua_viva.lens_field_contract import read_for

        reading = read_for("parent_report", lens)
        trend = self.analyzer.analyze_student(student_id)
        name = lens.get("display_name") or "your child"

        intro = f"We noticed {name} trying new ways to make meaning in class."
        body_parts = [intro]
        # Structured sections mirror body_parts sentence-for-sentence:
        # every strength/growth sentence also joins the body, so the
        # existing trauma-safety and publication-safety gates (which run
        # on the body) cover the sections too.
        strengths: list = []
        growth_areas: list = []
        activities: list = []

        progressed_dims = [d for d in trend.cefr_dimensions if d.direction == "improved"]
        if progressed_dims:
            dim = progressed_dims[0]
            sentence = (
                f"In {dim.dimension}, {name}'s progress is visible in growing confidence "
                "and more independent choices."
            )
            body_parts.append(sentence)
            strengths.append(sentence)
            activities.append(_CEFR_ACTIVITY.get(dim.dimension, _GENERAL_ACTIVITY))
        elif trend.cefr_dimensions:
            dim = trend.cefr_dimensions[0]
            sentence = (
                f"In {dim.dimension}, we are watching for the next small signs of confidence."
            )
            body_parts.append(sentence)
            growth_areas.append(sentence)
            activities.append(_CEFR_ACTIVITY.get(dim.dimension, _GENERAL_ACTIVITY))
        else:
            # Honest empty: no observations means no strengths/growth
            # sections get invented — the body says so instead.
            body_parts.append(
                f"We are still collecting classroom observations so the next note can be more specific."
            )

        if trend.sel_positive_count > 0:
            sentence = f"{name} has brought care and attention to class moments this month."
            body_parts.append(sentence)
            strengths.append(sentence)

        # The support profile and profile-level strengths (2026-09-04): what a
        # report card and the teacher's own Observe notes put on the lens.
        # Family audience: personal_context is excluded and only report-grade
        # entries (teacher_confirmed / imported_verified) survive —
        # support_profile_for_audience already enforces both. Only the
        # STRENGTHS and STRATEGIES_WORKED buckets are read: needs, open
        # questions and raw evidence are teacher-facing and would put deficit
        # or clinical framing in front of a parent. Sentences join body_parts
        # here so the trauma-safety and publication gates below cover them.
        source_entry_ids: list = []
        family_profile = support_profile_for_audience(lens.get("support_profile") or {}, "family")
        strength_items: list = []
        strategy_items: list = []
        for cat_data in (family_profile.get("categories") or {}).values():
            strength_items.extend(cat_data.get("strengths") or [])
            strategy_items.extend(cat_data.get("strategies_worked") or [])
        for kind in ("academic_strengths", "personal_strengths"):
            for item in (lens.get("strengths_profile") or {}).get(kind) or []:
                if not isinstance(item, dict) or item.get("active", True) is False:
                    continue
                if item.get("confidence", "teacher_confirmed") not in REPORT_GRADE_CONFIDENCE:
                    continue
                if str(item.get("text") or "").strip():
                    strength_items.append(item)
        for item in strength_items[:3]:
            text = str(item.get("text") or "").strip().rstrip(".")
            sentence = f"At school, {name} shows strength in {text}."
            body_parts.append(sentence)
            strengths.append(sentence)
            if item.get("id"):
                source_entry_ids.append(str(item["id"]))
        for item in strategy_items[:2]:
            text = str(item.get("text") or "").strip().rstrip(".")
            sentence = f"Something that has helped {name} in class: {text}."
            body_parts.append(sentence)
            strengths.append(sentence)
            if item.get("id"):
                source_entry_ids.append(str(item["id"]))

        # Only explicit teacher-reviewed support decisions from active diagnostics.
        # Raw work/transcripts are never copied into a parent note.
        for assessment in (reading['fields_used'].get('assessment_profile') or [])[-2:]:
            for dimension, finding in assessment['dimensions'].items():
                if finding['needs_support'] is None:
                    continue
                sentence = f"In recent language work ({dimension}), the teacher noted: {finding['note']}"
                body_parts.append(sentence)
                if finding['needs_support']:
                    growth_areas.append(sentence)
                else:
                    strengths.append(sentence)
                source_entry_ids.append(assessment['assessment_id'])

        # Evidence summaries (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01):
        # report-grade ledger evidence only (teacher_confirmed /
        # imported_verified — never model_suggested), newest first, capped
        # at 3 per (target_type, target_id). Gate order is sacred: these
        # sentences join body_parts HERE, before _check_trauma_safety below
        # and before the endpoint's _strip_parent_output +
        # check_publication_safety — evidence text passes every gate the
        # generated prose passes.
        #
        # personal_context is EXCLUDED unconditionally: safeguarding,
        # family-situation, and wellbeing evidence must never appear in
        # parent/student-facing output regardless of confidence or teacher
        # confirmation. The teacher can choose to share that information
        # directly; the system must not surface it.
        if include_evidence_summaries:
            per_target: dict = {}
            picked = []
            for item in self.store.list_evidence(student_id):
                if item.get("confidence_level") not in REPORT_GRADE_CONFIDENCE:
                    continue
                if item.get("target_id") == "personal_context":
                    continue
                key = (item.get("target_type"), item.get("target_id"))
                if per_target.get(key, 0) >= 3:
                    continue
                per_target[key] = per_target.get(key, 0) + 1
                picked.append(item)
            if picked:
                body_parts.append("A few moments from our classroom records:")
                for item in picked:
                    summary = str(item.get("summary") or "").strip().rstrip(".")
                    body_parts.append(f"{summary}.")
                    strengths.append(f"{summary}.")

        if not activities:
            activities.append(_GENERAL_ACTIVITY)

        subject_line = f"A note about {name}'s progress"
        body = " ".join(body_parts)
        tone = "encouraging"

        _check_trauma_safety(subject_line)
        _check_trauma_safety(body)
        for activity in activities:
            _check_trauma_safety(activity)

        generated_at = _now_iso()
        return ParentReportDraft(
            student_id=student_id,
            teacher_id=teacher_id,
            template_type=template_type,
            generated_at=generated_at,
            subject_line=subject_line,
            body=body,
            home_activities=activities,
            tone=tone,
            intro=intro,
            strengths=strengths,
            growth_areas=growth_areas,
            student_name=name,
            grade_level=str(lens.get("grade_level") or ""),
            # Honest label: this is when the note was written, not a school
            # term boundary the system has no data for.
            reporting_period=datetime.now(timezone.utc).strftime("%B %Y"),
            fields_used=sorted(reading["fields_used"]),
            fields_enriching_missing=list(reading["fields_enriching_missing"]),
            source_entry_ids=source_entry_ids,
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
            student_name=draft.student_name,
            grade_level=draft.grade_level,
            reporting_period=draft.reporting_period,
            # A teacher edit is the message — it replaces the opening
            # paragraph in the printed report too. The structured sections
            # stay: they are derived from the same reviewed data.
            intro=body if teacher_edited_body is not None else draft.intro,
            strengths=list(draft.strengths),
            growth_areas=list(draft.growth_areas),
        )


# ---------------------------------------------------------------------------
# Print template (P1-DOC-001). `templates/parent_report.html` documents the
# fields this renderer supports — keep the two in sync, same contract as
# templates/lesson_plan.html and render_lesson_plan_html.
# ---------------------------------------------------------------------------

_PARENT_REPORT_CSS = """
    body { font-family: Georgia, 'Times New Roman', serif; color: #17202a; line-height: 1.5; margin: 16mm; }
    .parent-report { max-width: 720px; margin: 0 auto; }
    h1 { font-size: 22px; margin: 0 0 6px; }
    h2 { font-size: 15px; margin: 18px 0 6px; border-bottom: 1px solid #d8dee4; padding-bottom: 3px; }
    .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px 14px; font-size: 12px; margin: 10px 0 16px; }
    .fill-line { display: inline-block; min-width: 140px; border-bottom: 1px solid #5f6b76; }
    ul { margin-top: 4px; padding-left: 20px; }
    .empty-note { color: #5f6b76; font-style: italic; }
    .signature { margin-top: 28px; break-inside: avoid; }
    .signature .line { border-bottom: 1px solid #17202a; width: 220px; height: 24px; }
    .signature .label { font-size: 11px; color: #5f6b76; margin-top: 2px; }
"""


def _esc(value: object) -> str:
    return _html.escape(str(value or ""))


def _bullets(items: list, empty_note: str) -> str:
    cleaned = [str(item).strip() for item in items or [] if str(item).strip()]
    if not cleaned:
        return f'<p class="empty-note">{_esc(empty_note)}</p>'
    lis = "".join(f"<li>{_esc(item)}</li>" for item in cleaned)
    return f"<ul>{lis}</ul>"


def render_parent_report_html(report: dict) -> str:
    """Render a printable parent report from a ParentArtifact-shaped dict.

    Privacy contract: renders ONLY the fields it is given — it never reaches
    back into any store, adds no IDs, no AI attribution, no internal fields.
    A blank student_name renders as a fill-in line (the name-stripped draft
    surface in web.py uses this on purpose: the teacher writes the name in
    after review). Empty sections render an honest note, never invented
    content.
    """
    student_name = str(report.get("student_name") or "").strip()
    name_html = (
        _esc(student_name)
        if student_name
        else '<span class="fill-line">&nbsp;</span>'
    )
    opening = str(report.get("intro") or report.get("body") or "").strip()
    from_label = str(report.get("from_label") or "").strip()

    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{_esc(report.get('subject_line') or 'A note from class')}</title>",
        f"<style>{_PARENT_REPORT_CSS}</style>",
        "</head><body>",
        '<article class="parent-report">',
        f"<h1>{_esc(report.get('subject_line') or 'A note from class')}</h1>",
        '<section class="meta">',
        f"<div><strong>Student</strong><br>{name_html}</div>",
        f"<div><strong>Grade</strong><br>{_esc(report.get('grade_level'))}</div>",
        f"<div><strong>Reporting period</strong><br>{_esc(report.get('reporting_period'))}</div>",
        "</section>",
    ]
    if opening:
        parts.append(f"<p>{_esc(opening)}</p>")
    parts.append("<h2>Strengths</h2>")
    parts.append(_bullets(
        report.get("strengths") or [],
        "We are still collecting classroom observations for this section.",
    ))
    parts.append("<h2>Growth areas</h2>")
    parts.append(_bullets(
        report.get("growth_areas") or [],
        "None noted for this period.",
    ))
    parts.append("<h2>Next steps — things to try at home</h2>")
    parts.append(_bullets(
        report.get("home_activities") or [],
        "None noted for this period.",
    ))
    parts.append('<section class="signature">')
    if from_label:
        parts.append(f"<p>&mdash; {_esc(from_label)}</p>")
    parts.append('<div class="line"></div>')
    parts.append('<p class="label">Teacher signature / date</p>')
    parts.append("</section>")
    parts.append("</article></body></html>")
    return "\n".join(parts)
