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
import html
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.education.content_differentiator import (
    TIERS,
    ContentDifferentiator,
    LessonInput,
    _cefr_shift,
)
from src.education.help_artifacts import _validate_safe_text
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
            "heavy (word banks, sentence starters, concrete visual cue labels)"
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

PLACEHOLDER_OUTPUT_RE = re.compile(
    r"\[[^\]\n]*(?:no model available|Local reasoning|stub|placeholder)[^\]\n]*\]",
    re.I,
)


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
class IndividualSupportStudent:
    student_id: str
    display_name: str
    reason: str


@dataclass
class RosterPlacement:
    student_id: str
    display_name: str
    source: str


@dataclass
class LessonMaterialsResult:
    materials: list[TierMaterial]
    lesson_summary: str
    sync_status: str  # "pushed_to_drive" | "drive_not_configured" | "push_failed" | "not_requested"
    individual_support: list[IndividualSupportStudent] = field(default_factory=list)


@dataclass
class RosterSplit:
    tier_groups: dict[str, list[str]]
    roster_names: list[str]
    individual_support: list[IndividualSupportStudent]
    group_members: dict[str, list[RosterPlacement]] = field(default_factory=dict)
    # Teacher overrides actually applied to this split (student_id -> tier or
    # "individual_support"). Recorded so per-day assignment changes are
    # auditable, per SPEC_LV_TIERED_MATERIALS_FULL_CIRCLE G2.
    overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class CourseLibraryEntry:
    drive_id: str
    name: str
    local_path: str
    sha256: str
    pulled_at: str
    status: str


@dataclass
class LessonSelection:
    selection_id: str
    teacher_id: str
    class_id: str
    grade: str
    subject: str
    local_path: str
    selected_at: str


def lesson_materials_runtime_dir() -> Path:
    override = os.environ.get("LV_LESSON_MATERIALS_DIR")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "lesson_materials"


def course_library_root() -> Path:
    override = os.environ.get("LV_COURSE_LIBRARY_DIR")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "library"


def lesson_selection_dir() -> Path:
    override = os.environ.get("LV_LESSON_SELECTION_DIR")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "selections"


