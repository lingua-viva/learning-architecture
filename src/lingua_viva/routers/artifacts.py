"""Artifact + PoI progression routes (W3, 2026-08-09).

Registered via the router plug-in point (routers/__init__.py
ROUTER_MODULES). Contract: never import src.web; runtime modules only.

Endpoints:
- POST /api/artifacts/coursework-pack — generate teacher/student PDFs for
  a class (curriculum-driven), return file paths + metadata
- GET  /api/artifacts/list            — list generated artifacts
- GET  /api/artifacts/download        — serve ONE pdf strictly from inside
  the artifacts dir (kind + filename; traversal rejected). The app binds
  127.0.0.1, so this stays on-machine — it exists so the teacher can open
  and print packs from the browser UI.
- GET  /api/poi/progression/{student_id} — PoI progression summary
- POST /api/poi/record                — append one activity iteration

Privacy: PoI responses contain only what the teacher recorded locally;
download refuses any path that does not resolve inside artifacts_dir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.lingua_viva import coursework_pack as cwp
from src.lingua_viva.pdf_generator import artifacts_dir
from src.lingua_viva.poi_progression import PROGRESSION_PHASES, PoIProgressionStore

router = APIRouter(prefix="/api")


def _saved_work_access(request: Request, teacher_id: str):
    from src.lingua_viva.access_roles import access_context_from_request, auth_mode
    ctx = access_context_from_request(request)
    if auth_mode() == "off":
        return True
    return ctx.authenticated and (ctx.role in {"admin", "coordinator"} or ctx.teacher_id == teacher_id)


@router.get("/artifacts/saved")
def saved_work(request: Request):
    from src.lingua_viva.deliverables.store import list_snapshots
    from src.lingua_viva.access_roles import require_role
    refusal = require_role(request, {"teacher"})
    if refusal is not None:
        return refusal
    items, unreadable = list_snapshots()
    return {"items": [item for item in items if _saved_work_access(request, item["teacher_id"])],
            "unreadable_count": unreadable}


@router.get("/artifacts/saved/{identifier}")
def saved_work_detail(identifier: str, request: Request):
    from src.lingua_viva.deliverables.store import read_snapshot
    from src.lingua_viva.access_roles import require_role
    refusal = require_role(request, {"teacher"})
    if refusal is not None:
        return refusal
    try:
        record = read_snapshot(identifier)
    except FileNotFoundError:
        raise HTTPException(404, "Saved work was not found")
    except (OSError, ValueError):
        raise HTTPException(409, "This saved file could not be read. The original is preserved on disk.")
    if not _saved_work_access(request, record.get("teacher_id", "")):
        raise HTTPException(404, "Saved work was not found")
    return record


class CourseworkPackRequest(BaseModel):
    class_id: str = Field(..., description='Grade/class ref, e.g. "G3"')
    unit_id: Optional[str] = None
    activities_per_unit: int = Field(default=3, ge=1, le=6)
    include_student_version: bool = True
    include_model_enrichment: bool = False


class PoIRecordRequest(BaseModel):
    student_id: str
    unit_id: str
    objective: str
    activity_id: str
    tier_demonstrated: str = Field(..., description=f"One of {PROGRESSION_PHASES}")
    evidence_note: str = ""
    recorded_at: Optional[str] = None


@router.post("/artifacts/coursework-pack")
def create_coursework_pack(payload: CourseworkPackRequest) -> dict:
    try:
        result = cwp.generate_class_pack(
            payload.class_id,
            unit_id=payload.unit_id,
            activities_per_unit=payload.activities_per_unit,
            include_student_version=payload.include_student_version,
            include_model_enrichment=payload.include_model_enrichment,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc))
    return {"status": "generated", **result}


@router.get("/artifacts/list")
def list_artifacts() -> dict:
    base = artifacts_dir()
    files = []
    for path in sorted(base.rglob("*.pdf")):
        stat = path.stat()
        files.append({
            "name": path.name,
            "kind": path.parent.name if path.parent != base else "",
            "path": str(path),
            "bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        })
    return {"artifacts_dir": str(base), "count": len(files), "files": files}


@router.get("/artifacts/download")
def download_artifact(kind: str, name: str):
    """Serve one generated PDF from inside the artifacts dir, nothing else."""
    from fastapi.responses import FileResponse

    base = artifacts_dir().resolve()
    candidate = (base / kind / name).resolve()
    # Fail closed on traversal ("../", absolute names) and non-PDFs.
    if base not in candidate.parents or candidate.suffix != ".pdf":
        raise HTTPException(status_code=403, detail="outside artifacts dir")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(candidate, media_type="application/pdf", filename=candidate.name)


@router.get("/poi/progression/{student_id}")
def poi_progression(student_id: str) -> dict:
    with PoIProgressionStore() as store:
        return store.student_summary(student_id)


@router.post("/poi/record")
def poi_record(payload: PoIRecordRequest) -> dict:
    with PoIProgressionStore() as store:
        try:
            record = store.record_iteration(
                student_id=payload.student_id,
                unit_id=payload.unit_id,
                objective=payload.objective,
                activity_id=payload.activity_id,
                tier_demonstrated=payload.tier_demonstrated,
                evidence_note=payload.evidence_note,
                recorded_at=payload.recorded_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        summary = store.objective_summary(
            payload.student_id, payload.unit_id, payload.objective
        )
    summary.pop("history", None)
    return {"status": "recorded", "iteration": record, "summary": summary}
