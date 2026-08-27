"""Students routes — roster, ingest, lens, evidence, RTI, artifacts.

Moved verbatim from src/web.py (P1-ARCH-001 web.py split, 2026-08-22) into
the router plug-in pattern (routers/__init__.py ROUTER_MODULES). The ONLY
mechanical change is ``@app.`` -> ``@router.`` on the decorators; handler
bodies, helper functions, and route paths are byte-identical to what web.py
registered before the move.

Contract notes:
- ``router`` uses NO prefix: every decorator carries its full literal
  "/api/students/..." path, so the paths stay greppable and the
  route-reachability manifest entries stay byte-identical.
- NEVER import src.web (circular). Shared definitions used by both this
  module and web.py (student store access, broadcaster, deliverable
  builder) live in src.lingua_viva.web_helpers.
- The server-side role gate in web.py matches by path prefix
  ("/api/students" -> teacher-or-higher), so router-registered routes are
  covered exactly like the originals.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from src.lingua_viva.web_helpers import (
    STUDENT_GRADE_LEVELS,
    _decision_deliverable,
    _with_student_store,
    broadcaster,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Students ingest — file → vault → extraction → lens scaffolds (T9,
# SPEC_T9_INGEST_UI_2026-08-04). One tab end-to-end. T1 (Drive fetch) and T3
# (extraction) are contract-frozen seams: call sites use the exact frozen
# signatures and degrade honestly while a seam is unimplemented.
# ---------------------------------------------------------------------------

INGEST_MAX_BYTES = 15 * 1024 * 1024
BULK_IMPORT_CONFIRMATION_THRESHOLD = 2
_INGEST_JOBS: dict[str, dict] = {}


def _ingest_job(job_id: str) -> Optional[dict]:
    job = _INGEST_JOBS.get(job_id)
    if job is not None:
        return job
    path = _ingest_job_path(job_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    _INGEST_JOBS[job_id] = data
    return data


def _ingest_jobs_dir() -> Path:
    root = Path(os.environ.get("LV_STATE_HOME") or Path.home() / ".lingua-viva")
    return root / "ingest-jobs"


def _ingest_job_path(job_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", job_id)
    return _ingest_jobs_dir() / f"{safe}.json"


def _save_ingest_job(job: dict) -> None:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        return
    path = _ingest_job_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _new_ingest_job(source_id: str, source_name: str, teacher_id: str = "teacher:ingest") -> dict:
    job = {
        "job_id": f"JOB-{uuid.uuid4()}",
        "status": "queued",
        "source_id": source_id,
        "source_name": source_name,
        "teacher_id": teacher_id,
        "students_found": 0,
        "preview_students": [],
        "preview_classes": [],
        "students_created": [],
        "needs_confirmation": [],
        "identity_review": [],
        "warnings": [],
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _INGEST_JOBS[job["job_id"]] = job
    _save_ingest_job(job)
    return job


def _build_source_record(*, filename: str, content: bytes, origin: str, path: str,
                         drive_file_id: Optional[str] = None) -> "object":
    import mimetypes

    from src.lingua_viva.docpipe.contracts import SourceRecord

    ext = Path(filename).suffix.lower()
    mime = mimetypes.guess_type(filename)[0] or (
        "text/markdown" if ext in (".md", ".markdown") else "application/octet-stream"
    )
    return SourceRecord({
        "schema_version": "docpipe.source.v1",
        "source_id": f"SRC-{uuid.uuid4()}",
        "origin": origin,
        "drive_file_id": drive_file_id,
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mime": mime,
        "owner": "teacher:local",
        "original_filename": filename,
        "original_ext": ext,
        "byte_size": len(content),
    })


def _create_lens_for_detected(extraction, detected: dict, teacher_id: str = "teacher:ingest") -> dict:
    """Create (or merge into) a lens for one detected student, bridged into
    the roster via StudentLensStore. Runs in a worker thread."""
    from src.lingua_viva.docpipe import lens as docpipe_lens

    student_id = str(detected.get("student_id") or f"student-{uuid.uuid4()}")
    display_name = str(detected.get("display_name") or "").strip()

    def bridge(store):
        return docpipe_lens.create_from_extraction(
            extraction,
            student_id=student_id,
            student_name=display_name,
            added_by=str(teacher_id or "teacher:ingest").strip() or "teacher:ingest",
            student_store=store,
        )

    record = _with_student_store(bridge)
    # Operator ruling (brief §8.1): a locally saved lens propagates to Drive.
    # Enqueue is offline-safe — the T6 queue holds until push_file can drain.
    try:
        from src.lingua_viva.docpipe import sync as docpipe_sync

        docpipe_sync.enqueue_lens(student_id)
    except Exception:
        pass
    populated = [
        field_id
        for field_id, field in record.data.get("profile", {}).items()
        if field.get("evidence")
    ]
    return {
        "student_id": student_id,
        "display_name": display_name,
        "fields_populated": populated,
    }


def _safe_confidence(student: dict) -> float:
    try:
        return float(student.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _trusted_detection(student: dict) -> bool:
    """STEP 3 (SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19): trust rides on HOW
    the name was found, not on a number. The numeric confidence is a flat
    constant (VERBATIM_STUDENT_CONFIDENCE = 0.99), so the old
    INGEST_CONFIDENCE_THRESHOLD = 0.7 gate could never fire — a check that
    reported as working but did not happen. The corpus proved the evidence
    CLASS discriminates instead: student_column detections scored precision
    1.00 on every real file, while the bigram fallback scored 0.14/0.00/0.00
    on the same files. Detections without an evidence class (older
    extractions) are untrusted."""
    return student.get("evidence") in {"student_column", "per_class_sheet_support"}


def _detected_students(extraction) -> list[dict]:
    return [
        student
        for student in extraction.data.get("structure", {}).get("students_detected", [])
        if isinstance(student, dict) and str(student.get("display_name") or "").strip()
    ]


def _teacher_roster_snapshot(teacher_id: str) -> list[dict]:
    """STEP 5 (SPEC §STEP 5, L8): the identity-resolution scope — the
    approving teacher's roster (~39 names, never the whole school; a fresh
    single-teacher install's fallback IS her roster). Snapshotted once per
    approve so resolution is deterministic across the batch."""
    def read(store):
        return [
            {
                "student_id": str(lens.get("student_id") or ""),
                "display_name": str(lens.get("display_name") or ""),
            }
            for lens in store.list_lenses_for_teacher(teacher_id)
        ]

    return _with_student_store(read)


def _resolve_or_queue(student: dict, *, job: dict, roster: list[dict]) -> Optional[dict]:
    """Resolve one detection's identity before ANY lens creation (STEP 5).

    Returns the (possibly id-rewritten) student to create, or None when the
    spelling landed in the unresolved queue. Default per ruling §8-3: a
    plausible-but-inexact match is ALWAYS queued for a human, NEVER
    auto-merged — "Marco B-R" must not silently become a second child next
    to "Marco Bianchi", and must not silently become the same child either.
    """
    from src.lingua_viva.docpipe import identity

    display_name = str(student.get("display_name") or "").strip()
    resolution = identity.resolve(display_name, roster)
    if resolution["status"] == "exact":
        # The spelling IS a roster student (or a spelling a human already
        # ruled on) — merge into the canonical lens, whatever the slug says.
        return {**student, "student_id": resolution["student_id"]}
    if resolution["status"] == "queue":
        identity.enqueue_unresolved(
            teacher_id=str(job.get("teacher_id") or "teacher:ingest"),
            display_name=display_name,
            source_id=str(job.get("source_id") or ""),
            candidates=resolution["candidates"],
            job_id=str(job.get("job_id") or ""),
        )
        job.setdefault("identity_review", []).append({
            "display_name": display_name,
            "candidates": resolution["candidates"],
        })
        return None
    if student.get("evidence") == "per_class_sheet_support":
        identity.enqueue_unresolved(
            teacher_id=str(job.get("teacher_id") or "teacher:ingest"),
            display_name=display_name,
            source_id=str(job.get("source_id") or ""),
            candidates=[],
            job_id=str(job.get("job_id") or ""),
        )
        job.setdefault("identity_review", []).append({
            "display_name": display_name,
            "candidates": [],
            "possible_new_student": True,
        })
        return None
    return student


async def _create_from_preview(job: dict, extraction) -> None:
    """Runs only after the teacher's explicit approve. Everything that writes
    to the student store or touches Drive lives here — never in the preview
    path (Phase 0A, SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19 §2A)."""
    try:
        detected = _detected_students(extraction)
        # STEP 4 (SPEC §STEP 4, L4): "only my class" — when the approve
        # carried a class scope, only students whose detected class is in it
        # are created. The teacher wants her ~39, not 400. Students the
        # detector could not place in a class are excluded by an explicit
        # scope (never silently included) and counted in a warning.
        approved_classes = [
            str(item).strip()
            for item in (job.get("approved_classes") or [])
            if str(item).strip()
        ]
        if approved_classes:
            in_scope = [
                student for student in detected
                if str(student.get("class") or "").strip() in approved_classes
            ]
            skipped = len(detected) - len(in_scope)
            if skipped:
                job["warnings"].append(
                    f"Skipped {skipped} detected name(s) outside your selected "
                    f"class ({', '.join(approved_classes)})."
                )
            detected = in_scope
        # F1b (SPEC_LV_DEMO_EVE_FIX_2026-08-19 §2): names the teacher toggled
        # OUT of the confirm set in the preview are never created — her
        # per-entry remedy against the next structural surprise.
        excluded_names = {
            str(item).strip()
            for item in (job.get("excluded_names") or [])
            if str(item).strip()
        }
        if excluded_names:
            before = len(detected)
            detected = [
                student for student in detected
                if str(student.get("display_name") or "").strip() not in excluded_names
            ]
            removed = before - len(detected)
            if removed:
                job["warnings"].append(
                    f"Left out {removed} name(s) you unticked in the preview."
                )
        # SPEC_LV_DRIVE_OOTB 2026-08-18 (G3): roster-style imports (more than
        # BULK_IMPORT_CONFIRMATION_THRESHOLD students) auto-create EVERY
        # detected student — the teacher contract allows no per-name confirm
        # clicks. Untrusted names are still created but flagged in warnings;
        # "Undo this import" (one click, archives all) is the review
        # mechanism. Small imports keep the gate: a single pattern-matched
        # guess in one student's document must not silently become a roster
        # entry. STEP 3: the gate is the corpus-measured evidence class
        # (_trusted_detection), not a numeric threshold that never fired.
        roster_import = len(detected) > BULK_IMPORT_CONFIRMATION_THRESHOLD
        # STEP 5 (SPEC §STEP 5, L8): identity resolves against the approving
        # teacher's roster BEFORE any creation — exact spellings (and human-
        # ruled surface forms) merge into their canonical lens, plausible
        # matches go to the unresolved queue, only genuinely new names mint
        # new lenses. Zero silent duplicates.
        roster = await asyncio.to_thread(
            _teacher_roster_snapshot, job.get("teacher_id") or "teacher:ingest"
        )
        low_confidence_names: list[str] = []
        veto_flagged_names: list[str] = []
        for student in detected:
            # STEP 6 (SPEC §STEP 6, L7): the enrichment veto is review-gated,
            # never auto-applied. On a small import a flagged name waits for
            # the teacher's confirm click (with the model's reason); on a
            # roster import the G3 zero-click contract holds — the name is
            # created but the veto is surfaced loudly in warnings, and the
            # one-click Remove is the mechanism.
            veto_reason = str(student.get("removal_proposed") or "").strip()
            if veto_reason and not roster_import:
                job["needs_confirmation"].append({
                    "display_name": str(student.get("display_name")),
                    "confidence": _safe_confidence(student),
                    "reason": f"The AI thinks this may not be a student: {veto_reason}",
                })
                continue
            if roster_import:
                if veto_reason:
                    veto_flagged_names.append(str(student.get("display_name")))
                student = _resolve_or_queue(student, job=job, roster=roster)
                if student is None:
                    continue
                created = await asyncio.to_thread(
                    _create_lens_for_detected, extraction, student, job.get("teacher_id") or "teacher:ingest"
                )
                job["students_created"].append(created)
                if not _trusted_detection(student):
                    low_confidence_names.append(str(student.get("display_name")))
            elif _trusted_detection(student):
                student = _resolve_or_queue(student, job=job, roster=roster)
                if student is None:
                    continue
                created = await asyncio.to_thread(
                    _create_lens_for_detected, extraction, student, job.get("teacher_id") or "teacher:ingest"
                )
                job["students_created"].append(created)
            else:
                # Never auto-create on a guess — surface for the teacher.
                job["needs_confirmation"].append({
                    "display_name": str(student.get("display_name")),
                    "confidence": _safe_confidence(student),
                    "reason": "Found by pattern-matching the text, not in a student-name column.",
                })
        if low_confidence_names:
            job["warnings"].append(
                "Check these names — they were read with low confidence: "
                + ", ".join(low_confidence_names)
            )
        if veto_flagged_names:
            job["warnings"].append(
                "The AI thinks these may not be students: "
                + ", ".join(veto_flagged_names)
                + ". If it's right, remove them from the roster with one click."
            )
        if job.get("identity_review"):
            names = ", ".join(item["display_name"] for item in job["identity_review"])
            job["warnings"].append(
                f"Not created yet — these names look like students you already "
                f"have: {names}. Decide in the identity review below."
            )
        job["status"] = "done"
        _save_ingest_job(job)
        # SPEC_LV_DRIVE_OOTB 2026-08-18 (G5): freshly created lenses propagate
        # to Drive with zero teacher action. Auto-provision the lens folder on
        # first need, then fire-and-forget sync per student — failures queue
        # honestly and drain later; the import itself is already done.
        if job["students_created"]:
            try:
                from src.lingua_viva.drive_sync import ensure_lens_sync_folder, trigger_sync

                await asyncio.to_thread(ensure_lens_sync_folder)
                for created in job["students_created"]:
                    student_id = str((created or {}).get("student_id") or "").strip()
                    if student_id:
                        trigger_sync(student_id)
            except Exception:
                pass  # sync is best-effort; the import itself already succeeded
    except Exception as error:
        job["status"] = "failed"
        job["error"] = f"Could not create the students: {error}"
        _save_ingest_job(job)


async def _run_ingest_job(job: dict, source, content: bytes) -> None:
    from src.lingua_viva.docpipe import extract as docpipe_extract
    from src.lingua_viva.docpipe import vault as docpipe_vault

    try:
        job["status"] = "extracting"
        _save_ingest_job(job)
        # Local model enrichment when available; extraction is deterministic
        # without it (offline is a supported state — T3 spec §0).
        model_client = None
        try:
            from src.lingua_viva.docpipe.model import LocalModelClient

            model_client = LocalModelClient()
        except Exception:
            model_client = None
        extraction = await docpipe_extract.extract_document(
            source, content, model_client=model_client
        )
        await asyncio.to_thread(docpipe_vault.put_extraction, extraction)
        job["status"] = "identifying"
        _save_ingest_job(job)
        detected = _detected_students(extraction)
        job["students_found"] = len(detected)
        job["warnings"] = [str(w) for w in extraction.data.get("warnings", [])]
        # Phase 0A (SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19 §2A): the ingest
        # job stops here, at a PREVIEW. It has created NOTHING and synced
        # NOTHING — the extraction sits in the vault, the would-be result is
        # reported per student, and only the explicit approve step
        # (/api/students/ingest/approve) may create lenses. Always-preview is
        # the default pending operator ruling §8-1.
        if not detected:
            # Nothing to approve — finishing as "done" with zero creations is
            # the same honest outcome with one fewer click.
            job["status"] = "done"
            _save_ingest_job(job)
            return
        # STEP 4 (SPEC §STEP 4, L4): detections from class-pair sheets carry
        # class / grade / teacher_attribution — surfaced on every preview row
        # so the teacher can scope the approve to "only my class".
        job["preview_students"] = [
            {
                "display_name": str(student.get("display_name") or "").strip(),
                "confidence": _safe_confidence(student),
                "low_confidence": not _trusted_detection(student),
                "span_ids": [str(sid) for sid in (student.get("span_ids") or [])],
                **{
                    key: str(student.get(key))
                    for key in (
                        "class",
                        "grade",
                        "teacher_attribution",
                        "removal_proposed",
                        # F1.4: block provenance — which sheet rows/columns the
                        # name came from, so a wrong segmentation is visible
                        # in the preview before confirm.
                        "source_rows",
                    )
                    if str(student.get(key) or "").strip()
                },
            }
            for student in detected
        ]
        job["preview_classes"] = sorted({
            str(student.get("class"))
            for student in detected
            if str(student.get("class") or "").strip()
        })
        job["status"] = "preview"
        _save_ingest_job(job)
    except NotImplementedError:
        job["status"] = "failed"
        job["error"] = (
            "Document extraction is not available in this build yet. The file "
            "was saved safely and nothing was invented — try again after the "
            "next update."
        )
        _save_ingest_job(job)
    except Exception as error:
        job["status"] = "failed"
        msg = str(error)
        if "no extractable text" in msg:
            msg += " If this is a scanned document, try a Word or text version instead."
        job["error"] = f"Could not read this document: {msg}"
        _save_ingest_job(job)


@router.post("/api/students/ingest")
async def students_ingest(request: Request, background_tasks: BackgroundTasks):
    from src.lingua_viva.docpipe import vault as docpipe_vault

    content_type = request.headers.get("content-type", "")
    filename = ""
    content = b""
    origin = "local"
    drive_file_id = None
    path = ""
    ingest_teacher = "teacher:ingest"
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            return JSONResponse({"error": "attach a file to import"}, status_code=400)
        content = await upload.read()
        filename = upload.filename or "imported-file"
        path = filename
        ingest_teacher = str(form.get("teacher_id") or "").strip() or "teacher:ingest"
    else:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "attach a file to import"}, status_code=400)
        drive_ref = str((payload or {}).get("drive_ref", "")).strip()
        ingest_teacher = str((payload or {}).get("teacher_id") or "").strip() or "teacher:drive"
        if not drive_ref:
            return JSONResponse({"error": "attach a file or provide a drive_ref"}, status_code=400)
        # Real fetch (SPEC_LV_DRIVE_OOTB 2026-08-18, G2) — errors map to
        # honest teacher-readable failures, never a 500.
        from src.lingua_viva.docpipe import drive as docpipe_drive
        from src.lingua_viva.google_drive_integration import (
            DriveAuthError,
            DriveConfigError,
            DriveFileTooLarge,
            parse_folder_link,
        )

        # A pasted FOLDER link routes to the class-folder ingest (match every
        # document inside by student name) instead of the single-file roster
        # path. Only unambiguous folder URLs qualify — "?id=" links stay on
        # the file path because both URL grammars use that form.
        if "/folders/" in drive_ref:
            folder_id = parse_folder_link(drive_ref)
            if not folder_id:
                return JSONResponse(
                    {"error": "That looks like a Drive folder link, but no folder ID could be read from it."},
                    status_code=400,
                )
            from src.lingua_viva.class_folder_ingest import ingest_class_folder

            def run_folder(store):
                return ingest_class_folder(folder_id, ingest_teacher, store=store)

            try:
                result = await asyncio.to_thread(_with_student_store, run_folder)
            except DriveConfigError:
                return JSONResponse(
                    {"error": "Connect Google Drive first, then import the folder."},
                    status_code=409,
                )
            except DriveAuthError as exc:
                return JSONResponse(
                    {"error": str(exc) or "Google Drive could not be reached safely."},
                    status_code=502,
                )
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            result["kind"] = "class_folder"
            return result

        try:
            fetched = await asyncio.to_thread(docpipe_drive.fetch_file, drive_ref)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except DriveFileTooLarge:
            return JSONResponse({"error": "file is larger than 15 MB"}, status_code=413)
        except DriveConfigError:
            return JSONResponse(
                {"error": "Connect Google Drive first, then import the roster."},
                status_code=409,
            )
        except DriveAuthError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        content = fetched.content
        filename = fetched.filename
        origin = "drive"
        drive_file_id = fetched.drive_file_id
        path = fetched.path
    if not content:
        return JSONResponse({"error": "the file is empty"}, status_code=400)
    if len(content) > INGEST_MAX_BYTES:
        return JSONResponse({"error": "file is larger than 15 MB"}, status_code=413)

    source = _build_source_record(
        filename=filename, content=content, origin=origin,
        path=path, drive_file_id=drive_file_id,
    )
    await asyncio.to_thread(docpipe_vault.put_source, source, content)
    job = _new_ingest_job(source.source_id, filename, teacher_id=ingest_teacher)
    # BackgroundTasks (not a bare create_task): the framework keeps the
    # reference and runs the job after the response is sent, so the browser
    # gets the job_id immediately and the chain cannot be garbage-collected
    # mid-flight or die with a per-request test event loop.
    background_tasks.add_task(_run_ingest_job, job, source, content)
    return {"job_id": job["job_id"], "source_id": source.source_id, "status": job["status"]}


@router.post("/api/students/ingest/class-folder")
async def students_ingest_class_folder(payload: dict):
    folder_id = str((payload or {}).get("folder_id") or "").strip()
    teacher_id = str((payload or {}).get("teacher_id") or "teacher:drive").strip()
    if not folder_id:
        return JSONResponse({"error": "folder_id is required"}, status_code=400)

    from src.lingua_viva.class_folder_ingest import ingest_class_folder
    from src.lingua_viva.google_drive_integration import DriveAuthError, DriveConfigError

    def run(store):
        return ingest_class_folder(folder_id, teacher_id, store=store)

    try:
        return await asyncio.to_thread(_with_student_store, run)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError:
        return JSONResponse({"error": "Google Drive could not be reached safely."}, status_code=503)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/api/students/ingest/unattributed")
async def students_ingest_unattributed(teacher_id: str = ""):
    from src.lingua_viva.ingest_review import list_open_items

    return {"items": list_open_items(str(teacher_id or "") or None)}


@router.get("/api/students/ingest/identity")
async def students_ingest_identity(teacher_id: str = ""):
    """STEP 5 (SPEC §STEP 5, L8): the unresolved-identity queue — detected
    spellings that plausibly match roster students, waiting for a human
    ruling (always queue, never auto-merge — ruling §8-3 default)."""
    from src.lingua_viva.docpipe import identity

    return {"items": identity.list_open_items(str(teacher_id or "") or None)}


@router.post("/api/students/ingest/identity/resolve")
async def students_ingest_identity_resolve(payload: dict):
    """The human ruling on one queued spelling.

    action=assign  → this spelling IS student_id (the same_person_as
                     relation): recorded as a surface form future imports
                     replay, document evidence merged into the CANONICAL
                     lens — never a second lens.
    action=create  → genuinely new student: a lens is minted for the
                     spelling.
    action=dismiss → not a student / not mine: queue item closed, nothing
                     created.
    """
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.docpipe import identity
    from src.lingua_viva.docpipe import vault as docpipe_vault

    data = payload or {}
    display_name = str(data.get("display_name") or "").strip()
    teacher_id = str(data.get("teacher_id") or "teacher:ingest").strip() or "teacher:ingest"
    action = str(data.get("action") or "").strip()
    if not display_name:
        return JSONResponse({"error": "display_name is required"}, status_code=400)
    if action not in ("assign", "create", "dismiss"):
        return JSONResponse({"error": "action must be assign, create, or dismiss"}, status_code=400)

    item = identity.current_items().get(identity._item_key(teacher_id, display_name))
    if not item or item.get("status") != "open":
        return JSONResponse({"error": "identity_item_not_open"}, status_code=409)

    if action == "dismiss":
        event = identity.mark_dismissed(teacher_id=teacher_id, display_name=display_name)
        return {"status": "dismissed", "event": event}

    source_id = str(item.get("source_id") or "")
    extraction = None
    if source_id:
        try:
            extraction = await asyncio.to_thread(docpipe_vault.get_extraction, source_id)
        except FileNotFoundError:
            extraction = None

    def _detected_for_name():
        if extraction is None:
            return None
        for student in extraction.data.get("structure", {}).get("students_detected", []):
            if isinstance(student, dict) and str(student.get("display_name") or "").strip() == display_name:
                return student
        return None

    if action == "assign":
        student_id = str(data.get("student_id") or "").strip()
        if not student_id:
            return JSONResponse({"error": "student_id is required for assign"}, status_code=400)
        # the canonical student must exist — assigning to a ghost is a bug
        try:
            await asyncio.to_thread(_with_student_store, lambda store: store.get_lens(student_id))
        except LensNotFoundError:
            return JSONResponse({"error": "unknown student_id"}, status_code=404)
        merged = None
        if extraction is not None:
            detected = _detected_for_name() or {"display_name": display_name}
            merged = await asyncio.to_thread(
                _create_lens_for_detected, extraction,
                {**detected, "student_id": student_id}, teacher_id,
            )
        event = identity.mark_assigned(
            teacher_id=teacher_id, display_name=display_name,
            student_id=student_id, source_id=source_id,
        )
        return {
            "status": "assigned",
            "student_id": student_id,
            "evidence_merged": merged is not None,
            "event": event,
        }

    # action == "create": the human ruled "genuinely new student"
    if extraction is None:
        return JSONResponse({
            "error": "The extracted document is no longer available — import the file again (re-imports merge safely).",
        }, status_code=409)
    detected = _detected_for_name() or {"display_name": display_name}
    created = await asyncio.to_thread(
        _create_lens_for_detected, extraction, detected, teacher_id
    )
    event = identity.mark_created(
        teacher_id=teacher_id, display_name=display_name,
        student_id=created["student_id"],
    )
    return {"status": "created", "student": created, "event": event}


@router.post("/api/students/ingest/attribute")
async def students_ingest_attribute(payload: dict):
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.class_folder_ingest import attribute_extraction_to_student
    from src.lingua_viva.docpipe import vault as docpipe_vault
    from src.lingua_viva.ingest_review import (
        current_items,
        mark_assigned,
        mark_dismissed,
    )

    data = payload or {}
    source_id = str(data.get("source_id") or "").strip()
    drive_id = str(data.get("drive_id") or "").strip()
    teacher_id = str(data.get("teacher_id") or "teacher:drive").strip() or "teacher:drive"
    if not source_id or not drive_id:
        return JSONResponse({"error": "source_id and drive_id are required"}, status_code=400)

    if bool(data.get("dismiss")):
        event = mark_dismissed(source_id=source_id, drive_id=drive_id, teacher_id=teacher_id)
        return {"status": "dismissed", "event": event}

    student_id = str(data.get("student_id") or "").strip()
    if not student_id:
        return JSONResponse({"error": "student_id is required"}, status_code=400)

    item = current_items().get(drive_id) or {}
    if item.get("status") != "open" or item.get("source_id") != source_id:
        return JSONResponse({"error": "review_item_not_open"}, status_code=409)

    def assign(store):
        try:
            lens = store.get_lens(student_id)
        except LensNotFoundError as exc:
            raise PermissionError("off_roster_student") from exc
        extraction = docpipe_vault.get_extraction(source_id)
        created = attribute_extraction_to_student(
            extraction,
            store=store,
            student_id=student_id,
            student_name=str(lens.get("display_name") or student_id),
            teacher_id=teacher_id,
            drive_id=drive_id,
            name=str(item.get("name") or data.get("name") or drive_id),
            attribution_method="manual_teacher",
            attribution_confidence=1.0,
            confidence_level="teacher_confirmed",
        )
        event = mark_assigned(
            source_id=source_id,
            drive_id=drive_id,
            student_id=student_id,
            teacher_id=teacher_id,
            evidence_id=created["evidence_id"],
        )
        return created, event

    try:
        created, event = await asyncio.to_thread(_with_student_store, assign)
    except PermissionError:
        return JSONResponse({"error": "off_roster_student"}, status_code=422)
    except FileNotFoundError:
        return JSONResponse({"error": "extraction_not_found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"status": "assigned", "assignment": created, "event": event}


@router.get("/api/students/ingest/{job_id}")
async def students_ingest_status(job_id: str):
    job = _ingest_job(job_id)
    if job is None:
        return JSONResponse({
            "error": (
                "This import job is no longer tracked (the app may have "
                "restarted). Your file is saved — importing it again is safe: "
                "duplicate imports merge into existing students, never fork."
            ),
        }, status_code=404)
    return job


@router.post("/api/students/ingest/approve")
async def students_ingest_approve(payload: dict, background_tasks: BackgroundTasks):
    """Phase 0A (SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19 §2A): the explicit
    confirm step. Only a job sitting at "preview" may create students; the
    creation itself runs in _create_from_preview.

    STEP 4 (SPEC §STEP 4, L4): the payload may carry `classes` — a list of
    class names from the preview's `preview_classes` — to scope creation to
    "only my class". An unknown class name is a 422, not a silent no-op.

    F1b (SPEC_LV_DEMO_EVE_FIX_2026-08-19 §2): the payload may carry
    `exclude` — display names the teacher toggled OUT of the confirm set in
    the preview. Her safety net against the next structural surprise: a
    per-entry remedy instead of create-all-or-Cancel. An unknown name is a
    422, not a silent no-op."""
    from src.lingua_viva.docpipe import vault as docpipe_vault

    job_id = str((payload or {}).get("job_id", "")).strip()
    job = _ingest_job(job_id)
    if job is None:
        return JSONResponse({"error": "import job not found"}, status_code=404)
    if job.get("status") != "preview":
        return JSONResponse({
            "error": (
                "This import is not awaiting approval "
                f"(status: {job.get('status')})."
            ),
        }, status_code=409)
    classes = [
        str(item).strip()
        for item in ((payload or {}).get("classes") or [])
        if str(item).strip()
    ]
    known = set(job.get("preview_classes") or [])
    unknown = [name for name in classes if name not in known]
    if unknown:
        return JSONResponse({
            "error": (
                "Unknown class selection: " + ", ".join(unknown)
                + ". Pick from the classes shown in the preview."
            ),
        }, status_code=422)
    excluded = [
        str(item).strip()
        for item in ((payload or {}).get("exclude") or [])
        if str(item).strip()
    ]
    preview_names = {
        str(student.get("display_name") or "").strip()
        for student in (job.get("preview_students") or [])
    }
    unknown_names = [name for name in excluded if name not in preview_names]
    if unknown_names:
        return JSONResponse({
            "error": (
                "Unknown excluded name(s): " + ", ".join(unknown_names)
                + ". Pick from the names shown in the preview."
            ),
        }, status_code=422)
    try:
        extraction = await asyncio.to_thread(docpipe_vault.get_extraction, job["source_id"])
    except FileNotFoundError:
        return JSONResponse({
            "error": "The extracted document is no longer available — import the file again (re-imports merge safely).",
        }, status_code=409)
    job["approved_classes"] = classes
    job["excluded_names"] = excluded
    job["status"] = "creating"
    _save_ingest_job(job)
    background_tasks.add_task(_create_from_preview, job, extraction)
    return {"job_id": job_id, "status": job["status"]}


@router.post("/api/students/ingest/cancel")
async def students_ingest_cancel(payload: dict):
    """Phase 0A: cancelling a preview leaves zero trace — nothing was created,
    nothing was synced, and nothing ever will be from this job."""
    job_id = str((payload or {}).get("job_id", "")).strip()
    job = _ingest_job(job_id)
    if job is None:
        return JSONResponse({"error": "import job not found"}, status_code=404)
    if job.get("status") != "preview":
        return JSONResponse({
            "error": (
                "Only an import awaiting approval can be cancelled "
                f"(status: {job.get('status')})."
            ),
        }, status_code=409)
    job["status"] = "cancelled"
    _save_ingest_job(job)
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/api/students/ingest/confirm")
async def students_ingest_confirm(payload: dict):
    from src.lingua_viva.docpipe import vault as docpipe_vault

    job_id = str((payload or {}).get("job_id", "")).strip()
    display_name = str((payload or {}).get("display_name", "")).strip()
    display_names = [
        str(item).strip()
        for item in ((payload or {}).get("display_names") or [])
        if str(item).strip()
    ]
    if display_name and not display_names:
        display_names = [display_name]
    # Optional starting CEFR level per student (Prepare-fix P3c): either one
    # level for the single-name form ("cefr_level") or a per-name map
    # ("cefr_levels": {display_name: level}). Empty values mean "skip".
    from src.education.student_lens import VALID_CEFR_LEVELS

    cefr_levels: dict[str, str] = {}
    raw_levels = (payload or {}).get("cefr_levels")
    if isinstance(raw_levels, dict):
        cefr_levels = {
            str(name).strip(): str(level).strip()
            for name, level in raw_levels.items()
            if str(level or "").strip()
        }
    single_level = str((payload or {}).get("cefr_level") or "").strip()
    if single_level and display_name:
        cefr_levels.setdefault(display_name, single_level)
    invalid_levels = sorted({lvl for lvl in cefr_levels.values() if lvl not in VALID_CEFR_LEVELS})
    if invalid_levels:
        return JSONResponse(
            {"error": f"invalid_cefr_level: {', '.join(invalid_levels)} — valid levels: {', '.join(VALID_CEFR_LEVELS)}"},
            status_code=400,
        )
    job = _ingest_job(job_id)
    if job is None:
        return JSONResponse({"error": "import job not found"}, status_code=404)
    if not display_names and not cefr_levels:
        return JSONResponse({"error": "display_name is required"}, status_code=400)
    pending_names = {
        str(item.get("display_name") or "").strip()
        for item in job["needs_confirmation"]
    }
    missing = [name for name in display_names if name not in pending_names]
    if missing:
        return JSONResponse({"error": "one or more students are not awaiting confirmation"}, status_code=404)
    created_students = []
    if display_names:
        try:
            extraction = await asyncio.to_thread(docpipe_vault.get_extraction, job["source_id"])
        except FileNotFoundError:
            return JSONResponse({
                "error": "The extracted document is no longer available — import the file again (re-imports merge safely).",
            }, status_code=409)
        detected_by_name = {
            str(student.get("display_name") or "").strip(): student
            for student in extraction.data.get("structure", {}).get("students_detected", [])
            if isinstance(student, dict)
        }
        # STEP 5: confirmed names pass through identity resolution too — a
        # teacher confirming "this IS a student" must not silently mint a
        # duplicate of a child already on her roster under another spelling.
        roster = await asyncio.to_thread(
            _teacher_roster_snapshot, job.get("teacher_id") or "teacher:ingest"
        )
        for name in display_names:
            detected = detected_by_name.get(name) or {"display_name": name}
            detected = _resolve_or_queue(detected, job=job, roster=roster)
            if detected is None:
                job["needs_confirmation"] = [
                    item for item in job["needs_confirmation"]
                    if item.get("display_name") != name
                ]
                continue
            created = await asyncio.to_thread(
                _create_lens_for_detected, extraction, detected, job.get("teacher_id") or "teacher:ingest"
            )
            level = cefr_levels.get(name)
            if level:
                def set_level(store, student_id=created["student_id"], cefr=level):
                    return store.set_initial_cefr(
                        student_id, cefr, teacher_id=job.get("teacher_id") or "teacher:import"
                    )

                await asyncio.to_thread(_with_student_store, set_level)
                created["cefr_level"] = level
            created_students.append(created)
            job["students_created"].append(created)
        job["needs_confirmation"] = [
            item for item in job["needs_confirmation"] if item.get("display_name") not in set(display_names)
        ]
    # Starting levels for students this job already auto-created (roster
    # imports create everyone up front, so the confirm step never runs for
    # them — the level dropdowns on those rows land here instead).
    cefr_updated = []
    confirmed_names = set(display_names)
    created_by_name = {
        str(item.get("display_name") or "").strip(): item
        for item in job.get("students_created", [])
        if isinstance(item, dict) and str(item.get("student_id") or "").strip()
    }
    for name, level in cefr_levels.items():
        if name in confirmed_names:
            continue
        existing = created_by_name.get(name)
        if existing is None:
            continue

        def set_existing_level(store, student_id=existing["student_id"], cefr=level):
            return store.set_initial_cefr(
                student_id, cefr, teacher_id=job.get("teacher_id") or "teacher:import"
            )

        await asyncio.to_thread(_with_student_store, set_existing_level)
        existing["cefr_level"] = level
        cefr_updated.append({
            "student_id": existing["student_id"],
            "display_name": name,
            "cefr_level": level,
        })
    _save_ingest_job(job)
    body = {"status": "created" if created_students else "updated", "students": created_students}
    if job.get("identity_review"):
        body["identity_review"] = job["identity_review"]
    if cefr_updated:
        body["cefr_updated"] = cefr_updated
    if len(created_students) == 1:
        body["student"] = created_students[0]
    return body


@router.delete("/api/students/ingest/{job_id}")
async def students_ingest_undo(job_id: str):
    from src.education.student_lens import LensNotFoundError

    job = _ingest_job(job_id)
    if job is None:
        return JSONResponse({"error": "import job not found"}, status_code=404)
    created = [
        item for item in job.get("students_created", [])
        if isinstance(item, dict) and str(item.get("student_id") or "").strip()
    ]
    archived: list[dict] = []
    skipped: list[dict] = []

    def do_archive(store):
        for item in created:
            student_id = str(item.get("student_id"))
            try:
                store.delete_lens(student_id, hard=False)
                archived.append({
                    "student_id": student_id,
                    "display_name": str(item.get("display_name") or ""),
                })
            except LensNotFoundError:
                skipped.append({"student_id": student_id, "reason": "not found"})

    await asyncio.to_thread(_with_student_store, do_archive)
    job["undo"] = {
        "status": "archived",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "students_archived": archived,
        "skipped": skipped,
    }
    _save_ingest_job(job)
    return {
        "status": "archived",
        "job_id": job_id,
        "students_archived": archived,
        "skipped": skipped,
    }


@router.get("/api/students/growth")
async def students_growth():
    """Growth badge and any tier recommendation per student (Gap 6, Phase 1).

    Recommendations only — nothing here changes a tier. The teacher confirms.
    """
    def build(store):
        from src.lingua_viva.adaptive import RECOMMENDATION_THRESHOLD, growth_for_all

        rows = growth_for_all(store)
        return {
            "students": rows,
            "with_recommendations": sum(1 for row in rows if row["recommendation"]),
            "threshold": RECOMMENDATION_THRESHOLD,
            "note": (
                "Lingua Viva suggests; you decide. No support tier changes on its own."
            ),
        }

    return await asyncio.to_thread(_with_student_store, build)


@router.get("/api/students/{student_id}/lens/markdown")
async def student_lens_markdown_preview(student_id: str):
    """Human-readable, Drive-safe lens preview.

    This is the exact Markdown shape used for manual Drive sharing and
    automatic lens sync: readable to a normal teacher, but with raw
    observation narration and Personal Context omitted.
    """
    from src.lingua_viva.drive_sync import format_lens_markdown

    def build(store):
        return format_lens_markdown(store.export_lens(student_id))

    try:
        markdown = await asyncio.to_thread(_with_student_store, build)
    except Exception:
        return JSONResponse({"error": "Student lens could not be rendered."}, status_code=404)
    return {
        "student_id": student_id,
        "format": "markdown",
        "markdown": markdown,
        "privacy_boundary": {
            "raw_observations_included": False,
            "personal_context_included": False,
            "unconfirmed_evidence_included": False,
        },
    }


@router.post("/api/students/{student_id}/lens/pdf")
async def student_lens_pdf_export(student_id: str, payload: dict):
    from src.education.student_lens import LENS_SHARE_AUDIENCES
    from src.lingua_viva.audit_receipts.builder import build_receipt
    from src.lingua_viva.deliverables.schema import (
        DeliverableLocation,
        DeliverableRecord,
        compute_deliverable_id,
    )
    from src.lingua_viva.deliverables.store import upsert_deliverable
    from src.lingua_viva.pdf_generator import artifacts_dir, render_student_lens_pdf

    audience = str(payload.get("audience") or "teacher").strip().lower()
    if audience not in LENS_SHARE_AUDIENCES:
        return JSONResponse({"error": "audience must be teacher, family, or hr"}, status_code=400)

    def build(store):
        view = store.export_lens_view(student_id, audience)
        stable_payload = {"audience": audience, "view": view}
        artifact_hash = hashlib.sha256(
            json.dumps(stable_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        safe_student = re.sub(r"[^A-Za-z0-9_-]+", "-", student_id).strip("-") or "student"
        path = artifacts_dir("student_lenses") / f"student-lens-{safe_student}-{audience}-{artifact_hash[:12]}.pdf"
        if not path.exists():
            render_student_lens_pdf(view, audience=audience, output_path=path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return view, path, artifact_hash

    try:
        view, path, artifact_hash = await asyncio.to_thread(_with_student_store, build)
    except Exception:
        return JSONResponse({"error": "Student lens could not be exported."}, status_code=404)

    trace_id = f"student-lens-{student_id}-{audience}-{uuid.uuid4().hex[:12]}"
    deliverable_id = compute_deliverable_id(trace_id, "")
    deliverable = DeliverableRecord(
        deliverable_id=deliverable_id,
        session_id=broadcaster.session_id or "",
        trace_id=trace_id,
        type="student_lens",
        title=f"Student lens PDF: {view.get('display_name') or student_id} ({audience})",
        status="created",
        location=DeliverableLocation(kind="local_path", path=str(path)),
        source_record_ids=[student_id],
        summary="Share-scoped student lens PDF. Personal Context is HR-only.",
        content_hash=artifact_hash,
    )
    upsert_deliverable(deliverable)
    receipt = build_receipt(
        scope="student_lens",
        session_id=broadcaster.session_id or "",
        trace_id=trace_id,
        deliverable_id=deliverable_id,
        source_record_ids=[student_id],
        export_format="pdf",
        export_path=str(path),
    )
    return {
        "student_id": student_id,
        "audience": audience,
        "file_path": str(path),
        "share_scope": view.get("share_scope"),
        "deliverable": deliverable.as_dict(),
        "audit_receipt": receipt.as_dict(),
    }


@router.get("/api/students")
async def students():
    def list_roster(store):
        from src.lingua_viva.governance import aron_ref

        roster = []
        for lens in store.list_lenses():
            roster.append({
                "student_id": lens["student_id"],
                # The teacher's own roster legitimately shows names, so the id
                # is fine here. The ARON code rides along so surfaces that
                # must NOT show names can join to this row without ever
                # receiving the id.
                "reference": aron_ref(lens["student_id"]),
                "display_name": lens.get("display_name"),
                "grade_level": lens.get("grade_level"),
                "rti_current_tier": lens.get("rti_current_tier"),
                "cefr_snapshot": lens.get("cefr_snapshot"),
                "cefr_trajectory_30d": lens.get("cefr_trajectory_30d"),
            })
        return roster

    return {"students": await asyncio.to_thread(_with_student_store, list_roster)}


@router.post("/api/students")
async def create_student(payload: dict):
    """Create a new student lens from the Add Student form.

    Grade is validated against the school's canonical student grades, not
    against whichever grades currently have curriculum content loaded. The
    client form sends this dropdown; this check is defense-in-depth for any
    other caller of this endpoint.
    """
    display_name = (payload.get("display_name") or "").strip()
    if not display_name:
        return JSONResponse({"error": "display_name is required"}, status_code=400)

    grade_level = (payload.get("grade_level") or "").strip()
    if grade_level:
        from src.lingua_viva.curriculum import CurriculumService

        service = CurriculumService()
        normalized = service._normalize_grade(grade_level)
        known_grades = set(STUDENT_GRADE_LEVELS)
        if normalized not in known_grades:
            return JSONResponse(
                {
                    "error": (
                        f"'{grade_level}' is not a known student grade "
                        f"({', '.join(sorted(known_grades))})."
                    )
                },
                status_code=400,
            )
        payload = {**payload, "grade_level": normalized}

    def do_create(store):
        student_id = store.create_lens(
            display_name=display_name,
            campus=payload.get("campus", ""),
            grade_level=payload.get("grade_level", ""),
            home_languages=payload.get("home_languages") or [],
            learning_differences=payload.get("learning_differences") or [],
            rti_current_tier=payload.get("rti_current_tier", 1),
        )
        return {"student_id": student_id, "display_name": display_name}

    return await asyncio.to_thread(_with_student_store, do_create)


@router.delete("/api/students/{student_id}")
async def archive_student(student_id: str):
    """Archive (soft-delete) a student lens (BUG-8, QA 2026-08-02).

    Tombstone only: the student disappears from rosters, grouping, and
    recommendation queries (list_lenses filters deleted=0), but their
    observation history is retained for audit/records-retention. Hard purge
    is deliberately NOT exposed over HTTP — it stays an explicit store-level
    operator action.
    """
    from src.education.student_lens import LensNotFoundError

    def do_archive(store):
        store.delete_lens(student_id, hard=False)

    try:
        await asyncio.to_thread(_with_student_store, do_archive)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    return {"status": "archived", "student_id": student_id, "observations_retained": True}


@router.patch("/api/students/{student_id}")
async def update_student_profile(student_id: str, payload: dict):
    """Teacher edits background/profile fields on an existing student lens
    ("where can we add any background info?" — SPEC_LV_BASE_LENS_SCHOOL_
    CATEGORIES_2026-08-01). Accepts any subset of the store's
    UPDATABLE_PROFILE_FIELDS; unknown fields are a 400, never dropped."""
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.privacy_log import log_event

    if not isinstance(payload, dict) or not payload:
        return JSONResponse({"error": "At least one field is required"}, status_code=400)

    def do_update(store):
        return store.update_profile(student_id, payload)

    try:
        lens = await asyncio.to_thread(_with_student_store, do_update)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    # Privacy event carries the student_id hash only — never a name.
    await asyncio.to_thread(log_event, "profile_updated", query_text=student_id)
    return {
        "status": "updated",
        "student_id": student_id,
        "profile_version": lens["profile_version"],
        "updated_fields": sorted(payload.keys()),
    }


@router.post("/api/students/{student_id}/support-entry")
async def add_support_entry_endpoint(request: Request, student_id: str, payload: dict):
    """Inline teacher entry (2026-08-18): type directly into a Category
    Profile section. The teacher typing it IS the evidence, so it lands
    already teacher_confirmed — no suggestion/confirm round-trip."""
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.access_roles import effective_teacher_id
    from src.lingua_viva.privacy_log import log_event

    if not isinstance(payload, dict):
        return JSONResponse({"error": "payload must be an object"}, status_code=400)
    category_id = str(payload.get("category_id") or "").strip()
    bucket = str(payload.get("bucket") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not (category_id and bucket and text):
        return JSONResponse(
            {"error": "category_id, bucket, and text are required"},
            status_code=400,
        )
    teacher_id = effective_teacher_id(
        request, str(payload.get("teacher_id") or "local-teacher")
    )

    def do_add(store):
        return store.add_support_entry(
            student_id,
            category_id,
            bucket,
            text,
            created_by=teacher_id,
            confidence="teacher_confirmed",
        )

    try:
        await asyncio.to_thread(_with_student_store, do_add)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    # Privacy event carries the student id only — never the typed text.
    await asyncio.to_thread(log_event, "support_entry_added", query_text=student_id)
    return {
        "status": "recorded",
        "student_id": student_id,
        "category_id": category_id,
        "bucket": bucket,
    }


@router.post("/api/students/{student_id}/support-entry/confirm")
async def confirm_support_entry(student_id: str, payload: dict):
    """Tap-to-confirm: flip a model_suggested support-profile entry to
    teacher_confirmed. The only path from suggestion to evidence-grade."""
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.privacy_log import log_event

    category_id = str(payload.get("category_id") or "").strip()
    bucket = str(payload.get("bucket") or "").strip()
    entry_id = str(payload.get("entry_id") or "").strip()
    if not (category_id and bucket and entry_id):
        return JSONResponse(
            {"error": "category_id, bucket, and entry_id are required"},
            status_code=400,
        )

    def do_confirm(store):
        return store.confirm_support_entry(student_id, category_id, bucket, entry_id)

    try:
        await asyncio.to_thread(_with_student_store, do_confirm)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    await asyncio.to_thread(log_event, "support_entry_confirmed", query_text=student_id)

    # Routing memory (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01): a confirm-tap
    # is ground truth that the category suggestion was RIGHT — append a
    # positive correction row. The decision id resolves server-side from
    # the entry's source observation (persisted at capture time); a client
    # -supplied id wins if present. Pre-feature observations resolve to
    # nothing and skip silently.
    routing_decision_id = str(payload.get("routing_decision_id") or "").strip()
    if not routing_decision_id:
        try:
            def _lookup_ids(store):
                return store.routing_decision_ids_for_support_entry(
                    student_id, category_id, bucket, entry_id
                )

            _ids = await asyncio.to_thread(_with_student_store, _lookup_ids)
            routing_decision_id = str(_ids.get("category_suggest") or "").strip()
        except Exception:
            routing_decision_id = ""
    if routing_decision_id:
        from src.lingua_viva.routing_memory import record_correction

        await asyncio.to_thread(
            record_correction,
            routing_decision_id,
            {
                "type": "category_suggest",
                "positive": True,
                "category_id": category_id,
                "source": "support_entry_confirm",
            },
        )

    return {
        "status": "confirmed",
        "student_id": student_id,
        "category_id": category_id,
        "bucket": bucket,
        "entry_id": entry_id,
    }


@router.get("/api/students/{student_id}/evidence/pending")
async def pending_student_evidence(student_id: str):
    """Teacher review queue for model/import-suggested strengths and ethos evidence."""
    from src.education.student_lens import LensNotFoundError

    def do_export(store):
        report = store.export_ethos_report(student_id, include_unconfirmed=True)
        return report.get("pending_review", {})

    try:
        pending = await asyncio.to_thread(_with_student_store, do_export)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )

    return {"student_id": student_id, "pending_review": pending}


@router.post("/api/students/{student_id}/evidence/confirm")
async def confirm_student_evidence(request: Request, student_id: str, payload: dict):
    """Confirm or dismiss one pending strength/ethos evidence item."""
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.access_roles import effective_teacher_id
    from src.lingua_viva.privacy_log import log_event

    if not isinstance(payload, dict):
        return JSONResponse({"error": "payload must be an object"}, status_code=400)
    teacher_id = effective_teacher_id(
        request, str(payload.get("teacher_id") or "local-teacher")
    )
    target = str(payload.get("target") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    entry_id = str(payload.get("entry_id") or "").strip()
    if target not in ("strength", "trait"):
        return JSONResponse(
            {"error": "target must be strength or trait"}, status_code=400
        )
    if action not in ("confirm", "dismiss"):
        return JSONResponse(
            {"error": "action must be confirm or dismiss"}, status_code=400
        )
    if not entry_id:
        return JSONResponse({"error": "entry_id is required"}, status_code=400)

    kind = str(payload.get("kind") or "").strip()
    trait_id = str(payload.get("trait_id") or "").strip()
    if target == "strength" and not kind:
        return JSONResponse({"error": "kind is required for strength"}, status_code=400)
    if target == "trait" and not trait_id:
        return JSONResponse({"error": "trait_id is required for trait"}, status_code=400)

    def do_review(store):
        if target == "strength":
            if action == "confirm":
                return store.confirm_profile_strength(student_id, kind, entry_id)
            return store.dismiss_profile_strength(student_id, kind, entry_id)
        if action == "confirm":
            return store.confirm_ethos_evidence(student_id, trait_id, entry_id)
        return store.dismiss_ethos_evidence(student_id, trait_id, entry_id)

    try:
        await asyncio.to_thread(_with_student_store, do_review)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )

    await asyncio.to_thread(
        log_event,
        f"pending_evidence_{action}ed",
        query_text=f"{student_id}:{teacher_id}",
    )
    return {
        "status": f"{action}ed",
        "student_id": student_id,
        "target": target,
        "entry_id": entry_id,
    }


@router.post("/api/students/{student_id}/evidence")
async def add_student_evidence(request: Request, student_id: str, payload: dict):
    """Append one record to the unified evidence ledger
    (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01). Append-only: corrections
    are new records, removal is soft-delete. Provenance is a pointer
    (source_ref), never file bytes — content stays where it lives."""
    from src.education.ethos import EthosValidationError
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.access_roles import effective_teacher_id
    from src.lingua_viva.privacy_log import log_event

    if not isinstance(payload, dict):
        return JSONResponse({"error": "payload must be an object"}, status_code=400)
    teacher_id = effective_teacher_id(
        request, str(payload.get("teacher_id") or "local-teacher")
    )
    kind = str(payload.get("kind") or "").strip()
    source_ref = (
        payload.get("source_ref")
        if isinstance(payload.get("source_ref"), dict)
        else None
    )

    # kind=document must point at a real sources-ledger record: resolve it
    # through the same read path /api/sources/records uses (never HTTP to
    # ourselves), reject bogus pointers, and store an enriched ref built
    # from ledger ground truth rather than trusting client-supplied fields.
    if kind == "document":
        source_record_id = str(
            (source_ref or {}).get("source_record_id") or ""
        ).strip()
        if not source_record_id:
            return JSONResponse(
                {"error": "document evidence requires source_ref.source_record_id"},
                status_code=400,
            )
        from src.lingua_viva.sources.ledger import read_records

        records = await asyncio.to_thread(read_records, None, None, None)
        match = next(
            (
                r
                for r in records
                if r.get("source_record_id") == source_record_id
            ),
            None,
        )
        if match is None:
            return JSONResponse(
                {"error": f"Unknown source_record_id '{source_record_id}'"},
                status_code=400,
            )
        source_ref = {
            "source_record_id": source_record_id,
            "source_type": match.get("source_type"),
            "title": match.get("title"),
            "uri": match.get("uri"),
        }

    record = {
        "student_id": student_id,
        "teacher_id": teacher_id,
        "kind": kind,
        "target_type": payload.get("target_type"),
        "target_id": payload.get("target_id"),
        "summary": payload.get("summary"),
        "source_ref": source_ref,
        "confidence_level": payload.get("confidence_level", "teacher_confirmed"),
    }

    def do_append(store):
        return store.append_evidence(record)

    try:
        evidence_id = await asyncio.to_thread(_with_student_store, do_append)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    except (ValueError, EthosValidationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    # Privacy event carries ids only — never a name or the summary text.
    await asyncio.to_thread(log_event, "evidence_recorded", query_text=student_id)
    return {
        "status": "recorded",
        "student_id": student_id,
        "evidence_id": evidence_id,
    }


@router.get("/api/students/{student_id}/evidence")
async def list_student_evidence(
    student_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
    include_deleted: bool = False,
):
    """Evidence ledger for one student, newest first, grouped by target so
    the lens view can render per-category / per-trait sections directly."""
    from src.education.student_lens import (
        VALID_EVIDENCE_TARGET_TYPES,
        LensNotFoundError,
    )

    if target_type is not None and target_type not in VALID_EVIDENCE_TARGET_TYPES:
        return JSONResponse(
            {
                "error": (
                    f"Invalid target_type '{target_type}'. "
                    f"Allowed: {VALID_EVIDENCE_TARGET_TYPES}"
                )
            },
            status_code=400,
        )

    def do_list(store):
        return store.list_evidence(
            student_id,
            target_type=target_type,
            target_id=target_id,
            include_deleted=include_deleted,
        )

    try:
        items = await asyncio.to_thread(_with_student_store, do_list)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    by_target: dict = {}
    for item in items:
        bucket = by_target.setdefault(item["target_type"], {})
        bucket.setdefault(item["target_id"] or "", []).append(item)
    return {
        "student_id": student_id,
        "evidence": items,
        "by_target": by_target,
        "total": len(items),
    }


@router.delete("/api/students/{student_id}/evidence/{evidence_id}")
async def delete_student_evidence(student_id: str, evidence_id: str):
    """Soft-delete (tombstone) one evidence record. Never a hard DELETE:
    the ledger is append-only, same pattern as the students table. ethos
    rows also retire the mirrored profile item and refresh rollups."""
    from src.education.student_lens import LensNotFoundError
    from src.lingua_viva.privacy_log import log_event

    def do_delete(store):
        # Scope the delete to this student's ledger so a URL with a
        # mismatched student_id can never tombstone someone else's row.
        rows = store.list_evidence(student_id, include_deleted=True)
        if not any(r["evidence_id"] == evidence_id for r in rows):
            raise ValueError(f"Unknown evidence_id '{evidence_id}'")
        store.soft_delete_evidence(evidence_id)

    try:
        await asyncio.to_thread(_with_student_store, do_delete)
    except LensNotFoundError:
        return JSONResponse(
            {"error": f"Student '{student_id}' not found."}, status_code=404
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    await asyncio.to_thread(log_event, "evidence_deleted", query_text=student_id)
    return {
        "status": "deleted",
        "student_id": student_id,
        "evidence_id": evidence_id,
    }


@router.get("/api/students/support-summary")
async def students_support_summary():
    """Return aggregate counts of support entries per student across categories.
    Exposes aggregate counts only; zero raw transcript text."""
    def get_summary(store):
        summary = []
        for lens in store.list_lenses():
            sp = lens.get("support_profile") or {}
            cats = sp.get("categories") or {}
            student_counts = {}
            total_items = 0
            for cat_id, cat_data in cats.items():
                if isinstance(cat_data, dict):
                    count = sum(
                        len(cat_data.get(b) or [])
                        for b in ("needs", "strengths", "strategies_worked", "strategies_not_worked", "evidence", "open_questions")
                    )
                    student_counts[cat_id] = count
                    total_items += count
            summary.append({
                "student_id": lens["student_id"],
                "display_name": lens.get("display_name"),
                "rti_current_tier": lens.get("rti_current_tier"),
                "category_counts": student_counts,
                "total_support_items": total_items,
            })
        return summary

    return {"students": await asyncio.to_thread(_with_student_store, get_summary)}


@router.get("/api/students/{student_id}/lens")
async def student_lens(student_id: str):
    def get_lens(store):
        lens = store.export_lens(student_id)
        lens["rti_proposals"] = [
            {
                "message": "System suggests: review current RTI support before changing tier.",
                "action": "teacher_decides",
                "available_decisions": ["Confirm", "Defer"],
            }
        ] + store.evaluate_rti_rules(student_id)
        # Multi-teacher triangulation (operator ruling 2026-08-01): deterministic
        # convergence/divergence signals over local + imported observations.
        # Display names come from Tier 2 school config only — never from ledger
        # filenames or any Drive artifact. Unknown ids fall back to the raw id.
        from src.education.student_lens import compute_triangulation
        from src.lingua_viva.config import read_school_profile

        triangulation = compute_triangulation(lens)
        display_names = read_school_profile().get("teacher_display_names") or {}
        for colleague in triangulation.get("colleagues", []):
            teacher_id = colleague.get("teacher_id") or ""
            colleague["author_display"] = display_names.get(teacher_id, teacher_id)
        lens["triangulation"] = triangulation
        return lens

    try:
        lens = await asyncio.to_thread(_with_student_store, get_lens)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    # Fire-and-forget throttled background pull of colleague ledgers so the
    # lens view drifts toward fresh without ever blocking on Drive.
    try:
        from src.lingua_viva.drive_sync import trigger_pull

        trigger_pull(student_id)
    except Exception:
        pass
    return lens


@router.post("/api/students/{student_id}/rti/decision")
async def record_rti_decision(student_id: str, payload: dict):
    """Record a teacher's confirm/defer decision on an RTI proposal."""
    decision = (payload.get("decision") or "").strip().lower()
    if decision not in ("confirm", "defer"):
        return JSONResponse(
            {"error": "decision must be 'confirm' or 'defer'"}, status_code=400
        )

    def do_record(store):
        store.record_rti_decision(student_id, decision, note=payload.get("note", ""))

    try:
        await asyncio.to_thread(_with_student_store, do_record)
        return {"status": "recorded", "student_id": student_id, "decision": decision}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@router.put("/api/students/{student_id}/rti")
