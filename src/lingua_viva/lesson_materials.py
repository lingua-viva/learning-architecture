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
import uuid
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

# The 10 official IB Learner Profile attributes — model output is validated
# against this list so a hallucinated attribute never prints on a plan.
# Single source of truth: a second, identical definition sat at module level
# further down until 2026-08-27. It was a leftover from the ed20299 merge and
# was removed — two copies of a validation allowlist is one edit away from
# two different allowlists.
IB_LEARNER_PROFILE_ATTRIBUTES: tuple[str, ...] = (
    "Inquirers", "Knowledgeable", "Thinkers", "Communicators", "Principled",
    "Open-minded", "Caring", "Risk-takers", "Balanced", "Reflective",
)

SYSTEM_PROMPT = (
    "You are a curriculum materials writer for an international school. You produce "
    "student-facing exercises — clear, age-appropriate, and scaffolded to the "
    "specified CEFR level. Never mention student names, RTI tiers, AI, or diagnostic "
    "information. Write in the language of instruction unless the exercise specifically "
    "practices the target language."
)

LESSON_PLAN_SYSTEM_PROMPT = (
    "You are a curriculum planner for an Italian-immersion IB PYP elementary classroom. "
    "Return ONLY a valid JSON object for a teacher-facing lesson plan. Do not include "
    "student names, diagnoses, RTI labels, AI language, markdown, or prose outside JSON. "
    "Use only the supplied curriculum context for curriculum-standard claims."
)

LESSON_PLAN_REVISION_SYSTEM_PROMPT = (
    "You revise an existing structured lesson plan. Return ONLY the complete revised "
    "lesson-plan JSON object with the same schema. Modify only the sections requested "
    "by the teacher and preserve the rest."
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
    # STEP 10 (C2): "generated" | "template_fallback" — mirrors the Drive
    # leg's sync_status. The teacher must be able to see "AI generation did
    # not run; this is template text"; no fallback output without its signal.
    generation_status: str = "generated"


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
class CurriculumKnowledgeEntry:
    id: str
    title: str
    content: str
    citations: list[str]
    source_path: str


@dataclass
class LessonPlanArtifactResult:
    plan: dict
    html: str
    print_html: str
    markdown: str
    generation_status: str
    curriculum_sources: list[dict]
    generated_at: str


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


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _unique_library_path(directory: Path, filename: str, digest: str) -> Path:
    """Return a path that will not overwrite a different existing file."""
    base = directory / _safe_library_filename(filename)
    existing_digest = _file_sha256(base) if base.exists() else None
    if existing_digest is None or existing_digest == digest:
        return base
    stem = base.stem or "lesson"
    suffix = base.suffix
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for attempt in range(20):
        extra = "" if attempt == 0 else f"-{attempt + 1}"
        candidate = directory / f"{stem}-{stamp}-{digest[:8]}{extra}{suffix}"
        if not candidate.exists() or _file_sha256(candidate) == digest:
            return candidate
    return directory / f"{stem}-{stamp}-{digest[:8]}-{uuid.uuid4().hex[:8]}{suffix}"


def _write_private_bytes_no_overwrite(path: Path, body: bytes) -> None:
    if path.exists() and _file_sha256(path) == hashlib.sha256(body).hexdigest():
        return
    with path.open("xb") as handle:
        handle.write(body)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _snapshot_stem(key: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{key}-{stamp}-{uuid.uuid4().hex[:12]}"


def _append_snapshot_index(directory: Path, record: dict) -> None:
    index_path = directory / "index.ndjson"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        os.chmod(index_path, 0o600)
    except OSError:
        pass


def _write_immutable_json_snapshot(directory: Path, key: str, record_type: str, record: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stored_at = _now_z()
    for _ in range(20):
        path = directory / f"{_snapshot_stem(key)}.json"
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, indent=2))
            break
        except FileExistsError:
            continue
    else:
        path = directory / f"{_snapshot_stem(key)}-{uuid.uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _append_snapshot_index(
        directory,
        {
            "version": 1,
            "record_type": record_type,
            "key": key,
            "path": path.name,
            "teacher_id": record.get("teacher_id"),
            "generated_at": record.get("generated_at"),
            "stored_at": stored_at,
        },
    )
    return path


def _load_latest_json_snapshot(
    directory: Path,
    key: str,
    record_type: str,
    is_valid,
) -> dict | None:
    index_path = directory / "index.ndjson"
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if item.get("key") != key or item.get("record_type") != record_type:
            continue
        name = str(item.get("path") or "")
        if not name or Path(name).name != name:
            continue
        record = _read_json(directory / name)
        if is_valid(record):
            return record
    legacy = _read_json(directory / f"{key}.json")
    return legacy if is_valid(legacy) else None


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