def lesson_upload_queue_path() -> Path:
    override = os.environ.get("LV_LESSON_UPLOAD_QUEUE_PATH")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "upload_queue.json"


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_json(path: Path, default: dict | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(default or {})
    return data if isinstance(data, dict) else dict(default or {})


def _is_explicit_individual_support(lens: dict) -> bool:
    profile = lens.get("support_profile") or {}
    if not isinstance(profile, dict):
        return False
    for key in (
        "needs_individual_support",
        "individual_support",
        "requires_individual_support",
    ):
        if profile.get(key) is True:
            return True
    flags = profile.get("flags")
    if isinstance(flags, dict):
        return any(
            flags.get(key) is True
            for key in ("needs_individual_support", "individual_support")
        )
    return False


def _individual_support_reason(lens: dict) -> str | None:
    try:
        if int(lens.get("rti_current_tier") or 1) == 3:
            return "rti_current_tier_3"
    except (TypeError, ValueError):
        pass
    if _is_explicit_individual_support(lens):
        return "support_profile_flag"
    return None


def _placement_source(lens: dict, tier: str) -> str:
    try:
        rti_tier = int(lens.get("rti_current_tier") or 1)
    except (TypeError, ValueError):
        rti_tier = 1
    if rti_tier == 2:
        return "rti"
    cefr_snapshot = lens.get("cefr_snapshot")
    if isinstance(cefr_snapshot, dict) and any(cefr_snapshot.values()):
        return "cefr"
    return "default"


def assign_roster_split(
    store,
    teacher_id: str,
    student_ids: list[str] | None = None,
    overrides: dict[str, str] | None = None,
    record_overrides: bool = True,
) -> RosterSplit:
    """Group the roster into three tiers plus kept-apart support.

    Individual support is deliberately narrow: RTI tier 3 or an explicit
    support-profile flag. General support notes alone do not remove a
    student from classwide materials.

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

    overrides = {
        str(key): str(value)
        for key, value in (overrides or {}).items()
        if str(value) in TIERS or str(value) == "individual_support"
    }
    diff = ContentDifferentiator()
    groups: dict[str, list[str]] = {tier: [] for tier in TIERS}
    group_members: dict[str, list[RosterPlacement]] = {tier: [] for tier in TIERS}
    names: list[str] = []
    individual_support: list[IndividualSupportStudent] = []
    applied: dict[str, str] = {}
    for lens in roster:
        student_id = str(lens.get("student_id") or "")
        if not student_id:
            continue
        display_name = str(lens.get("display_name") or "").strip()
        if display_name:
            names.append(display_name)
        if student_id in overrides:
            applied[student_id] = overrides[student_id]
            if overrides[student_id] == "individual_support":
                individual_support.append(
                    IndividualSupportStudent(
                        student_id=student_id,
                        display_name=display_name or student_id,
                        reason="teacher_override",
                    )
                )
            else:
                tier = overrides[student_id]
                groups[tier].append(student_id)
                group_members[tier].append(
                    RosterPlacement(
                        student_id=student_id,
                        display_name=display_name or student_id,
                        source="teacher_override",
                    )
                )
            continue
        reason = _individual_support_reason(lens)
        if reason:
            individual_support.append(
                IndividualSupportStudent(
                    student_id=student_id,
                    display_name=display_name or student_id,
                    reason=reason,
                )
            )
            continue
        tier = diff.assign_tier_for_student(lens)
        groups[tier].append(student_id)
        group_members[tier].append(
            RosterPlacement(
                student_id=student_id,
                display_name=display_name or student_id,
                source=_placement_source(lens, tier),
            )
        )
    if applied and record_overrides:
        record_roster_overrides(teacher_id, applied)
    return RosterSplit(
        groups,
        names,
        individual_support,
        group_members=group_members,
        overrides=applied,
    )


def roster_overrides_path() -> Path:
    override = os.environ.get("LV_ROSTER_OVERRIDES_PATH")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "roster_overrides.ndjson"


def record_roster_overrides(teacher_id: str, applied: dict[str, str]) -> None:
    """Append-only record of teacher tier overrides actually applied.

    One line per split that used overrides — dated, teacher-attributed, so
    per-day assignment changes stay auditable (spec G2: "overrides recorded").
    Contains student_ids and tier names only, never narration or lens content.
    """
    path = roster_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"recorded_at": _now_z(), "teacher_id": teacher_id, "overrides": applied},
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def assign_tier_groups(
    store,
    teacher_id: str,
    student_ids: list[str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Backward-compatible tier grouping wrapper.

    RTI tier 3 / explicitly flagged individual-support students are kept
    apart from the three classroom tiers.
    """
    split = assign_roster_split(store, teacher_id, student_ids)
    return split.tier_groups, split.roster_names


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


def _deterministic_material_fields(tier: str, lesson: LessonInput) -> dict:
    """Last-resort tier copy when a model emits placeholder-shaped text."""
    title = f"{lesson.topic} - {_tier_display(tier)} Practice"
    if tier == "foundational":
        instructions = "Use the word bank and model sentence first, then try two short answers."
        exercise = (
            f"1. Read the model sentence about {lesson.topic}.\n"
            "2. Circle three useful words.\n"
            "3. Complete two sentence starters.\n"
            "4. Share one answer with a partner."
        )
        scaffolding = ["word bank", "sentence starters", "visual cue labels"]
    elif tier == "extended":
        instructions = "Work independently, then add one reason or follow-up question."
        exercise = (
            f"1. Write three connected sentences about {lesson.topic}.\n"
            "2. Add one detail that explains your thinking.\n"
            "3. Ask a partner one follow-up question.\n"
            "4. Revise one sentence for precision."
        )
        scaffolding = ["open-ended prompt", "peer discussion"]
    else:
        instructions = "Read the model, then complete the practice independently."
        exercise = (
            f"1. Read the example about {lesson.topic}.\n"
            "2. Write three complete practice sentences.\n"
            "3. Check that each sentence answers the task.\n"
            "4. Choose one sentence to share."
        )
        scaffolding = ["model example"]
    return {"title": title, "instructions": instructions, "exercise": exercise, "scaffolding": scaffolding}


def _has_placeholder_output(parsed: dict) -> bool:
    values = [
        str(parsed.get("title") or ""),
        str(parsed.get("instructions") or ""),
        str(parsed.get("exercise") or ""),
        " ".join(str(item) for item in parsed.get("scaffolding") or []),
    ]
    return any(PLACEHOLDER_OUTPUT_RE.search(value) for value in values)


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
        parsed = _deterministic_material_fields(tier, lesson)
    else:
        parsed = _parse_material_response(content, tier, lesson)
    if _has_placeholder_output(parsed):
        parsed = _deterministic_material_fields(tier, lesson)
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
        "foundational": "Foundational",
        "on_track": "On Track",
        "extended": "Extended",
    }.get(tier, tier.replace("_", " ").title())


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:60] or "lesson"


