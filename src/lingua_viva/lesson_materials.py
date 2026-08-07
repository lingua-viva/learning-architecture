"""
Differentiated Lesson Materials Generator — SPEC_LV_LESSON_MATERIALS_2026-08-01.

Takes a lesson + roster, groups students by differentiation tier (same
tier-assignment logic as cohort planning), and calls the reasoning engine to
produce actual STUDENT-FACING exercise content per tier — the worksheets the
cohort planner's teacher guide talks about but never produces.

Privacy contract (hard rules from the build prompt):
- The LLM prompt NEVER contains student names, RTI tiers, trauma flags,
  support-profile details, or observation transcripts. The only context sent
  is: tier name, CEFR level, subject, topic, duration, scaffolding level,
  and a student COUNT.
- Student IDs appear only in response metadata (which students got which
  tier), never in generated content.
- All generated text passes the same UNSAFE_STUDENT_COPY + trauma-safety
  validation used by help_artifacts, plus a roster-name scan mirroring
  cohort_planning.validate_plan_safety.
- Materials are always draft until a teacher approves them.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.education.content_differentiator import (
    TIERS,
    ContentDifferentiator,
    LessonInput,
    _cefr_shift,
)
from src.education.help_artifacts import _validate_safe_text
from src.lingua_viva.messages import no_model_message
from src.lingua_viva.config import lv_home

SYSTEM_PROMPT = (
    "You are a curriculum materials writer for an international school. You produce "
    "student-facing exercises — clear, age-appropriate, and scaffolded to the "
    "specified CEFR level. Never mention student names, RTI tiers, AI, or diagnostic "
    "information. Write in the language of instruction unless the exercise specifically "
    "practices the target language."
)

# Per-tier generation parameters: CEFR shift relative to the lesson target,
# scaffolding description sent to the LLM, and the deterministic (local-only,
# never LLM-generated) teacher note template.
TIER_PROFILES = {
    "foundational": {
        "cefr_shift": -1,
        "scaffolding_description": (
            "heavy (word banks, sentence starters, visual cue placeholders)"
        ),
        "teacher_note": (
            "Heavy-scaffolding tier. Offer a model first; allow pointing, "
            "drawing, or L1 responses."
        ),
    },
    "on_track": {
        "cefr_shift": 0,
        "scaffolding_description": "moderate (one model example, then independent)",
        "teacher_note": (
            "Moderate-scaffolding tier. Walk through the model example "
            "together, then release to independent practice."
        ),
    },
    "extended": {
        "cefr_shift": +1,
        "scaffolding_description": "minimal (open-ended, peer discussion)",
        "teacher_note": (
            "Minimal-scaffolding tier. Invite transfer to new contexts; ask "
            "for evidence, not speed."
        ),
    },
}


@dataclass
class TierMaterial:
    tier: str                        # "foundational" | "on_track" | "extended"
    student_ids: list[str]           # which students are assigned here
    title: str
    instructions_for_student: str
    exercise_body: str
    scaffolding: list[str]
    teacher_note: str


@dataclass
class LessonMaterialsResult:
    materials: list[TierMaterial]
    lesson_summary: str
    sync_status: str  # "pushed_to_drive" | "drive_not_configured" | "push_failed" | "not_requested"


def assign_tier_groups(
    store,
    teacher_id: str,
    student_ids: list[str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Group the teacher's roster (or the requested subset) by content tier.

    Returns ({tier: [student_id, ...]}, [display_name, ...]). Display names
    are used only for the post-generation name-leak scan — they are never
    put anywhere near an LLM prompt.

    Same roster-authorization semantics as cohort_planning.generate_cohort_plan:
    requesting a student outside the teacher's roster raises PermissionError.
    """
    roster = store.list_lenses_for_teacher(teacher_id)
    roster_by_id = {str(lens.get("student_id")): lens for lens in roster}
    if student_ids:
        requested = [str(sid) for sid in student_ids if str(sid).strip()]
        unknown = sorted(sid for sid in requested if sid not in roster_by_id)
        if unknown:
            raise PermissionError(f"unauthorized_student_ids:{','.join(unknown)}")
        roster = [roster_by_id[sid] for sid in requested]

    diff = ContentDifferentiator()
    groups: dict[str, list[str]] = {tier: [] for tier in TIERS}
    names: list[str] = []
    for lens in roster:
        student_id = str(lens.get("student_id") or "")
        if not student_id:
            continue
        groups[diff.assign_tier_for_student(lens)].append(student_id)
        display_name = str(lens.get("display_name") or "").strip()
        if display_name:
            names.append(display_name)
    return groups, names


