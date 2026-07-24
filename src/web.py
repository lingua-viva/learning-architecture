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
import re
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


@app.middleware("http")
async def _log_request_outcome(request: Request, call_next):
    """Append one request-outcome event per response (MC-lessons §5).

    Path-template only (never the raw URL with resolved dynamic segments)
    so no student/path-parameter content reaches the log — same
    privacy-first discipline as traces.ndjson and privacy_events.ndjson.
    Logging failures never break the response.
    """
    response = await call_next(request)
    try:
        from src.lingua_viva.request_log import append_request_event
        route = request.scope.get("route")
        path_template = route.path_format if route is not None else request.url.path
        append_request_event(request.method, path_template, response.status_code)
    except Exception:
        pass
    return response


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
    try:
        from doctor.support_loop.doctor import run_doctor
        return await asyncio.to_thread(run_doctor)
    except Exception as e:
        # Never let the health endpoint crash — a crashing health probe
        # fills stdio pipes and deadlocks the Electron wrapper (Bug 2, v0.2.4 report).
        return {"status": "degraded", "error": str(e)}


@app.get("/api/slack/status")
async def slack_integration_status():
    """Return Slack readiness without returning credentials or channel IDs."""
    from src.lingua_viva.slack_integration import slack_status

    return slack_status()


_slack_runtime: dict = {}


def _get_slack_observation_bot():
    """Build one process-long bot so dedupe and continuation state persist."""
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.slack_bot import SlackObservationBot
    from src.education.student_lens import StudentLensStore
    from src.lingua_viva.slack_integration import (
        post_slack_message,
        require_slack_config,
    )

    signing_secret, bot_token, channels = require_slack_config()
    fingerprint = (signing_secret, bot_token, tuple(sorted(channels.items())))
    if _slack_runtime.get("fingerprint") == fingerprint:
        return _slack_runtime["bot"]

    previous_store = _slack_runtime.get("store")
    if previous_store is not None:
        previous_store.close()

    store = StudentLensStore(db_path=_student_db_path())
    _seed_demo_roster(store)
    bot = SlackObservationBot(
        capture_pipeline=ObservationCapturePipeline(store=store),
        teacher_channel_map=channels,
        signing_secret=signing_secret,
        post_message=lambda channel, text: post_slack_message(
            bot_token, channel, text
        ),
    )
    _slack_runtime.clear()
    _slack_runtime.update(
        {"fingerprint": fingerprint, "bot": bot, "store": store}
    )
    return bot


@app.post("/api/slack/events")
async def slack_events(request: Request):
    """Receive signed Slack Events API payloads for local observation capture."""
    from src.education.slack_bot import (
        InvalidSlackSignatureError,
        verify_slack_signature,
    )
    from src.lingua_viva.slack_integration import (
        SlackConfigurationError,
    )

    raw_bytes = await request.body()
    if len(raw_bytes) > 1_000_000:
        return JSONResponse({"error": "Slack payload is too large."}, status_code=413)
    try:
        raw_body = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"error": "Slack payload must be UTF-8."}, status_code=400)
    headers = {
        "x-slack-request-timestamp": request.headers.get(
            "x-slack-request-timestamp", ""
        ),
        "x-slack-signature": request.headers.get("x-slack-signature", ""),
    }
    signing_secret = os.environ.get("LV_SLACK_SIGNING_SECRET", "").strip()
    if not signing_secret:
        return JSONResponse(
            {"error": "Slack is not configured. Missing: LV_SLACK_SIGNING_SECRET"},
            status_code=503,
        )
    if not verify_slack_signature(
        signing_secret,
        headers["x-slack-request-timestamp"],
        raw_body,
        headers["x-slack-signature"],
    ):
        return JSONResponse({"error": "Invalid Slack signature."}, status_code=401)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid Slack JSON payload."}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Invalid Slack payload shape."}, status_code=400)

    # Slack verifies the callback before the app is fully installed. Only the
    # signing secret is required for this authenticated one-time handshake.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    try:
        result = _get_slack_observation_bot().handle_request(headers, raw_body)
    except InvalidSlackSignatureError:
        return JSONResponse({"error": "Invalid Slack signature."}, status_code=401)
    except SlackConfigurationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return result


def _student_db_path() -> Path:
    override = os.environ.get("LV_STUDENT_DB_PATH")
    if override:
        return Path(override)
    from src.lingua_viva.config import lv_home
    return lv_home() / "runtime" / "student_lenses.db"


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
    store.create_lens(
        student_id="student-luca",
        display_name="Luca",
        campus="local",
        grade_level="G3",
        home_languages=["it", "en"],
        rti_current_tier=1,
    )


def _with_student_store(callback):
    from src.education.student_lens import StudentLensStore

    with StudentLensStore(db_path=_student_db_path()) as store:
        _seed_demo_roster(store)
        return callback(store)


def _student_store_for_brief():
    from src.education.student_lens import StudentLensStore

    store = StudentLensStore(db_path=_student_db_path())
    _seed_demo_roster(store)
    return store


def _revision_log_path() -> Path:
    return Path(os.environ.get("LV_REVISION_LOG_PATH", LV_ROOT / "dev" / "lv_revision_log.ndjson"))


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


def _parse_schedule(schedule_text: str | None) -> dict:
    if not schedule_text:
        return {}
    try:
        schedule = json.loads(schedule_text)
    except json.JSONDecodeError:
        return {}
    return schedule if isinstance(schedule, dict) else {}


def _schedule_day_key(day: str | None = None) -> str:
    if day:
        return str(day).strip().lower()
    return datetime.now().strftime("%A").lower()


def _today_from_schedule(schedule: dict, day: str | None = None) -> dict:
    day_key = _schedule_day_key(day)
    entry = schedule.get(day_key) or schedule.get(day_key.title()) or {}
    if not isinstance(entry, dict) or not entry.get("grade"):
        return {"configured": False, "day": day_key.title()}

    unit = _safe_unit(str(entry.get("unit_id") or ""), str(entry.get("grade") or ""))
    return {
        "configured": True,
        "day": day_key.title(),
        "grade": unit["grade"],
        "unit": unit["title"],
        "unit_id": unit["unit_id"],
        "cefr_targets": [unit["cefr_language"]],
        "source": f"Manuale §{unit['manuale_section']}",
        "source_citation": unit["source_citation"],
    }