def _tier_prompt(
    tier: str,
    lesson: LessonInput,
    student_count: int,
    source_excerpt: str | None = None,
) -> str:
    profile = TIER_PROFILES[tier]
    cefr_for_tier = _cefr_shift(lesson.cefr_target, profile["cefr_shift"])
    source_section = ""
    if source_excerpt:
        # The whole point of selecting a coursework file: the worksheet must
        # adapt THIS content, not invent a fresh activity from the topic name.
        source_section = (
            "\nBase the worksheet on this lesson content — adapt its "
            "vocabulary, examples, and activity, do not invent a new topic:\n"
            "--- LESSON CONTENT START ---\n"
            f"{source_excerpt}\n"
            "--- LESSON CONTENT END ---\n"
        )
    return (
        f"Create a {tier}-tier worksheet for this lesson:\n"
        f"- Subject: {lesson.subject}\n"
        f"- Topic: {lesson.topic}\n"
        f"- CEFR target for this tier: {cefr_for_tier}\n"
        f"- Duration: {lesson.duration_minutes} minutes\n"
        f"- Scaffolding level: {profile['scaffolding_description']}\n"
        f"- Students at this tier: {student_count}\n"
        f"{source_section}"
        "\n"
        "Output exactly this format and nothing else:\n"
        "TITLE: (a short, student-friendly title)\n"
        "INSTRUCTIONS: (1-2 short sentences telling the student what to do)\n"
        "EXERCISE:\n"
        "(the main activity — 5 to 8 short lines of actual exercise content)\n"
        "SCAFFOLDING NOTES: (comma-separated list of supports included)\n"
        "\n"
        # C8 (teacher-readiness): a small local model must finish inside the
        # 60s reasoning budget even with three tier calls queued on one
        # Ollama. Keep the requested output short and bound it hard.
        "Keep the entire response under 120 words.\n"
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


def _has_blank_output(parsed: dict) -> bool:
    """STEP 10 (C3): a parse that yields blank instructions or a blank
    exercise is a failed generation, not a material. This was the blank
    foundational tier: empty model content flowed through the tolerant
    parser into empty fields that the placeholder regex never matched."""
    return not str(parsed.get("instructions") or "").strip() or not str(parsed.get("exercise") or "").strip()


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


# STEP 12 (C5, SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19): cap RE-DERIVED from
# measurement on the governed auto-pick (nemotron-3.5-lightning, resident),
# 2026-08-19. Ollama serializes the three "parallel" tier calls, so the worst
# call runs ~3x a single call against the 60s per-call budget. Measured worst
# call (3-tier, 400 max_tokens): 1500 chars -> 36.0s; 2000 -> 58.8s;
# 2400 -> 55.0s; 3000 -> TIMEOUT. Run-to-run variance (~±10s, generation-
# length noise) puts everything >=2000 within noise of the timeout; 1500 is
# the only point with real margin (24s — enough to absorb a cold model load).
# Raising this cap trades "more source grounding" for flaky on-surface
# template_fallback failures. Re-derive if the timeout budget or the governed
# model class changes.
_SOURCE_EXCERPT_CHARS = 1500


def _source_excerpt(source_text: str | None) -> str | None:
    """Bound the lesson-content excerpt so three parallel tier calls still
    fit a small local model's 60s budget (same C8 constraint as the <120-word
    output cap)."""
    if not source_text:
        return None
    text = str(source_text).strip()
    if not text:
        return None
    if len(text) <= _SOURCE_EXCERPT_CHARS:
        return text
    cut = text[:_SOURCE_EXCERPT_CHARS]
    if " " in cut:
        cut = cut.rsplit(None, 1)[0]
    return cut + " …"


async def _generate_tier_material(
    engine,
    tier: str,
    lesson: LessonInput,
    student_ids: list[str],
    source_excerpt: str | None = None,
) -> TierMaterial:
    prompt = _tier_prompt(tier, lesson, len(student_ids), source_excerpt)
    # max_tokens matches the slimmed prompt's <120-word ask: 400 tokens is
    # generous headroom for the four sections while capping the generation
    # time that made qwen2.5:3b blow the 60s budget (C8 root cause).
    result = await engine.reason(prompt, context={}, system_prompt=SYSTEM_PROMPT, max_tokens=400)

    content = getattr(result, "content", "") or ""
    model_used = str(getattr(result, "model_used", "") or "")
    error = str(getattr(result, "error", "") or "")
    generation_status = "generated"
    if error or model_used.startswith("none") or content.startswith("[Local reasoning"):
        parsed = _deterministic_material_fields(tier, lesson)
        generation_status = "template_fallback"
    else:
        parsed = _parse_material_response(content, tier, lesson)
    if _has_placeholder_output(parsed) or _has_blank_output(parsed):
        parsed = _deterministic_material_fields(tier, lesson)
        generation_status = "template_fallback"
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
        generation_status=generation_status,
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
            path = _unique_library_path(target_dir, name, digest)
            _write_private_bytes_no_overwrite(path, body)
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


_LOCAL_IMPORT_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".csv", ".xlsx"}


def pull_local_folder(folder_path: str, grade: str, subject: str) -> dict:
    """Import lesson files from a local folder into the course library.

    Same downstream effect as pull_course_library (Drive): files are copied
    into the library dir, manifest is updated, and everything from Refresh
    Local Files onward works identically.
    """
    source = Path(folder_path).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Not a folder or does not exist: {source}")

    target_dir = _library_dir(grade, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _library_manifest_path(grade, subject)
    manifest = _read_json(manifest_path, {"files": {}})
    files_by_id = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}

    pulled: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    now = _now_z()

    for src_file in sorted(source.iterdir()):
        if not src_file.is_file():
            continue
        if src_file.suffix.lower() not in _LOCAL_IMPORT_EXTENSIONS:
            continue
        name = src_file.name
        # Use a stable key derived from the absolute source path so re-pulls
        # of the same folder skip already-imported files.
        local_id = f"local:{hashlib.sha256(str(src_file).encode()).hexdigest()[:16]}"
        existing = files_by_id.get(local_id) if isinstance(files_by_id, dict) else None
        existing_path = Path(str((existing or {}).get("local_path") or ""))
        if isinstance(existing, dict) and existing_path.exists():
            # Check if content changed by comparing sha256.
            try:
                new_digest = hashlib.sha256(src_file.read_bytes()).hexdigest()
                if existing.get("sha256") == new_digest:
                    skipped.append({**existing, "status": "unchanged"})
                    continue
            except OSError:
                skipped.append({**existing, "status": "unchanged"})
                continue
        try:
            body = src_file.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            dest = _unique_library_path(target_dir, name, digest)
            _write_private_bytes_no_overwrite(dest, body)
            entry = CourseLibraryEntry(
                drive_id=local_id,
                name=name,
                local_path=str(dest),
                sha256=digest,
                pulled_at=now,
                status="pulled",
            )
            files_by_id[local_id] = asdict(entry)
            pulled.append(asdict(entry))
        except Exception as exc:
            failed.append({"name": name, "status": "failed", "reason": str(exc)})

    _atomic_write_json(
        manifest_path,
        {
            "version": 1,
            "source_folder": str(source),
            "grade": grade,
            "subject": subject,
            "updated_at": now,
            "files": files_by_id,
        },
    )
    return {
        "grade": grade,
        "subject": subject,
        "source_folder": str(source),
        "library_dir": str(target_dir),
        "manifest_path": str(manifest_path),
        "pulled": pulled,
        "skipped": skipped,
        "failed": failed,
    }


def _import_lesson_bytes(
    name: str,
    body: bytes,
    local_id: str,
    grade: str,
    subject: str,
) -> dict:
    """Shared single-file import core: copy into the library dir, update the
    manifest (same shape pull_local_folder/pull_course_library write), and
    return the manifest entry. Unchanged content (same id + sha256) is a
    no-op re-import."""
    suffix = Path(name).suffix.lower()
    if suffix not in _LOCAL_IMPORT_EXTENSIONS:
        raise ValueError(
            f"unsupported lesson file type: {suffix or 'unknown'} — "
            f"supported: {', '.join(sorted(_LOCAL_IMPORT_EXTENSIONS))}"
        )
    target_dir = _library_dir(grade, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _library_manifest_path(grade, subject)
    manifest = _read_json(manifest_path, {"files": {}})
    files_by_id = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}

    now = _now_z()
    digest = hashlib.sha256(body).hexdigest()
    existing = files_by_id.get(local_id) if isinstance(files_by_id, dict) else None
    existing_path = Path(str((existing or {}).get("local_path") or ""))
    if (
        isinstance(existing, dict)
        and existing_path.exists()
        and existing.get("sha256") == digest
    ):
        return {
            "grade": grade,
            "subject": subject,
            "library_dir": str(target_dir),
            "manifest_path": str(manifest_path),
            "entry": {**existing, "status": "unchanged"},
        }

    dest = _unique_library_path(target_dir, name, digest)
    _write_private_bytes_no_overwrite(dest, body)
    entry = CourseLibraryEntry(
        drive_id=local_id,
        name=name,
        local_path=str(dest),
        sha256=digest,
        pulled_at=now,
        status="pulled",
    )
    files_by_id[local_id] = asdict(entry)
    merged = {
        "version": 1,
        "grade": grade,
        "subject": subject,
        "updated_at": now,
        "files": files_by_id,
    }
    if manifest.get("source_folder"):
        merged["source_folder"] = manifest["source_folder"]
    _atomic_write_json(manifest_path, merged)
    return {
        "grade": grade,
        "subject": subject,
        "library_dir": str(target_dir),
        "manifest_path": str(manifest_path),
        "entry": asdict(entry),
    }