def _tier_prompt(tier: str, lesson: LessonInput, student_count: int) -> str:
    profile = TIER_PROFILES[tier]
    cefr_for_tier = _cefr_shift(lesson.cefr_target, profile["cefr_shift"])
    return (
        f"Create a {tier}-tier worksheet for this lesson:\n"
        f"- Subject: {lesson.subject}\n"
        f"- Topic: {lesson.topic}\n"
        f"- CEFR target for this tier: {cefr_for_tier}\n"
        f"- Duration: {lesson.duration_minutes} minutes\n"
        f"- Scaffolding level: {profile['scaffolding_description']}\n"
        f"- Students at this tier: {student_count}\n"
        "\n"
        "Output exactly this format:\n"
        "TITLE: (a short, student-friendly title)\n"
        "INSTRUCTIONS: (1-3 sentences telling the student what to do)\n"
        "EXERCISE:\n"
        "(the main activity — 5-15 lines of actual exercise content)\n"
        "SCAFFOLDING NOTES: (comma-separated list of supports included)\n"
    )


def _parse_material_response(text: str, tier: str, lesson: LessonInput) -> dict:
    """Parse the TITLE/INSTRUCTIONS/EXERCISE/SCAFFOLDING NOTES format.

    Tolerant of missing sections — a model that drifts from the format still
    yields a usable material (whole response becomes the exercise body)
    rather than a crash. Safety validation runs after parsing either way.
    """
    text = str(text or "").strip()
    title_match = re.search(r"^\s*TITLE:\s*(.+)$", text, re.MULTILINE)
    instructions_match = re.search(r"^\s*INSTRUCTIONS:\s*(.+?)(?=^\s*EXERCISE\s*:|\Z)", text, re.MULTILINE | re.DOTALL)
    exercise_match = re.search(r"^\s*EXERCISE\s*:\s*\n?(.*?)(?=^\s*SCAFFOLDING NOTES\s*:|\Z)", text, re.MULTILINE | re.DOTALL)
    scaffolding_match = re.search(r"^\s*SCAFFOLDING NOTES:\s*(.+)$", text, re.MULTILINE)

    title = (title_match.group(1).strip() if title_match else f"{lesson.topic} — {tier.replace('_', ' ').title()} Practice")
    instructions = instructions_match.group(1).strip() if instructions_match else ""
    exercise = exercise_match.group(1).strip() if exercise_match else ""
    if not exercise:
        exercise = text
    scaffolding = (
        [item.strip() for item in scaffolding_match.group(1).split(",") if item.strip()]
        if scaffolding_match
        else []
    )
    return {
        "title": title,
        "instructions": instructions,
        "exercise": exercise,
        "scaffolding": scaffolding,
    }


def _check_roster_names(material: TierMaterial, roster_names: list[str]) -> None:
    """Mirror cohort_planning.validate_plan_safety's name scan: no roster
    student's display name may appear in student-facing generated text."""
    student_facing = " ".join(
        [material.title, material.instructions_for_student, material.exercise_body]
        + material.scaffolding
    ).lower()
    for name in roster_names:
        name = name.strip()
        if len(name) >= 3 and name.lower() in student_facing:
            raise ValueError("student_name_in_generated_content")