def _strip_parent_output(text: str, names: list[str]) -> str:
    from src.lingua_viva.privacy import redact_runtime_text
    from src.lingua_viva.privacy_log import log_event

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
        if phrase in cleaned:
            cleaned = cleaned.replace(phrase, "")
            try:
                log_event("ai_attribution_stripped")
            except Exception:
                pass
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


@app.get("/api/teacher/today")
async def teacher_today(request: Request, schedule: str | None = None, day: str | None = None):
    schedule_payload = schedule or request.headers.get("X-LV-Schedule")
    return _today_from_schedule(_parse_schedule(schedule_payload), day)


@app.get("/api/brief")
async def teacher_brief(request: Request, schedule: str | None = None, day: str | None = None, days: int = 14):
    from src.lingua_viva.brief import BriefService

    service = BriefService(
        student_store_factory=_student_store_for_brief,
        revision_log_path=_revision_log_path(),
    )
    schedule_payload = schedule or request.headers.get("X-LV-Schedule")
    return await asyncio.to_thread(
        service.get_brief,
        _parse_schedule(schedule_payload),
        day,
        days,
    )


@app.post("/api/filemap/scan")
async def filemap_scan(payload: dict):
    from src.lingua_viva.filemap import run_scan, summarize

    root_path = str(payload.get("root_path") or "").strip()
    if not root_path:
        return JSONResponse({"error": "root_path is required"}, status_code=400)
    try:
        max_depth = int(payload.get("max_depth", 3))
        mapped = await asyncio.to_thread(run_scan, root_path, max_depth)
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    summary = summarize(mapped)
    return {
        "status": "ok",
        "total_entries": summary["total_directories"],
        "domain_summary": summary["domains_detected"],
        "student_zones_detected": summary["student_zones_excluded"],
        "summary": summary,
    }


@app.get("/api/filemap")
async def filemap_get():
    from src.lingua_viva.filemap import load_map, to_api

    return await asyncio.to_thread(lambda: to_api(load_map()))


@app.post("/api/filemap/confirm")
async def filemap_confirm(payload: dict):
    from src.lingua_viva.filemap import confirm_entry, to_api

    path = str(payload.get("path") or "").strip()
    purpose = str(payload.get("purpose") or "").strip()
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    try:
        mapped = await asyncio.to_thread(confirm_entry, path, purpose)
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"status": "ok", **to_api(mapped)}


@app.post("/api/filemap/peek")
async def filemap_peek(payload: dict):
    from src.lingua_viva.filemap import (
        _normal,
        _path_from_storage,
        display_path,
        list_files_in_zone,
        load_map,
    )

    zone_path = str(payload.get("zone_path") or "").strip()
    if not zone_path:
        return JSONResponse({"error": "zone_path is required"}, status_code=400)
    mapped = await asyncio.to_thread(load_map)
    requested_input = Path(_path_from_storage(zone_path)).expanduser()
    if requested_input.is_symlink():
        return JSONResponse(
            {"error": "zone_path cannot be a symbolic link"},
            status_code=400,
        )
    requested = _normal(_path_from_storage(zone_path))
    known_zones = {
        _normal(_path_from_storage(zone))
        for zone in mapped.student_zones
    }
    if requested not in known_zones:
        return JSONResponse(
            {"error": "zone_path is not a detected student zone"},
            status_code=400,
        )
    try:
        files = await asyncio.to_thread(list_files_in_zone, requested)
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {
        "status": "ok",
        "zone_path": display_path(requested),
        "items": [
            {**item, "path": display_path(item["path"])}
            for item in files
        ],
    }


@app.post("/api/filemap/assign")
async def filemap_assign(payload: dict):
    from src.lingua_viva.filemap import assign_student_file, to_api

    file_path = str(payload.get("file_path") or "").strip()
    student_id = payload.get("assigned_student_id")
    if not file_path:
        return JSONResponse({"error": "file_path is required"}, status_code=400)
    if student_id is not None and not isinstance(student_id, str):
        return JSONResponse({"error": "assigned_student_id must be a string or null"}, status_code=400)
    student_id = student_id.strip() if isinstance(student_id, str) else None
    if student_id:
        known_student = await asyncio.to_thread(
            _with_student_store,
            lambda store: any(
                lens["student_id"] == student_id
                for lens in store.list_lenses()
            ),
        )
        if not known_student:
            return JSONResponse(
                {"error": "assigned_student_id is not in the current roster"},
                status_code=400,
            )
    try:
        mapped = await asyncio.to_thread(assign_student_file, file_path, student_id)
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"status": "ok", **to_api(mapped)}


@app.get("/api/why")
async def why(trace_id: str | None = None, limit: int = 5):
    from dataclasses import asdict
    from src.lingua_viva.traces import get_trace, read_traces

    if trace_id:
        trace = await asyncio.to_thread(get_trace, trace_id)
        if not trace:
            return JSONResponse({"error": "Trace not found."}, status_code=404)
        return asdict(trace)
    traces = await asyncio.to_thread(read_traces, limit)
    return {"traces": [asdict(trace) for trace in traces], "route": "local", "external_calls": 0}


@app.get("/api/privacy")
async def privacy_events():
    from dataclasses import asdict
    from src.lingua_viva.privacy_log import privacy_summary, read_privacy_events

    summary = await asyncio.to_thread(privacy_summary)
    events = await asyncio.to_thread(read_privacy_events, 25)
    return {**summary, "events": [asdict(event) for event in events]}


