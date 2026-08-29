"""
Document-to-Lens Import Router (R7 API routes).

SPEC: dev/SPEC_LV_DOCUMENT_TO_LENS_PIPELINE_2026-08-23.md

Two-step flow:
1. POST /api/students/import-document → classify, match, extract, preview
2. POST /api/students/apply-extractions → teacher confirms, write to lenses
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/students")


@router.post("/import-document")
async def import_document(request: Request):
    """Step 1: Upload a document, classify it, match students, extract data.

    Accepts multipart file upload.
    Returns: {document_type, matched_students, extractions_preview, extraction_log_path}
    """
    from src.lingua_viva.docpipe.extract import classify_document_type
    from src.lingua_viva.docpipe.lens_match import match_document_to_students
    from src.lingua_viva.docpipe.lens_extract import (
        extract_for_lens_update,
        save_extraction_log,
    )
    from src.education.student_lens import StudentLensStore

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return JSONResponse(
            {"error": "Please upload a file (multipart/form-data)."},
            status_code=400,
        )

    form = await request.form()
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        return JSONResponse(
            {"error": "Please attach a file to import."},
            status_code=400,
        )

    content = await upload.read()
    filename = upload.filename or "imported-file"

    # Decode for text analysis
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        text = ""

    if not text.strip():
        return JSONResponse(
            {"error": "The file appears to be empty or unreadable."},
            status_code=400,
        )

    # R1: Classify document type
    doc_type = classify_document_type(text, filename)

    # If it's a class list, tell them to use the roster import
    if doc_type == "class_list":
        return JSONResponse({
            "document_type": "class_list",
            "message": "This looks like a class list. Use the roster import above to create student lenses.",
            "matched_students": [],
            "extractions_preview": {},
        })

    # If it's curriculum or other, tell them plainly
    if doc_type in ("curriculum", "other"):
        return JSONResponse({
            "document_type": doc_type,
            "message": (
                f"This doesn't look like a student file. It looks like a {doc_type} document. "
                "To import a class list, use a spreadsheet with student names."
            ),
            "matched_students": [],
            "extractions_preview": {},
        })

    # R2: Match against existing roster
    store = StudentLensStore()
    try:
        lenses = store.list_lenses()
        roster = [
            {"student_id": l["student_id"], "display_name": l["display_name"]}
            for l in lenses
        ]
        matched = match_document_to_students(text, filename, roster)

        if not matched:
            return JSONResponse({
                "document_type": doc_type,
                "message": "No matching students found in your roster. Import a class list first.",
                "matched_students": [],
                "extractions_preview": {},
            })

        # R3+R4: Extract data
        results = await extract_for_lens_update(
            document_bytes=content,
            document_type=doc_type,
            matched_students=matched,
            lens_store=store,
        )

        # R6: Persist extraction log BEFORE any lens write
        log_path = save_extraction_log(results, filename)

        # Build preview for UI
        preview: dict[str, dict] = {}
        for student_id, result in results.items():
            preview[student_id] = {
                "fields": [
                    {
                        "field_path": f.field_path,
                        "value": f.value,
                        "confidence": f.confidence,
                        "status": f.status,
                    }
                    for f in result.fields
                ],
                "unresolved_questions": result.unresolved_questions,
                "field_count": len([f for f in result.fields if f.status != "unsupported"]),
            }

        return JSONResponse({
            "document_type": doc_type,
            "matched_students": matched,
            "extractions_preview": preview,
            "extraction_log_path": str(log_path),
            "message": (
                f"Found information for {len(matched)} student(s). "
                "Review below and click 'Update lenses' to apply."
            ),
        })
    finally:
        store.close()


@router.post("/apply-extractions")
async def apply_extractions(request: Request):
    """Step 2: Teacher confirms, write extractions to lenses.

    Accepts JSON: {extraction_log_path, confirmed_students: [student_id, ...]}
    Returns: {updated_students: [{student_id, fields_written, ...}]}
    """
    from src.lingua_viva.docpipe.lens_extract import (
        apply_extractions_to_lenses,
        load_extraction_log,
        resolve_import_log_path,
    )
    from src.education.student_lens import StudentLensStore

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Invalid request body."},
            status_code=400,
        )

    log_path_str = payload.get("extraction_log_path", "")
    confirmed_students = payload.get("confirmed_students", [])

    if not log_path_str:
        return JSONResponse(
            {"error": "Missing extraction_log_path."},
            status_code=400,
        )

    try:
        log_path = resolve_import_log_path(log_path_str)
    except ValueError:
        return JSONResponse(
            {"error": "Extraction log path is not valid. Please re-upload the document."},
            status_code=400,
        )
    if not log_path.exists():
        return JSONResponse(
            {"error": "Extraction log not found. Please re-upload the document."},
            status_code=404,
        )

    # Load saved extraction results
    results = load_extraction_log(log_path)
    if not results:
        return JSONResponse(
            {"error": "No extraction data found in log."},
            status_code=400,
        )

    # Apply to lenses
    store = StudentLensStore()
    try:
        summaries = await apply_extractions_to_lenses(
            results=results,
            lens_store=store,
            confirmed_students=confirmed_students or None,
        )

        updated = []
        for student_id, summary in summaries.items():
            updated.append({
                "student_id": student_id,
                "fields_written": summary.get("written_fields", []),
                "review_required": summary.get("review_required", []),
                "written_count": summary.get("feedback", {}).get("written_count", 0),
            })

        return JSONResponse({
            "updated_students": updated,
            "message": f"Updated {len(updated)} student lens(es).",
        })
    finally:
        store.close()