async def _generate_tier_material(
    engine,
    tier: str,
    lesson: LessonInput,
    student_ids: list[str],
) -> TierMaterial:
    prompt = _tier_prompt(tier, lesson, len(student_ids))
    result = await engine.reason(prompt, context={}, system_prompt=SYSTEM_PROMPT)

    content = getattr(result, "content", "") or ""
    model_used = str(getattr(result, "model_used", "") or "")
    error = str(getattr(result, "error", "") or "")
    if error or model_used.startswith("none") or content.startswith("[Local reasoning"):
        # P1-2 (Claudia QA 2026-08-03): the detail string is shown to the
        # teacher via the 422 response — use the shared setup message
        # instead of assuming she knows what Ollama is.
        raise ValueError(f"generation_failed:{tier}: {no_model_message()}")

    parsed = _parse_material_response(content, tier, lesson)
    note = TIER_PROFILES[tier]["teacher_note"]
    if student_ids:
        teacher_note = f"{len(student_ids)} student(s) assigned. {note}"
    else:
        teacher_note = f"No students currently at this tier. {note}"

    material = TierMaterial(
        tier=tier,
        student_ids=list(student_ids),
        title=parsed["title"],
        instructions_for_student=parsed["instructions"],
        exercise_body=parsed["exercise"],
        scaffolding=parsed["scaffolding"],
        teacher_note=teacher_note,
    )
    # Same safety bar as help_artifacts student copy: unsafe markers +
    # trauma-informed guardrails, applied to everything we return.
    _validate_safe_text(
        material.title,
        material.instructions_for_student,
        material.exercise_body,
        material.teacher_note,
        *material.scaffolding,
    )
    return material


def _materials_markdown(lesson: LessonInput, materials: list[TierMaterial]) -> str:
    return render_printable_packet_markdown(lesson, materials, status="DRAFT")


def _tier_display(tier: str) -> str:
    return {
        "foundational": "Foundational Practice",
        "on_track": "Core Practice",
        "extended": "Extension Practice",
    }.get(tier, tier.replace("_", " ").title())


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:60] or "lesson"


def render_printable_packet_markdown(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    status: str = "DRAFT",
) -> str:
    """Teacher-reviewable printable packet.

    The packet is Markdown on purpose: teachers can print it directly,
    paste it into a school doc, or share the approved file to Drive without
    requiring PDF tooling. Student handouts are separated by horizontal
    rules and contain no student names, RTI labels, or internal process
    language.
    """
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Printable Lesson Packet - {lesson.topic}",
        "",
        "## Teacher Cover Page",
        "",
        f"- Subject: {lesson.subject}",
        f"- Unit: {lesson.unit_title}",
        f"- Topic: {lesson.topic}",
        f"- CEFR target: {lesson.cefr_target}",
        f"- Duration: {lesson.duration_minutes} minutes",
        f"- Status: {status} - teacher review required before classroom use",
        "",
        "### Distribution",
        "",
    ]
    for material in materials:
        lines.append(
            f"- {_tier_display(material.tier)}: {len(material.student_ids)} assigned student(s). "
            f"{material.teacher_note}"
        )
    lines.extend([
        "",
        "### Review Checklist",
        "",
        "- Confirm the language level is appropriate.",
        "- Replace or remove any classroom detail that does not fit today's lesson.",
        "- Print only the handout section each group should receive.",
        "",
    ])
    for material in materials:
        lines.extend([
            "---",
            "",
            f"# Student Handout - {_tier_display(material.tier)}",
            "",
            f"## {material.title}",
            "",
            "### Learning Goal",
            "",
            f"- {lesson.topic}",
            "",
            "### Instructions",
            "",
            material.instructions_for_student or "Complete the activity below.",
            "",
            "### Activity",
            "",
            material.exercise_body,
            "",
        ])
        if material.scaffolding:
            lines.extend([
                "### Support",
                "",
                ", ".join(material.scaffolding),
                "",
            ])
        lines.extend([
            "### Exit Ticket",
            "",
            "- Write one sentence about what you practiced today.",
            "",
        ])
    lines.append(f"*Teacher copy generated by Lingua Viva - {generated}*")
    packet = "\n".join(lines)
    _validate_printable_packet(packet)
    return packet


def _validate_printable_packet(markdown: str) -> None:
    lowered = markdown.lower()
    forbidden = (" rti ", "diagnostic", "generated by ai", "[", "]", "student_ids")
    for token in forbidden:
        if token in lowered:
            raise ValueError("unsafe_or_placeholder_printable_packet")
    if markdown.count("# Student Handout -") != len(TIERS):
        raise ValueError("printable_packet_missing_tier_handout")
    if "### Activity" not in markdown or "### Exit Ticket" not in markdown:
        raise ValueError("printable_packet_missing_student_work")


def lesson_packet_dir() -> Path:
    override = os.environ.get("LV_LESSON_PACKET_DIR")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "lesson_packets"


def lesson_packet_filename(lesson: LessonInput) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"lesson-packet-{_safe_slug(lesson.topic)}-{stamp}.md"


