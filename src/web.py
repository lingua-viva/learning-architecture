"""
Lingua Viva — Web Surface

Embedded web server that syncs with the CLI through a shared session.
Both surfaces see the same app events in real-time.

Architecture:
    Lingua Viva Process (single Python)
    ├── CLI Loop (stdin/stdout)
    ├── Session (shared state)
    └── FastAPI + WebSocket Server (localhost:8787)

Start: automatically launched as a local teacher app server.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
import uvicorn
from urllib.parse import urlencode

LV_ROOT = Path(__file__).parent.parent
if str(LV_ROOT) not in sys.path:
    sys.path.insert(0, str(LV_ROOT))

app = FastAPI(title="Lingua Viva", docs_url=None, redoc_url=None)


class SessionBroadcaster:
    """Manages WebSocket connections and broadcasts app events."""

    def __init__(self):
        self.connections: list[WebSocket] = []
        self.history: list[dict] = []
        self.session_id: Optional[str] = None
        self.governance_context: Optional[str] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        # Send session history to new connection
        for entry in self.history:
            await ws.send_json(entry)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event: dict):
        self.history.append(event)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, event: dict):
        """Synchronous broadcast for use from CLI thread."""
        self.history.append(event)
        # Will be picked up by the event loop in the web thread


broadcaster = SessionBroadcaster()


def load_governance_context() -> str:
    """Load steering files into ambient context. Called once per session."""
    parts = []

    manifest_path = LV_ROOT / "MANIFEST.yaml"
    if manifest_path.exists():
        parts.append(f"# MANIFEST\n{manifest_path.read_text()[:2000]}")

    core_path = LV_ROOT / "config" / "core.md"
    if core_path.exists():
        parts.append(f"# TIER 1 RULES\n{core_path.read_text()}")

    return "\n---\n".join(parts)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = LV_ROOT / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse(FALLBACK_HTML)


@app.post("/")
async def share_target(request: Request):
    """PWA share target. Redirect shared mobile content into the query box."""
    try:
        form = await request.form()
        shared = " ".join(
            str(form.get(k, "")).strip()
            for k in ("title", "text", "url")
            if str(form.get(k, "")).strip()
        )
    except Exception:
        shared = ""
    query = urlencode({"shared": shared}) if shared else "shared=1"
    return RedirectResponse(f"/?{query}", status_code=303)


@app.get("/manifest.json")
async def manifest():
    from src.pwa import build_manifest
    return JSONResponse(build_manifest(), media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(LV_ROOT / "static" / "sw.js", media_type="application/javascript")


@app.get("/offline.html", response_class=HTMLResponse)
async def offline_page():
    return FileResponse(LV_ROOT / "static" / "offline.html", media_type="text/html")


@app.get("/icons/{name}")
async def icon_asset(name: str):
    safe_name = Path(name).name
    return FileResponse(LV_ROOT / "static" / "icons" / safe_name)


@app.get("/api/health")
async def health():
    from doctor.support_loop.doctor import run_doctor
    return await asyncio.to_thread(run_doctor)


def _student_db_path() -> Path:
    override = os.environ.get("LV_STUDENT_DB_PATH")
    return Path(override) if override else LV_ROOT / ".lv_support" / "runtime" / "student_lenses.db"


def _seed_demo_roster(store) -> None:
    if store.list_lenses():
        return
    store.create_lens(
        student_id="student-marco",
        display_name="Marco",
        campus="local",
        grade_level="G3",
        home_languages=["it"],
        rti_current_tier=1,
    )
    store.create_lens(
        student_id="student-nora",
        display_name="Nora",
        campus="local",
        grade_level="G3",
        home_languages=["it"],
        rti_current_tier=2,
    )


def _with_student_store(callback):
    from src.education.student_lens import StudentLensStore

    with StudentLensStore(db_path=_student_db_path()) as store:
        _seed_demo_roster(store)
        return callback(store)


def _safe_unit(unit_id: str | None = None, grade: str | None = None) -> dict:
    from src.lingua_viva.curriculum import CurriculumService

    service = CurriculumService()
    if unit_id:
        try:
            return service.get_unit(unit_id)
        except KeyError:
            pass
    units = service.get_grade(grade or "G3")
    if units:
        return units[0]
    return service.get_grade("G3")[0]


def _strip_parent_output(text: str, names: list[str]) -> str:
    from src.lingua_viva.privacy import redact_runtime_text

    cleaned = text
    banned = (
        "AI suggests",
        "AI generated",
        "generated by AI",
        "generated with AI",
        "as an AI",
        "language model",
    )
    for phrase in banned:
        cleaned = cleaned.replace(phrase, "")
    for name in names:
        if name:
            cleaned = cleaned.replace(name, "your child")
    return redact_runtime_text(cleaned).strip()


@app.get("/api/curriculum/overview")
async def curriculum_overview():
    from src.lingua_viva.curriculum import CurriculumService

    return await asyncio.to_thread(CurriculumService().get_overview)


@app.get("/api/curriculum/grade/{grade}")
async def curriculum_grade(grade: str):
    from src.lingua_viva.curriculum import CurriculumService

    units = await asyncio.to_thread(CurriculumService().get_grade, grade)
    return {"grade": grade.upper(), "units": units, "source_status": CurriculumService().source_status()}


@app.get("/api/curriculum/unit/{unit_id}")
async def curriculum_unit(unit_id: str):
    from src.lingua_viva.curriculum import CurriculumService

    service = CurriculumService()
    try:
        return await asyncio.to_thread(service.get_unit, unit_id)
    except KeyError:
        return JSONResponse({"error": "Unknown curriculum unit."}, status_code=404)


@app.post("/api/prepare/activity")
async def prepare_activity(payload: dict):
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    unit = _safe_unit(payload.get("unit_id"), payload.get("grade"))
    grade_number = unit["grade"].removeprefix("G")
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Italian",
        unit_title=str(payload.get("unit_title") or unit["title"]),
        topic=str(payload.get("topic") or unit["focus"]),
        atl_skills=["communication", "self-management"],
        cefr_target="A2" if unit["grade"] in ("G3", "G4") else "A1",
        duration_minutes=int(payload.get("duration_minutes") or 45),
        language_of_instruction="it",
        created_by="teacher",
    )
    pack = await asyncio.to_thread(ContentDifferentiator().generate, lesson)
    result = pack.to_dict()
    result["source_citation"] = f"Generated from Manuale §{unit['manuale_section']}, Grade {grade_number}"
    result["source_status"] = "authoritative"
    result["cefr_rule"] = unit["cefr_language"]
    return result


@app.post("/api/observe/capture")
async def observe_capture(payload: dict):
    from src.education.observation_capture import ObservationCapturePipeline

    student_id = str(payload.get("student_id") or "student-marco")
    transcript = str(payload.get("transcript") or payload.get("raw_transcript") or "").strip()
    if not transcript:
        return JSONResponse({"error": "Observation text is required."}, status_code=400)

    def capture(store):
        pipeline = ObservationCapturePipeline(store=store)
        return pipeline.capture(
            student_id=student_id,
            teacher_id=str(payload.get("teacher_id") or "local-teacher"),
            raw_transcript=transcript,
            template_type=str(payload.get("template_type") or "cefr"),
            cefr_dimension=str(payload.get("cefr_dimension") or "speaking"),
            cefr_level_observed=str(payload.get("cefr_level_observed") or "A1"),
            cefr_direction=str(payload.get("cefr_direction") or "progressing"),
            sel_domain=payload.get("sel_domain"),
            sel_valence=payload.get("sel_valence"),
            urgency_flag=bool(payload.get("urgency_flag", False)),
        )

    result = await asyncio.to_thread(_with_student_store, capture)
    result["local_only"] = True
    return result


@app.get("/api/students")
async def students():
    def list_roster(store):
        roster = []
        for lens in store.list_lenses():
            roster.append({
                "student_id": lens["student_id"],
                "display_name": lens.get("display_name"),
                "grade_level": lens.get("grade_level"),
                "rti_current_tier": lens.get("rti_current_tier"),
                "cefr_snapshot": lens.get("cefr_snapshot"),
                "cefr_trajectory_30d": lens.get("cefr_trajectory_30d"),
            })
        return roster

    return {"students": await asyncio.to_thread(_with_student_store, list_roster)}


@app.get("/api/students/{student_id}/lens")
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
        return lens

    try:
        return await asyncio.to_thread(_with_student_store, get_lens)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.get("/api/assess/rubric/{unit_id}")
async def assess_rubric(unit_id: str):
    from src.education.assessment_generator import AssessmentGenerator
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    unit = _safe_unit(unit_id)
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Italian",
        unit_title=unit["title"],
        topic=unit["focus"],
        atl_skills=["communication"],
        cefr_target="A2" if unit["grade"] in ("G3", "G4") else "A1",
        duration_minutes=45,
        language_of_instruction="it",
        created_by="teacher",
    )
    pack = await asyncio.to_thread(ContentDifferentiator().generate, lesson)
    assessment = await asyncio.to_thread(AssessmentGenerator().generate, pack)
    return {
        "unit": unit,
        "assessment": {
            "assessment_id": assessment.assessment_id,
            "criteria": assessment.criteria,
            "band_descriptors": assessment.band_descriptors,
            "tier_assessments": {
                tier: vars(item) for tier, item in assessment.tier_assessments.items()
            },
            "cefr_language": f"Designed to target {lesson.cefr_target} listening and speaking.",
            "source_citation": unit["source_citation"],
        },
    }


@app.post("/api/parents/recommendation")
async def parent_recommendation(payload: dict):
    from src.education.parent_report import ParentReportGenerator

    student_id = str(payload.get("student_id") or "student-nora")

    def generate(store):
        generator = ParentReportGenerator(store)
        draft = generator.generate_draft(student_id, str(payload.get("teacher_id") or "local-teacher"))
        lens = store.get_lens(student_id)
        names = [lens.get("display_name") or ""]
        extra = str(payload.get("focus") or "").strip()
        body = draft.body
        if extra:
            body = f"{body} At home, a {extra} may help your child begin tasks more independently."
        return {
            "student_id": student_id,
            "subject_line": _strip_parent_output(draft.subject_line, names),
            "body": _strip_parent_output(body, names),
            "home_activities": [_strip_parent_output(item, names) for item in draft.home_activities],
            "review_label": "Review before sending. No AI attribution in final message.",
            "source_citation": "Generated from Manuale v1 and local teacher observations.",
        }

    return await asyncio.to_thread(_with_student_store, generate)


@app.post("/api/reflect/note")
async def reflect_note(payload: dict):
    from src.lingua_viva.privacy import redact_runtime_text

    note = str(payload.get("note") or "").strip()
    if not note:
        return JSONResponse({"error": "Reflection note is required."}, status_code=400)
    log_path = Path(os.environ.get("LV_REVISION_LOG_PATH", LV_ROOT / "dev" / "lv_revision_log.ndjson"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "teacher_reflection",
        "private": True,
        "note": redact_runtime_text(note),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return {"status": "saved", "timestamp": entry["timestamp"], "private": True}


@app.get("/api/publication/status")
async def publication_status():
    import yaml

    governance_path = LV_ROOT / "governance" / "publication_safety.yaml"
    claims_path = LV_ROOT / "claims" / "evidence_register.yaml"
    with governance_path.open(encoding="utf-8") as handle:
        governance = yaml.safe_load(handle) or {}
    with claims_path.open(encoding="utf-8") as handle:
        claims = yaml.safe_load(handle) or {}
    return {
        "status": governance.get("status"),
        "release_checklist": governance.get("release_checklist", []),
        "privacy_rules": governance.get("privacy_rules", {}),
        "claim_count": len(claims.get("claims", [])),
        "claims": claims.get("claims", []),
    }


@app.get("/api/stats")
async def stats():
    try:
        from ontology.engine import OntologyEngine
        from knowledge import KnowledgeStore
        from memory.store import MemoryStore
        engine = OntologyEngine()
        kl = KnowledgeStore()
        memory = MemoryStore()
        return {
            "ontology_nodes": engine.node_count,
            "domains": engine.domain_count,
            "knowledge_entries": kl.entry_count,
            "citations": kl.citation_count,
            "path_records": memory.total_path_count(),
            "gap_signals": memory.gap_signal_count(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/session")
async def session_info():
    from src.session import session_status
    status = session_status()
    return status or {"active": False}


@app.get("/api/provider")
async def provider_info():
    """Current provider-connection state for the Gap 5a onboarding screen
    (SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md) — never returns the key
    itself, only whether a provider is connected and whether local Ollama
    is currently reachable."""
    from src.provider_config import provider_status
    return await asyncio.to_thread(provider_status)


@app.post("/api/provider/connect")
async def provider_connect(payload: dict):
    """
    Verify a provider API key with a lightweight test call before ever
    saving it (Gap 5a point 3). `provider` must be one of openai/groq
    /mistral — Claude/Gemini aren't implemented in the reasoning call
    path yet (see src.lingua_viva.reasoning.ReasoningEngine._resolve_endpoint).
    """
    from src.provider_config import SUPPORTED_PROVIDERS, connect_provider

    provider = str(payload.get("provider") or "").lower()
    api_key = str(payload.get("api_key") or "")
    model = payload.get("model")

    if provider not in SUPPORTED_PROVIDERS:
        return JSONResponse(
            {"error": f"Unsupported provider — choose one of: {', '.join(SUPPORTED_PROVIDERS)}."},
            status_code=400,
        )
    if not api_key.strip():
        return JSONResponse({"error": "This key didn't work — check it and try again."}, status_code=400)
    if model is not None and not isinstance(model, str):
        return JSONResponse({"error": "Unsupported model value."}, status_code=400)

    result = await asyncio.to_thread(connect_provider, provider, api_key, model)
    if result["status"] == "rejected":
        return JSONResponse({"error": result["message"]}, status_code=400)
    return {"status": result["status"], "message": result["message"], "provider": provider}


@app.post("/api/provider/disconnect")
async def provider_disconnect():
    """Reversible — Gap 5a point 4. Deletes the key material from disk
    entirely, reverting to local-only (or whatever install.sh's own
    Ollama auto-detection wrote)."""
    from src.provider_config import disconnect_provider
    await asyncio.to_thread(disconnect_provider)
    return {"status": "disconnected"}


@app.post("/api/query")
async def query_endpoint(payload: dict):
    """Run a teacher query through the Lingua Viva app runtime."""
    query_text = payload.get("query", "")
    intent = payload.get("intent")
    eval_mode = payload.get("eval_mode", False)

    if not query_text:
        return {"error": "query is required"}

    from src.session import get_active_session, increment_session

    session_id = get_active_session()

    # Broadcast: query received
    await broadcaster.broadcast({
        "type": "query_received",
        "query": query_text,
        "intent": intent,
        "timestamp": time.time(),
    })

    try:
        from src.lingua_viva.app import run_teacher_query

        result = await run_teacher_query(
            query_text,
            intent=intent,
            session_id=session_id,
            eval_mode=eval_mode,
        )
        if session_id and not eval_mode:
            increment_session()

        response = {
            "type": "result",
            "classification": {
                "node": result.classification.riu_id,
                "name": result.classification.name,
                "domain": result.classification.domain,
                "confidence": result.classification.confidence,
            },
            "result": {
                "content": result.synthesis.content,
                "confidence": result.synthesis.confidence,
            },
            "pipeline": {
                "steps": result.steps_executed,
                "external_called": result.external_called,
                "duration_ms": result.duration_ms,
                "gap_signals": result.gap_signals,
            },
            "session_id": session_id,
            "timestamp": time.time(),
        }

        await broadcaster.broadcast(response)
        return response

    except Exception as e:
        error = {"type": "error", "error": str(e), "timestamp": time.time()}
        await broadcaster.broadcast(error)
        return error


# Gap 2, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md: PDF upload -> governed
# ingestion, so a teacher never needs `mc ingest` in a terminal. Only
# .pdf is accepted (matches DocumentParser's actual support), capped at
# 50MB, and ingestion requests are serialized behind one lock — a single
# local user is the real-world case, not a queue-worthy one.
MAX_INGEST_BYTES = 50 * 1024 * 1024
_ingest_lock = asyncio.Lock()


def _ingest_temp_dir() -> Path:
    """Scoped scratch dir for uploads-in-flight — never the shared system
    tmp root, so the lifecycle (write, parse, always delete) is easy to
    reason about and to grep for. Lives under the same gitignored `data/`
    tree the document store itself uses."""
    d = LV_ROOT / "case-studies" / "04-still-i-rise" / "data" / "ingest-tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.post("/api/ingest")
async def ingest_endpoint(request: Request):
    """
    Upload a PDF for ingestion into the local education document
    store. Thin-wraps src.lingua_viva.ingest.ingest_document() — the identical
    parse -> PII-redact -> store flow `lv ingest` uses,
    including the `student-records` hard refusal.

    Never trusts a client-supplied filesystem path: only the uploaded
    byte stream is read; it is written to a server-chosen temp path
    (tempfile.mkstemp) and always deleted in a `finally` block.
    """
    # Primary size guard: reject before touching the body at all when the
    # client is honest about Content-Length (the common case).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_INGEST_BYTES:
                return JSONResponse(
                    {"error": "This file is too large — the limit is 50MB."},
                    status_code=413,
                )
        except ValueError:
            pass

    try:
        form = await request.form()
    except Exception:
        return JSONResponse(
            {"error": "This file couldn't be read — try a different PDF."},
            status_code=400,
        )

    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", None):
        return JSONResponse({"error": "No file was uploaded."}, status_code=400)

    filename = upload.filename
    if Path(filename).suffix.lower() != ".pdf":
        return JSONResponse(
            {"error": "Only PDF files are supported right now."},
            status_code=400,
        )

    doc_type = str((form.get("doc_type") or "curriculum"))

    # Secondary size guard: even if Content-Length was absent or wrong,
    # never hand more than the cap down to the parser/store.
    data = await upload.read()
    await upload.close()
    if len(data) > MAX_INGEST_BYTES:
        return JSONResponse(
            {"error": "This file is too large — the limit is 50MB."},
            status_code=413,
        )
    if not data:
        return JSONResponse({"error": "The uploaded file was empty."}, status_code=400)

    from src.lingua_viva.ingest import ingest_document

    fd, tmp_path_str = tempfile.mkstemp(suffix=".pdf", dir=_ingest_temp_dir())
    tmp_path = Path(tmp_path_str)
    try:
        with open(fd, "wb") as f:
            f.write(data)

        # Serialize ingestion (parsing + embedding calls) behind one lock;
        # run the blocking parse/store work off the event loop so /api/health
        # and the WebSocket stay responsive during a large PDF.
        async with _ingest_lock:
            result = await asyncio.to_thread(ingest_document, tmp_path, doc_type)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not result["ok"]:
        return JSONResponse({"error": result["error"]}, status_code=400)

    return JSONResponse({
        "status": "done",
        "filename": filename,
        "chunks_added": result["chunks_added"],
        "tables": result["tables"],
        "prose": result["prose"],
        "redactions": result["redactions"],
        "needs_review": result["needs_review"],
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "query":
                # Browser sent a query.
                result = await query_endpoint({
                    "query": data.get("query", ""),
                    "intent": data.get("intent"),
                })
                # Result already broadcast by query_endpoint
            elif data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)


def start_web_server(port: int = 8787):
    """Start the web server."""
    broadcaster.governance_context = load_governance_context()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    # Standalone/detached launch — e.g. `python3 -m src.web 8787 &` from an
    # installer. Mirrors src/api_server.py's own __main__ pattern; without
    # this, start_web_server() can only ever run as a daemon thread inside
    # another foreground process, which dies with its parent.
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    start_web_server(_port)


FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lingua Viva</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #0a0a0a; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
  header { padding: 16px 24px; border-bottom: 1px solid #222; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; }
  .status { font-size: 12px; color: #888; margin-left: auto; }
  .status.connected { color: #4ade80; }
  main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #output { flex: 1; overflow-y: auto; padding: 16px 24px; font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
  .event { margin-bottom: 8px; }
  .event.query { color: #60a5fa; }
  .event.classify { color: #a78bfa; }
  .event.result { color: #e0e0e0; }
  .event.error { color: #f87171; }
  .event.system { color: #666; font-style: italic; }
  #input-bar { padding: 12px 24px; border-top: 1px solid #222; display: flex; gap: 8px; }
  #query-input { flex: 1; background: #1a1a1a; border: 1px solid #333; border-radius: 6px;
                 padding: 10px 14px; color: #e0e0e0; font-size: 14px; outline: none;
                 font-family: 'SF Mono', 'Fira Code', monospace; }
  #query-input:focus { border-color: #555; }
  #query-input::placeholder { color: #555; }
  select { background: #1a1a1a; border: 1px solid #333; border-radius: 6px;
           padding: 10px; color: #888; font-size: 13px; outline: none; }
  button { background: #2563eb; color: white; border: none; border-radius: 6px;
           padding: 10px 20px; font-size: 14px; cursor: pointer; font-weight: 500; }
  button:hover { background: #1d4ed8; }
  button:disabled { background: #333; color: #666; cursor: not-allowed; }
  .pipeline-steps { display: flex; gap: 4px; padding: 4px 24px; font-size: 11px; color: #555; }
  .step { padding: 2px 6px; border-radius: 3px; background: #1a1a1a; }
  .step.active { background: #1e3a5f; color: #60a5fa; }
  .step.done { background: #14532d; color: #4ade80; }
  .meta { font-size: 11px; color: #666; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <h1>Lingua Viva</h1>
  <span class="status" id="status">connecting...</span>
</header>
<div class="pipeline-steps" id="pipeline">
  <span class="step" data-step="SCAN">SCAN</span>
  <span class="step" data-step="CLASSIFY">CLASSIFY</span>
  <span class="step" data-step="RETRIEVE">RETRIEVE</span>
  <span class="step" data-step="RESEARCH">RESEARCH</span>
  <span class="step" data-step="CONTEXT">CONTEXT</span>
  <span class="step" data-step="REASON">REASON</span>
  <span class="step" data-step="SYNTHESIZE">SYNTHESIZE</span>
  <span class="step" data-step="STORE">STORE</span>
</div>
<main>
  <div id="output"></div>
</main>
<div id="input-bar">
  <select id="intent">
    <option value="">auto</option>
    <option value="PROTECT">protect</option>
    <option value="RESEARCH">research</option>
    <option value="DECIDE">decide</option>
    <option value="CREATE">create</option>
    <option value="DIAGNOSE">diagnose</option>
    <option value="REFLECT">reflect</option>
  </select>
  <input type="text" id="query-input" placeholder="Ask Lingua Viva..." autofocus>
  <button id="send-btn" onclick="sendQuery()">Send</button>
</div>
<script>
const output = document.getElementById('output');
const input = document.getElementById('query-input');
const intentSel = document.getElementById('intent');
const statusEl = document.getElementById('status');
const sendBtn = document.getElementById('send-btn');
const pipelineEl = document.getElementById('pipeline');
let ws;

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { statusEl.textContent = 'connected'; statusEl.className = 'status connected'; };
  ws.onclose = () => { statusEl.textContent = 'disconnected'; statusEl.className = 'status'; setTimeout(connect, 2000); };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    handleEvent(data);
  };
}

function handleEvent(data) {
  const div = document.createElement('div');
  div.className = 'event';

  if (data.type === 'query_received') {
    div.className += ' query';
    const intent = data.intent ? `[${data.intent}] ` : '';
    div.textContent = `> ${intent}${data.query}`;
    resetPipeline();
  } else if (data.type === 'result') {
    div.className += ' result';
    const cls = data.classification;
    const pl = data.pipeline;
    div.innerHTML = `<span class="meta">[${cls.node}] ${cls.name} — ${(cls.confidence*100).toFixed(0)}% — ${pl.duration_ms}ms${pl.external_called ? ' — external' : ''}</span>\\n${data.result.content}`;
    if (pl.steps) updatePipeline(pl.steps);
    sendBtn.disabled = false;
  } else if (data.type === 'error') {
    div.className += ' error';
    div.textContent = `ERROR: ${data.error}`;
    sendBtn.disabled = false;
  } else {
    div.className += ' system';
    div.textContent = JSON.stringify(data);
  }

  output.appendChild(div);
  output.scrollTop = output.scrollHeight;
}

function resetPipeline() {
  pipelineEl.querySelectorAll('.step').forEach(s => { s.className = 'step'; });
}

function updatePipeline(steps) {
  pipelineEl.querySelectorAll('.step').forEach(s => {
    if (steps.includes(s.dataset.step)) s.className = 'step done';
    else if (steps.includes(s.dataset.step + '(skipped)')) s.className = 'step';
  });
}

function sendQuery() {
  const query = input.value.trim();
  if (!query || !ws || ws.readyState !== 1) return;
  const intent = intentSel.value || undefined;
  ws.send(JSON.stringify({ type: 'query', query, intent }));
  input.value = '';
  sendBtn.disabled = true;
}

input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendQuery(); });

connect();

// Load stats on connect
fetch('/api/stats').then(r => r.json()).then(data => {
  const div = document.createElement('div');
  div.className = 'event system';
  div.textContent = `Lingua Viva — ${data.ontology_nodes} nodes, ${data.knowledge_entries} KL entries, ${data.path_records} paths`;
  output.appendChild(div);
});
</script>
</body>
</html>"""
