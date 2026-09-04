"""Observe → the lens, through the ONE logic documents already use.

PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md §0.1: the single lens-update logic
already exists (`docpipe/lens_extract.py`) and Observe did not use it — a
teacher's comment took a shorter path that shares one function with the
document pipeline and never gets sentence-by-sentence routing, per-field
confidence, or the review contract.

This module routes a comment through exactly that logic and then through the
lens field contract's writer:

    comment text ─► extract_for_lens_update()   (same splitter, same
                                                  safeguarding gate, same
                                                  heuristic + classifier routing)
                 ─► write_student_lens()          (every candidate field resolved
                                                  through lens_field_contract.resolve(),
                                                  same refusal semantics, same
                                                  accounting invariant)

Kill gate K2 (spec §6.2) is respected by construction: no existing field's
meaning changes. Candidates land in the same buckets a report card would
fill, at `needs_confirmation` where the classifier is unsure, with
`source_kind="teacher_note"` so the lens records that the entry came from a
teacher's own comment and not from a PDF.

This does NOT replace `ObservationCapturePipeline.capture()`, which still
records the raw comment as an append-only observation. It is the second
half: the comment's *content* reaching the lens's fields, accounted for.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from src.education.student_lens import StudentLensStore
from src.lingua_viva.docpipe.lens_extract import extract_for_lens_update
from src.lingua_viva.student_lens_writer import write_student_lens

SOURCE_KIND = "teacher_note"


async def observe_comment_to_lens(
    text: str,
    *,
    student_id: str,
    display_name: str,
    teacher_id: str,
    store: StudentLensStore,
    engine: Any = None,
    confirmed_fields: Optional[list[Any]] = None,
) -> dict:
    """Route one teacher comment to one student's lens through the contract.

    Returns the writer's result (written_fields / review_required /
    unresolved_questions / accounting) plus `candidate_fields`: every field
    the routing proposed, with its status, so a UI can offer the
    `needs_confirmation` ones for a two-second confirm (U8).
    """
    comment = (text or "").strip()
    if not comment:
        return {
            "student_id": student_id,
            "written_fields": [],
            "review_required": [],
            "unresolved_questions": ["The comment was empty; nothing to route."],
            "accounting": [],
            "candidate_fields": [],
        }

    results = await extract_for_lens_update(
        document_bytes=comment.encode("utf-8"),
        document_type="observation",
        matched_students=[{"student_id": student_id, "display_name": display_name}],
        lens_store=store,
        engine=engine,
    )
    result = results[student_id]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result.source_files = [f"observe:{teacher_id}:{stamp}"]

    out = write_student_lens(
        result,
        teacher_id=teacher_id,
        confirmed_fields=confirmed_fields,
        hint={"assigned_student_id": student_id},
        store=store,
        source_kind=SOURCE_KIND,
    )
    out["candidate_fields"] = [
        {
            "field_path": f.field_path,
            "value": f.value,
            "status": f.status,
            "confidence": f.confidence,
        }
        for f in result.fields
    ]
    out["source"] = result.source_files[0]
    return out


def observe_comment_to_lens_sync(text: str, **kwargs: Any) -> dict:
    """Blocking convenience for callers without an event loop."""
    return asyncio.run(observe_comment_to_lens(text, **kwargs))