def write_printable_packet(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    directory: Path | None = None,
) -> Path:
    target_dir = directory or lesson_packet_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / lesson_packet_filename(lesson)
    markdown = render_printable_packet_markdown(lesson, materials, status="APPROVED")
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def printable_packet_hash(markdown: str) -> str:
    return hashlib.sha256(str(markdown or "").encode("utf-8")).hexdigest()


def material_from_dict(data: dict) -> TierMaterial:
    return TierMaterial(
        tier=str(data.get("tier") or ""),
        student_ids=[str(item) for item in data.get("student_ids", []) if str(item).strip()]
        if isinstance(data.get("student_ids"), list)
        else [],
        title=str(data.get("title") or ""),
        instructions_for_student=str(data.get("instructions_for_student") or ""),
        exercise_body=str(data.get("exercise_body") or ""),
        scaffolding=[str(item) for item in data.get("scaffolding", []) if str(item).strip()]
        if isinstance(data.get("scaffolding"), list)
        else [],
        teacher_note=str(data.get("teacher_note") or ""),
    )


def _drive_filename(lesson: LessonInput) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", lesson.topic.lower()).strip("-")[:60] or "lesson"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"lesson-materials_{slug}_{stamp}.md"


async def _push_materials_to_drive(lesson: LessonInput, materials: list[TierMaterial]) -> str:
    from src.lingua_viva.drive_sync import get_sync_folder_id

    folder_id = get_sync_folder_id()
    if not folder_id:
        return "drive_not_configured"
    try:
        from src.lingua_viva.google_drive_integration import upload_text_to_folder

        await asyncio.to_thread(
            upload_text_to_folder,
            folder_id=folder_id,
            filename=_drive_filename(lesson),
            content=_materials_markdown(lesson, materials),
            mime_type="text/markdown",
        )
        return "pushed_to_drive"
    except Exception:
        return "push_failed"


async def generate_lesson_materials(
    lesson: LessonInput,
    student_ids: list[str] | None = None,
    teacher_id: str = "local-teacher",
    push_to_drive: bool = True,
    store=None,
    engine=None,
    tier_groups: dict[str, list[str]] | None = None,
    roster_names: list[str] | None = None,
) -> LessonMaterialsResult:
    """Generate tier-differentiated student-facing materials for a lesson.

    `store`/`engine` are injectable for tests (mocked LLM). The web layer
    passes precomputed `tier_groups`/`roster_names` instead of a store:
    StudentLensStore's sqlite connection is thread-bound, so the whole
    store phase must run inside one thread — when no groups are given,
    open + assign + close happens in a single to_thread hop here.
    """
    errors = lesson.validate()
    if errors:
        raise ValueError(f"Invalid LessonInput: {errors}")

    if tier_groups is None:
        def _load() -> tuple[dict[str, list[str]], list[str]]:
            own_store = store is None
            active = store
            if own_store:
                from src.education.student_lens import StudentLensStore

                active = StudentLensStore()
            try:
                return assign_tier_groups(active, teacher_id, student_ids)
            finally:
                if own_store:
                    active.close()

        tier_groups, roster_names = await asyncio.to_thread(_load)
    groups = tier_groups
    roster_names = roster_names or []

    if engine is None:
        from src.lingua_viva.reasoning import ReasoningEngine

        engine = ReasoningEngine()

    # All three tiers always generate (even with no students assigned) so a
    # teacher planning ahead still gets the full set — matches the spec's
    # example output. The three LLM calls run in parallel.
    materials = list(
        await asyncio.gather(
            *(_generate_tier_material(engine, tier, lesson, groups[tier]) for tier in TIERS)
        )
    )
    for material in materials:
        _check_roster_names(material, roster_names)

    if not push_to_drive:
        sync_status = "not_requested"
    else:
        sync_status = await _push_materials_to_drive(lesson, materials)

    lesson_summary = (
        f"{lesson.topic} ({lesson.cefr_target} target, {lesson.duration_minutes}min)"
    )
    return LessonMaterialsResult(
        materials=materials,
        lesson_summary=lesson_summary,
        sync_status=sync_status,
    )


def materials_as_dicts(result: LessonMaterialsResult | list[TierMaterial]) -> list[dict]:
    materials = result if isinstance(result, list) else result.materials
    return [asdict(material) for material in materials]
