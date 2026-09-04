"""
Student Lens Artifact Writer v3 — the IN filter of the lens field contract.

SPEC_LV_INGESTION_EXTRACTION_MAPPING_V2_2026-07-23.md (§10) rules still hold:
  1. trauma_flag is NEVER auto-written.
  2. Support-profile entries require non-empty supporting_chunk_ids (source refs).
  3. Verified fields write with confidence="imported_verified".
  4. Teacher-confirmed fields write with confidence="imported_needs_confirmation".
  5. Unconfirmed needs_confirmation fields remain pending review.

Added 2026-09-03 (dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md):
  6. EVERY field path is resolved through lens_field_contract.resolve() and
     dispatched on the resolved spec's KIND. There is no string-prefix chain.
  7. THE ACCOUNTING INVARIANT: every field that enters ends up in exactly one
     of written_fields / review_required / unresolved_questions. The result
     also carries `accounting`, one row per field, and the writer asserts the
     invariant before returning. Nothing can be absent from all three.
  8. Glass-box, not gatekeeping: a refusal names its field and its reason and
     never voids the document. A store-level ValueError refuses that field
     instead of raising through the import.
  9. Re-applying the same import is idempotent: an entry already present with
     the same text and source refs is reported written, not written twice.
"""

from __future__ import annotations

from typing import Any, Optional

from src.education.student_lens import (
    StudentLensStore,
    Observation,
    ObservationValidationError,
)
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
from src.lingua_viva.lens_field_contract import ResolvedField, resolve

# A CEFR observation imported from the same source file is the same claim;
# a later document carrying the same level is a new observation (plateau
# evidence). The dedupe key is the transcript, which names the source file.
_CEFR_DUPLICATE_WINDOW_SECONDS = 400 * 24 * 3600

# source_kind -> (support evidence_type, observation source_type); both
# vocabularies are the store's (VALID_EVIDENCE_TYPES / VALID_SOURCE_TYPES).
_SOURCE_KINDS = {
    "report": ("report", "local_file"),
    "teacher_note": ("teacher_note", "teacher_note"),
}

_CLASSIFY_FAILED_NOTE = (
    "Field 'unclassified': a sentence could not be classified (model call "
    "failed) and was not imported — review the source document."
)


class _Outcome:
    WRITTEN = "written"
    REVIEW = "review_required"
    REFUSED = "refused"


