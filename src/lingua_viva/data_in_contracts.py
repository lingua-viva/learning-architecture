"""
Data-In Contracts — shared interfaces for the file-map -> extract -> verify ->
artifact pipeline. Frozen by SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md.

Every "data in" spec (extraction engine, student lens writer, curriculum unit
writer) imports from here instead of re-deriving its own shapes. If a field
needs to change, it changes here first, and every consumer updates together —
that is the whole point of freezing this before parallel builds start.

This module defines contracts only. No extraction logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Provenance primitives
# ---------------------------------------------------------------------------

@dataclass
class SourceChunk:
    """One semantically-bounded slice of a source file. The unit the
    extraction engine reasons over and the unit a field cites as support."""

    chunk_id: str
    file_path: str
    text: str
    char_start: int
    char_end: int


FieldStatus = Literal["verified", "needs_confirmation", "unsupported"]


@dataclass
class ExtractedField:
    """One value the engine proposed for one field of a target schema.

    status is set by the verification pass, never by the extraction pass:
      - "verified": the cited chunks actually contain/support this value.
      - "needs_confirmation": plausible but ambiguous (e.g. grade could be
        3rd or 4th) — surfaces to the teacher, never auto-written.
      - "unsupported": the verification pass could not find grounding for
        this value in the cited chunks — dropped, never written, logged in
        ExtractionResult.unresolved_questions instead so the teacher isn't
        silently missing something.
    """

    field_path: str  # dotted path into the target schema, e.g. "cefr_snapshot.listening"
    value: Any
    confidence: float  # 0.0-1.0, engine's own estimate before verification
    supporting_chunk_ids: list[str]
    status: FieldStatus


@dataclass
class ExtractionResult:
    """What extract() returns. An artifact writer only ever consumes the
    "verified" subset; "needs_confirmation" fields are surfaced to the
    teacher as a review step (not the ambiguity-resolution chat — that's
    deferred; for now this just means the field is left blank with a note
    in unresolved_questions)."""

    target_schema_id: str  # "student_lens" | "curriculum_unit"
    fields: list[ExtractedField]
    unresolved_questions: list[str]
    source_files: list[str]
    chunks_used: list[SourceChunk] = field(default_factory=list)

    def verified_only(self) -> list[ExtractedField]:
        return [f for f in self.fields if f.status == "verified"]

    def needs_confirmation(self) -> list[ExtractedField]:
        return [f for f in self.fields if f.status == "needs_confirmation"]


# ---------------------------------------------------------------------------
# Target schema 1: Student Lens
# ---------------------------------------------------------------------------
# Field paths an extraction engine may populate. This is NOT a new schema —
# it is the existing src/education/student_lens.py StudentLensStore.create_lens()
# argument set, restated here as the extraction target so Spec 5 (engine) and
# Spec 6 (lens writer) agree on field names without either importing the other.

SUPPORT_PROFILE_CATEGORIES: tuple[str, ...] = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "advanced_enrichment",
)

SUPPORT_PROFILE_BUCKETS: tuple[str, ...] = (
    "needs",
    "strengths",
    "strategies_worked",
    "strategies_not_worked",
    "evidence",
    "open_questions",
)

SUPPORT_PROFILE_EXTRACTION_FIELDS: tuple[str, ...] = tuple(
    f"support_profile.categories.{cat}.{bucket}"
    for cat in SUPPORT_PROFILE_CATEGORIES
    for bucket in SUPPORT_PROFILE_BUCKETS
)

STUDENT_LENS_FIELDS: tuple[str, ...] = (
    "display_name",
    "campus",
    "grade_level",
    "home_languages",          # list[str]
    "learning_differences",    # list[str]
    "trauma_flag",             # bool — HIGH sensitivity, must always be
                                # "needs_confirmation" from extraction, never
                                # auto-verified. See Spec 0 §4.
    "cefr_snapshot.reading",
    "cefr_snapshot.writing",
    "cefr_snapshot.speaking",
    "cefr_snapshot.listening",
    *SUPPORT_PROFILE_EXTRACTION_FIELDS,
)


# ---------------------------------------------------------------------------
# Target schema 2: Curriculum Unit
# ---------------------------------------------------------------------------
# NEW schema. Does not exist as a store yet — Spec 7 builds it. Deliberately
# separate from curriculum/lingua_viva_matrix.yaml, which Doctor governs as
# non_authoritative and forbids promoting (see doctor/support_loop/doctor.py
# check_matrix_authority). Teacher-ingested units must never write into that
# file. This schema mirrors curriculum.py's existing unit dict shape
# (unit_id, grade, title, focus, cefr_target, cefr_language, source_citation,
# materials) so Plan/Prepare/Assess can consume real units through the same
# code path they already use for the fixture ones — only the source changes.

@dataclass
class CurriculumUnit:
    unit_id: str
    grade: str
    title: str
    focus: str
    cefr_target: str
    teacher_id: str
    source_files: list[str]
    source_status: Literal[
        "teacher_ingested_unverified",   # extraction ran, teacher hasn't reviewed
        "teacher_ingested_confirmed",    # teacher reviewed needs_confirmation fields
    ]
    materials: list[str] = field(default_factory=list)


CURRICULUM_UNIT_FIELDS: tuple[str, ...] = (
    "grade", "title", "focus", "cefr_target", "materials",
)


# ---------------------------------------------------------------------------
# Engine + writer interfaces (implemented by Spec 5 / Spec 6 / Spec 7)
# ---------------------------------------------------------------------------

def extract(
    files: list[str],
    target_schema_id: Literal["student_lens", "curriculum_unit"],
    hint: dict | None = None,
) -> Any:
    from src.lingua_viva.extraction_engine import extract as _extract
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running loop in async test/server environment: schedule coroutine
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(_extract(files, target_schema_id, hint)))
            return future.result()
    else:
        return asyncio.run(_extract(files, target_schema_id, hint))


def write_student_lens(
    result: ExtractionResult,
    teacher_id: str = "local-teacher",
    confirmed_fields: list[Any] | None = None,
    rejected_fields: list[Any] | None = None,
    hint: dict | None = None,
    store: Any = None,
) -> Any:
    from src.lingua_viva.student_lens_writer import write_student_lens as _write
    return _write(result, teacher_id=teacher_id, confirmed_fields=confirmed_fields, rejected_fields=rejected_fields, hint=hint, store=store)


def write_curriculum_unit(result: ExtractionResult, teacher_id: str) -> str:
    """Contract only — implemented in Spec 7. Consumes result.verified_only().
    Writes to the new per-teacher curriculum_units store (Spec 7 defines the
    storage), never to curriculum/lingua_viva_matrix.yaml."""
    raise NotImplementedError("Spec 7: Curriculum Unit artifact writer")
