"""
Student Lens Artifact Writer v2 — SPEC_LV_INGESTION_EXTRACTION_MAPPING_V2_2026-07-23.md (§10)

Consumes ExtractionResult objects and writes verified/teacher-confirmed fields into
StudentLensStore. Enforces:
  1. trauma_flag is NEVER auto-written.
  2. Support-profile entries require non-empty supporting_chunk_ids (source refs).
  3. Verified fields write with confidence="imported_verified".
  4. Teacher-confirmed fields write with confidence="imported_needs_confirmation".
  5. Unconfirmed needs_confirmation fields remain pending review.
"""

from __future__ import annotations

from typing import Any, Optional
from src.education.student_lens import (
    StudentLensStore,
    SUPPORT_CATEGORY_IDS,
    Observation,
    ObservationValidationError,
    VALID_CEFR_DIMENSIONS,
    VALID_CEFR_LEVELS,
)
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult


def write_student_lens(
    result: ExtractionResult,
    teacher_id: str = "local-teacher",
    confirmed_fields: Optional[list[Any]] = None,
    rejected_fields: Optional[list[Any]] = None,
    hint: Optional[dict] = None,
    store: Optional[StudentLensStore] = None,
) -> dict:
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
        confirmed_set = set()
        if confirmed_fields:
            for item in confirmed_fields:
                if isinstance(item, str):
                    confirmed_set.add(item)
                elif isinstance(item, dict) and item.get("field_path"):
                    confirmed_set.add(item["field_path"])
                elif isinstance(item, ExtractedField):
                    confirmed_set.add(item.field_path)

        rejected_set = set()
        if rejected_fields:
            for item in rejected_fields:
                if isinstance(item, str):
                    rejected_set.add(item)
                elif isinstance(item, dict) and item.get("field_path"):
                    rejected_set.add(item["field_path"])
                elif isinstance(item, ExtractedField):
                    rejected_set.add(item.field_path)

        # 1. Determine student ID
        student_id = hint.get("assigned_student_id") or hint.get("student_id")
        
        # Check if display_name is present in verified or confirmed fields
        display_name = None
        for field in result.fields:
            if field.field_path == "display_name":
                if field.status == "verified" or field.field_path in confirmed_set:
                    display_name = str(field.value)

        if not student_id:
            if display_name:
                student_id = store.create_lens(display_name=display_name)
            else:
                # Default to first lens or create lens with default name if result has any content
                lenses = store.list_lenses()
                if lenses:
                    student_id = lenses[0]["student_id"]
                else:
                    student_id = store.create_lens(display_name="Imported Student")

        written_fields = []
        review_required = []
        unresolved_questions = list(result.unresolved_questions or [])
        written_count = 0
        review_confirmed = 0
        review_rejected = len(rejected_set)

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
                                supporting_chunk_ids=item.get("supporting_chunk_ids") or [f"{result.source_files[0] if result.source_files else 'file.txt'}#chunk-0000"],
                                status="verified",
                            )
                        )
                        existing_paths.add(item["field_path"])

        for field in fields_to_process:
            path = field.field_path
            value = field.value
            status = field.status

            # Trauma flag safety rule
            if path == "trauma_flag":
                if path in confirmed_set:
                    store._conn.execute(
                        "UPDATE students SET trauma_flag = ? WHERE student_id = ?",
                        (1 if bool(value) else 0, student_id),
                    )
                    store._conn.commit()
                    written_fields.append(path)
                    written_count += 1
                    review_confirmed += 1
                else:
                    review_required.append(path)
                continue

            if status == "classify_failed":
                # P0-3: sentences whose classification batch failed are
                # visible in the import result but NEVER written to the
                # lens — no data beats fake data. Content-free note only.
                unresolved_questions.append(
                    "A sentence could not be classified (model call failed) "
                    "and was not imported — review the source document."
                )
                continue

            if status == "unsupported" and path not in confirmed_set:
                unresolved_questions.append(f"Field '{path}' was unsupported by source references.")
                continue

            if status == "needs_confirmation" and path not in confirmed_set:
                review_required.append(path)
                continue

            if path in rejected_set:
                continue

            # Determine confidence tag
            confidence = "imported_verified" if status == "verified" else "imported_needs_confirmation"
            if path in confirmed_set:
                review_confirmed += 1

            # Handle support profile fields
            if path.startswith("support_profile.categories."):
                if not field.supporting_chunk_ids:
                    unresolved_questions.append(
                        f"Refused support profile entry for '{path}': missing source references."
                    )
                    continue

                parts = path.split(".")
                if len(parts) >= 4:
                    cat_id = parts[2]
                    bucket = parts[3]

                    if cat_id in SUPPORT_CATEGORY_IDS:
                        texts = value if isinstance(value, list) else [value]
                        for txt in texts:
                            if isinstance(txt, str) and txt.strip():
                                if bucket == "evidence":
                                    store.add_support_evidence(
                                        student_id=student_id,
                                        category_id=cat_id,
                                        summary=txt.strip(),
                                        created_by=teacher_id,
                                        evidence_type="report",
                                        source_ref_ids=field.supporting_chunk_ids,
                                    )
                                else:
                                    store.add_support_entry(
                                        student_id=student_id,
                                        category_id=cat_id,
                                        bucket=bucket,
                                        text=txt.strip(),
                                        created_by=teacher_id,
                                        confidence=confidence,
                                        source_ref_ids=field.supporting_chunk_ids,
                                    )
                        written_fields.append(path)
                        written_count += 1
                continue

            # CEFR levels extracted from a document (2026-09-03).
            #
            # These were previously DROPPED IN SILENCE. The extractor emits
            # cefr_snapshot.{reading,writing,speaking,listening} at status
            # "verified", confidence 0.95; the preview showed them; this
            # function had no branch for the path, so they fell off the end of
            # the loop. A teacher saw four CEFR levels in the import preview,
            # clicked "Update lenses", got a success message naming four other
            # fields, and the lens still read null on all four dimensions.
            #
            # The write goes through append_observation, NOT a direct column
            # write. set_initial_cefr's docstring carries the law: cefr_snapshot
            # must stay DERIVED from the append-only observation log so
            # get_lens_as_of() reconstruction holds — the same rule that keeps
            # rti_current_tier out of update_profile(). set_initial_cefr itself
            # cannot be reused here because it applies one level to all four
            # dimensions, and a report card carries a different level per
            # dimension (reading A2, writing A1, ...).
            if path.startswith("cefr_snapshot."):
                dimension = path.split(".", 1)[1].strip()
                level = str(value or "").strip()
                if dimension not in VALID_CEFR_DIMENSIONS:
                    unresolved_questions.append(
                        f"Refused '{path}': '{dimension}' is not a CEFR dimension."
                    )
                    continue
                if level not in VALID_CEFR_LEVELS:
                    unresolved_questions.append(
                        f"Refused '{path}': '{level}' is not a recognised CEFR level."
                    )
                    continue
                if not field.supporting_chunk_ids:
                    unresolved_questions.append(
                        f"Refused CEFR level for '{path}': missing source references."
                    )
                    continue
                try:
                    store.append_observation(
                        Observation(
                            student_id=student_id,
                            teacher_id=teacher_id,
                            template_type="cefr",
                            raw_transcript=(
                                f"CEFR {dimension} level {level} imported from a "
                                f"source document."
                            ),
                            cefr_dimension=dimension,
                            cefr_level_observed=level,
                            source_type="local_file",
                        )
                    )
                except ObservationValidationError as exc:
                    unresolved_questions.append(f"Refused '{path}': {exc}")
                    continue
                written_fields.append(path)
                written_count += 1
                continue

            # Handle ordinary fields (grade_level, campus, home_languages, learning_differences, etc.)
            if path == "grade_level" and value:
                store._conn.execute(
                    "UPDATE students SET grade_level = ? WHERE student_id = ?",
                    (str(value), student_id),
                )
                store._conn.commit()
                written_fields.append(path)
                written_count += 1
                continue
            if path == "campus" and value:
                store._conn.execute(
                    "UPDATE students SET campus = ? WHERE student_id = ?",
                    (str(value), student_id),
                )
                store._conn.commit()
                written_fields.append(path)
                written_count += 1
                continue

            # REFUSE ON UNKNOWN FIELD PATH (2026-09-03).
            #
            # Every branch above either writes the field or says why it did
            # not. Before this, anything the chain did not recognise fell off
            # the end of the loop in silence: not written, not reviewed, not
            # reported, and absent from written_fields — so the caller returned
            # a success payload that simply did not mention it.
            #
            # That is how the CEFR defect above survived a week of work on this
            # exact feature. A field path this writer cannot handle is now a
            # visible refusal, and the same rule protects Observe and Assess
            # before either is wired: any new extractor that invents a field
            # path this writer does not implement will SAY SO instead of
            # quietly discarding a teacher's input.
            unresolved_questions.append(
                f"'{path}' was extracted but this version cannot write it to the "
                f"lens, so it was not imported. Nothing was changed for that field."
            )

        message = (
            f"{written_count} fields were written with source references."
            + (f" {review_confirmed} ambiguous fields were confirmed by the teacher." if review_confirmed else "")
        )

        return {
            "student_id": student_id,
            "written_fields": written_fields,
            "review_required": review_required,
            "unresolved_questions": unresolved_questions,
            "feedback": {
                "written_count": written_count,
                "review_confirmed": review_confirmed,
                "review_rejected": review_rejected,
                "message": message,
                "next_review_prompt": "Check whether strategy outcomes were language-specific or setting-specific.",
            },
        }
    finally:
        if close_store_on_exit:
            store.close()