def write_student_lens(
    result: ExtractionResult,
    teacher_id: str = "local-teacher",
    confirmed_fields: Optional[list[Any]] = None,
    rejected_fields: Optional[list[Any]] = None,
    hint: Optional[dict] = None,
    store: Optional[StudentLensStore] = None,
    source_kind: str = "report",
) -> dict:
    """`source_kind` names where the fields came from so provenance survives
    into the lens: "report" (a document; the default and the pre-2026-09-03
    behaviour) or "teacher_note" (an Observe comment). It maps onto the
    store's evidence_type / observation source_type vocabularies."""
    if source_kind not in _SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {tuple(_SOURCE_KINDS)}")
    # Teacher-identity seam (P1, 2026-08-02): callers that don't pass a
    # teacher_id (e.g. the Drive auto-import extraction path) inherit the
    # machine's configured identity instead of re-creating sentinel-attributed
    # entries after the provisioning backfill. Explicit non-default ids win.
    from src.lingua_viva.access_roles import configured_teacher_id

    teacher_id = configured_teacher_id(teacher_id) or teacher_id
    hint = hint or {}
    close_store_on_exit = False
    if store is None:
        store = StudentLensStore()
        close_store_on_exit = True

    try:
        confirmed_set = _paths_of(confirmed_fields)
        rejected_set = _paths_of(rejected_fields)

        # 1. Determine student ID
        student_id = hint.get("assigned_student_id") or hint.get("student_id")

        display_name = None
        for field in result.fields:
            if field.field_path == "display_name":
                if field.status == "verified" or field.field_path in confirmed_set:
                    display_name = str(field.value)

        if not student_id:
            if display_name:
                student_id = store.create_lens(display_name=display_name)
            else:
                lenses = store.list_lenses()
                if lenses:
                    student_id = lenses[0]["student_id"]
                else:
                    student_id = store.create_lens(display_name="Imported Student")

        written_fields: list[str] = []
        review_required: list[str] = []
        unresolved_questions: list[str] = list(result.unresolved_questions or [])
        accounting: list[dict] = []
        written_count = 0
        review_confirmed = 0
        review_rejected = len(rejected_set)
        source_file = result.source_files[0] if result.source_files else "file.txt"

        # Build fields_to_process combining result.fields and confirmed_fields
        existing_paths = {f.field_path for f in result.fields}
        fields_to_process = list(result.fields)
        if confirmed_fields:
            for item in confirmed_fields:
                if isinstance(item, dict) and item.get("field_path"):
                    if item["field_path"] not in existing_paths:
                        fields_to_process.append(
                            ExtractedField(
                                field_path=item["field_path"],
                                value=item.get("value"),
                                confidence=item.get("confidence", 0.85),
                                supporting_chunk_ids=item.get("supporting_chunk_ids")
                                or [f"{source_file}#chunk-0000"],
                                status="verified",
                            )
                        )
                        existing_paths.add(item["field_path"])

        def account(field: ExtractedField, outcome: str, reason: str = "") -> None:
            accounting.append({"field_path": field.field_path, "outcome": outcome, "reason": reason})

        def refuse(field: ExtractedField, message: str) -> None:
            unresolved_questions.append(message)
            account(field, _Outcome.REFUSED, message)

        for field in fields_to_process:
            path = field.field_path
            status = field.status

            # -- status gates that apply before resolution ------------------
            if status == "classify_failed":
                # P0-3: never written, visible, content-free — names the path,
                # never the sentence.
                refuse(field, _CLASSIFY_FAILED_NOTE)
                continue

            resolved = resolve(path)
            if resolved is None:
                refuse(
                    field,
                    f"'{path}' is not a declared lens field, so it was not imported. "
                    f"Nothing was changed for that field.",
                )
                continue
            spec = resolved.spec

            if status == "unsupported" and path not in confirmed_set:
                refuse(field, f"Field '{path}' was unsupported by source references.")
                continue

            # Restricted fields and needs_confirmation fields wait for the teacher.
            if spec.sensitivity == "restricted" and path not in confirmed_set:
                review_required.append(path)
                account(field, _Outcome.REVIEW, "restricted field awaits teacher confirmation")
                continue
            if status == "needs_confirmation" and path not in confirmed_set:
                review_required.append(path)
                account(field, _Outcome.REVIEW, "needs teacher confirmation")
                continue

            if path in rejected_set:
                refuse(field, f"'{path}' was rejected by the teacher and was not imported.")
                continue

            if spec.status == "declared_not_implemented":
                refuse(
                    field,
                    f"'{path}' is a declared lens field that this version cannot write "
                    f"yet, so it was not imported. Nothing was changed for that field.",
                )
                continue
            if spec.status == "read_only":
                refuse(
                    field,
                    f"'{path}' is read-only on the lens and is not set by import."
                    + (" It was used to create the lens." if path == "display_name" else ""),
                )
                continue

            if spec.requires_sources and not field.supporting_chunk_ids:
                refuse(field, f"Refused '{path}': missing source references.")
                continue
            if spec.validator is not None:
                problem = spec.validator(field.value, resolved.bound)
                if problem:
                    refuse(field, f"Refused '{path}': {problem}")
                    continue

            confidence = "imported_verified" if status == "verified" else "imported_needs_confirmation"
            if path in confirmed_set:
                review_confirmed += 1

            # -- dispatch on KIND ------------------------------------------------
            try:
                note = _dispatch(
                    store, resolved, field, student_id, teacher_id, confidence, source_file,
                    _SOURCE_KINDS[source_kind],
                )
            except (ValueError, ObservationValidationError) as exc:
                # A store-level rejection refuses THIS field; it never voids the import.
                refuse(field, f"Refused '{path}': {exc}")
                continue

            written_fields.append(path)
            written_count += 1
            account(field, _Outcome.WRITTEN, note)

        # -- THE INVARIANT ----------------------------------------------------
        assert len(accounting) == len(fields_to_process), (
            "lens writer accounting invariant broken: "
            f"{len(fields_to_process)} fields entered, {len(accounting)} accounted"
        )
        n_written = sum(1 for a in accounting if a["outcome"] == _Outcome.WRITTEN)
        n_review = sum(1 for a in accounting if a["outcome"] == _Outcome.REVIEW)
        n_refused = sum(1 for a in accounting if a["outcome"] == _Outcome.REFUSED)
        assert n_written == len(written_fields) and n_review == len(review_required), (
            "lens writer accounting invariant broken: list lengths disagree with the ledger"
        )
        assert n_written + n_review + n_refused == len(fields_to_process)

        message = (
            f"{written_count} fields were written with source references."
            + (f" {review_confirmed} ambiguous fields were confirmed by the teacher." if review_confirmed else "")
            + (f" {n_refused} fields were not imported; each is named below." if n_refused else "")
        )

        return {
            "student_id": student_id,
            "written_fields": written_fields,
            "review_required": review_required,
            "unresolved_questions": unresolved_questions,
            "accounting": accounting,
            "feedback": {
                "written_count": written_count,
                "review_confirmed": review_confirmed,
                "review_rejected": review_rejected,
                "refused_count": n_refused,
                "message": message,
                "next_review_prompt": "Check whether strategy outcomes were language-specific or setting-specific.",
            },
        }
    finally:
        if close_store_on_exit:
            store.close()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _paths_of(items: Optional[list[Any]]) -> set[str]:
    out: set[str] = set()
    for item in items or []:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict) and item.get("field_path"):
            out.add(item["field_path"])
        elif isinstance(item, ExtractedField):
            out.add(item.field_path)
    return out