@app.get("/api/profile")
async def profile():
    from src.lingua_viva.filemap import load_map, summarize
    from src.lingua_viva.privacy_log import privacy_summary
    from src.lingua_viva.traces import read_traces

    def build():
        schedule_days = 0
        grades = set()
        observations = 0
        students_count = 0
        reflections = 0
        try:
            with _student_store_for_brief() as store:
                lenses = store.list_lenses()
                students_count = len(lenses)
                rows = store._conn.execute("SELECT COUNT(*) AS count FROM observations").fetchone()
                observations = int(rows["count"]) if rows else 0
                grades = {str(lens.get("grade_level")) for lens in lenses if lens.get("grade_level")}
        except Exception:
            pass
        try:
            reflections = len([line for line in _revision_log_path().read_text(encoding="utf-8").splitlines() if line.strip()])
        except OSError:
            reflections = 0
        file_map_summary = summarize(load_map())
        return {
            "role": "teacher",
            "schedule_days_configured": schedule_days,
            "grades_taught": sorted(grades),
            "observations": observations,
            "students_tracked": students_count,
            "reflections": reflections,
            "filemap": file_map_summary if file_map_summary["configured"] else None,
            "reasoning_traces": len(read_traces(limit=10_000)),
            "privacy": privacy_summary(),
            "storage": "~/.lingua-viva/",
            "local_only": True,
        }

    return await asyncio.to_thread(build)


@app.get("/api/profile/export")
async def profile_export():
    """Export right (MC-lessons §8): everything /api/profile/clear would
    delete, bundled as one local-download JSON. Must be offered before
    clear, never after — there is no undo for clear."""
    from src.lingua_viva.filemap import load_map, summarize
    from src.lingua_viva.privacy_log import read_privacy_events
    from src.lingua_viva.traces import read_traces
    from dataclasses import asdict

    def build():
        try:
            with _student_store_for_brief() as store:
                students = [store.export_lens(lens["student_id"]) for lens in store.list_lenses()]
        except Exception:
            students = []
        try:
            revision_log = [
                json.loads(line)
                for line in _revision_log_path().read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            revision_log = []
        bundle = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "storage": "~/.lingua-viva/",
            "traces": [asdict(t) for t in read_traces(limit=10_000)],
            "privacy_events": [asdict(e) for e in read_privacy_events(limit=10_000)],
            "students": students,
            "revision_log": revision_log,
            "filemap": summarize(load_map()),
        }
        return JSONResponse(
            bundle,
            headers={"Content-Disposition": 'attachment; filename="lingua-viva-export.json"'},
        )

    return await asyncio.to_thread(build)


@app.post("/api/profile/clear")
async def profile_clear(payload: dict):
    if payload.get("confirm") != "clear-all-data":
        return JSONResponse({"error": "Confirmation required."}, status_code=400)

    from src.lingua_viva.filemap import clear_map
    from src.lingua_viva.privacy_log import clear_privacy_events
    from src.lingua_viva.traces import clear_traces

    def clear():
        clear_traces()
        clear_privacy_events()
        clear_map()
        for path in (_student_db_path(), _revision_log_path()):
            try:
                Path(path).unlink()
            except FileNotFoundError:
                pass
        return {"status": "cleared", "local_only": True}

    return await asyncio.to_thread(clear)


@app.post("/api/filemap/exclude")
async def filemap_exclude(payload: dict):
    from src.lingua_viva.filemap import add_exclusion, remove_exclusion, to_api

    path = str(payload.get("path") or "").strip()
    action = str(payload.get("action") or "add").strip().lower()
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    if action not in {"add", "remove"}:
        return JSONResponse({"error": "action must be add or remove"}, status_code=400)
    try:
        mapped = await asyncio.to_thread(add_exclusion if action == "add" else remove_exclusion, path)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"status": "ok", **to_api(mapped)}


@app.post("/api/filemap/clear")
async def filemap_clear():
    from src.lingua_viva.filemap import clear_map

    await asyncio.to_thread(clear_map)
    return {"status": "ok"}


@app.post("/api/prepare/activity")
async def prepare_activity(payload: dict):
    from src.education.content_differentiator import ContentDifferentiator, LessonInput

    unit = _safe_unit(payload.get("unit_id"), payload.get("grade"))
    grade_number = unit["grade"].removeprefix("G")
    try:
        duration_minutes = int(payload.get("duration_minutes") or 45)
    except (TypeError, ValueError):
        return JSONResponse({"error": "duration_minutes must be a number."}, status_code=400)
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Italian",
        unit_title=str(payload.get("unit_title") or unit["title"]),
        topic=str(payload.get("topic") or unit["focus"]),
        atl_skills=["communication", "self-management"],
        cefr_target="A2" if unit["grade"] in ("G3", "G4") else "A1",
        duration_minutes=duration_minutes,
        language_of_instruction="it",
        created_by="teacher",
    )
    pack = await asyncio.to_thread(_generate_activity_pack, lesson)
    result = pack.to_dict()
    result["source_citation"] = f"Generated from Manuale §{unit['manuale_section']}, Grade {grade_number}"
    result["source_status"] = "authoritative"
    result["cefr_rule"] = unit["cefr_language"]
    return result


def _generate_activity_pack(lesson):
    """Try document-backed generation first; fall back to template."""
    from src.education.content_differentiator import ContentDifferentiator
    from src.lingua_viva.ingest import document_retriever

    diff = ContentDifferentiator()
    retriever = document_retriever()
    if retriever is not None:
        return diff.generate_from_documents(lesson, retriever, domain="curriculum")
    return diff.generate(lesson)


@app.get("/api/prepare/tier-assignments")
async def tier_assignments():
    """Show which tier each student would receive for the next lesson pack.

    This is the demo story: given a roster of students with varying
    RTI tiers and CEFR levels, the system assigns each to the right
    content tier — foundational, on_track, or extended.
    """
    from src.education.content_differentiator import ContentDifferentiator

    diff = ContentDifferentiator()

    def compute(store):
        roster = store.list_lenses()
        assignments = []
        for lens in roster:
            tier = diff.assign_tier_for_student(lens)
            assignments.append({
                "student_id": lens["student_id"],
                "display_name": lens.get("display_name"),
                "rti_current_tier": lens.get("rti_current_tier"),
                "cefr_snapshot": lens.get("cefr_snapshot"),
                "assigned_tier": tier,
            })
        return {"assignments": assignments, "logic": "RTI tier is primary; CEFR adjusts within tier (see content-differentiation.md)"}

    result = await asyncio.to_thread(_with_student_store, compute)
    return result