def pull_local_file(file_path: str, grade: str, subject: str) -> dict:
    """Import ONE local lesson file into the course library (Browse button).

    Same downstream effect as pull_local_folder for a single file."""
    source = Path(file_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Not a file or does not exist: {source}")
    # Same path-keyed id as pull_local_folder so re-importing the same file
    # (via Browse or via its parent folder) dedupes to one manifest entry.
    local_id = f"local:{hashlib.sha256(str(source).encode()).hexdigest()[:16]}"
    return _import_lesson_bytes(source.name, source.read_bytes(), local_id, grade, subject)


def import_lesson_file_bytes(name: str, body: bytes, grade: str, subject: str) -> dict:
    """Import uploaded lesson file content (drag-and-drop / file picker in the
    browser, where no filesystem path exists). Content-keyed id: dropping the
    same bytes twice dedupes."""
    if not str(name or "").strip():
        raise ValueError("file name is required")
    if not body:
        raise ValueError("uploaded file is empty")
    local_id = f"upload:{hashlib.sha256(body).hexdigest()[:16]}"
    return _import_lesson_bytes(str(name).strip(), body, local_id, grade, subject)


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
    """Read lesson content from a course-library file for display AND for
    generation. Extension-aware: pdf/docx/xlsx go through the docpipe
    extractors (a plain utf-8 read crashes on binaries)."""
    path = Path(local_path).expanduser().resolve()
    library_root = course_library_root().resolve()
    if library_root not in path.parents:
        raise ValueError("lesson_file_outside_course_library")
    if not path.is_file():
        raise ValueError("lesson_file_missing")
    from src.lingua_viva.docpipe.extract import extract_plain_text

    return extract_plain_text(path.read_bytes(), path.suffix)


def parse_lesson_file_metadata(local_path: str, *, text: str | None = None) -> dict:
    """Deterministic metadata auto-detect for a course-library lesson file —
    what Prepare uses to pre-fill Grade/Unit/Topic from the selected file."""
    if text is None:
        text = read_todays_lesson_text(local_path)
    from src.lingua_viva.docpipe.extract import parse_lesson_metadata

    meta = parse_lesson_metadata(text)
    curriculum = meta.get("curriculum") if isinstance(meta.get("curriculum"), dict) else {}
    return {
        "title": meta.get("title"),
        "document_type": meta.get("document_type"),
        "grade": curriculum.get("grade"),
        "subject": curriculum.get("subject"),
        "unit": curriculum.get("unit"),
        "topic": curriculum.get("task") or meta.get("title"),
        "excerpt": text[:1000],
    }


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
    # "[" / "]" used to be banned outright here, which failed EVERY packet
    # containing ordinary teaching brackets ("[word bank]", "[your answer]")
    # — FIX_PREPARE_CLASS_MATERIALS 2026-08-18 Issue 7. Placeholder-shaped
    # bracket content ("[no model available]", "[Local reasoning stub]") is
    # still rejected by the targeted regex below.
    forbidden = (" rti ", "diagnostic", "generated by ai", "student_ids")
    for token in forbidden:
        if token in lowered:
            raise ValueError("unsafe_or_placeholder_printable_packet")
    if PLACEHOLDER_OUTPUT_RE.search(markdown):
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
    return f"lesson-packet-{_safe_slug(lesson.topic)}-{stamp}-{uuid.uuid4().hex[:12]}.md"


def lesson_packet_pdf_stem(lesson: LessonInput, materials: list[TierMaterial]) -> str:
    lesson_identity = asdict(lesson)
    # created_at is request-time metadata, not artifact content. Excluding it
    # makes repeated approvals of unchanged lesson material reuse the same PDF.
    lesson_identity.pop("created_at", None)
    payload = {"lesson": lesson_identity, "materials": [asdict(material) for material in materials]}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:12]
    return f"lesson-packet-{_safe_slug(lesson.topic)}-{digest}"


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
    from src.lingua_viva.docpipe.vault import _atomic_write_bytes
    _atomic_write_bytes(path, markdown.encode('utf-8'))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def write_printable_packet_pdfs(
    lesson: LessonInput,
    materials: list[TierMaterial],
    *,
    directory: Path | None = None,
) -> dict[str, Path | dict[str, Path]]:
    from src.lingua_viva.pdf_generator import artifacts_dir, render_lesson_pdf, render_tier_pdf

    target_dir = directory or artifacts_dir("lesson_packets")
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = lesson_packet_pdf_stem(lesson, materials)
    lesson_dict = asdict(lesson)
    material_dicts = [asdict(material) for material in materials]

    teacher_path = target_dir / f"{stem}-teacher.pdf"
    if not teacher_path.exists():
        render_lesson_pdf(lesson_dict, material_dicts, output_path=teacher_path)
    tier_paths: dict[str, Path] = {}
    for material in materials:
        tier_path = target_dir / f"{stem}-{_safe_slug(material.tier)}.pdf"
        if not tier_path.exists():
            render_tier_pdf(material.tier, asdict(material), lesson_dict, output_path=tier_path)
        tier_paths[material.tier] = tier_path
    for path in [teacher_path, *tier_paths.values()]:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return {"teacher": teacher_path, "student_tiers": tier_paths}


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
        generation_status=str(data.get("generation_status") or "generated"),
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
    source_text: str | None = None,
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
    # example output. The three LLM calls run in parallel. When a coursework
    # file is selected, a bounded excerpt of ITS content grounds every tier
    # (teacher's own lesson material — no student data, per the privacy
    # contract above).
    excerpt = _source_excerpt(source_text)
    materials = list(
        await asyncio.gather(
            *(
                _generate_tier_material(engine, tier, lesson, groups[tier], excerpt)
                for tier in TIERS
            )
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


# --- F3 (SPEC_LV_DEMO_EVE_FIX_2026-08-19 §2): the packet prints what the
# teacher reviewed. Generation persists its output here; the packet
# preview/print path renders THIS stored artifact with zero model calls.
# New content only ever comes from an explicit regenerate (which calls
# store_generated_materials again and records a new immutable snapshot).


def generated_materials_dir() -> Path:
    override = os.environ.get("LV_GENERATED_MATERIALS_DIR")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "generated"


def _generated_materials_key(lesson: LessonInput, teacher_id: str) -> str:
    raw = "|".join(
        [
            teacher_id,
            lesson.ib_programme,
            lesson.subject,
            lesson.unit_title,
            lesson.topic,
            lesson.cefr_target,
            lesson.language_of_instruction,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def store_generated_materials(
    lesson: LessonInput,
    result: LessonMaterialsResult,
    teacher_id: str = "local-teacher",
) -> Path:
    """Persist the artifact the teacher is about to review, keyed to the lesson.

    Local JSON only (lv_home runtime dir) — same privacy boundary as every
    other lesson-materials artifact.
    """
    directory = generated_materials_dir()
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "lesson": asdict(lesson),
        "materials": materials_as_dicts(result),
        "individual_support": [asdict(item) for item in result.individual_support],
        "lesson_summary": result.lesson_summary,
        "generated_at": _now_z(),
        "teacher_id": teacher_id,
    }
    key = _generated_materials_key(lesson, teacher_id)
    return _write_immutable_json_snapshot(directory, key, "generated_materials", record)


def load_generated_materials(
    lesson: LessonInput,
    teacher_id: str = "local-teacher",
) -> dict | None:
    """Return the stored record for this lesson, or None if never generated."""
    key = _generated_materials_key(lesson, teacher_id)
    return _load_latest_json_snapshot(
        generated_materials_dir(),
        key,
        "generated_materials",
        lambda record: isinstance(record, dict) and isinstance(record.get("materials"), list),
    )


# --- Lesson-plan artifact loop (SPEC_LV_LESSON_PLAN_ARTIFACT_2026-08-22).
# This is separate from tier worksheet packets but deliberately reuses the
# same LessonInput, roster split, runtime storage, and print-integrity pattern.


def curriculum_knowledge_root() -> Path:
    override = os.environ.get("LV_KNOWLEDGE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[2] / "knowledge"


def load_curriculum_knowledge(subject: str, topic: str, *, root: Path | None = None) -> list[CurriculumKnowledgeEntry]:
    import yaml

    base = root or curriculum_knowledge_root()
    education = base / "education"
    if not education.exists():
        return []
    query = f"{subject} {topic}".lower()
    candidates: list[CurriculumKnowledgeEntry] = []
    for path in sorted(education.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for entry in data.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            nodes = {str(item) for item in entry.get("ontology_nodes") or []}
            tags = " ".join(str(item) for item in entry.get("tags") or [])
            haystack = " ".join([
                str(entry.get("id") or ""),
                str(entry.get("title") or ""),
                str(entry.get("content") or ""),
                tags,
                " ".join(nodes),
            ]).lower()
            is_curriculum = bool(nodes & {"LV-CUR-001", "LV-CUR-002", "LV-CUR-003", "LV-CUR-004", "LV-CUR-005"})
            mentions_request = any(token in haystack for token in re.findall(r"[a-zA-Z]+", query) if len(token) >= 4)
            if is_curriculum or mentions_request:
                candidates.append(
                    CurriculumKnowledgeEntry(
                        id=str(entry.get("id") or ""),
                        title=str(entry.get("title") or ""),
                        content=str(entry.get("content") or ""),
                        citations=[str(item) for item in entry.get("citations") or []],
                        source_path=str(path),
                    )
                )
    return candidates[:8]


def _curriculum_context(entries: list[CurriculumKnowledgeEntry]) -> str:
    parts = []
    for entry in entries:
        citation = "; ".join(entry.citations)
        parts.append(f"- {entry.id}: {entry.title}\n  {entry.content[:700]}\n  Citations: {citation}")
    return "\n".join(parts)


def _lesson_plan_prompt(
    lesson: LessonInput,
    curriculum_entries: list[CurriculumKnowledgeEntry],
    split: RosterSplit | None,
    source_text: str | None = None,
) -> str:
    tier_counts = {tier: 0 for tier in TIERS}
    individual_support_count = 0
    if split is not None:
        tier_counts = {tier: len(split.tier_groups.get(tier, [])) for tier in TIERS}
        individual_support_count = len(split.individual_support)
    source_section = ""
    excerpt = _source_excerpt(source_text)
    if excerpt:
        source_section = f"\nOptional teacher-provided lesson/coursework content:\n{excerpt}\n"
    return f"""Create a printable lesson plan as JSON.

Lesson input:
- Programme: {lesson.ib_programme}
- Subject: {lesson.subject}
- Grade/unit: {lesson.unit_title}
- Topic: {lesson.topic}
- ATL skills (teacher-selected, fixed): {", ".join(lesson.atl_skills) or "none specified"}
- Duration: {lesson.duration_minutes} minutes
- CEFR target: {lesson.cefr_target}
- Language of instruction: {lesson.language_of_instruction}

Curriculum context, the only allowed source for standards:
{_curriculum_context(curriculum_entries)}
{source_section}
Differentiation context, counts only:
- Foundation/foundational count: {tier_counts.get('foundational', 0)}
- Core/on-track count: {tier_counts.get('on_track', 0)}
- Extension count: {tier_counts.get('extended', 0)}
- Teacher-handled individual support count: {individual_support_count}

Output ONLY this JSON object shape:
{{
  "subject": "...",
  "grade": "...",
  "date": "...",
  "duration_minutes": 45,
  "teacher_name": "...",
  "topic": "...",
  "curriculum_standard": "cite one supplied KL id and title",
  "curriculum_citations": ["KL id or citation"],
  "central_idea": "one transdisciplinary sentence for this unit",
  "lines_of_inquiry": ["...", "...", "..."],
  "learner_profile_attributes": [{{"attribute": "one of the 10 IB attributes", "connection": "how this lesson develops it"}}],
  "cross_curricular_connections": ["subject: connection", "..."],
  "learning_objectives": ["...", "...", "..."],
  "success_criteria": ["Students can ...", "..."],
  "materials": ["item (quantity)", "..."],
  "lesson_structure": {{
    "warmup": {{"duration": "5 min", "activity": "...", "instructions": "..."}},
    "main_activity": {{"duration": "20 min", "activity": "...", "instructions": "..."}},
    "guided_practice": {{"duration": "10 min", "activity": "...", "instructions": "..."}},
    "independent_work": {{"duration": "5 min", "activity": "...", "instructions": "..."}},
    "wrapup": {{"duration": "5 min", "activity": "...", "instructions": "..."}}
  }},
  "differentiation": {{
    "foundation": {{"description": "...", "modifications": "..."}},
    "core": {{"description": "...", "activities": "..."}},
    "extension": {{"description": "...", "challenges": "..."}}
  }},
  "assessment": "...",
  "teacher_notes": "..."
}}"""


def parse_lesson_plan_json(text: str) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _phase(value: object, fallback_activity: str, fallback_instructions: str, duration: str) -> dict:
    data = value if isinstance(value, dict) else {}
    return {
        "duration": str(data.get("duration") or duration),
        "activity": str(data.get("activity") or fallback_activity),
        "instructions": str(data.get("instructions") or fallback_instructions),
    }




def _normalize_learner_profile(value: object) -> list[dict[str, str]]:
    allowed = {item.lower(): item for item in IB_LEARNER_PROFILE_ATTRIBUTES}
    normalized: list[dict[str, str]] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            attribute = str(item.get("attribute") or "").strip()
            connection = str(item.get("connection") or "").strip()
        else:
            attribute, connection = str(item).strip(), ""
        canonical = allowed.get(attribute.lower())
        if canonical:
            normalized.append({"attribute": canonical, "connection": connection})
    return normalized[:3]


def _normalize_lesson_plan(plan: dict, lesson: LessonInput, entries: list[CurriculumKnowledgeEntry], teacher_name: str = "") -> dict:
    first = entries[0] if entries else CurriculumKnowledgeEntry("missing", "Missing curriculum knowledge", "", [], "")
    structure = plan.get("lesson_structure") if isinstance(plan.get("lesson_structure"), dict) else {}
    differentiation = plan.get("differentiation") if isinstance(plan.get("differentiation"), dict) else {}
    normalized = {
        "subject": str(plan.get("subject") or lesson.subject),
        "grade": str(plan.get("grade") or lesson.unit_title or "Grade 3"),
        "date": str(plan.get("date") or datetime.now(timezone.utc).date().isoformat()),
        "duration_minutes": int(plan.get("duration_minutes") or lesson.duration_minutes),
        "teacher_name": str(plan.get("teacher_name") or teacher_name or lesson.created_by or ""),
        "topic": str(plan.get("topic") or lesson.topic),
        "curriculum_standard": str(plan.get("curriculum_standard") or f"{first.id}: {first.title}"),
        "curriculum_citations": [
            str(item) for item in (
                plan.get("curriculum_citations")
                if isinstance(plan.get("curriculum_citations"), list)
                else [first.id, *first.citations[:1]]
            )
            if str(item).strip()
        ],
        # IB PYP framing. ATL skills are the teacher's own lesson-input
        # selection — ground truth, never the model's.
        "central_idea": str(plan.get("central_idea") or "").strip()
        or f"{lesson.unit_title}: we build {lesson.subject} understanding through {lesson.topic}.",
        "lines_of_inquiry": [str(item).strip() for item in plan.get("lines_of_inquiry") or [] if str(item).strip()][:3]
        or [
            f"Key words and phrases for {lesson.topic}",
            f"How we use this language in daily life",
            "Expressing ourselves with growing independence",
        ],
        "atl_skills": [str(item) for item in lesson.atl_skills if str(item).strip()],
        "learner_profile_attributes": _normalize_learner_profile(plan.get("learner_profile_attributes"))
        or [{"attribute": "Communicators", "connection": "Students express ideas in more than one language."}],
        "cross_curricular_connections": [
            str(item).strip() for item in plan.get("cross_curricular_connections") or [] if str(item).strip()
        ][:3],
        "learning_objectives": [str(item) for item in plan.get("learning_objectives") or [] if str(item).strip()][:3],
        "success_criteria": [str(item).strip() for item in plan.get("success_criteria") or [] if str(item).strip()][:4],
        "materials": [str(item) for item in plan.get("materials") or [] if str(item).strip()],
        "lesson_structure": {
            "warmup": _phase(structure.get("warmup"), "Vocabulary hook", "Activate prior knowledge with visuals and oral repetition.", "5 min"),
            "main_activity": _phase(structure.get("main_activity"), "Guided inquiry", "Model the target language, then practice through a shared task.", "20 min"),
            "guided_practice": _phase(structure.get("guided_practice"), "Small-group practice", "Students rehearse with sentence frames and teacher circulation.", "10 min"),
            "independent_work": _phase(structure.get("independent_work"), "Independent transfer", "Students complete a short individual or partner task.", "5 min"),
            "wrapup": _phase(structure.get("wrapup"), "Exit check", "Students show one example of understanding before closing.", "5 min"),
        },
        "differentiation": {
            "foundation": differentiation.get("foundation") if isinstance(differentiation.get("foundation"), dict) else {},
            "core": differentiation.get("core") if isinstance(differentiation.get("core"), dict) else {},
            "extension": differentiation.get("extension") if isinstance(differentiation.get("extension"), dict) else {},
        },
        "assessment": str(plan.get("assessment") or "Use the wrap-up response and guided-practice notes to check understanding."),
        "teacher_notes": str(plan.get("teacher_notes") or "Record what to adjust after the lesson."),
    }
    if not normalized["learning_objectives"]:
        normalized["learning_objectives"] = [
            f"Students use target vocabulary for {lesson.topic}.",
            "Students respond orally with increasing independence.",
            "Students show understanding through a short formative check.",
        ]
    if not normalized["materials"]:
        normalized["materials"] = ["visual vocabulary cards", "whiteboard or chart paper", "student notebooks"]
    defaults = {
        "foundation": ("Concrete visuals, word bank, gestures, and sentence starters.", "Use pointing, repetition, and partner rehearsal before independent response."),
        "core": ("Shared target with moderate scaffolding.", "Complete the main task with one model and peer practice."),
        "extension": ("Greater independence and transfer.", "Add detail, explain a choice, or create a new example."),
    }
    for key, (description, detail) in defaults.items():
        tier = normalized["differentiation"][key]
        if not isinstance(tier, dict):
            tier = {}
        if key == "foundation":
            tier = {"description": str(tier.get("description") or description), "modifications": str(tier.get("modifications") or detail)}
        elif key == "core":
            tier = {"description": str(tier.get("description") or description), "activities": str(tier.get("activities") or detail)}
        else:
            tier = {"description": str(tier.get("description") or description), "challenges": str(tier.get("challenges") or detail)}
        normalized["differentiation"][key] = tier
    _validate_lesson_plan_safety(normalized)
    return normalized


def _deterministic_lesson_plan(lesson: LessonInput, entries: list[CurriculumKnowledgeEntry], split: RosterSplit | None, teacher_name: str = "") -> dict:
    first = entries[0]
    # ATL skills come from the teacher's lesson input, never the model
    atl_skills = list(getattr(lesson, "atl_skills", None) or [])
    # Learner profile attributes: select from the official IB 10 based on topic
    lp_attrs = _select_learner_profile_attributes(lesson)
    plan = {
        "curriculum_standard": f"{first.id}: {first.title}",
        "curriculum_citations": [first.id, *first.citations[:1]],
        "learning_objectives": [
            f"Use key language for {lesson.topic} in a supported oral exchange.",
            "Match words or phrases to visual examples and classroom contexts.",
            "Show understanding through one spoken or written exit response.",
        ],
        "materials": ["picture cards", "word bank", "mini whiteboards", "exit ticket slips"],
        "lesson_structure": {
            "warmup": {"duration": "5 min", "activity": "Visual vocabulary activation", "instructions": "Show images, say each word aloud, and invite gesture-based responses."},
            "main_activity": {"duration": "20 min", "activity": "Model and guided practice", "instructions": "Model two examples, then have students practice the language in pairs."},
            "guided_practice": {"duration": "10 min", "activity": "Teacher-led check", "instructions": "Circulate, prompt with visuals, and collect quick oral responses from each group."},
            "independent_work": {"duration": "5 min", "activity": "Personalized example", "instructions": "Students create one example using the target vocabulary."},
            "wrapup": {"duration": "5 min", "activity": "Exit response", "instructions": "Students share or submit one accurate target-language phrase."},
        },
        "atl_skills": atl_skills,
        "learner_profile_attributes": lp_attrs,
    }
    return _normalize_lesson_plan(plan, lesson, entries, teacher_name)


def _select_learner_profile_attributes(lesson: LessonInput) -> list[dict]:
    """Select relevant IB Learner Profile attributes for a lesson.
    Only official IB 10 attributes are allowed."""
    # Default selection based on language lessons
    attrs = [
        {"attribute": "Communicators", "connection": f"Developing language skills through {getattr(lesson, 'topic', 'classroom activities')}"},
    ]
    atl = getattr(lesson, "atl_skills", None) or []
    if "self-management" in atl:
        attrs.append({"attribute": "Balanced", "connection": "Practicing self-management during learning activities"})
    if "thinking" in atl:
        attrs.append({"attribute": "Thinkers", "connection": "Applying thinking skills to language challenges"})
    return attrs


def _validate_lesson_plan_safety(plan: dict, roster_names: list[str] | None = None) -> None:
    text = json.dumps(plan, ensure_ascii=False).lower()
    for token in (" rti ", "diagnosis", "diagnostic", "generated by ai", "student_ids"):
        if token in text:
            raise ValueError("unsafe_lesson_plan")
    for name in roster_names or []:
        lowered = str(name).strip().lower()
        if len(lowered) >= 3 and lowered in text:
            raise ValueError("student_name_in_lesson_plan")


async def generate_lesson_plan_artifact(
    lesson: LessonInput,
    *,
    teacher_id: str = "local-teacher",
    teacher_name: str = "",
    store=None,
    engine=None,
    student_ids: list[str] | None = None,
    tier_groups: dict[str, list[str]] | None = None,
    roster_names: list[str] | None = None,
    individual_support: list[IndividualSupportStudent] | None = None,
    source_text: str | None = None,
    curriculum_entries: list[CurriculumKnowledgeEntry] | None = None,
) -> LessonPlanArtifactResult:
    errors = lesson.validate()
    if errors:
        raise ValueError(f"Invalid LessonInput: {errors}")
    curriculum_entries = curriculum_entries if curriculum_entries is not None else load_curriculum_knowledge(lesson.subject, lesson.topic)
    if not curriculum_entries:
        raise LookupError("missing_curriculum_knowledge")
    split: RosterSplit | None = None
    if tier_groups is None:
        own_store = store is None
        active = store
        if own_store:
            from src.education.student_lens import StudentLensStore

            active = StudentLensStore()
        try:
            split = assign_roster_split(active, teacher_id, student_ids) if active is not None else None
        finally:
            if own_store and active is not None:
                active.close()
    else:
        split = RosterSplit(tier_groups, roster_names or [], individual_support or [])
    if engine is None:
        from src.lingua_viva.reasoning import ReasoningEngine

        engine = ReasoningEngine()
    prompt = _lesson_plan_prompt(lesson, curriculum_entries, split, source_text)
    # 1600 (was 1200): the IB PYP fields (central idea, lines of inquiry,
    # learner profile, success criteria) grew the JSON — truncated JSON would
    # silently demote every generation to template_fallback.
    result = await engine.reason(prompt, context={}, system_prompt=LESSON_PLAN_SYSTEM_PROMPT, max_tokens=1600)
    content = getattr(result, "content", "") or ""
    model_used = str(getattr(result, "model_used", "") or "")
    error = str(getattr(result, "error", "") or "")
    parsed = None if error or model_used.startswith("none") else parse_lesson_plan_json(content)
    generation_status = "generated"
    if parsed is None:
        parsed = _deterministic_lesson_plan(lesson, curriculum_entries, split, teacher_name)
        generation_status = "template_fallback"
    plan = _normalize_lesson_plan(parsed, lesson, curriculum_entries, teacher_name)
    _validate_lesson_plan_safety(plan, (split.roster_names if split else roster_names) or [])
    rendered = render_lesson_plan_bundle(plan)
    return LessonPlanArtifactResult(
        plan=plan,
        html=rendered["html"],
        print_html=rendered["print_html"],
        markdown=rendered["markdown"],
        generation_status=generation_status,
        curriculum_sources=[asdict(entry) for entry in curriculum_entries],
        generated_at=_now_z(),
    )


def _lesson_plan_title(plan: dict) -> str:
    return f"Lesson Plan - {plan.get('topic') or 'Lesson'}"


def render_lesson_plan_markdown(plan: dict) -> str:
    lines = [
        f"# {_lesson_plan_title(plan)}",
        "",
        f"- Subject: {plan.get('subject', '')}",
        f"- Grade: {plan.get('grade', '')}",
        f"- Date: {plan.get('date', '')}",
        f"- Duration: {plan.get('duration_minutes', '')} minutes",
        f"- Teacher: {plan.get('teacher_name', '')}",
        f"- Curriculum standard: {plan.get('curriculum_standard', '')}",
        "",
        "## IB PYP Framing",
        "",
        f"**Central idea:** {plan.get('central_idea', '')}",
        "",
        "**Lines of inquiry:**",
        "",
    ]
    lines.extend(f"- {item}" for item in plan.get("lines_of_inquiry") or [])
    atl = ", ".join(plan.get("atl_skills") or [])
    lines.extend(["", f"**Approaches to Learning:** {atl or 'none selected'}", "", "**Learner Profile:**", ""])
    for item in plan.get("learner_profile_attributes") or []:
        connection = str(item.get("connection") or "").strip()
        lines.append(f"- {item.get('attribute', '')}" + (f" — {connection}" if connection else ""))
    lines.extend(["", "## Learning Objectives", ""])
    lines.extend(f"- {item}" for item in plan.get("learning_objectives") or [])
    lines.extend(["", "## Materials Needed", ""])
    lines.extend(f"- [ ] {item}" for item in plan.get("materials") or [])
    lines.extend(["", "## Lesson Structure", ""])
    labels = [
        ("warmup", "Warm-up / Hook"),
        ("main_activity", "Main Activity"),
        ("guided_practice", "Guided Practice"),
        ("independent_work", "Independent Work / Extension"),
        ("wrapup", "Wrap-up / Assessment"),
    ]
    structure = plan.get("lesson_structure") or {}
    for key, label in labels:
        phase = structure.get(key) or {}
        lines.extend([
            f"### {label} ({phase.get('duration', '')})",
            "",
            f"**{phase.get('activity', '')}**",
            "",
            str(phase.get("instructions") or ""),
            "",
        ])
    lines.extend(["## Differentiation", ""])
    for key, label in (("foundation", "Foundation"), ("core", "Core"), ("extension", "Extension")):
        tier = (plan.get("differentiation") or {}).get(key) or {}
        detail = tier.get("modifications") or tier.get("activities") or tier.get("challenges") or ""
        lines.extend([f"### {label}", "", str(tier.get("description") or ""), "", str(detail), ""])
    connections = plan.get("cross_curricular_connections") or []
    lines.extend(["## Cross-Curricular Connections", ""])
    if connections:
        lines.extend(f"- {item}" for item in connections)
    else:
        lines.append("None noted for this lesson.")
    lines.extend([
        "",
        "## Assessment",
        "",
        str(plan.get("assessment") or ""),
        "",
    ])
    criteria = plan.get("success_criteria") or []
    if criteria:
        lines.extend(["**Success criteria:**", ""])
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
    lines.extend([
        f"Linked standard: {plan.get('curriculum_standard', '')}",
        "",
        "## Notes",
        "",
        str(plan.get("teacher_notes") or ""),
        "",
    ])
    citations = [str(item) for item in plan.get("curriculum_citations") or [] if str(item).strip()]
    if citations:
        lines.extend(["## Curriculum Citations", ""])
        lines.extend(f"- {item}" for item in citations)
        lines.append("")
    lines.extend([
        "## Teacher Reflection (after the lesson)",
        "",
        "- What worked: ____________________________________________",
        "- What to adjust: _________________________________________",
        "- Students to follow up with (initials only): _____________",
        "",
    ])
    return "\n".join(lines)


def render_lesson_plan_html(plan: dict, *, print_ready: bool = False) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value if value is not None else ""))

    structure = plan.get("lesson_structure") or {}
    phases = [
        ("warmup", "Warm-up / Hook"),
        ("main_activity", "Main Activity"),
        ("guided_practice", "Guided Practice"),
        ("independent_work", "Independent Work / Extension"),
        ("wrapup", "Wrap-up / Assessment"),
    ]
    diff = plan.get("differentiation") or {}
    css = """
      body { font-family: Arial, Helvetica, sans-serif; color: #17202a; line-height: 1.42; margin: 28px; }
      .lesson-plan { max-width: 960px; margin: 0 auto; }
      h1 { font-size: 26px; margin: 0 0 8px; }
      h2 { font-size: 17px; margin: 22px 0 8px; border-bottom: 1px solid #d8dee4; padding-bottom: 3px; }
      h3 { font-size: 13px; margin: 0 0 4px; }
      .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px 14px; font-size: 12px; margin: 12px 0 18px; }
      .phase { break-inside: avoid; border-left: 3px solid #f06820; padding-left: 10px; margin: 10px 0 14px; }
      .duration { color: #5f6b76; font-size: 12px; font-weight: normal; }
      .tiers { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
      .tier { border: 1px solid #d8dee4; border-radius: 6px; padding: 10px; break-inside: avoid; }
      ul { margin-top: 4px; padding-left: 20px; }
      .ib-framing { border: 1px solid #d8dee4; border-left: 3px solid #f06820; border-radius: 6px; padding: 10px 12px; margin: 10px 0 14px; break-inside: avoid; }
      .ib-framing p, .ib-framing ul { margin: 4px 0; font-size: 13px; }
      .atl { color: #5f6b76; font-size: 12px; }
      .checklist { list-style: none; padding-left: 4px; }
      .checklist li::before { content: "\\2610\\00a0 "; }
      .linked-standard { color: #5f6b76; font-size: 12px; }
      .reflection { border: 1px dashed #aab4bd; border-radius: 6px; padding: 10px 12px; break-inside: avoid; }
      .reflection p { border-bottom: 1px solid #d8dee4; padding-bottom: 16px; margin: 10px 0 0; font-size: 12px; color: #5f6b76; }
      @media print { body { margin: 14mm; } .lesson-plan { max-width: none; } .tiers { grid-template-columns: repeat(3, 1fr); } }
      @media (max-width: 720px) { .meta, .tiers { grid-template-columns: 1fr; } }
    """
    body = [
        '<article class="lesson-plan">',
        f"<h1>{esc(_lesson_plan_title(plan))}</h1>",
        '<section class="meta">',
        f"<div><strong>Subject</strong><br>{esc(plan.get('subject'))}</div>",
        f"<div><strong>Grade</strong><br>{esc(plan.get('grade'))}</div>",
        f"<div><strong>Date</strong><br>{esc(plan.get('date'))}</div>",
        f"<div><strong>Duration</strong><br>{esc(plan.get('duration_minutes'))} min</div>",
        f"<div><strong>Teacher</strong><br>{esc(plan.get('teacher_name'))}</div>",
        f"<div><strong>Curriculum</strong><br>{esc(plan.get('curriculum_standard'))}</div>",
        "</section>",
        "<h2>IB PYP Framing</h2>",
        '<section class="ib-framing">',
        f"<p><strong>Central idea:</strong> {esc(plan.get('central_idea'))}</p>",
        "<p><strong>Lines of inquiry:</strong></p>",
        "<ul>",
    ]
    body.extend(f"<li>{esc(item)}</li>" for item in plan.get("lines_of_inquiry") or [])
    atl = ", ".join(str(item) for item in plan.get("atl_skills") or [])
    body.extend([
        "</ul>",
        f'<p class="atl"><strong>Approaches to Learning:</strong> {esc(atl or "none selected")}</p>',
        "<p><strong>Learner Profile:</strong></p>",
        "<ul>",
    ])
    for item in plan.get("learner_profile_attributes") or []:
        connection = str(item.get("connection") or "").strip()
        suffix = f" — {esc(connection)}" if connection else ""
        body.append(f"<li><strong>{esc(item.get('attribute'))}</strong>{suffix}</li>")
    body.extend(["</ul>", "</section>", "<h2>Learning Objectives</h2>", "<ul>"])
    body.extend(f"<li>{esc(item)}</li>" for item in plan.get("learning_objectives") or [])
    body.extend(["</ul>", "<h2>Materials Needed</h2>", '<ul class="checklist">'])
    body.extend(f"<li>{esc(item)}</li>" for item in plan.get("materials") or [])
    body.extend(["</ul>", "<h2>Lesson Structure</h2>"])
    for key, label in phases:
        phase = structure.get(key) or {}
        body.extend([
            '<section class="phase">',
            f"<h3>{esc(label)} <span class=\"duration\">{esc(phase.get('duration'))}</span></h3>",
            f"<p><strong>{esc(phase.get('activity'))}</strong></p>",
            f"<p>{esc(phase.get('instructions'))}</p>",
            "</section>",
        ])
    body.extend(["<h2>Differentiation</h2>", '<section class="tiers">'])
    for key, label, detail_key in (("foundation", "Foundation", "modifications"), ("core", "Core", "activities"), ("extension", "Extension", "challenges")):
        tier = diff.get(key) or {}
        body.extend([
            '<div class="tier">',
            f"<h3>{label}</h3>",
            f"<p>{esc(tier.get('description'))}</p>",
            f"<p>{esc(tier.get(detail_key))}</p>",
            "</div>",
        ])
    body.append("</section>")
    connections = plan.get("cross_curricular_connections") or []
    body.append("<h2>Cross-Curricular Connections</h2>")
    if connections:
        body.append("<ul>")
        body.extend(f"<li>{esc(item)}</li>" for item in connections)
        body.append("</ul>")
    else:
        body.append("<p>None noted for this lesson.</p>")
    body.extend([
        "<h2>Assessment</h2>",
        f"<p>{esc(plan.get('assessment'))}</p>",
    ])
    criteria = plan.get("success_criteria") or []
    if criteria:
        body.extend(["<p><strong>Success criteria:</strong></p>", "<ul>"])
        body.extend(f"<li>{esc(item)}</li>" for item in criteria)
        body.append("</ul>")
    body.extend([
        f'<p class="linked-standard">Linked standard: {esc(plan.get("curriculum_standard"))}</p>',
        "<h2>Notes</h2>",
        f"<p>{esc(plan.get('teacher_notes'))}</p>",
        "<h2>Teacher Reflection (after the lesson)</h2>",
        '<section class="reflection">',
        "<p>What worked:</p>",
        "<p>What to adjust:</p>",
        "<p>Students to follow up with (initials only):</p>",
        "</section>",
        "</article>",
    ])
    document = f"<style>{css}</style>\n{''.join(body)}"
    if not print_ready:
        return document
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>Printable Lesson Plan</title></head><body>" + document + "</body></html>"


def render_lesson_plan_bundle(plan: dict) -> dict[str, str]:
    return {
        "markdown": render_lesson_plan_markdown(plan),
        "html": render_lesson_plan_html(plan),
        "print_html": render_lesson_plan_html(plan, print_ready=True),
    }


def generated_lesson_plans_dir() -> Path:
    override = os.environ.get("LV_GENERATED_LESSON_PLANS_DIR")
    return Path(override).expanduser() if override else lesson_materials_runtime_dir() / "lesson_plans"


def _generated_lesson_plan_key(lesson: LessonInput, teacher_id: str) -> str:
    return _generated_materials_key(lesson, teacher_id)


def store_generated_lesson_plan(
    lesson: LessonInput,
    result: LessonPlanArtifactResult,
    teacher_id: str = "local-teacher",
) -> Path:
    directory = generated_lesson_plans_dir()
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "lesson": asdict(lesson),
        "plan": result.plan,
        "generation_status": result.generation_status,
        "curriculum_sources": result.curriculum_sources,
        "generated_at": result.generated_at,
        "teacher_id": teacher_id,
    }
    key = _generated_lesson_plan_key(lesson, teacher_id)
    return _write_immutable_json_snapshot(directory, key, "generated_lesson_plan", record)


def load_generated_lesson_plan(lesson: LessonInput, teacher_id: str = "local-teacher") -> dict | None:
    key = _generated_lesson_plan_key(lesson, teacher_id)
    return _load_latest_json_snapshot(
        generated_lesson_plans_dir(),
        key,
        "generated_lesson_plan",
        lambda record: isinstance(record, dict) and isinstance(record.get("plan"), dict),
    )


def _revision_prompt(plan: dict, revision_text: str) -> str:
    return (
        "Here is the current lesson plan JSON:\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f'Teacher revision request: "{revision_text}"\n\n'
        "Return the COMPLETE revised lesson plan JSON with the same structure. "
        "Only modify the relevant section and preserve everything else."
    )


def _apply_deterministic_revision(plan: dict, revision_text: str) -> dict:
    revised = json.loads(json.dumps(plan))
    text = revision_text.lower()
    if "song" in text and ("warm" in text or "hook" in text):
        warmup = revised.setdefault("lesson_structure", {}).setdefault("warmup", {})
        warmup["activity"] = "Song and movement vocabulary hook"
        warmup["instructions"] = "Start with a short call-and-response song using the target words, add gestures, then repeat with student volunteers leading."
    elif "visual" in text:
        revised.setdefault("materials", [])
        if "visual cue cards" not in revised["materials"]:
            revised["materials"].append("visual cue cards")
        foundation = revised.setdefault("differentiation", {}).setdefault("foundation", {})
        foundation["modifications"] = "Add visual cue cards, gesture prompts, and picture matching before oral production."
    elif "extension" in text and ("hard" in text or "challenge" in text):
        extension = revised.setdefault("differentiation", {}).setdefault("extension", {})
        extension["challenges"] = "Create a new example, explain the choice, and ask a follow-up question using the target language."
    else:
        notes = revised.get("teacher_notes") or ""
        revised["teacher_notes"] = (notes + f"\nRevision request to consider: {revision_text}").strip()
    return revised


async def revise_lesson_plan_artifact(
    lesson: LessonInput,
    current_plan: dict,
    revision_text: str,
    *,
    teacher_id: str = "local-teacher",
    teacher_name: str = "",
    engine=None,
    curriculum_entries: list[CurriculumKnowledgeEntry] | None = None,
) -> LessonPlanArtifactResult:
    if not str(revision_text or "").strip():
        raise ValueError("revision_text_required")
    curriculum_entries = curriculum_entries if curriculum_entries is not None else load_curriculum_knowledge(lesson.subject, lesson.topic)
    if not curriculum_entries:
        raise LookupError("missing_curriculum_knowledge")
    if engine is None:
        from src.lingua_viva.reasoning import ReasoningEngine

        engine = ReasoningEngine()
    result = await engine.reason(
        _revision_prompt(current_plan, revision_text),
        context={},
        system_prompt=LESSON_PLAN_REVISION_SYSTEM_PROMPT,
        # Matches generation: the revised plan carries the full IB PYP schema.
        max_tokens=1600,
    )
    content = getattr(result, "content", "") or ""
    model_used = str(getattr(result, "model_used", "") or "")
    error = str(getattr(result, "error", "") or "")
    parsed = None if error or model_used.startswith("none") else parse_lesson_plan_json(content)
    generation_status = "revised"
    if parsed is None:
        parsed = _apply_deterministic_revision(current_plan, revision_text)
        generation_status = "template_fallback"
    plan = _normalize_lesson_plan(parsed, lesson, curriculum_entries, teacher_name)
    rendered = render_lesson_plan_bundle(plan)
    return LessonPlanArtifactResult(
        plan=plan,
        html=rendered["html"],
        print_html=rendered["print_html"],
        markdown=rendered["markdown"],
        generation_status=generation_status,
        curriculum_sources=[asdict(entry) for entry in curriculum_entries],
        generated_at=_now_z(),
    )


def lesson_plan_pdf_stem(plan: dict) -> str:
    payload = json.dumps(plan, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"lesson-plan-{_safe_slug(str(plan.get('topic') or 'lesson'))}-{digest}"


def write_lesson_plan_pdf(plan: dict, *, directory: Path | None = None) -> Path:
    from src.lingua_viva.pdf_generator import artifacts_dir, render_lesson_plan_artifact_pdf

    target_dir = directory or artifacts_dir("lesson_plans")
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{lesson_plan_pdf_stem(plan)}.pdf"
    if not path.exists():
        render_lesson_plan_artifact_pdf(plan, output_path=path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