def _texts(value: Any) -> list[str]:
    texts = value if isinstance(value, list) else [value]
    return [t.strip() for t in texts if isinstance(t, str) and t.strip()]


def _already_present(items: list[dict], text: str, key: str, refs: list[str]) -> bool:
    for item in items:
        if not isinstance(item, dict) or item.get("active", True) is False:
            continue
        if item.get(key) == text and list(item.get("source_ref_ids") or []) == list(refs):
            return True
    return False


def _dispatch(
    store: StudentLensStore,
    resolved: ResolvedField,
    field: ExtractedField,
    student_id: str,
    teacher_id: str,
    confidence: str,
    source_file: str,
    source_types: tuple[str, str] = ("report", "local_file"),
) -> str:
    """Persist one resolved field through its declared store operation.
    Returns a short note for the accounting ledger. Raises ValueError /
    ObservationValidationError for a store-level refusal."""
    spec = resolved.spec
    path = resolved.path
    value = field.value
    refs = list(field.supporting_chunk_ids or [])
    evidence_type, observation_source_type = source_types

    if spec.kind == "cefr":
        dimension = resolved.bound["dimension"]
        level = str(value).strip()
        out = store.append_observation(
            Observation(
                student_id=student_id,
                teacher_id=teacher_id,
                template_type="cefr",
                raw_transcript=(
                    f"CEFR {dimension} level {level} from a teacher's observation ({source_file})."
                    if observation_source_type == "teacher_note"
                    else f"CEFR {dimension} level {level} imported from a source document ({source_file})."
                ),
                cefr_dimension=dimension,
                cefr_level_observed=level,
                source_type=observation_source_type,
            ),
            duplicate_window_seconds=_CEFR_DUPLICATE_WINDOW_SECONDS,
        )
        return "already present (deduplicated)" if out.get("duplicate") else "cefr observation appended"

    if spec.kind == "support_profile":
        category = resolved.bound.get("category")
        bucket = resolved.bound["bucket"]
        note = ""
        if spec.rehome:
            # Ruling A: the bridge's declared mapping, applied and SAID.
            category = spec.rehome["category"]
            bucket = spec.rehome["bucket"] if bucket == "evidence" else bucket
            note = f"re-homed to support_profile.categories.{category}.{bucket} per the declared bridge mapping; "
        profile = store.get_support_profile(student_id)
        existing = (profile.get("categories") or {}).get(category, {}).get(bucket) or []
        wrote = 0
        skipped = 0
        for txt in _texts(value):
            if bucket == "evidence":
                if _already_present(existing, txt, "summary", refs):
                    skipped += 1
                    continue
                store.add_support_evidence(
                    student_id=student_id, category_id=category, summary=txt,
                    created_by=teacher_id, evidence_type=evidence_type, source_ref_ids=refs,
                )
            else:
                if _already_present(existing, txt, "text", refs):
                    skipped += 1
                    continue
                store.add_support_entry(
                    student_id=student_id, category_id=category, bucket=bucket, text=txt,
                    created_by=teacher_id, confidence=confidence, source_ref_ids=refs,
                )
            wrote += 1
        return note + (f"{wrote} entries written" + (f", {skipped} already present" if skipped else ""))

    if spec.kind == "strengths":
        kind = "academic" if path == "academic_strengths" else "personal"
        for txt in _texts(value):
            store.add_profile_strength(
                student_id=student_id, kind=kind, text=txt, created_by=teacher_id,
                source_ref_ids=refs, confidence=confidence,
            )  # idempotent inside the store (same text + source)
        return "profile strength appended"

    if spec.kind == "scalar" and spec.writer == "column:trauma_flag":
        store._conn.execute(
            "UPDATE students SET trauma_flag = ?, updated_at = updated_at WHERE student_id = ?",
            (1 if bool(value) else 0, student_id),
        )
        store._conn.commit()
        return "column set on teacher confirmation"

    if spec.kind == "scalar" and spec.writer == "store:update_profile":
        current = store.get_lens(student_id).get(path)
        new_value = value if isinstance(value, list) else str(value)
        if current == new_value:
            return "already present (unchanged)"
        store.update_profile(student_id, {path: new_value})
        return "profile field updated"

    raise ValueError(f"no dispatch for kind {spec.kind!r} with writer {spec.writer!r}")