def _teacher_lens_storage_dir() -> Path:
    override = os.environ.get("LV_TEACHER_LENS_STORAGE_PATH")
    if override:
        return Path(override)
    from src.lingua_viva.config import lv_home
    return lv_home() / "runtime" / "teacher_lenses"


def _with_teacher_lens_builder(teacher_id: str, callback):
    from src.education.teacher_lens_builder import TeacherLensBuilder

    builder = TeacherLensBuilder(teacher_id, _teacher_lens_storage_dir())
    return callback(builder)


@app.get("/api/teacher/lens")
async def teacher_lens(teacher_id: str = "local-teacher"):
    from dataclasses import asdict

    def get_lens(builder):
        return asdict(builder.build_lens())

    try:
        return await asyncio.to_thread(_with_teacher_lens_builder, teacher_id, get_lens)
    except ValueError:
        return JSONResponse(
            {"error": "No teaching history ingested yet.", "teacher_id": teacher_id, "ingested_doc_count": 0},
            status_code=404,
        )


@app.post("/api/teacher/ingest")
async def teacher_ingest(payload: dict):
    from dataclasses import asdict

    teacher_id = str(payload.get("teacher_id") or "local-teacher")
    file_path = str(payload.get("file_path") or "").strip()
    doc_type = str(payload.get("doc_type") or "auto")
    if not file_path:
        return JSONResponse({"error": "file_path is required"}, status_code=400)
    if not Path(file_path).exists():
        return JSONResponse({"error": f"File not found: {file_path}"}, status_code=400)

    def ingest(builder):
        return asdict(builder.ingest(Path(file_path), doc_type=doc_type))

    try:
        result = await asyncio.to_thread(_with_teacher_lens_builder, teacher_id, ingest)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return result


@app.post("/api/teacher/holdout")
async def teacher_holdout(payload: dict):
    from dataclasses import asdict

    teacher_id = str(payload.get("teacher_id") or "local-teacher")
    test_artifact = str(payload.get("test_artifact") or "").strip()
    artifact_type = str(payload.get("artifact_type") or "").strip()
    if not test_artifact or not artifact_type:
        return JSONResponse({"error": "test_artifact and artifact_type are required"}, status_code=400)
    if not Path(test_artifact).exists():
        return JSONResponse({"error": f"File not found: {test_artifact}"}, status_code=400)

    def score(builder):
        return asdict(builder.holdout_score(Path(test_artifact), artifact_type))

    try:
        result = await asyncio.to_thread(_with_teacher_lens_builder, teacher_id, score)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
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
            support_category=payload.get("support_category"),
            need_statement=payload.get("need_statement"),
            strength_statement=payload.get("strength_statement"),
            strategy_statement=payload.get("strategy_statement"),
            strategy_outcome=payload.get("strategy_outcome"),
            evidence_summary=payload.get("evidence_summary"),
            source_type=payload.get("source_type"),
            support_entries=payload.get("support_entries") or [],
            classification_guidance=payload.get("classification_guidance"),
            teacher_feedback=payload.get("teacher_feedback"),
        )

    try:
        result = await asyncio.to_thread(_with_student_store, capture)
    except Exception as exc:
        if "LensNotFoundError" in type(exc).__name__ or "LensNotFoundError" in str(type(exc)):
            return JSONResponse(
                {"error": f"Student '{student_id}' not found. Create their profile first in the Students view."},
                status_code=404,
            )
        raise
    result["local_only"] = True
    return result


def _empty_observation_proposal() -> dict:
    return {
        "template_type": None,
        "cefr_dimension": None,
        "cefr_level_observed": None,
        "cefr_direction": None,
        "sel_domain": None,
        "sel_valence": None,
        "urgency_flag": None,
        "support_category": None,
        "need_statement": None,
        "strength_statement": None,
        "strategy_statement": None,
        "strategy_outcome": None,
        "evidence_summary": None,
        "support_entries": [],
        "classification_guidance": {
            "scaffolding_level": "intermediate",
            "category_definitions": [],
            "examples": [],
            "non_examples": [],
        },
        "teacher_feedback": {"message": None, "review_prompt": None},
    }


def _first_json_object(content: str) -> dict | None:
    decoder = json.JSONDecoder()
    text = str(content or "")
    for match in re.finditer(r"\{", text):
        try:
            parsed, _end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _category_guidance(category_ids: list[str]) -> dict:
    from src.education.student_lens import SUPPORT_CATEGORY_LABELS, support_category_definition

    seen = []
    for cat_id in category_ids:
        if cat_id and cat_id not in seen:
            seen.append(cat_id)
    return {
        "scaffolding_level": "intermediate",
        "category_definitions": [
            {
                "category_id": cat_id,
                "label": SUPPORT_CATEGORY_LABELS.get(cat_id, cat_id),
                "definition": support_category_definition(cat_id),
            }
            for cat_id in seen
        ],
        "examples": [
            "Student starts the task after a two-step checklist is provided.",
            "Student explains the idea orally but needs vocabulary support in writing.",
        ][: max(1, min(2, len(seen) or 1))],
        "non_examples": [
            "Do not record a clinical diagnosis unless it appears in a verified source.",
        ],
    }