def _safe_library_filename(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name).strip(" .")
    return candidate or "lesson.txt"


def _library_dir(grade: str, subject: str) -> Path:
    return course_library_root() / _safe_slug(grade) / _safe_slug(subject)


def _library_manifest_path(grade: str, subject: str) -> Path:
    return _library_dir(grade, subject) / "manifest.json"


def pull_course_library(folder_id: str, grade: str, subject: str) -> dict:
    """Mirror a Drive coursework folder into the local read-many library."""
    from src.lingua_viva.google_drive_integration import download_file_text, list_folder_files

    target_dir = _library_dir(grade, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _library_manifest_path(grade, subject)
    manifest = _read_json(manifest_path, {"files": {}})
    files_by_id = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}

    pulled: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    now = _now_z()
    for meta in list_folder_files(folder_id):
        drive_id = str(meta.get("id") or "").strip()
        name = str(meta.get("name") or drive_id).strip() or drive_id
        existing = files_by_id.get(drive_id) if isinstance(files_by_id, dict) else None
        existing_path = Path(str((existing or {}).get("local_path") or ""))
        if isinstance(existing, dict) and existing_path.exists():
            skipped.append({**existing, "status": "unchanged"})
            continue
        try:
            text = download_file_text(drive_id)
            body = text.encode("utf-8")
            digest = hashlib.sha256(body).hexdigest()
            path = target_dir / _safe_library_filename(name)
            if path.exists() and path.name != _safe_library_filename(name):
                path = target_dir / f"{path.stem}-{drive_id[:8]}{path.suffix}"
            path.write_bytes(body)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            entry = CourseLibraryEntry(
                drive_id=drive_id,
                name=name,
                local_path=str(path),
                sha256=digest,
                pulled_at=now,
                status="pulled",
            )
            files_by_id[drive_id] = asdict(entry)
            pulled.append(asdict(entry))
        except Exception as exc:
            failed.append({"drive_id": drive_id, "name": name, "status": "failed", "reason": str(exc)})

    _atomic_write_json(
        manifest_path,
        {
            "version": 1,
            "folder_id": folder_id,
            "grade": grade,
            "subject": subject,
            "updated_at": now,
            "files": files_by_id,
        },
    )
    return {
        "grade": grade,
        "subject": subject,
        "library_dir": str(target_dir),
        "manifest_path": str(manifest_path),
        "pulled": pulled,
        "skipped": skipped,
        "failed": failed,
    }


def list_course_library(grade: str, subject: str) -> dict:
    manifest_path = _library_manifest_path(grade, subject)
    manifest = _read_json(manifest_path, {"files": {}})
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    entries = []
    for entry in files.values():
        if not isinstance(entry, dict):
            continue
        path = Path(str(entry.get("local_path") or ""))
        entries.append({**entry, "exists": path.exists()})
    return {
        "grade": grade,
        "subject": subject,
        "library_dir": str(_library_dir(grade, subject)),
        "manifest_path": str(manifest_path),
        "files": sorted(entries, key=lambda item: str(item.get("name") or "").lower()),
    }