async def student_rti_update(student_id: str, payload: dict):
    """Record a teacher-confirmed RTI tier change (audit-trailed, never silent)."""
    try:
        new_tier = int(payload.get("new_tier"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "new_tier must be an integer (1, 2, or 3)."}, status_code=400)
    trigger = str(payload.get("trigger") or "teacher_decision")

    def update(store):
        store.update_rti_tier(student_id, new_tier, trigger)
        return store.export_lens(student_id)

    try:
        return await asyncio.to_thread(_with_student_store, update)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        if "LensNotFoundError" in type(exc).__name__:
            return JSONResponse({"error": f"Student '{student_id}' not found."}, status_code=404)
        raise


@router.post("/api/students/{student_id}/help-artifact/preview")
async def help_artifact_preview(student_id: str, request: Request, payload: dict):
    from src.education.help_artifacts import generate_help_artifact
    from src.lingua_viva.access_roles import effective_teacher_id

    teacher_id = effective_teacher_id(request, str(payload.get("teacher_id") or "local-teacher"))
    artifact_type = str(payload.get("artifact_type") or "practice")

    def build(store):
        draft = generate_help_artifact(store, student_id, teacher_id, artifact_type)
        return draft.as_dict()

    try:
        draft = await asyncio.to_thread(_with_student_store, build)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return {"draft": draft, "requires_teacher_approval": True, "writes": {"deliverables": 0, "audit_receipts": 0}}