def _parse_observation_proposal(content: str) -> dict:
    from src.education.student_lens import (
        SUPPORT_CATEGORY_IDS,
        VALID_CEFR_DIMENSIONS,
        VALID_CEFR_DIRECTIONS,
        VALID_CEFR_LEVELS,
        VALID_SEL_VALENCE,
        VALID_STRATEGY_OUTCOMES,
        VALID_TEMPLATE_TYPES,
        normalize_support_entries,
        support_entry_from_scalar_fields,
    )

    proposal = _empty_observation_proposal()
    parsed = _first_json_object(content)
    if parsed is None:
        return proposal

    allowed = {
        "template_type": VALID_TEMPLATE_TYPES,
        "cefr_dimension": VALID_CEFR_DIMENSIONS,
        "cefr_level_observed": VALID_CEFR_LEVELS,
        "cefr_direction": (*VALID_CEFR_DIRECTIONS, "mixed"),
        "sel_valence": VALID_SEL_VALENCE,
    }
    for field, values in allowed.items():
        value = parsed.get(field)
        proposal[field] = value if value in values else None

    sel_domain = parsed.get("sel_domain")
    if isinstance(sel_domain, str) and sel_domain.strip():
        proposal["sel_domain"] = " ".join(sel_domain.split())[:80]
    if isinstance(parsed.get("urgency_flag"), bool):
        proposal["urgency_flag"] = parsed["urgency_flag"]

    cat_val = parsed.get("support_category")
    proposal["support_category"] = cat_val if cat_val in SUPPORT_CATEGORY_IDS else None

    strat_out = parsed.get("strategy_outcome")
    proposal["strategy_outcome"] = strat_out if strat_out in VALID_STRATEGY_OUTCOMES else None

    for statement_field in (
        "need_statement",
        "strength_statement",
        "strategy_statement",
        "evidence_summary",
    ):
        val = parsed.get(statement_field)
        if isinstance(val, str) and val.strip():
            proposal[statement_field] = " ".join(val.split())[:2000]
        else:
            proposal[statement_field] = None

    support_entries = normalize_support_entries(parsed.get("support_entries"))
    if not support_entries:
        support_entries = support_entry_from_scalar_fields(
            proposal["support_category"],
            proposal["need_statement"],
            proposal["strength_statement"],
            proposal["strategy_statement"],
            proposal["strategy_outcome"],
            proposal["evidence_summary"],
        )
    for entry in support_entries:
        entry["model_suggested"] = True
        entry["teacher_confirmed"] = False
    proposal["support_entries"] = support_entries
    proposal["classification_guidance"] = _category_guidance(
        [entry["support_category"] for entry in support_entries]
    )
    proposal["teacher_feedback"] = {
        "message": None,
        "review_prompt": "Review suggested categories and statements before saving."
        if support_entries
        else None,
    }

    return proposal


@app.post("/api/observe/classify")
async def observe_classify(payload: dict):
    """Propose observation tags for teacher review; never writes student data."""
    from src.education.student_lens import (
        SUPPORT_CATEGORY_IDS,
        VALID_CEFR_DIMENSIONS,
        VALID_CEFR_LEVELS,
        VALID_SEL_VALENCE,
        VALID_STRATEGY_OUTCOMES,
        VALID_TEMPLATE_TYPES,
    )
    from src.lingua_viva import config as lv_config
    from src.lingua_viva.reasoning import ReasoningEngine

    student_id = str(payload.get("student_id") or "").strip()
    transcript = str(payload.get("raw_transcript") or "").strip()
    if not student_id:
        return JSONResponse({"error": "student_id is required"}, status_code=400)
    if not transcript:
        return JSONResponse({"error": "raw_transcript is required"}, status_code=400)
    if len(transcript) > 4000:
        return JSONResponse(
            {"error": "raw_transcript must be 4000 characters or fewer"},
            status_code=413,
        )

    system_prompt = (
        "You classify one teacher observation for a form the teacher will review. "
        "Return one strict JSON object and no prose. Never rewrite the transcript. "
        "Leave any uncertain or unsupported field null; do not guess. "
        "Do not infer disability, diagnosis, trauma, or protected traits. "
        f"template_type must be one of {list(VALID_TEMPLATE_TYPES)} or null. "
        f"cefr_dimension must be one of {list(VALID_CEFR_DIMENSIONS)} or null. "
        f"cefr_level_observed must be one of {list(VALID_CEFR_LEVELS)} or null. "
        "cefr_direction may be progressing, plateaued, regressing, mixed, or null. "
        "sel_domain is a short plain-language label or null. "
        f"sel_valence must be one of {list(VALID_SEL_VALENCE)} or null. "
        "urgency_flag must be true, false, or null. "
        f"support_category must be one of {list(SUPPORT_CATEGORY_IDS)} or null. "
        "Prefer support_entries as an array; include more than one entry only when the transcript explicitly supports multiple categories. "
        "advanced_enrichment is for challenge/extension needs. "
        "need_statement, strength_statement, strategy_statement, and evidence_summary are short teacher-readable strings or null. "
        f"strategy_outcome must be one of {list(VALID_STRATEGY_OUTCOMES)} or null, and is only worked or did_not_work if the note explicitly states strategy success. "
        "Preserve language and setting context when present as context_tags language and setting. "
        "Use exactly these top-level keys: template_type, cefr_dimension, cefr_level_observed, cefr_direction, sel_domain, sel_valence, urgency_flag, support_category, need_statement, strength_statement, strategy_statement, strategy_outcome, evidence_summary, support_entries."
    )
    try:
        result = await asyncio.wait_for(
            ReasoningEngine().reason(
                transcript,
                context={"domain": "observation", "student_id": "selected-local-student"},
                model=lv_config.detect_model(),
                system_prompt=system_prompt,
            ),
            timeout=15,
        )
    except Exception:
        result = None

    degraded = (
        result is None
        or result.model_used == "none"
        or result.confidence <= 0
        or "appears to be down" in result.content.lower()
        or "no model available" in result.content.lower()
    )
    proposal = (
        _empty_observation_proposal()
        if degraded
        else _parse_observation_proposal(result.content)
    )
    return {
        "proposal": proposal,
        "model_used": "none" if degraded else result.model_used,
        "suggestions_available": not degraded and any(
            value not in (None, [], {})
            for key, value in proposal.items()
            if key not in ("classification_guidance", "teacher_feedback")
        ),
        "writes_made": 0,
        "teacher_confirmation_required": True,
    }


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


