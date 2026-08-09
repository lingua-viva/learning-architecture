"""
Sources + library routes (W1 information-categorization spine).

Wires the previously-unwired sources ledger (src/lingua_viva/sources/) and
the per-machine knowledge library (src/lingua_viva/library.py) into the web
app via the router plug-in pattern (routers/__init__.py ROUTER_MODULES).

Auth: the server-side role gate (src/lingua_viva/access_roles.py) defaults to
LV_AUTH_MODE=off, in which every request resolves to a permissive local
context — these routes therefore work unauthenticated in dev, same as the
rest of the API surface.

Zero-egress: every handler here is local-only except POST /library/research,
which delegates to the fail-closed perplexity_gateway (refuses unless the
teacher has set BOTH PERPLEXITY_API_KEY and LV_ALLOW_RESEARCH=1).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.lingua_viva import library
from src.lingua_viva.sources import ledger
from src.lingua_viva.sources.schema import SourceObservation, SourceRecord

router = APIRouter(prefix="/api")


# ── sources ledger ──────────────────────────────────────────────────────────

@router.get("/sources/records")
def get_source_records(
    source_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "records": ledger.read_records(source_type=source_type, limit=limit, q=q),
        "counts": ledger.counts_by_type(),
        "initialized": ledger.is_initialized(),
    }


@router.get("/sources/observations")
def get_source_observations(
    source_record_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "observations": ledger.read_observations(source_record_id=source_record_id, limit=limit),
    }


@router.post("/sources/records")
def post_source_record(payload: dict = Body(...)):
    data = dict(payload or {})
    source_type = str(data.get("source_type") or "local")
    source_id = str(data.get("source_id") or "local")
    container = str(data.get("container") or "")
    record_id = str(data.get("record_id") or data.get("uri") or data.get("title") or "")
    if not record_id:
        return JSONResponse({"error": "record_id (or uri/title) is required"}, status_code=422)
    data.setdefault("source_type", source_type)
    data.setdefault("source_id", source_id)
    data.setdefault("container", container)
    data.setdefault("record_id", record_id)
    data.setdefault(
        "source_record_id",
        ledger.compute_source_record_id(source_type, source_id, container, record_id),
    )
    now = ledger.now_iso()
    data.setdefault("created_at", now)
    data.setdefault("observed_at", now)
    data.setdefault("title", record_id)
    data.setdefault("uri", record_id)
    data.setdefault("retrieval_scope", "metadata")
    data.setdefault("provenance", "capture")
    try:
        record = SourceRecord.from_dict(data)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": f"invalid source record: {exc}"}, status_code=422)
    stored, changed = ledger.upsert(record)
    return {"record": stored.as_dict(), "changed": changed}


@router.post("/sources/observations")
def post_source_observation(payload: dict = Body(...)):
    data = dict(payload or {})
    source_record_id = str(data.get("source_record_id") or "")
    if not source_record_id:
        return JSONResponse({"error": "source_record_id is required"}, status_code=422)
    observation = SourceObservation(
        observation_id=str(data.get("observation_id") or f"OBS-{uuid.uuid4().hex[:20]}"),
        source_record_id=source_record_id,
        source_type=str(data.get("source_type") or "local"),
        event=str(data.get("event") or "seen"),
        observed_at=str(data.get("observed_at") or ledger.now_iso()),
        content_hash=str(data.get("content_hash") or ""),
        detail=dict(data.get("detail") or {}),
    )
    ledger.append_observation(observation)
    return {"observation": observation.as_dict()}


# ── knowledge library ───────────────────────────────────────────────────────

@router.get("/library/status")
def get_library_status() -> dict[str, Any]:
    return library.status()


@router.get("/library/search")
def get_library_search(
    q: Optional[str] = None,
    category: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    return {
        "results": library.search(q, category=category, role=role, limit=limit),
        "query": q,
        "category": category,
        "role": role,
    }


@router.post("/library/add")
def post_library_add(payload: dict = Body(...)):
    path = str((payload or {}).get("path") or "").strip()
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=422)
    try:
        entry = library.add_document(path, title=(payload or {}).get("title"))
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return {"doc": entry}


@router.post("/library/research")
def post_library_research(payload: dict = Body(...)):
    """Teacher-initiated external research (fail-closed). This endpoint is the
    ONLY web surface that can trigger the perplexity gateway — nothing in the
    pipeline calls it."""
    from src.lingua_viva import perplexity_gateway

    query = str((payload or {}).get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=422)
    dry_run = bool((payload or {}).get("dry_run", False))
    try:
        result = perplexity_gateway.research(query, dry_run=dry_run)
    except perplexity_gateway.ResearchDisabledError as exc:
        return JSONResponse({"error": str(exc), "enabled": False}, status_code=403)
    except perplexity_gateway.ResearchBlockedError as exc:
        return JSONResponse({"error": str(exc), "blocked": True}, status_code=403)
    return result