@router.post("/api/students/{student_id}/help-artifact/approve")
async def help_artifact_approve(student_id: str, request: Request, payload: dict):
    from src.education.help_artifacts import approve_help_artifact, save_draft
    from src.lingua_viva.access_roles import effective_teacher_id
    from src.lingua_viva.governance import check_publication_safety

    teacher_id = effective_teacher_id(request, str(payload.get("teacher_id") or "local-teacher"))
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    if not draft:
        return JSONResponse({"error": "draft is required"}, status_code=400)
    draft["student_id"] = student_id
    draft["teacher_id"] = teacher_id

    def approve(store):
        lens = store.get_lens(student_id)
        approved = approve_help_artifact(draft, payload.get("teacher_edits") if isinstance(payload.get("teacher_edits"), dict) else {})
        safety = check_publication_safety(
            {
                "title": approved.title,
                "instructions": approved.instructions,
                "student_prompt": approved.student_prompt,
            },
            student_names=[str(lens.get("display_name") or "")],
        )
        if safety["blocked"]:
            return {"__error__": "unsafe_teacher_edit", "__status__": 422, "__safety__": safety}
        save_draft(approved)
        deliverable, receipt = _decision_deliverable(approved.as_dict(), "help_artifact", broadcaster.session_id or "")
        return {"record": approved.as_dict(), "publication_safety": safety, "deliverable": deliverable, "audit_receipt": receipt}

    try:
        result = await asyncio.to_thread(_with_student_store, approve)
    except ValueError as exc:
        return JSONResponse({"error": "unsafe_teacher_edit", "detail": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if "__error__" in result:
        return JSONResponse({"error": result["__error__"], "publication_safety": result.get("__safety__")}, status_code=result["__status__"])
    return result


@router.post("/api/students/{student_id}/portfolio-entry/preview")
async def portfolio_entry_preview(student_id: str, request: Request, payload: dict):
    from src.education.help_artifacts import generate_portfolio_entry
    from src.lingua_viva.access_roles import effective_teacher_id

    teacher_id = effective_teacher_id(request, str(payload.get("teacher_id") or "local-teacher"))

    def build(store):
        draft = generate_portfolio_entry(store, student_id, teacher_id)
        return draft.as_dict()

    try:
        draft = await asyncio.to_thread(_with_student_store, build)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return {"draft": draft, "requires_teacher_approval": True, "writes": {"deliverables": 0, "audit_receipts": 0}}


@router.post("/api/students/{student_id}/portfolio-entry/approve")
async def portfolio_entry_approve(student_id: str, request: Request, payload: dict):
    from src.education.help_artifacts import approve_portfolio_entry, save_draft
    from src.lingua_viva.access_roles import effective_teacher_id
    from src.lingua_viva.governance import check_publication_safety

    teacher_id = effective_teacher_id(request, str(payload.get("teacher_id") or "local-teacher"))
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    if not draft:
        return JSONResponse({"error": "draft is required"}, status_code=400)
    draft["student_id"] = student_id
    draft["teacher_id"] = teacher_id

    def approve(store):
        lens = store.get_lens(student_id)
        approved = approve_portfolio_entry(draft, payload.get("teacher_edits") if isinstance(payload.get("teacher_edits"), dict) else {})
        safety = check_publication_safety(
            {"title": approved.title, "body": approved.body},
            student_names=[str(lens.get("display_name") or "")],
        )
        if safety["blocked"]:
            return {"__error__": "unsafe_teacher_edit", "__status__": 422, "__safety__": safety}
        save_draft(approved)
        deliverable, receipt = _decision_deliverable(approved.as_dict(), "portfolio_entry", broadcaster.session_id or "")
        return {"record": approved.as_dict(), "publication_safety": safety, "deliverable": deliverable, "audit_receipt": receipt}

    try:
        result = await asyncio.to_thread(_with_student_store, approve)
    except ValueError as exc:
        return JSONResponse({"error": "unsafe_teacher_edit", "detail": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if "__error__" in result:
        return JSONResponse({"error": result["__error__"], "publication_safety": result.get("__safety__")}, status_code=result["__status__"])
    return result


@router.get("/api/students/{student_id}/lens-as-of")
async def student_lens_as_of(student_id: str, as_of: str):
    """Reconstruct a student's lens (CEFR snapshot + RTI tier) as it stood at a past timestamp."""
    def get_lens(store):
        return store.get_lens_as_of(student_id, as_of)

    try:
        return await asyncio.to_thread(_with_student_store, get_lens)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        if "LensNotFoundError" in type(exc).__name__:
            return JSONResponse({"error": f"Student '{student_id}' not found."}, status_code=404)
        raise


@router.post("/api/students/{student_id}/remove-colleague")
async def remove_colleague_data(student_id: str, payload: dict):
    """Remove one colleague's imported observations (and their fanned-out
    support entries) from a local lens. Local rows are never touched."""
    teacher_id = str(payload.get("teacher_id") or "").strip()
    if not teacher_id:
        return JSONResponse({"error": "teacher_id is required"}, status_code=400)

    def do_remove(store):
        return store.remove_imported(student_id, teacher_id)

    try:
        result = await asyncio.to_thread(_with_student_store, do_remove)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return {"status": "removed", "student_id": student_id, "teacher_id": teacher_id, **result}