@app.post("/api/students")
async def create_student(payload: dict):
    """Create a new student lens from the Add Student form."""
    display_name = (payload.get("display_name") or "").strip()
    if not display_name:
        return JSONResponse({"error": "display_name is required"}, status_code=400)

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


@app.get("/api/students/unobserved")
async def unobserved_students(days: int = 14):
    cutoff = time.time() - max(days, 0) * 86400

    def list_unobserved(store):
        students_out = []
        for lens in store.list_lenses():
            rows = store._conn.execute(
                "SELECT recorded_at FROM observations WHERE student_id = ? ORDER BY recorded_at DESC LIMIT 1",
                (lens["student_id"],),
            ).fetchall()
            last_observed = rows[0]["recorded_at"] if rows else None
            stale = True
            if last_observed:
                try:
                    stale = datetime.fromisoformat(last_observed).timestamp() < cutoff
                except ValueError:
                    stale = True
            if stale:
                students_out.append({
                    "student_id": lens["student_id"],
                    "display_name": lens.get("display_name"),
                    "grade_level": lens.get("grade_level"),
                    "rti_current_tier": lens.get("rti_current_tier"),
                    "last_observed": last_observed,
                    "days_threshold": days,
                })
        return students_out

    return {
        "days": days,
        "students": await asyncio.to_thread(_with_student_store, list_unobserved),
    }


@app.get("/api/extraction/sources")
async def extraction_sources():
    """List confirmed local and Google Drive import files available for extraction."""
    def get_sources(store):
        sources = []
        try:
            assigned = store.list_assigned_files() if hasattr(store, "list_assigned_files") else []
            for f in assigned:
                sources.append({
                    "file_path": f.get("file_path"),
                    "display_name": f.get("display_name") or Path(f.get("file_path", "")).name,
                    "source_type": "file_map",
                    "student_id": f.get("student_id"),
                })
        except Exception:
            pass

        from src.lingua_viva.config import lv_home
        import_dir = lv_home() / "imports"
        if import_dir.exists():
            for p in import_dir.glob("*"):
                if p.is_file() and p.suffix.lower() in (".txt", ".md", ".pdf"):
                    sources.append({
                        "file_path": str(p),
                        "display_name": p.name,
                        "source_type": "google_drive",
                        "student_id": None,
                    })

        if not sources:
            demo_path = lv_home() / "imports" / "demo_observation.txt"
            demo_path.parent.mkdir(parents=True, exist_ok=True)
            if not demo_path.exists():
                demo_path.write_text(
                    "Student Marco shows strong executive functioning when provided visual checklist cards. "
                    "Needs structured graphic organizers for essay writing. "
                    "Tried open-ended silent reading without checklist which failed.",
                    encoding="utf-8"
                )
            sources.append({
                "file_path": str(demo_path),
                "display_name": demo_path.name,
                "source_type": "local_note",
                "student_id": None,
            })
        return sources

    return {"sources": await asyncio.to_thread(_with_student_store, get_sources)}


@app.post("/api/extraction/run")
async def extraction_run(payload: dict):
    """Run extract-fill-verify on a selected file."""
    from src.lingua_viva.extraction_engine import extract

    file_path = str(payload.get("file_path") or "").strip()
    if not file_path:
        return JSONResponse({"error": "file_path is required"}, status_code=400)

    target_schema = str(payload.get("target_schema_id") or "student_lens")
    hint = payload.get("hint") or {}
    if payload.get("student_id"):
        hint["student_id"] = payload["student_id"]

    try:
        result = await extract([file_path], target_schema_id=target_schema, hint=hint)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    verified_fields = []
    needs_confirmation_fields = []
    for f in result.fields:
        item = {
            "field_path": f.field_path,
            "value": f.value,
            "confidence": f.confidence,
            "status": f.status,
            "supporting_chunk_ids": f.supporting_chunk_ids,
            "review_tip": f"Check whether source describes {f.field_path.split('.')[-1]} or general setting.",
            "category_id": f.field_path.split(".")[2] if "categories." in f.field_path else None,
        }
        if f.status == "verified":
            verified_fields.append(item)
        elif f.status == "needs_confirmation":
            needs_confirmation_fields.append(item)

    chunks_used = [
        {
            "chunk_id": c.chunk_id,
            "file_path": c.file_path,
            "snippet": c.text[:300],
        }
        for c in result.chunks_used
    ]

    return {
        "target_schema_id": target_schema,
        "source_file": file_path,
        "verified_fields": verified_fields,
        "needs_confirmation_fields": needs_confirmation_fields,
        "unresolved_questions": result.unresolved_questions,
        "chunks_used": chunks_used,
    }


@app.post("/api/extraction/review")
async def extraction_review(payload: dict):
    """Submit teacher confirmations/rejections and write confirmed fields into student lens."""
    from src.lingua_viva.extraction_engine import extract
    from src.lingua_viva.student_lens_writer import write_student_lens

    file_path = str(payload.get("file_path") or "").strip()
    target_schema = str(payload.get("target_schema_id") or "student_lens")
    hint = payload.get("hint") or {}
    student_id = payload.get("student_id")
    if student_id:
        hint["assigned_student_id"] = student_id

    confirmed = payload.get("confirmed_fields") or []
    rejected = payload.get("rejected_fields") or []

    if file_path and Path(file_path).exists():
        ext_result = await extract([file_path], target_schema_id=target_schema, hint=hint)
    else:
        from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
        fields = []
        for item in confirmed:
            if isinstance(item, dict) and item.get("field_path"):
                fields.append(
                    ExtractedField(
                        field_path=item["field_path"],
                        value=item.get("value"),
                        confidence=item.get("confidence", 0.85),
                        supporting_chunk_ids=item.get("supporting_chunk_ids") or ["file#chunk-0001"],
                        status=item.get("status", "verified"),
                    )
                )
        ext_result = ExtractionResult(
            target_schema_id=target_schema,
            fields=fields,
            unresolved_questions=[],
            source_files=[file_path] if file_path else [],
            chunks_used=[],
        )

    def do_write(store):
        return write_student_lens(
            ext_result,
            teacher_id=str(payload.get("teacher_id") or "local-teacher"),
            confirmed_fields=confirmed,
            rejected_fields=rejected,
            hint=hint,
            store=store,
        )

    try:
        result = await asyncio.to_thread(_with_student_store, do_write)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/categories")