def select_todays_lesson(
    *,
    teacher_id: str,
    class_id: str,
    grade: str,
    subject: str,
    local_path: str,
) -> LessonSelection:
    path = Path(local_path).expanduser().resolve()
    library_root = course_library_root().resolve()
    if library_root not in path.parents:
        raise ValueError("lesson_file_outside_course_library")
    if not path.exists() or not path.is_file():
        raise ValueError("lesson_file_missing")
    selection = LessonSelection(
        selection_id=hashlib.sha256(
            f"{teacher_id}|{class_id}|{grade}|{subject}|{path}|{datetime.now(timezone.utc).date()}".encode("utf-8")
        ).hexdigest()[:16],
        teacher_id=teacher_id,
        class_id=class_id,
        grade=grade,
        subject=subject,
        local_path=str(path),
        selected_at=_now_z(),
    )
    target = lesson_selection_dir() / f"{_safe_slug(teacher_id)}-{_safe_slug(class_id)}-{_safe_slug(grade)}-{_safe_slug(subject)}.json"
    _atomic_write_json(target, {"version": 1, "selection": asdict(selection)})
    return selection


def read_todays_lesson_text(local_path: str) -> str:
    path = Path(local_path).expanduser().resolve()
    library_root = course_library_root().resolve()
    if library_root not in path.parents:
        raise ValueError("lesson_file_outside_course_library")
    return path.read_text(encoding="utf-8")


def render_printable_packet_markdown(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    status: str = "DRAFT",
    individual_support: list[IndividualSupportStudent] | None = None,
    include_support_section: bool = True,
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
    if individual_support and include_support_section:
        names = ", ".join(student.display_name for student in individual_support)
        lines.extend([
            "",
            "### Teacher-Only Individual Support",
            "",
            f"- Keep separate from tier packets today: {names}.",
            "- Prepare individual work directly; do not distribute this section.",
        ])
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


def render_printable_packet_html(markdown: str, *, print_ready: bool = False) -> str:
    """Render the canonical packet Markdown as readable HTML.

    This intentionally supports the packet subset we generate instead of
    adding a Markdown dependency to the desktop bundle.
    """
    body: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        if not line:
            close_list()
            continue
        if line == "---":
            close_list()
            body.append('<hr class="page-break">')
            continue
        if line.startswith("# "):
            close_list()
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
            continue
        if line.startswith("## "):
            close_list()
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
            continue
        if line.startswith("### "):
            close_list()
            body.append(f"<h3>{html.escape(line[4:])}</h3>")
            continue
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        close_list()
        body.append(f"<p>{html.escape(line)}</p>")
    close_list()
    css = """
      body { font-family: Georgia, 'Times New Roman', serif; color: #1f2933; line-height: 1.45; margin: 32px; }
      h1 { font-size: 26px; margin: 0 0 18px; }
      h2 { font-size: 20px; margin: 24px 0 10px; }
      h3 { font-size: 15px; margin: 18px 0 8px; text-transform: uppercase; letter-spacing: 0; }
      ul { margin: 0 0 14px 22px; padding: 0; }
      li { margin: 4px 0; }
      p { margin: 0 0 12px; }
      hr { border: 0; border-top: 1px solid #cfd8dc; margin: 28px 0; }
      @media print { .page-break { break-before: page; } body { margin: 18mm; } }
    """
    document = f"<style>{css}</style>\n<article class=\"lesson-packet\">\n{''.join(body)}\n</article>"
    if not print_ready:
        return document
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>Printable Lesson Packet</title></head><body>" + document + "</body></html>"


def render_shared_packet_markdown(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    status: str = "APPROVED",
) -> str:
    return render_printable_packet_markdown(
        lesson,
        materials,
        status=status,
        individual_support=[],
        include_support_section=False,
    )


def render_packet_bundle(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    status: str,
    individual_support: list[IndividualSupportStudent] | None,
) -> dict[str, str]:
    """Render teacher and student-safe packet variants at one chokepoint."""
    markdown = render_printable_packet_markdown(
        lesson,
        materials,
        status=status,
        individual_support=individual_support or [],
    )
    student_markdown = render_shared_packet_markdown(lesson, materials, status=status)
    return {
        "markdown": markdown,
        "html": render_printable_packet_html(markdown),
        "print_html": render_printable_packet_html(markdown, print_ready=True),
        "student_print_html": render_printable_packet_html(student_markdown, print_ready=True),
    }


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
    individual_support: list[IndividualSupportStudent] | None = None,
) -> Path:
    target_dir = directory or lesson_packet_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / lesson_packet_filename(lesson)
    markdown = render_printable_packet_markdown(
        lesson,
        materials,
        status="APPROVED",
        individual_support=individual_support or [],
    )
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


