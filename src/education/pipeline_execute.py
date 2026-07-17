"""
Education EXECUTE step — Gap 4, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Wires ContentDifferentiator / TeacherGuideGenerator / StudentLensStore /
AssessmentGenerator into the governed pipeline at the EXECUTE step — after
CLASSIFY, before REASON — via the node-to-module map specified there:

    LV-CUR-002 (differentiation) -> ContentDifferentiator.generate_from_documents
    LV-TCH-002 (grouping)        -> TeacherGuideGenerator.generate + build_cross_level_groups
    LV-STU-003 (RTI)             -> StudentLensStore.evaluate_rti_rules (public wrapper)
    LV-ASS-001 (assessment)      -> AssessmentGenerator.generate

Duck-typed injection, same pattern as `document_retriever`
(src/education/document_retrieval.py): `src/pipeline.py` never imports
this module directly. It calls `.execute(riu_id, query) -> Optional[
ExecutionResult]` on whatever object was passed as `education_executor`
at `Pipeline(...)` construction, keeping the core pipeline decoupled from
any single vertical.

Missing-data fallback is the load-bearing part of this module, not a
nicety. Every one of these four modules needs real, already-recorded
data (an ingested curriculum document, a student's observation history,
a class roster) that plausibly does not exist yet on a fresh install.
When it doesn't, `execute()` returns a structured, honest "I need X
first" message (`status="missing_data"`) instead of silently falling
through to a generic answer that LOOKS grounded but isn't — a
wrong-looking-right answer is worse than an honest "I don't have this
yet" for this audience. `ContentDifferentiator.generate_from_documents()`
has its own silent template fallback for other callers (an empty
document store must never block a teacher from getting SOME pack) —
this module explicitly intercepts that by checking `ContentPack
.source_mode`, which the spec confirms is `"generated"` when that
fallback fired, and treats it as missing data rather than surfacing the
templated pack as if it were grounded in the teacher's own material.

All rendering here is deterministic string assembly — no model call, no
hallucination risk — matching the no-LLM pattern already used by every
other education module (content_differentiator.py, teacher_guide.py,
trend_analysis.py, weekly_recommendation.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.education.content_differentiator import ContentDifferentiator, ContentPack, LessonInput
from src.education.teacher_guide import TeacherGuideGenerator
from src.education.assessment_generator import AssessmentGenerator
from src.education.student_lens import StudentLensStore, LensNotFoundError


# Node-to-module map, verified against ontology/education/*.yaml:
#   LV-CUR-002 = curriculum.yaml "Differentiation Layer"
#   LV-TCH-002 = teacher.yaml "Flexible Grouping"
#   LV-STU-003 = student.yaml "Support Classification (RTI)"
#   LV-ASS-001 = assessment.yaml "Assessment Design"
NODE_HANDLERS = {
    "LV-CUR-002": "_execute_differentiation",
    "LV-TCH-002": "_execute_grouping",
    "LV-STU-003": "_execute_rti",
    "LV-ASS-001": "_execute_assessment",
}

NO_CURRICULUM_MESSAGE = (
    "I don't have curriculum content matching this lesson yet — upload the "
    "curriculum PDF for this lesson first (drop it in the upload bar above), "
    "then ask me again."
)
NO_STUDENTS_MESSAGE = (
    "I don't have any student records yet — log at least one observation for "
    "your students first, then ask me again."
)
NO_STUDENT_IDENTIFIED_MESSAGE = (
    "I couldn't tell which student you mean — include the student's name or "
    "ID in your question, then ask me again."
)


@dataclass
class ExecutionResult:
    riu_id: str
    status: str  # "ok" | "missing_data"
    markdown: str


def _guess_lesson(query: str) -> LessonInput:
    """
    Best-effort LessonInput from a free-text chat query.

    There is no structured lesson-intake form yet — a teacher just types a
    question. This heuristic exists only to give the differentiation/
    assessment/grouping modules a plausible title/topic to hang generic
    framing (learning-objective verbs, tier labels) on. It never claims to
    be grounded in real curriculum content by itself — that claim is only
    made when `ContentPack.source_mode == "adapted"`, which depends on
    real document retrieval succeeding, not on this heuristic.
    """
    topic = (query or "").strip()[:120] or "this lesson"
    return LessonInput(
        ib_programme="MYP",
        subject="General",
        unit_title=topic,
        topic=topic,
        atl_skills=[],
        cefr_target="B1",
        duration_minutes=40,
    )


def _differentiation_markdown(pack: ContentPack) -> str:
    title = pack.lesson.get("unit_title") or pack.lesson.get("topic") or "Lesson"
    lines = [f"# Differentiated Content: {title}", ""]
    for tier in ("foundational", "on_track", "extended"):
        data = pack.tiers[tier]
        lines.append(f"## {tier.replace('_', ' ').title()} (CEFR {data['cefr_target']})")
        lines.append("")
        lines.append(f"**Learning objective**: {data['learning_objective']}")
        lines.append("")
        if data.get("vocabulary_list"):
            terms = ", ".join(v["term"] for v in data["vocabulary_list"])
            lines.append(f"**Vocabulary**: {terms}")
            lines.append("")
        for task in data["tasks"]:
            lines.append(f"- _{task['type'].replace('_', ' ')}_: {task['prompt']}")
        lines.append("")
    if pack.source_mode == "adapted" and pack.source_provenance:
        lines.append("## Source Material")
        lines.append("")
        for prov in pack.source_provenance:
            page_start = prov.get("page_start", "?")
            page_end = prov.get("page_end", page_start)
            loc = f"{prov.get('source_file', '?')} p.{page_start}"
            if page_end != page_start:
                loc += f"-{page_end}"
            lines.append(f"- {loc} — {prov.get('section', '?')}")
        lines.append("")
    return "\n".join(lines)


def _rti_markdown(student_id: str, lens: dict, escalations: list[dict]) -> str:
    display_name = lens.get("display_name") or student_id
    lines = [
        f"# RTI Status: {display_name}",
        "",
        f"Current tier: **Tier {lens.get('rti_current_tier', 1)}**",
        f"CEFR trajectory (30d): {lens.get('cefr_trajectory_30d', 'insufficient_data')}",
        "",
        "## CEFR Snapshot",
        "",
    ]
    # A freshly created lens (student_lens.StudentLensStore.create_lens())
    # seeds cefr_snapshot with every dimension present but set to None —
    # a non-empty dict that still means "nothing observed yet". Filter to
    # observed dimensions before deciding, so a brand-new lens renders the
    # honest "no observations" line instead of four literal "None"s.
    cefr_snapshot = {
        dim: level for dim, level in (lens.get("cefr_snapshot") or {}).items() if level
    }
    if cefr_snapshot:
        for dimension, level in cefr_snapshot.items():
            lines.append(f"- {dimension}: {level}")
    else:
        lines.append("- No CEFR observations recorded yet.")
    lines.append("")
    lines.append("## Rule Evaluation (Rules A-E, observation-capture.md Stage 6)")
    lines.append("")
    if escalations:
        for e in escalations:
            lines.append(f"- Rule {e['rule']}: {e['action']} (from observation `{e['trigger_observation_id']}`)")
    else:
        lines.append("- No escalation rules currently triggered.")
    lines.append("")
    lines.append(
        "_Tier movement is always a human decision — this evaluation flags "
        "signals only._"
    )
    return "\n".join(lines)


def _find_student(query: str, roster: list[dict]) -> Optional[dict]:
    """
    Identify which roster student a free-text query is about, by looking
    for their student_id or display_name as a substring of the query.
    There is no structured "which student" field on a chat query — this is
    a deliberately narrow heuristic (exact-ish name/ID mention), not a
    general entity-resolution system. Ambiguous or zero matches both fall
    through to the honest missing-data message rather than guessing.
    """
    q = (query or "").lower()
    matches = [
        s for s in roster
        if (s.get("student_id") and s["student_id"].lower() in q)
        or (s.get("display_name") and s["display_name"].lower() in q)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


class EducationExecutor:
    """
    Duck-typed `education_executor` for `Pipeline(education_executor=...)`.

    Each `execute()` call opens and closes its own StudentLensStore SQLite
    connection — same per-call lifecycle already used for
    `document_retriever` elsewhere in this pipeline (see
    `src.lingua_viva.ingest.document_retriever`), rather than holding a
    long-lived connection across queries.
    """

    def __init__(self, document_retriever=None, student_lens_store_factory=None):
        self.document_retriever = document_retriever
        self._student_lens_store_factory = student_lens_store_factory or StudentLensStore

    def execute(self, riu_id: str, query: str) -> Optional[ExecutionResult]:
        handler_name = NODE_HANDLERS.get(riu_id)
        if handler_name is None:
            return None
        return getattr(self, handler_name)(riu_id, query)

    # -- LV-CUR-002 ---------------------------------------------------

    def _execute_differentiation(self, riu_id: str, query: str) -> ExecutionResult:
        if self.document_retriever is None:
            return ExecutionResult(riu_id, "missing_data", NO_CURRICULUM_MESSAGE)
        lesson = _guess_lesson(query)
        pack = ContentDifferentiator().generate_from_documents(
            lesson, self.document_retriever, domain="curriculum", query=query,
        )
        if pack.source_mode != "adapted":
            # generate_from_documents() falls back to the template path
            # silently when nothing was retrieved — intercept that here
            # rather than presenting a templated pack as grounded.
            return ExecutionResult(riu_id, "missing_data", NO_CURRICULUM_MESSAGE)
        return ExecutionResult(riu_id, "ok", _differentiation_markdown(pack))

    # -- LV-TCH-002 -----------------------------------------------------

    def _execute_grouping(self, riu_id: str, query: str) -> ExecutionResult:
        store = self._student_lens_store_factory()
        try:
            roster = store.list_lenses()
        finally:
            store.close()
        if not roster:
            return ExecutionResult(riu_id, "missing_data", NO_STUDENTS_MESSAGE)

        differentiator = ContentDifferentiator()
        assignments = {
            s["student_id"]: differentiator.assign_tier_for_student(s) for s in roster
        }
        pack = differentiator.generate(_guess_lesson(query))
        guide = TeacherGuideGenerator().generate(pack, roster, assignments)
        return ExecutionResult(riu_id, "ok", guide.to_markdown())

    # -- LV-STU-003 -----------------------------------------------------

    def _execute_rti(self, riu_id: str, query: str) -> ExecutionResult:
        store = self._student_lens_store_factory()
        try:
            roster = store.list_lenses()
            student = _find_student(query, roster)
            if student is None:
                return ExecutionResult(riu_id, "missing_data", NO_STUDENT_IDENTIFIED_MESSAGE)
            student_id = student["student_id"]
            try:
                lens = store.get_lens(student_id)
            except LensNotFoundError:
                return ExecutionResult(
                    riu_id, "missing_data",
                    f"I don't have a record for {student_id} yet — log an "
                    "observation first, then ask me again.",
                )
            if not lens.get("rti_tier_history"):
                return ExecutionResult(
                    riu_id, "missing_data",
                    f"I don't have enough observation history for {student_id} "
                    "yet to evaluate RTI rules — log an observation first, "
                    "then ask me again.",
                )
            escalations = store.evaluate_rti_rules(student_id)
        finally:
            store.close()
        return ExecutionResult(riu_id, "ok", _rti_markdown(student_id, lens, escalations))

    # -- LV-ASS-001 -----------------------------------------------------

    def _execute_assessment(self, riu_id: str, query: str) -> ExecutionResult:
        if self.document_retriever is None:
            return ExecutionResult(riu_id, "missing_data", NO_CURRICULUM_MESSAGE)
        lesson = _guess_lesson(query)
        pack = ContentDifferentiator().generate_from_documents(
            lesson, self.document_retriever, domain="curriculum", query=query,
        )
        if pack.source_mode != "adapted":
            # Same guard as LV-CUR-002 — depends on LV-CUR-002 having real
            # source material; a templated pack must not be assessed as if
            # it were the teacher's own curriculum.
            return ExecutionResult(riu_id, "missing_data", NO_CURRICULUM_MESSAGE)
        assessment = AssessmentGenerator().generate(pack)
        return ExecutionResult(riu_id, "ok", assessment.to_markdown())