async def get_categories():
    """Return static, secret-free category metadata for UI Scaffolding & Gagné Guidance."""
    from src.education.student_lens import SUPPORT_CATEGORY_IDS, SUPPORT_CATEGORY_LABELS

    category_definitions = {
        "learning_and_cognition": {
            "definition": "Academic learning, concept mastery, processing speed, memory, and cognitive task execution evidence.",
            "examples": ["Understands multi-step math word problems when given graphic organizer."],
            "non_examples": ["Do not record diagnostic labels without verified source."],
        },
        "communication_and_language": {
            "definition": "Receptive/expressive language, vocabulary acquisition, speech clarity, and communication modality evidence.",
            "examples": ["Uses CEFR B1 connective words during oral partner discussions."],
            "non_examples": ["Do not mark language learning support as a cognitive disability."],
        },
        "executive_functioning": {
            "definition": "Planning, sequencing, organization, attention, working memory, transition, and task-initiation evidence.",
            "examples": ["Student starts the task after a two-step checklist is provided."],
            "non_examples": ["Do not record a diagnosis unless it appears in a verified source."],
        },
        "social_skills": {
            "definition": "Peer interaction, group collaboration, turn-taking, conflict resolution, and relational dynamics.",
            "examples": ["Initiates cooperative turn-taking during science lab station."],
            "non_examples": ["Do not confuse temporary social conflict with permanent RTI tier changes."],
        },
        "emotional_regulation": {
            "definition": "Self-soothing, emotional awareness, frustration tolerance, impulse management, and coping strategies.",
            "examples": ["Uses break card independently when feeling overwhelmed during assessment."],
            "non_examples": ["Do not record clinical mental health diagnoses."],
        },
        "physical_sensory_needs": {
            "definition": "Sensory processing, ergonomics, movement needs, motor skills, and physical accommodation evidence.",
            "examples": ["Responds well to wobble stool and noise-canceling headphones during writing."],
            "non_examples": ["Do not infer medical conditions without explicit documentation."],
        },
        "attendance_and_engagement": {
            "definition": "Punctuality, class attendance, task persistence, motivation, and active participation signals.",
            "examples": ["Maintains 95% engagement when tasks link to personal interest topic."],
            "non_examples": ["Do not penalize unexcused absences in academic tier scoring."],
        },
        "advanced_enrichment": {
            "definition": "Extension, acceleration, passion project, depth of knowledge, and gifted/talented challenge needs.",
            "examples": ["Demonstrates B2/C1 reading comprehension; requires advanced text extension."],
            "non_examples": ["Do not use advanced enrichment needs to escalate RTI intervention tier."],
        },
    }

    categories = []
    for cat_id in SUPPORT_CATEGORY_IDS:
        meta = category_definitions.get(cat_id, {})
        categories.append({
            "id": cat_id,
            "label": SUPPORT_CATEGORY_LABELS.get(cat_id, cat_id),
            "definition": meta.get("definition", ""),
            "examples": meta.get("examples", []),
            "non_examples": meta.get("non_examples", []),
        })
    return {"categories": categories}


@app.get("/api/students/support-summary")
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


@app.post("/api/students/{student_id}/rti/decision")
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


@app.put("/api/students/{student_id}/rti")
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


@app.get("/api/students/{student_id}/lens-as-of")
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
        target_student_id = student_id
        try:
            lens = store.get_lens(target_student_id)
        except Exception:
            target_student_id = "student-nora"
            lens = store.get_lens(target_student_id)
        draft = generator.generate_draft(target_student_id, str(payload.get("teacher_id") or "local-teacher"))
        names = [lens.get("display_name") or ""]
        extra = str(payload.get("focus") or "").strip()
        body = draft.body
        if extra:
            body = (
                f"{body} At home, you might offer a {extra} and notice what your child "
                "chooses to try first."
            )
        return {
            "subject_line": _strip_parent_output(draft.subject_line, names),
            "body": _strip_parent_output(body, names),
            "home_activities": [_strip_parent_output(item, names) for item in draft.home_activities],
            "review_label": "Review before sending. No AI attribution in final message.",
            "source_citation": "Source: Manuale v1 and local teacher observations.",
        }

    return await asyncio.to_thread(_with_student_store, generate)


@app.post("/api/reflect/note")
async def reflect_note(payload: dict):
    from src.lingua_viva.privacy import redact_runtime_text

    note = str(payload.get("note") or "").strip()
    if not note:
        return JSONResponse({"error": "Reflection note is required."}, status_code=400)
    log_path = _revision_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "revision_id": f"teacher-reflection-{int(time.time())}",
        "artifact_id": "lv-private-teacher-reflection",
        "artifact_path": "dev/lv_revision_log.ndjson",
        "defect_class": "teacher_reflection",
        "origin": "teacher_input",
        "instrument_that_found_it": "reflect_view",
        "instrument_touched": False,
        "independent_cross_check": "private_teacher_note_no_external_sync",
        "decision": "Record private teacher reflection locally.",
        "proof": redact_runtime_text(note),
        "reviewer": "teacher",
        "teacher_contribution_involved": True,
        "privacy_review": "private_local_only",
        "private": True,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return {"status": "saved", "timestamp": entry["timestamp"], "private": True}


@app.get("/api/publication/status")
async def publication_status():
    from src.lingua_viva.publication import PublicationService

    return await asyncio.to_thread(PublicationService().get_status)


@app.post("/api/support-bundle")
async def support_bundle():
    from src.lingua_viva.support_bundle import SupportBundleService

    try:
        return await asyncio.to_thread(SupportBundleService().create_bundle)
    except Exception as exc:
        return JSONResponse(
            {
                "status": "ERROR",
                "error": str(exc),
                "summary": "I could not create the support bundle safely. No files were uploaded.",
                "external_calls": False,
            },
            status_code=500,
        )