def _share_filename(lesson: LessonInput, suffix: str, *, grade: str = "", subject: str = "", lesson_title: str = "") -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    grade_part = _safe_slug(grade or "class")
    subject_part = _safe_slug(subject or lesson.subject)
    title_part = _safe_slug(lesson_title or lesson.topic)
    return f"{date}_{grade_part}_{subject_part}_{title_part}_tiered_packet.{suffix.lstrip('.')}"


def _folder_from_map(folder_map: dict | None, *, class_id: str, grade: str, subject: str) -> str:
    if not isinstance(folder_map, dict):
        return ""
    lesson_materials = folder_map.get("lesson_materials")
    if not isinstance(lesson_materials, dict):
        return ""
    class_map = lesson_materials.get(class_id)
    if isinstance(class_map, dict):
        grade_map = class_map.get(grade)
        if isinstance(grade_map, dict):
            subject_map = grade_map.get(subject)
            if isinstance(subject_map, dict):
                return str(subject_map.get("folder_id") or "").strip()
    return str(lesson_materials.get("default_folder_id") or "").strip()


def _queue_upload_failure(entry: dict) -> None:
    queue = _read_json(lesson_upload_queue_path(), {"queued": []})
    queued = queue.get("queued") if isinstance(queue.get("queued"), list) else []
    queued.append({**entry, "queued_at": _now_z()})
    _atomic_write_json(lesson_upload_queue_path(), {"version": 1, "queued": queued})


def share_packet_to_drive(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    folder_map: dict | None = None,
    folder_id: str = "",
    class_id: str = "default",
    grade: str = "",
    subject: str = "",
    lesson_title: str = "",
) -> dict:
    from src.lingua_viva.google_drive_integration import upload_text_to_folder
    from src.lingua_viva.privacy import assert_safe_for_external_output

    destination = (folder_id or "").strip() or _folder_from_map(
        folder_map,
        class_id=class_id,
        grade=grade,
        subject=subject or lesson.subject,
    )
    if not destination:
        result = {"status": "queued", "reason": "drive_folder_not_configured"}
        _queue_upload_failure(result)
        return result
    markdown = render_shared_packet_markdown(lesson, materials)
    html_doc = render_printable_packet_html(markdown, print_ready=True)
    assert_safe_for_external_output(markdown)
    assert_safe_for_external_output(html_doc)
    try:
        md_result = upload_text_to_folder(
            folder_id=destination,
            filename=_share_filename(lesson, "md", grade=grade, subject=subject, lesson_title=lesson_title),
            content=markdown,
            mime_type="text/markdown",
        )
        html_result = upload_text_to_folder(
            folder_id=destination,
            filename=_share_filename(lesson, "html", grade=grade, subject=subject, lesson_title=lesson_title),
            content=html_doc,
            mime_type="text/html",
        )
        return {
            "status": "pushed_to_drive",
            "folder_id": destination,
            "uploaded": {"markdown": md_result, "html": html_result},
            "support_section_stripped": True,
        }
    except Exception as exc:
        result = {"status": "queued", "folder_id": destination, "reason": str(exc)}
        _queue_upload_failure(result)
        return result


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
    individual_support: list[IndividualSupportStudent] | None = None,
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
        def _load() -> RosterSplit:
            own_store = store is None
            active = store
            if own_store:
                from src.education.student_lens import StudentLensStore

                active = StudentLensStore()
            try:
                return assign_roster_split(active, teacher_id, student_ids)
            finally:
                if own_store:
                    active.close()

        split = await asyncio.to_thread(_load)
        tier_groups = split.tier_groups
        roster_names = split.roster_names
        individual_support = split.individual_support
    groups = tier_groups
    roster_names = roster_names or []
    individual_support = individual_support or []

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
        individual_support=individual_support,
    )


def materials_as_dicts(result: LessonMaterialsResult | list[TierMaterial]) -> list[dict]:
    materials = result if isinstance(result, list) else result.materials
    return [asdict(material) for material in materials]
