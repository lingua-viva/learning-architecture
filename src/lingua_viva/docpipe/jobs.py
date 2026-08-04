"""Persistent extraction job runner (T3, SPEC_T3_EXTRACTION_2026-08-04 §6).

Jobs survive restarts because extraction is a pure function of vault bytes:
resume == rerun. A job's status flips to done only AFTER the verified
extraction is written; a lens can only ever be created downstream of a done
extraction, so a crash can never leave a half-written lens.

Job state lives at <vault>/jobs/<job_id>.json via the same atomic
temp+replace pattern the vault uses (sync.py precedent).
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import extract as docpipe_extract
from . import vault
from .grounding_docs import verify_extraction

JOBS_RELATIVE = Path("jobs")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _jobs_dir(root: Optional[Path]) -> Path:
    base = root if root is not None else vault.vault_root()
    return base / JOBS_RELATIVE


def _job_path(job_id: str, root: Optional[Path]) -> Path:
    return _jobs_dir(root) / f"{job_id}.json"


def _write_job(job: dict[str, Any], root: Optional[Path]) -> None:
    path = _job_path(str(job["job_id"]), root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(job, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_job(path: Path) -> Optional[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def job_status(job_id: str, *, root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    return _read_job(_job_path(job_id, root))


def list_jobs(*, root: Optional[Path] = None) -> list[dict[str, Any]]:
    directory = _jobs_dir(root)
    if not directory.exists():
        return []
    jobs = []
    for path in sorted(directory.glob("JOB-*.json")):
        job = _read_job(path)
        if job is not None:
            jobs.append(job)
    return jobs


def _new_job(source_id: str) -> dict[str, Any]:
    return {
        "job_id": f"JOB-{uuid.uuid4()}",
        "source_id": source_id,
        "status": "queued",
        "progress": {"stage": "queued", "detail": ""},
        "error": None,
        "attempts": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _stamp(job: dict[str, Any], root: Optional[Path], *, status: Optional[str] = None,
           stage: Optional[str] = None, detail: str = "", error: Optional[str] = None) -> None:
    if status is not None:
        job["status"] = status
    if stage is not None:
        job["progress"] = {"stage": stage, "detail": detail}
    job["error"] = error
    job["updated_at"] = _now()
    _write_job(job, root)


async def run_extraction_job(
    source_id: str,
    *,
    root: Optional[Path] = None,
    model_client: Any | None = None,
    job: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run (or re-run) extraction for one source. Idempotent: extraction is a
    deterministic function of the stored bytes and overwrites the same
    extraction path. Never raises — the job record carries the outcome."""
    if job is None:
        job = _new_job(source_id)
    job["attempts"] = int(job.get("attempts") or 0) + 1
    _stamp(job, root, status="running", stage="normalizing")
    try:
        source = vault.get_source(source_id, root=root)
        base = root if root is not None else vault.vault_root()
        original = next(
            (base / "sources" / source_id).glob("original.*"), None
        )
        if original is None:
            raise FileNotFoundError(f"original file for {source_id} is missing from the vault")
        content = original.read_bytes()

        _stamp(job, root, stage="detecting_students")
        extraction = await docpipe_extract.extract_document(
            source, content, model_client=model_client
        )

        _stamp(job, root, stage="verifying")
        report = verify_extraction(extraction.data, apply_drops=True)
        if report.dropped:
            extraction.data["warnings"].extend(
                d for d in report.dropped if d not in extraction.data["warnings"]
            )
        if not report.ok:
            raise ValueError(
                "extraction failed grounding verification: " + "; ".join(report.errors[:3])
            )

        _stamp(job, root, stage="writing")
        await asyncio.to_thread(vault.put_extraction, extraction, root=root)
        _stamp(job, root, status="done", stage="done",
               detail=f"{len(extraction.data['structure']['students_detected'])} students detected")
    except Exception as error:
        _stamp(job, root, status="failed", stage="failed", error=str(error)[:300])
    return job


async def resume_pending(*, root: Optional[Path] = None, model_client: Any | None = None) -> list[dict[str, Any]]:
    """Re-run every job the app died on (queued/running on disk). Extraction
    is pure, so resume == rerun; done jobs are never touched."""
    resumed = []
    for job in list_jobs(root=root):
        if job.get("status") in ("queued", "running"):
            resumed.append(
                await run_extraction_job(
                    str(job["source_id"]), root=root, model_client=model_client, job=job
                )
            )
    return resumed