@app.get("/api/admin/programme")
async def admin_programme():
    from src.lingua_viva.curriculum import CurriculumService

    return await asyncio.to_thread(CurriculumService().get_overview)


def _admin_deferred(title: str, reason: str, requires: list[str]) -> dict:
    return {
        "status": "deferred",
        "phase": "LV Phase 7 admin dashboard",
        "title": title,
        "reason": reason,
        "requires": requires,
    }


@app.get("/api/admin/evidence")
async def admin_evidence():
    # DEFERRED: requires accumulated, consent-aware teacher evidence data.
    # Date: 2026-07-18. Owner: LV Phase 7 admin dashboard.
    return _admin_deferred(
        "Evidence",
        "Evidence bundles need consent-aware teacher observations accumulated over time.",
        ["teacher observation history", "consent review", "evidence export policy"],
    )


@app.get("/api/admin/capacity")
async def admin_capacity():
    # DEFERRED: requires staffing/capacity model inputs that do not exist yet.
    # Date: 2026-07-18. Owner: LV Phase 7 admin dashboard.
    return _admin_deferred(
        "Capacity",
        "Capacity planning needs staffing, enrollment, and classroom allocation inputs.",
        ["staffing roster", "projected enrollment", "classroom allocation model"],
    )


@app.get("/api/admin/trends")
async def admin_trends():
    # DEFERRED: requires accumulated anonymized trend data.
    # Date: 2026-07-18. Owner: LV Phase 7 admin dashboard.
    return _admin_deferred(
        "Trends",
        "School-wide trends need enough anonymized observations to avoid overclaiming.",
        ["anonymized observation history", "minimum cohort size", "trend review policy"],
    )


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


@app.get("/api/google-drive/status")
async def google_drive_status():
    from src.lingua_viva.google_drive_integration import status

    return await asyncio.to_thread(status)


@app.post("/api/google-drive/list")
async def google_drive_list(payload: dict):
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        list_files,
    )

    try:
        return await asyncio.to_thread(
            list_files,
            str(payload.get("query") or ""),
            str(payload.get("folder_id") or ""),
            str(payload.get("page_token") or ""),
        )
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError:
        return JSONResponse({"error": "Google Drive could not be reached safely."}, status_code=503)


@app.post("/api/google-drive/import")
async def google_drive_import(payload: dict):
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        import_files,
    )

    file_ids = payload.get("file_ids")
    if not isinstance(file_ids, list):
        return JSONResponse({"error": "file_ids must be a non-empty list of opaque IDs."}, status_code=400)
    purpose = str(payload.get("purpose") or "unassigned")
    assigned_student_id = payload.get("assigned_student_id")
    if assigned_student_id is not None and not isinstance(assigned_student_id, str):
        return JSONResponse({"error": "assigned_student_id must be a string or null"}, status_code=400)
    assigned_student_id = assigned_student_id.strip() if isinstance(assigned_student_id, str) else None

    def student_exists(student_id: str) -> bool:
        return _with_student_store(
            lambda store: any(
                lens["student_id"] == student_id
                for lens in store.list_lenses()
            )
        )

    try:
        return await asyncio.to_thread(
            import_files,
            file_ids,
            purpose,
            assigned_student_id,
            student_exists=student_exists,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError:
        return JSONResponse({"error": "Google Drive could not be reached safely."}, status_code=503)


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
        return JSONResponse({"error": "query is required"}, status_code=400)

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

        timeout_seconds = float(payload.get("timeout_seconds") or 25)
        result = await asyncio.wait_for(
            run_teacher_query(
                query_text,
                intent=intent,
                session_id=session_id,
                eval_mode=eval_mode,
            ),
            timeout=timeout_seconds,
        )
        from src.lingua_viva.privacy_log import log_event
        from src.lingua_viva.traces import append_trace, new_trace

        source_citations = result.synthesis.citations or ["Manuale v1"]
        query_trace = new_trace(
            query_text,
            domain=result.classification.domain,
            model_used=result.synthesis.model_used,
            duration_ms=result.duration_ms,
            token_count=0,
            source_citations=source_citations,
            privacy_events=[],
        )
        append_trace(query_trace)
        log_event("query_processed_locally", query_text=query_text)
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
                "external_called": False,
                "duration_ms": result.duration_ms,
                "gap_signals": result.gap_signals,
            },
            "trace_id": query_trace.trace_id,
            "route": "local",
            "model_used": result.synthesis.model_used,
            "duration_ms": result.duration_ms,
            "source_citation": source_citations[0] if source_citations else "Manuale v1",
            "external_calls": 0,
            "session_id": session_id,
            "timestamp": time.time(),
        }

        await broadcaster.broadcast(response)
        return response

    except asyncio.TimeoutError:
        error = {
            "type": "error",
            "error": "Local reasoning timed out. Check Ollama, then try again.",
            "timeout": True,
            "timestamp": time.time(),
        }
        await broadcaster.broadcast(error)
        return error

    except (ModuleNotFoundError, ImportError):
        error = {
            "type": "error",
            "error": "Ask isn't able to answer free-form questions in this build yet. Try Plan, Prepare, or Observe for now.",
            "unavailable": True,
            "timestamp": time.time(),
        }
        await broadcaster.broadcast(error)
        return error

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
    """Scoped scratch dir for uploads-in-flight.

    Never use the shared system tmp root; this keeps write/parse/delete easy
    to reason about and gives tests a single LV_INGEST_TMP_DIR override.
    """
    override = os.environ.get("LV_INGEST_TMP_DIR")
    if override:
        d = Path(override)
    else:
        from src.lingua_viva.config import lv_home
        d = lv_home() / "runtime" / "ingest-tmp"
    d.mkdir(parents=True, exist_ok=True)
    for stale in d.glob("tmp*.pdf"):
        try:
            stale.unlink()
        except OSError:
            pass
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
