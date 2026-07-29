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
import errno
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
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


@app.get("/assets/{name}")
async def static_asset(name: str):
    safe_name = Path(name).name
    return FileResponse(LV_ROOT / "static" / "assets" / safe_name)


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


# ---------------------------------------------------------------------------
# Slack Daily Operations Assistant (spec SPEC_LV_SLACK_OPS_ASSISTANT
# 2026-07-27, Lane E). Separate from the dormant observation path above:
# Socket Mode transport, ops records only, never student lenses.
# ---------------------------------------------------------------------------

_ops_runtime: dict = {}


def _ops_teacher_map() -> dict:
    """Teacher map from env if valid, else empty (read routes stay usable)."""
    from src.lingua_viva.slack_socket import (
        SlackOpsConfigurationError,
        require_ops_config,
    )

    try:
        return require_ops_config().teacher_map
    except SlackOpsConfigurationError:
        return {}


def _ops_local_today() -> str:
    return datetime.now().astimezone().date().isoformat()


@app.get("/api/slack/ops/status")
async def slack_ops_status():
    """Secret-free readiness/liveness for the Daily Operations Assistant."""
    from src.lingua_viva.slack_socket import ops_status

    return ops_status()


# --- Slack credential setup (Slice 5 — SPEC_CONNECTION_CREDENTIAL_SETUP ----
# Until now the ops assistant could only be configured by exporting four
# environment variables in a terminal. These routes let a teacher do it from
# Settings. No route ever returns a secret: reads report only whether a field
# is set and where it came from (env > stored), and the test route verifies a
# token against Slack without persisting it.
# ---------------------------------------------------------------------------


def _require_local(request: Request) -> JSONResponse | None:
    """Refuse credential operations that did not come from this machine.

    The server already binds 127.0.0.1 only, so this is defence in depth for
    the reverse-proxy case the Slack hardening pass (contract v12) called out.
    LV handles student data; a credential route is the last place to rely on
    a single layer.

    Returns an error response to hand straight back, or None when allowed —
    the routes below return `{"error": ...}` bodies (this repo's convention,
    which static/index.html's api() helper reads) rather than raising
    HTTPException, whose `detail` key that helper would silently drop.
    """
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return JSONResponse(
            {"error": "Credential setup is only available on this computer."},
            status_code=403,
        )
    return None


def _slack_credentials_payload() -> dict:
    """Secret-free view of Slack setup: per-field source + readiness."""
    from src.lingua_viva.slack_credentials import credential_status
    from src.lingua_viva.slack_socket import ops_status

    payload = credential_status()
    status = ops_status()
    payload["configured"] = bool(status.get("configured"))
    payload["config_error"] = status.get("config_error")
    payload["connected"] = bool(status.get("connected"))
    payload["teacher_count"] = status.get("teacher_count", 0)
    return payload


async def _restart_slack_ops() -> None:
    """Apply newly saved credentials without making the teacher restart.

    Saving is pointless if the assistant only picks it up on next launch —
    that is the difference between a setup form and a setup form that works.
    """
    await _shutdown_slack_ops()
    await _startup_slack_ops()


@app.get("/api/slack/credentials")
async def slack_credentials_get(request: Request):
    """Secret-free Slack credential status for the Settings panel."""
    denied = _require_local(request)
    if denied is not None:
        return denied
    return await asyncio.to_thread(_slack_credentials_payload)


@app.put("/api/slack/credentials")
async def slack_credentials_put(request: Request):
    """Save Slack credentials, then reconnect so they take effect now."""
    denied = _require_local(request)
    if denied is not None:
        return denied
    from src.lingua_viva.slack_credentials import (
        SLACK_ENV_VARS,
        SlackCredentialError,
        save_stored,
    )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Expected a JSON object."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Expected a JSON object."}, status_code=400)

    submitted = {k: v for k, v in body.items() if k in SLACK_ENV_VARS}
    if not submitted:
        return JSONResponse(
            {
                "error": "No Slack settings were sent. Expected any of: "
                + ", ".join(SLACK_ENV_VARS)
            },
            status_code=400,
        )

    try:
        await asyncio.to_thread(save_stored, submitted)
    except SlackCredentialError as exc:
        # Teacher-readable, field-named, never echoes the value.
        return JSONResponse({"error": str(exc)}, status_code=400)

    await _restart_slack_ops()
    return await asyncio.to_thread(_slack_credentials_payload)


@app.delete("/api/slack/credentials")
async def slack_credentials_delete(request: Request):
    """Forget every in-app Slack credential and disconnect."""
    denied = _require_local(request)
    if denied is not None:
        return denied
    from src.lingua_viva.slack_credentials import clear_stored

    await asyncio.to_thread(clear_stored)
    await _restart_slack_ops()
    return await asyncio.to_thread(_slack_credentials_payload)


@app.post("/api/slack/credentials/test")
async def slack_credentials_test(request: Request):
    """Check a bot token against Slack's auth.test before saving it.

    Accepts a token in the body so a teacher can verify what they pasted
    before committing it; falls back to the effective stored/env token so the
    panel can also re-test an existing setup. Nothing is written either way.
    """
    denied = _require_local(request)
    if denied is not None:
        return denied
    from src.lingua_viva.slack_credentials import effective_env
    from src.lingua_viva.slack_socket import auth_test

    try:
        body = await request.json()
    except Exception:
        body = {}
    token = ""
    if isinstance(body, dict):
        token = str(body.get("LV_SLACK_BOT_TOKEN") or "").strip()
    if not token:
        token = str(
            (await asyncio.to_thread(effective_env)).get("LV_SLACK_BOT_TOKEN", "")
        ).strip()
    if not token:
        return {
            "ok": False,
            "error": "not_authed",
            "message": "Add a bot token first, then test the connection.",
        }
    return await asyncio.to_thread(auth_test, token)


@app.get("/api/ops/daily")
async def ops_daily(teacher_id: str | None = None, date: str | None = None):
    """Render each teacher's daily file (same markdown as the Desktop file)."""

    def build() -> dict:
        from src.education.daily_file import DailyFileEngine
        from src.education.ops_records import OpsRecordStore

        date_iso = (date or "").strip() or _ops_local_today()
        teacher_map = _ops_teacher_map()
        with OpsRecordStore() as store:
            engine = DailyFileEngine(store, teacher_map=teacher_map)
            teachers: list[tuple[str, str]] = [
                (str(info.get("teacher_id") or ""), str(info.get("display_name") or ""))
                for info in teacher_map.values()
            ]
            if not teachers:
                # Unconfigured transport: derive teachers from the day itself.
                seen: dict[str, str] = {}
                for record in store.records_for_day(date_iso):
                    if record.teacher_id and record.teacher_id not in seen:
                        seen[record.teacher_id] = (
                            record.actor_name or record.teacher_id
                        )
                teachers = sorted(seen.items())
            if teacher_id:
                teachers = [t for t in teachers if t[0] == teacher_id]
            payload = []
            for tid, display in teachers:
                payload.append(
                    {
                        "teacher_id": tid,
                        "display_name": display,
                        "markdown": engine.render_markdown(tid, display, date_iso),
                        "file_path": str(engine.daily_file_path(display)),
                    }
                )
            return {
                "date": date_iso,
                "configured": bool(teacher_map),
                "teachers": payload,
                "needs_review": store.needs_review_count(date_iso),
            }

    return await asyncio.to_thread(build)


@app.get("/api/ops/records")
async def ops_records_for_day(teacher_id: str | None = None, date: str | None = None):
    """Raw operational records for a day (local audit surface)."""

    def build() -> dict:
        from dataclasses import asdict

        from src.education.ops_records import OpsRecordStore

        date_iso = (date or "").strip() or _ops_local_today()
        with OpsRecordStore() as store:
            records = store.records_for_day(date_iso, teacher_id=teacher_id or None)
            return {
                "date": date_iso,
                "count": len(records),
                "records": [asdict(record) for record in records],
            }

    return await asyncio.to_thread(build)


# --- v2 Bot Setup routes (spec SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS §6) -----
# Secret-free by construction: tokens/channel live only in LV_SLACK_* env,
# the bot-spec refuses token shapes at write time, and none of these
# payloads touch config values beyond the roster map (which is the panel's
# read-only confirmation surface — source of truth stays the env var).


def _ops_bot_spec_payload(spec) -> dict:
    """Shared shape for GET and PUT responses: the bot-spec state plus a
    compiled summary the panel renders (categories/sections/broadcast)."""
    from src.education.ops_bot_spec import bot_spec_path

    rules = spec.rule_set
    return {
        "exists": spec.exists,
        "live": spec.live,
        "fallback": spec.fallback,
        "schema_version": spec.schema_version,
        "spec_path": str(bot_spec_path()),
        "packs": {"enabled": list(spec.enabled_pack_ids)},
        "settings": {
            "briefing_hhmm": spec.briefing_hhmm,
            "eod_hhmm": spec.eod_hhmm,
            "period_aliases": list(spec.period_aliases),
            "claim_rights": spec.claim_rights,
            "review_required": list(spec.review_required),
        },
        "learned_rules": [dict(rule) for rule in spec.learned_rules],
        "corpus": {
            "admin_sentences": [dict(s) for s in spec.corpus_sentences],
            "last_run": dict(spec.corpus_last_run) if spec.corpus_last_run else None,
        },
        "compiled": {
            "categories": list(rules.category_ids()),
            "section_order": list(rules.section_order),
            "broadcast_categories": sorted(rules.broadcast_categories),
        },
    }


@app.get("/api/ops/setup/catalog")
async def ops_setup_catalog():
    """The shipped pack catalog (read-only data from config/ops_packs/)."""

    def build() -> dict:
        from src.education import ops_packs

        packs = ops_packs.load_packs()
        return {
            "packs": [
                {
                    "id": pack.id,
                    "name": pack.name,
                    "description": pack.description,
                    "enabled_by_default": pack.enabled_by_default,
                    "default_for_new_schools": pack.default_for_new_schools,
                    "categories": [
                        {
                            "id": entry.id,
                            "priority": entry.priority,
                            "section": entry.section,
                            "broadcast": entry.broadcast,
                            "capability": entry.capability,
                            "channel_default": entry.channel_default,
                            "vocabulary_count": len(entry.patterns),
                        }
                        for entry in pack.categories
                    ],
                    "sections": [section.name for section in pack.sections],
                    "samples": [
                        {"text": sample.text, "expect": dict(sample.expect)}
                        for sample in pack.samples
                    ],
                }
                for pack in sorted(packs.values(), key=lambda p: p.id)
            ],
            "core": {
                "category": "other",
                "note": "Fallback + clarification + To Review — core, cannot be disabled.",
            },
        }

    return await asyncio.to_thread(build)


@app.get("/api/ops/setup/bot-spec")
async def ops_setup_bot_spec_get():
    """Current bot-spec state (disk truth; pure read, no swap)."""

    def build() -> dict:
        from src.education.ops_bot_spec import load_compiled_spec

        return _ops_bot_spec_payload(load_compiled_spec())

    return await asyncio.to_thread(build)


@app.put("/api/ops/setup/bot-spec")
async def ops_setup_bot_spec_put(request: Request):
    """Write pack selections + interview settings, then atomically swap the
    live compile. NEVER touches the transport (spec §3.3: creating a
    bot-spec must not stop a running env-configured bot). Learned rules and
    corpus results are owned by the teach loop/corpus runner — this route
    preserves them from disk, so the panel can never clobber them."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)

    def build():
        from src.education import ops_bot_spec

        current = ops_bot_spec.load_compiled_spec()
        data = dict(current.raw) if current.exists and not current.fallback else (
            ops_bot_spec.default_bot_spec_data()
        )
        # Panel-owned fields only; teach-loop fields carry over from disk.
        packs_block = body.get("packs")
        if isinstance(packs_block, dict) and isinstance(
            packs_block.get("enabled"), list
        ):
            data["packs"] = {"enabled": [str(p) for p in packs_block["enabled"]]}
        settings_in = body.get("settings")
        if isinstance(settings_in, dict):
            settings = dict(data.get("settings") or {})
            for key in (
                "briefing_hhmm",
                "eod_hhmm",
                "period_aliases",
                "claim_rights",
                "review_required",
            ):
                if key in settings_in:
                    settings[key] = settings_in[key]
            data["settings"] = settings
        if "live" in body:
            data["live"] = bool(body["live"])

        # Staleness guard (spec §7): if this save changes what the
        # compiled rule set routes (pack membership, period aliases),
        # the recorded corpus run no longer describes the live rules —
        # drop it so go-live requires a fresh passing run.
        def _routing_signature(doc: dict) -> tuple:
            settings_block = doc.get("settings") or {}
            return (
                tuple(sorted((doc.get("packs") or {}).get("enabled") or [])),
                tuple(settings_block.get("period_aliases") or []),
            )

        before_data = (
            dict(current.raw)
            if current.exists and not current.fallback
            else ops_bot_spec.default_bot_spec_data()
        )
        if _routing_signature(data) != _routing_signature(before_data):
            corpus_block = dict(data.get("corpus") or {})
            corpus_block["last_run"] = None
            data["corpus"] = corpus_block

        # Go-live gate (spec §7): a school never goes live on untested
        # rules — the toggle requires a recorded passing corpus run.
        if data.get("live"):
            last_run = (data.get("corpus") or {}).get("last_run") or {}
            if not last_run.get("passed"):
                return JSONResponse(
                    {
                        "error": "Go-live requires a passing corpus test run. "
                        "Run the test corpus first."
                    },
                    status_code=409,
                )

        # Validate by compiling BEFORE writing — a spec that does not
        # compile is never written to disk.
        try:
            ops_bot_spec._compile_from_data(dict(data))
        except ops_bot_spec.PackLoadError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        try:
            ops_bot_spec.write_bot_spec(data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        spec = ops_bot_spec.refresh_from_disk()
        return _ops_bot_spec_payload(spec)

    return await asyncio.to_thread(build)


@app.post("/api/ops/review/reclassify")
async def ops_review_reclassify(request: Request):
    """Teach-loop record fix (spec §4): reclassify a To Review record, then
    optionally file a CANDIDATE learned rule ("treat future messages like
    this as X") in the bot-spec. Candidates never affect live
    classification — they wait for the corpus-gated approve ceremony."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    record_id = str(body.get("record_id") or "").strip()
    category = str(body.get("category") or "").strip()
    keyphrase = str(body.get("keyphrase") or "").strip()
    if not record_id or not category:
        return JSONResponse(
            {"error": "record_id and category are required."}, status_code=400
        )

    def build():
        from dataclasses import asdict

        from src.education import ops_bot_spec
        from src.education.daily_file import DailyFileEngine
        from src.education.ops_records import OpsRecordStore

        if keyphrase and category in ("other", "coverage_claim", "announcement"):
            return JSONResponse(
                {
                    "error": "Learned rules cannot target core 'other', "
                    "coverage_claim (claims belong to the machine), or "
                    "announcement (positional — it has no vocabulary by "
                    "design)."
                },
                status_code=400,
            )
        with OpsRecordStore() as store:
            before = store.get_record(record_id)
            if before is None:
                return JSONResponse({"error": "Unknown record."}, status_code=404)
            try:
                if category == "coverage_request":
                    # The claim machine owns coverage records — the past
                    # record just leaves To Review; the CANDIDATE rule is
                    # how future messages get real coverage treatment.
                    updated = store.mark_reviewed(record_id)
                else:
                    updated = store.reclassify_record(record_id, category)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            # Re-render BOTH placements: the files the old category reached
            # (a broadcast wrongly filed touches every teacher) and the
            # files the corrected category reaches now.
            engine = DailyFileEngine(store, teacher_map=_ops_teacher_map())
            engine.refresh_for_record(before)
            engine.refresh_for_record(updated)

            rule = None
            if keyphrase:
                current = ops_bot_spec.load_compiled_spec()
                data = (
                    dict(current.raw)
                    if current.exists and not current.fallback
                    else ops_bot_spec.default_bot_spec_data()
                )
                rule = ops_bot_spec.new_candidate_rule(
                    category=category,
                    keyphrase=keyphrase,
                    source_record_id=record_id,
                )
                data["learned_rules"] = list(data.get("learned_rules") or []) + [rule]
                try:
                    ops_bot_spec.write_bot_spec(data)
                except ValueError as exc:
                    return JSONResponse({"error": str(exc)}, status_code=400)
                ops_bot_spec.refresh_from_disk()
            return {"record": asdict(updated), "candidate_rule": rule}

    return await asyncio.to_thread(build)


@app.get("/api/ops/setup/roster")
async def ops_setup_roster():
    """Read-only roster view. Source of truth stays LV_SLACK_TEACHER_MAP
    env (v1 boundary) — no member pull, no CSV, not editable here."""
    teacher_map = _ops_teacher_map()
    return {
        "source": "LV_SLACK_TEACHER_MAP",
        "editable": False,
        "count": len(teacher_map),
        "teachers": [
            {
                "slack_user_id": user_id,
                "teacher_id": str(info.get("teacher_id") or ""),
                "display_name": str(info.get("display_name") or ""),
            }
            for user_id, info in sorted(teacher_map.items())
        ],
    }


@app.get("/api/ops/setup/suggestions")
async def ops_setup_suggestions():
    """Shadow suggester (spec §8): weekly would-have-matched counts of
    unmatched traffic against DISABLED packs. Suggestion only — enabling
    stays the admin's checklist + Save + corpus run. Payload carries pack
    names and counts, never record text."""

    def build() -> dict:
        from src.education import ops_suggest
        from src.education.ops_records import OpsRecordStore

        with OpsRecordStore() as store:
            records = store.recent_records_in_categories(
                ops_suggest.UNMATCHED_CATEGORIES,
                since_iso=ops_suggest.window_start_iso(),
            )
            suggestions = ops_suggest.shadow_suggestions(records)
        return {
            "window_days": ops_suggest.WINDOW_DAYS,
            "threshold": ops_suggest.SUGGESTION_THRESHOLD,
            "suggestions": suggestions,
        }

    return await asyncio.to_thread(build)


def _load_writable_bot_spec_data():
    """Disk bot-spec data for routes that RECORD into it (corpus runs,
    rule decisions). Returns (data, error_response): no file → the admin
    has not saved a setup yet; fallback → never write over a spec we
    could not compile (fail closed, spec §3.2)."""
    from src.education import ops_bot_spec

    current = ops_bot_spec.load_compiled_spec()
    if not current.exists:
        return None, JSONResponse(
            {
                "error": "No bot-spec yet — save your Bot Setup first; "
                "corpus results are recorded in the bot-spec."
            },
            status_code=409,
        )
    if current.fallback:
        return None, JSONResponse(
            {
                "error": "The bot-spec on disk failed to compile "
                f"({current.fallback}) — fix it via Save before recording "
                "corpus results."
            },
            status_code=409,
        )
    return dict(current.raw), None


@app.post("/api/ops/setup/corpus/run")
async def ops_setup_corpus_run():
    """Run the test corpus (pack samples + admin sentences) through the
    bot-spec's compiled rule set and RECORD the result (timestamp +
    result hash) — the recorded passing run is what the go-live toggle
    requires (spec §7). Deterministic: expectations are relative dates,
    so today's real date never changes pass/fail."""

    def build():
        from src.education import ops_bot_spec, ops_corpus

        data, error = _load_writable_bot_spec_data()
        if error is not None:
            return error
        spec = ops_bot_spec._compile_from_data(dict(data))
        result = ops_corpus.run_corpus(spec)
        corpus_block = dict(data.get("corpus") or {})
        corpus_block.setdefault("admin_sentences", [])
        corpus_block["last_run"] = result.last_run()
        data["corpus"] = corpus_block
        try:
            ops_bot_spec.write_bot_spec(data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        refreshed = ops_bot_spec.refresh_from_disk()
        payload = result.as_payload()
        payload["bot_spec"] = _ops_bot_spec_payload(refreshed)
        return payload

    return await asyncio.to_thread(build)


@app.post("/api/ops/setup/corpus/sentences")
async def ops_setup_corpus_add_sentence(request: Request):
    """Add an admin test sentence to the bot-spec corpus (spec §7).
    Clears the recorded run — new expectations mean the old result no
    longer describes this corpus, so go-live needs a fresh pass."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    text = str(body.get("text") or "").strip()
    expect = body.get("expect")
    if not text or not isinstance(expect, dict) or not str(expect.get("category") or "").strip():
        return JSONResponse(
            {"error": "text and expect.category are required."}, status_code=400
        )

    def build():
        from src.education import ops_bot_spec, ops_corpus

        data, error = _load_writable_bot_spec_data()
        if error is not None:
            return error
        spec = ops_bot_spec._compile_from_data(dict(data))
        unknown_keys = set(expect) - ops_corpus._KNOWN_EXPECT_KEYS
        if unknown_keys:
            return JSONResponse(
                {"error": f"Unknown expectation keys: {sorted(unknown_keys)}"},
                status_code=400,
            )
        category = str(expect["category"])
        known = set(spec.rule_set.category_ids()) | {"other"}
        if category not in known:
            return JSONResponse(
                {"error": f"Unknown expected category {category!r}."},
                status_code=400,
            )
        corpus_block = dict(data.get("corpus") or {})
        sentences = list(corpus_block.get("admin_sentences") or [])
        sentences.append({"text": text, "expect": dict(expect)})
        corpus_block["admin_sentences"] = sentences
        corpus_block["last_run"] = None
        data["corpus"] = corpus_block
        try:
            ops_bot_spec.write_bot_spec(data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        refreshed = ops_bot_spec.refresh_from_disk()
        return _ops_bot_spec_payload(refreshed)

    return await asyncio.to_thread(build)


@app.post("/api/ops/setup/rules/decide")
async def ops_setup_rule_decide(request: Request):
    """Candidate learned-rule promote ceremony (spec §4): approve is
    CORPUS-GATED — the corpus runs against a hypothetical compile with
    the candidate approved, and zero previously-passing samples may
    change routing (any failure → 409, nothing written). Reject just
    records the decision; rejected rules never compile."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    rule_id = str(body.get("rule_id") or "").strip()
    action = str(body.get("action") or "").strip()
    if not rule_id or action not in ("approve", "reject"):
        return JSONResponse(
            {"error": "rule_id and action ('approve' or 'reject') are required."},
            status_code=400,
        )

    def build():
        from src.education import ops_bot_spec, ops_corpus

        data, error = _load_writable_bot_spec_data()
        if error is not None:
            return error
        rules = [dict(r) for r in data.get("learned_rules") or []]
        target = next((r for r in rules if r.get("id") == rule_id), None)
        if target is None:
            return JSONResponse({"error": "Unknown rule."}, status_code=404)
        if target.get("status") != "candidate":
            return JSONResponse(
                {"error": "Only candidate rules can be approved or rejected."},
                status_code=409,
            )
        target["status"] = "approved" if action == "approve" else "rejected"
        target["decided_at"] = ops_bot_spec.utc_now_iso()
        data["learned_rules"] = rules

        run_payload = None
        if action == "approve":
            try:
                hypothetical = ops_bot_spec._compile_from_data(dict(data))
            except ops_bot_spec.PackLoadError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            result = ops_corpus.run_corpus(hypothetical)
            if not result.passed:
                failing = [
                    row.as_payload() for row in result.rows if not row.ok
                ]
                return JSONResponse(
                    {
                        "error": "Approving this rule breaks the test corpus "
                        f"({result.failed} of {result.total} sentences) — "
                        "nothing was changed.",
                        "rows": failing,
                        "run": result.last_run(),
                    },
                    status_code=409,
                )
            # The passing run INCLUDED the newly approved rule — record
            # it, keeping the go-live gate honest about the live rules.
            corpus_block = dict(data.get("corpus") or {})
            corpus_block.setdefault("admin_sentences", [])
            corpus_block["last_run"] = result.last_run()
            data["corpus"] = corpus_block
            run_payload = result.as_payload()

        try:
            ops_bot_spec.write_bot_spec(data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        refreshed = ops_bot_spec.refresh_from_disk()
        payload = _ops_bot_spec_payload(refreshed)
        payload["decided_rule"] = dict(target)
        if run_payload is not None:
            payload["corpus_run"] = run_payload
        return payload

    return await asyncio.to_thread(build)


async def _startup_slack_ops():
    """Start the Socket Mode ops assistant when configured; stay off cleanly
    when not. Guarded top to bottom — the ops assistant must never take the
    teacher's app down with it."""
    try:
        from src.education import ops_bot_spec

        # Install the bot-spec compile (v2). No file ⇒ exact v1 parity; a
        # malformed file fails closed to parity with a fallback reason.
        spec = ops_bot_spec.refresh_from_disk()

        from src.lingua_viva.slack_socket import (
            SlackOpsConfigurationError,
            SlackSocketClient,
            register_ops_client,
            require_ops_config,
        )

        try:
            config = require_ops_config()
        except SlackOpsConfigurationError:
            return  # unconfigured — the status route explains what is missing

        if spec.exists and not spec.live:
            # Go-live gate (spec §3.3): a bot-spec exists but has not passed
            # the corpus gate yet — the transport stays off. Applies ONLY
            # when a bot-spec exists; env-only setups keep v1 behavior.
            return

        from src.education.daily_file import DailyFileEngine
        from src.education.ops_records import OpsRecordStore
        from src.education.slack_ops_bot import SlackOpsBot

        store = OpsRecordStore()
        daily = DailyFileEngine(store, teacher_map=config.teacher_map)
        bot = SlackOpsBot(
            store=store,
            daily=daily,
            client=None,  # transport attached just below
            ops_channel=config.ops_channel,
            teacher_map=config.teacher_map,
        )
        client = SlackSocketClient(config, bot.on_envelope)
        bot.client = client
        register_ops_client(client)
        client.start()
        schedules = asyncio.create_task(
            bot.run_schedules(
                briefing_hhmm=spec.briefing_hhmm, eod_hhmm=spec.eod_hhmm
            )
        )
        _ops_runtime.update(
            {"store": store, "bot": bot, "client": client, "schedules": schedules}
        )
    except Exception:
        pass


async def _shutdown_slack_ops():
    try:
        from src.lingua_viva.slack_socket import register_ops_client

        schedules = _ops_runtime.pop("schedules", None)
        if schedules is not None:
            schedules.cancel()
            try:
                await schedules
            except (asyncio.CancelledError, Exception):
                pass
        client = _ops_runtime.pop("client", None)
        if client is not None:
            await client.stop()
        register_ops_client(None)
        store = _ops_runtime.pop("store", None)
        if store is not None:
            store.close()
        _ops_runtime.clear()
    except Exception:
        pass


# NOTE: must target app.router, not app — Starlette 1.0 removed
# add_event_handler from the application object (LV-5, v0.2.12).
# app.router.add_event_handler exists on both pre- and post-1.0 Starlette.
app.router.add_event_handler("startup", _startup_slack_ops)
app.router.add_event_handler("shutdown", _shutdown_slack_ops)


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
    # Default moved from LV_ROOT (the updater-owned bundle — erased on every
    # app update, mutates the signed macOS bundle) to lv_home()
    # (SPEC_ONE_BUTTON_UPDATE_2026-07-27 P0). Env override unchanged.
    from src.lingua_viva.config import lv_home

    return Path(os.environ.get("LV_REVISION_LOG_PATH", str(lv_home() / "dev" / "lv_revision_log.ndjson")))


def _legacy_revision_log_path() -> Path:
    """Pre-P0 reflection-log location inside the app bundle (read-only now)."""
    return LV_ROOT / "dev" / "lv_revision_log.ndjson"


def _migrate_legacy_revision_log() -> int:
    """One-time rescue of teacher reflections written inside the app bundle.

    Desktop builds 0.2.9/0.2.10 appended private teacher reflections to
    ``LV_ROOT/dev/lv_revision_log.ndjson`` — updater-owned territory, erased
    on every app update (SPEC_ONE_BUTTON_UPDATE_2026-07-27 §1/P0). Append
    those entries once to the new lv_home() location. Idempotent two ways:
    a sentinel file short-circuits repeat runs, and entries are deduped by
    ``revision_id``, so a crash between append and sentinel-write cannot
    duplicate entries on retry. Only private teacher reflections migrate —
    in a source checkout the legacy path is the *committed* dev audit
    trail, which is repo history, not teacher state. The legacy path is
    never written. Returns the number of migrated entries.
    """
    new_path = _revision_log_path()
    sentinel = new_path.with_name(new_path.name + ".migrated")
    if sentinel.exists():
        return 0
    legacy = _legacy_revision_log_path()

    def _finish(count: int) -> int:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(
            json.dumps({
                "migrated_entries": count,
                "migrated_at": datetime.now(timezone.utc).isoformat(),
                "legacy_path": str(legacy),
            }) + "\n",
            encoding="utf-8",
        )
        return count

    try:
        same_file = legacy.exists() and new_path.exists() and legacy.resolve() == new_path.resolve()
    except OSError:
        same_file = False
    if same_file or not legacy.exists():
        return _finish(0)

    try:
        legacy_lines = [line for line in legacy.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError):
        # Unreadable this launch — leave the sentinel unwritten so the next
        # launch retries; this is the only rescue window for those entries.
        return 0

    def _dedupe_key(entry: dict) -> tuple[str, str]:
        # revision_id ALONE is not enough: pre-uuid builds stamped
        # int(time.time()) — two distinct reflections in the same second
        # shared an ID, and the second was silently dropped (review
        # finding 2). Key on (revision_id, content-hash) so distinct notes
        # both survive while true double-submits still dedupe.
        canonical = json.dumps(entry, sort_keys=True, ensure_ascii=True)
        return (
            str(entry.get("revision_id")),
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    existing_keys: set[tuple[str, str]] = set()
    try:
        for line in new_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                existing_keys.add(_dedupe_key(parsed))
    except OSError:
        pass

    migrated = 0
    new_path.parent.mkdir(parents=True, exist_ok=True)
    with new_path.open("a", encoding="utf-8") as handle:
        for line in legacy_lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            is_teacher_reflection = entry.get("private") is True or (
                entry.get("artifact_id") == "lv-private-teacher-reflection"
            )
            if not is_teacher_reflection:
                continue
            key = _dedupe_key(entry)
            if key in existing_keys:
                continue
            existing_keys.add(key)  # dedupe within the legacy file too
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
            migrated += 1
    return _finish(migrated)


async def _startup_state_migrations():
    """P0 reflection-log rescue + first-launch template reconcile.

    Runs identically for desktop (bootstrap spawns this server), `lv serve`,
    and source installs (SPEC_ONE_BUTTON_UPDATE_2026-07-27 Phase 2). Each
    step is independently guarded — a failed migration or reconcile must
    never take the teacher's app down with it.
    """
    try:
        await asyncio.to_thread(_migrate_legacy_revision_log)
    except Exception:
        pass
    try:
        from src.lingua_viva.reconcile import reconcile_on_startup

        await asyncio.to_thread(reconcile_on_startup)
    except Exception:
        pass


# Registered via app.router.add_event_handler rather than the deprecated
# @app.on_event decorator or app.add_event_handler (removed in Starlette 1.0
# — calling it on the app object crashes the backend at import; LV-5).
app.router.add_event_handler("startup", _startup_state_migrations)


async def _startup_filemap_autoscan():
    """Populate the file map on first launch without the teacher asking.

    Gap 2 (SPEC_LV_REMAINING_GAPS_2026-07-29). Runs on a daemon thread and is
    never awaited: scanning a home folder takes seconds to minutes, and the
    teacher's app must be usable immediately. The scan itself is guarded
    (LV_AGENT / pytest) and never raises — see
    filemap.auto_scan_disabled_reason().
    """
    import threading

    def _scan() -> None:
        try:
            from src.lingua_viva.filemap import auto_scan_on_startup

            auto_scan_on_startup(max_depth=4)
        except Exception:
            pass  # a failed scan must never take the app down

    from src.lingua_viva.filemap import AUTO_SCAN_THREAD_NAME, auto_scan_disabled_reason

    if auto_scan_disabled_reason():
        return
    threading.Thread(target=_scan, daemon=True, name=AUTO_SCAN_THREAD_NAME).start()


app.router.add_event_handler("startup", _startup_filemap_autoscan)


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


def _filemap_error_code(exc: Exception) -> str:
    """Stable machine-readable code for filemap error responses.

    Derived from the exception class/errno only — the UI maps codes to
    teacher language instead of string-matching English error text.
    """
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EPERM):
            return "permission_denied"
        if exc.errno in (errno.ENOENT, errno.ENOTDIR):
            return "not_found"
    return "invalid_path"


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
        return JSONResponse(
            {"error": str(exc), "code": _filemap_error_code(exc)},
            status_code=400,
        )
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

    def _load() -> dict:
        payload = to_api(load_map())
        # Stat-only death-path signal: a scanned root renamed/removed after
        # scanning should not keep rendering as connected (SPEC_LV_FILE_MAP_FINAL §B).
        for root in payload.get("roots", []):
            root["exists"] = os.path.isdir(os.path.expanduser(root["path"]))
        return payload

    return await asyncio.to_thread(_load)


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
        return JSONResponse(
            {"error": str(exc), "code": _filemap_error_code(exc)},
            status_code=400,
        )
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
        return JSONResponse(
            {"error": str(exc), "code": _filemap_error_code(exc)},
            status_code=400,
        )
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
        return JSONResponse(
            {"error": str(exc), "code": _filemap_error_code(exc)},
            status_code=400,
        )
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

    from src.lingua_viva.governance import aron_status

    summary = await asyncio.to_thread(privacy_summary)
    events = await asyncio.to_thread(read_privacy_events, 25)
    # Gap 3: ARON is a real, always-on mechanism; the Privacy view should be
    # able to say so rather than leaving S-XXXX codes unexplained.
    aron = await asyncio.to_thread(aron_status)
    return {**summary, "events": [asdict(event) for event in events], "aron": aron}


RIME_TTS_URL = "https://users.rime.ai/v1/rime-tts"
RIME_MAX_CHARS = 12_000


def _rime_api_key() -> str:
    return os.environ.get("RIME_API_KEY", "").strip()


def _active_student_names() -> list[str]:
    """Names to check TTS text against. Empty on failure is NOT safe here, so
    the caller treats an unreadable roster as a reason to stay local."""
    def collect(store):
        return [str(lens.get("display_name") or "") for lens in store.list_lenses()]

    return _with_student_store(collect)


def _request_rime_audio(text: str, speaker: str, model_id: str, key: str) -> bytes:
    import json as _json
    import re as _re
    import urllib.request as _urlreq

    body = _json.dumps({
        "text": _re.sub(r"[#*_`>\[\]]", "", text),
        "speaker": speaker,
        "modelId": model_id,
    }).encode("utf-8")
    outgoing = _urlreq.Request(
        RIME_TTS_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        },
        method="POST",
    )
    with _urlreq.urlopen(outgoing, timeout=20) as response:
        return response.read()


@app.get("/api/students/growth")
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


@app.post("/api/voice/tts")
async def voice_tts(request: Request):
    """Read text aloud via Rime, but only after proving it names no child.

    Gap 5 (SPEC_LV_REMAINING_GAPS_2026-07-29). Rime is an external service, so
    this is an egress path and gets the same treatment as any other:
    check_publication_safety() runs BEFORE the key is even read, and a
    student name means the request never leaves this machine.

    Every non-200 here is a signal to the caller to use the browser's own
    voice, which speaks Italian (contract v52). Falling back is not a
    degraded experience — it is the private one.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    # A body of `"notjson"` parses as a valid JSON *string*, so the except
    # above never fires and .get() then raises AttributeError -> 500. The
    # sibling credential routes already guard this; this one did not.
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Expected a JSON object."}, status_code=400)
    text = str(payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    if len(text) > RIME_MAX_CHARS:
        return JSONResponse(
            {"error": f"Text must be under {RIME_MAX_CHARS:,} characters."},
            status_code=400,
        )

    from src.lingua_viva.governance import check_publication_safety
    from src.lingua_viva.privacy_log import log_event

    def gate() -> dict:
        names = _active_student_names()
        return check_publication_safety({"text": text}, student_names=names)

    try:
        safety = await asyncio.to_thread(gate)
    except Exception:
        # The roster could not be read, so we cannot prove the text is free of
        # student names. Fail closed: stay local.
        return JSONResponse(
            {
                "error": "Could not check this text for student information — reading it aloud on this computer instead.",
                "fallback": "local",
            },
            status_code=403,
        )

    if safety["blocked"]:
        await asyncio.to_thread(log_event, "voice_kept_local_student_data")
        return JSONResponse(
            {
                "error": "This text mentions a student, so it is read aloud on this computer instead of being sent to the speech service.",
                "fallback": "local",
                "violations": safety["violations"],
            },
            status_code=403,
        )

    key = _rime_api_key()
    if not key:
        return JSONResponse(
            {"error": "Rime is not set up on this computer.", "fallback": "local"},
            status_code=503,
        )

    speaker = str(payload.get("speaker") or os.environ.get("RIME_SPEAKER", "astra"))
    model_id = str(os.environ.get("RIME_MODEL_ID", "mistv3"))
    try:
        audio = await asyncio.to_thread(_request_rime_audio, text, speaker, model_id, key)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"error": f"The speech service could not be reached ({type(exc).__name__}).", "fallback": "local"},
            status_code=502,
        )

    await asyncio.to_thread(log_event, "voice_sent_to_external_tts")
    return Response(content=audio, media_type="audio/wav")


@app.get("/api/daily/briefing")
async def daily_briefing(days: int = 7):
    """Morning-briefing widgets for the Daily view.

    Slice 6 (SPEC_NATIVE_WORKSTATION_SURFACES_2026-07-28 §Lingua Viva item 2):
    Daily shows the Slack ops schedule; it should also answer "who have I not
    observed, what support decisions are waiting, what have I not confirmed?"

    Every student is referenced anonymously. Daily is read in staff rooms and
    projected in meetings, and the same spec's LV constraint applies here as
    to the Action Queue.
    """

    def build() -> dict:
        from src.lingua_viva.activity import pending_items
        from src.lingua_viva.brief import BriefService
        from src.lingua_viva.governance import aron_ref

        window = max(1, min(int(days or 7), 90))
        service = BriefService(
            student_store_factory=_student_store_for_brief,
            revision_log_path=_revision_log_path(),
        )
        try:
            from src.lingua_viva.adaptive import pending_recommendations

            with service.student_store_factory() as store:
                unobserved = service._unobserved(store, window)
                rti_pending = service._rti_pending(store)
                tier_suggestions = pending_recommendations(store)
            readable = True
        except Exception as exc:  # noqa: BLE001
            return {
                "readable": False,
                "reason": type(exc).__name__,
                "window_days": window,
                "widgets": [],
                "note": (
                    "The student record could not be opened. This is not the same "
                    "as having nothing waiting."
                ),
            }

        confirmations = [item for item in pending_items() if not item.get("unknown")]

        widgets = [
            {
                "id": "unobserved",
                "label": f"Not observed in {window} days",
                "count": len(unobserved),
                "students": [aron_ref(s["student_id"]) for s in unobserved],
                "detail": (
                    "Worth a note next time you see them."
                    if unobserved
                    else "Everyone has a recent observation."
                ),
                "status": "attention" if unobserved else "ok",
            },
            {
                "id": "rti_pending",
                "label": "Support decisions to look at",
                "count": len(rti_pending),
                "students": [aron_ref(s["student_id"]) for s in rti_pending],
                "detail": (
                    "The system flags; you decide."
                    if rti_pending
                    else "No support tiers are flagged."
                ),
                "status": "attention" if rti_pending else "ok",
            },
            {
                # Gap 6: recommendations surface here as pending items. They
                # are suggestions — the teacher confirms, nothing auto-applies.
                "id": "tier_recommendations",
                "label": "Support-tier suggestions to review",
                "count": len(tier_suggestions),
                "students": [row["reference"] for row in tier_suggestions],
                "detail": (
                    "Based on recorded level changes. Lingua Viva suggests; you decide."
                    if tier_suggestions
                    else "No tier suggestions right now."
                ),
                "status": "attention" if tier_suggestions else "ok",
            },
            {
                "id": "confirmations",
                "label": "Suggestions awaiting your confirmation",
                "count": sum(item.get("count") or 0 for item in confirmations),
                "students": [item["reference"] for item in confirmations if item.get("reference")],
                "detail": (
                    "Kept out of parent reports until you confirm them."
                    if confirmations
                    else "Nothing is waiting for confirmation."
                ),
                "status": "attention" if confirmations else "ok",
            },
        ]

        return {
            "readable": readable,
            "window_days": window,
            "widgets": widgets,
            "needs_attention": sum(1 for w in widgets if w["status"] == "attention"),
            "note": (
                "Students are shown by an anonymous reference so this view is safe "
                "to read in a staff room."
            ),
        }

    return await asyncio.to_thread(build)


@app.get("/api/actions/registry")
async def actions_registry():
    """The teacher actions LV can run, each with its governance preview.

    Slice 2 (SPEC_ACTION_DISPATCHER_FORMS_2026-07-28 §Lingua Viva item 3):
    before an action that touches student data, a teacher should be able to
    see what it reads and whether anything leaves the machine.
    """
    from src.lingua_viva.actions import registry

    return await asyncio.to_thread(registry)


@app.get("/api/actions/history")
async def actions_history(limit: int = 40):
    """Action Queue — what was done on this computer, and what is pending.

    Slice 3 (SPEC_NATIVE_WORKSTATION_SURFACES_2026-07-28 §Lingua Viva item 1).
    Built from the existing trace and privacy logs so it has real history from
    the moment it ships, rather than being empty until a new store fills up.
    """
    from src.lingua_viva.activity import activity_feed

    bounded = max(1, min(int(limit or 40), 200))
    return await asyncio.to_thread(activity_feed, bounded)


@app.get("/api/sources/status")
async def sources_status():
    """One registry row per source: status, count, and what is excluded.

    Slice 1 (SPEC_UNIFIED_SOURCES_WORKBENCH_2026-07-28 §Lingua Viva). Each
    source resolves independently and a failure degrades that row only — a
    Drive outage must not blank the local-folder count, because the whole
    point of the registry is to say what Lingua Viva can currently see.
    """

    def build() -> dict:
        sources = []

        # Local folders
        try:
            from src.lingua_viva.filemap import load_map, summarize

            summary = summarize(load_map())
            zones = summary.get("student_zones_excluded", 0)
            sources.append({
                "id": "local",
                "label": "Folders on this computer",
                "status": "connected" if summary.get("configured") else "not_configured",
                "count": summary.get("total_directories", 0),
                "count_label": "folders indexed",
                "detail": (
                    f"{summary.get('root_count', 0)} folder(s) scanned."
                    if summary.get("configured")
                    else "No folders added yet."
                ),
                "student_zones_excluded": zones,
                "setup_view": "sources",
            })
        except Exception as exc:  # noqa: BLE001
            sources.append({
                "id": "local", "label": "Folders on this computer",
                "status": "unavailable", "count": None,
                "detail": f"Could not read the file map ({type(exc).__name__}).",
                "student_zones_excluded": None, "setup_view": "sources",
            })

        # Google Drive
        try:
            from src.lingua_viva.google_drive_integration import list_connected_folders, status

            drive = status()
            folders = list_connected_folders()
            sources.append({
                "id": "drive",
                "label": "Google Drive",
                "status": "connected" if drive.get("configured") else "not_configured",
                "count": len(folders),
                "count_label": "folders connected",
                "detail": (
                    drive.get("account_email") or "Signed in."
                    if drive.get("configured")
                    else drive.get("setup_message") or "Not set up on this machine."
                ),
                "student_zones_excluded": None,
                "setup_view": "sources",
            })
        except Exception as exc:  # noqa: BLE001
            sources.append({
                "id": "drive", "label": "Google Drive", "status": "unavailable",
                "count": None, "detail": f"Could not read Drive status ({type(exc).__name__}).",
                "student_zones_excluded": None, "setup_view": "sources",
            })

        # Slack ops assistant
        try:
            from src.lingua_viva.slack_socket import ops_status

            ops = ops_status()
            sources.append({
                "id": "slack",
                "label": "Slack",
                "status": "connected" if ops.get("configured") else "not_configured",
                "count": ops.get("teacher_count", 0),
                "count_label": "teachers in the roster",
                "detail": (
                    "Daily briefing assistant is set up."
                    if ops.get("configured")
                    else "Set up in Settings -> Integrations."
                ),
                "student_zones_excluded": None,
                "setup_view": "settings",
            })
        except Exception as exc:  # noqa: BLE001
            sources.append({
                "id": "slack", "label": "Slack", "status": "unavailable",
                "count": None, "detail": f"Could not read Slack status ({type(exc).__name__}).",
                "student_zones_excluded": None, "setup_view": "settings",
            })

        try:
            from src.lingua_viva.sources import ledger as source_ledger

            if source_ledger.is_initialized():
                ledger_counts = source_ledger.counts_by_type()
                for source in sources:
                    if source["id"] in ledger_counts and source.get("status") != "unavailable":
                        source["count"] = ledger_counts[source["id"]]
                        source["count_label"] = "ledger record(s)"
                        source["ledger_backed"] = True
        except Exception:
            pass

        connected = [s for s in sources if s["status"] == "connected"]
        excluded = sum(s["student_zones_excluded"] or 0 for s in sources)
        return {
            "sources": sources,
            "connected_count": len(connected),
            "total_count": len(sources),
            "student_zones_excluded": excluded,
            "student_zone_note": (
                "Folders that look like student records are found during a scan and "
                "left out of everything Lingua Viva reads."
            ),
        }

    return await asyncio.to_thread(build)


@app.get("/api/sources/records")
async def source_records(type: str | None = None, limit: int = 25, q: str | None = None):
    from src.lingua_viva.sources.ledger import read_records

    bounded = max(1, min(int(limit or 25), 200))
    source_type = (type or "").strip() or None
    if source_type and source_type not in {"local", "drive", "slack"}:
        return JSONResponse({"error": "type must be local, drive, or slack"}, status_code=400)
    records = await asyncio.to_thread(read_records, source_type, bounded, q)
    return {"records": records, "count": len(records)}


@app.get("/api/sources/observations")
async def source_observations(source_record_id: str | None = None, limit: int = 25):
    from src.lingua_viva.sources.ledger import read_observations

    bounded = max(1, min(int(limit or 25), 200))
    observations = await asyncio.to_thread(read_observations, source_record_id, bounded)
    return {"observations": observations, "count": len(observations)}


@app.post("/api/action-plans/preview")
async def action_plan_preview(payload: dict):
    from src.lingua_viva.action_plans.schema import (
        ActionPlan,
        Approval,
        GroundingSummary,
        PlanPolicy,
        PlannedAction,
    )
    from src.lingua_viva.action_plans.store import compute_action_plan_id, now_iso, upsert_plan
    from src.lingua_viva.actions import preview_for

    action_id = str(payload.get("action_id") or "").strip()
    preview = preview_for(action_id)
    if not preview:
        return JSONResponse({"error": "Unknown action_id."}, status_code=404)
    source_record_ids = [str(item) for item in (payload.get("source_record_ids") or []) if item]
    grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
    leaves_machine = bool(preview.get("leaves_machine"))
    plan = ActionPlan(
        action_plan_id=compute_action_plan_id(),
        created_at=now_iso(),
        session_id=str(payload.get("session_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        grounding_id=str(payload.get("grounding_id") or grounding.get("grounding_id") or ""),
        intent=str(payload.get("intent") or ""),
        user_goal=str(payload.get("user_goal") or preview.get("label") or ""),
        source_record_ids=source_record_ids,
        grounding_summary=GroundingSummary(
            tier_used=str(grounding.get("tier_used") or "none"),
            gir_score=float((grounding.get("gir") or {}).get("score", 1.0)) if isinstance(grounding.get("gir"), dict) else 1.0,
            external_called=False,
        ),
        actions=[PlannedAction(
            action_id=action_id,
            name=str(preview.get("label") or action_id),
            params=dict(payload.get("params") or {}),
            param_sources={"input": source_record_ids} if source_record_ids else {},
            risk_level="medium" if leaves_machine else "low",
            side_effects=["external_upload"] if leaves_machine else [],
            allows_external=leaves_machine,
            requires_approval=True,
            expected_output="drive_export" if leaves_machine else "none",
        )],
        approval=Approval(status="pending"),
        policy=PlanPolicy(
            egress_hosts=["drive.google.com"] if leaves_machine else [],
            protect_forced_local=not leaves_machine,
            can_execute=False,
            reason="awaiting_approval",
        ),
    )
    stored = await asyncio.to_thread(upsert_plan, plan)
    return {"plan": stored.as_dict()}


@app.post("/api/action-plans/approve")
async def action_plan_approve(payload: dict):
    from src.lingua_viva.action_plans.store import now_iso, read_plan, upsert_plan

    plan_id = str(payload.get("action_plan_id") or "").strip()
    plan = await asyncio.to_thread(read_plan, plan_id)
    if not plan:
        return JSONResponse({"error": "Action plan not found."}, status_code=404)
    plan.approval.status = "approved"
    plan.approval.approved_by = str(payload.get("approved_by") or "operator")
    plan.approval.approved_at = now_iso()
    plan.policy.can_execute = True
    plan.policy.reason = "ready"
    await asyncio.to_thread(upsert_plan, plan)
    return {"plan": plan.as_dict()}


@app.post("/api/action-plans/reject")
async def action_plan_reject(payload: dict):
    from src.lingua_viva.action_plans.store import read_plan, upsert_plan

    plan_id = str(payload.get("action_plan_id") or "").strip()
    plan = await asyncio.to_thread(read_plan, plan_id)
    if not plan:
        return JSONResponse({"error": "Action plan not found."}, status_code=404)
    plan.approval.status = "rejected"
    plan.approval.rejected_reason = str(payload.get("reason") or "")
    plan.policy.can_execute = False
    plan.policy.reason = "blocked"
    await asyncio.to_thread(upsert_plan, plan)
    return {"plan": plan.as_dict()}


@app.get("/api/action-plans/history")
async def action_plans_history(status: str | None = None, limit: int = 50):
    from src.lingua_viva.action_plans.store import read_plans

    bounded = max(1, min(int(limit or 50), 200))
    plans = await asyncio.to_thread(read_plans, status, bounded)
    return {"plans": plans, "count": len(plans)}


# --- Governance control plane (Slice 4) ------------------------------------
# SPEC_GOVERNANCE_CONTROL_PLANE_2026-07-28 §Lingua Viva. Trust Status answers
# the five questions a school administrator asks; the observation export is
# the compliance artefact they can be handed.
# ---------------------------------------------------------------------------


@app.get("/api/governance/trust")
async def governance_trust():
    """Trust Status — five plain-language answers from local artefacts."""
    from src.lingua_viva.governance import trust_status

    return await asyncio.to_thread(trust_status)


@app.post("/api/governance/observation-export")
async def governance_observation_export(payload: dict):
    """Signed observation pack for one student.

    Refuses rather than exports when the publication-safety check finds a
    violation — an export that silently drops an offending field would leave
    the teacher believing the policy passed.
    """
    student_id = str(payload.get("student_id") or "").strip()
    if not student_id:
        return JSONResponse({"error": "student_id is required"}, status_code=400)

    def build():
        from src.education.student_lens import LensNotFoundError
        from src.lingua_viva.governance import (
            build_observation_pack,
            check_publication_safety,
        )

        def do(store):
            names = [
                str(lens.get("display_name") or "")
                for lens in store.list_lenses()
            ]
            try:
                pack = build_observation_pack(student_id, store=store)
            except LensNotFoundError:
                return {"__error__": "No student with that id on this computer.", "__status__": 404}
            safety = check_publication_safety(pack, student_names=names)
            if safety["blocked"]:
                return {
                    "__error__": safety["violations"][0]["message"],
                    "__status__": 422,
                    "__safety__": safety,
                }
            try:
                from src.lingua_viva.audit_receipts.builder import build_receipt
                from src.lingua_viva.deliverables.schema import DeliverableLocation, DeliverableRecord
                from src.lingua_viva.deliverables.store import upsert_deliverable

                receipt = build_receipt(scope="observation_export", session_id=broadcaster.session_id or "")
                deliverable = DeliverableRecord(
                    deliverable_id=f"DLV-{receipt.audit_receipt_id}",
                    session_id=broadcaster.session_id or "",
                    type="observation_export",
                    title="Observation export",
                    status="created",
                    location=DeliverableLocation(kind="download"),
                    summary="Sealed observation export; student identifiers remain inside the sealed pack only.",
                )
                upsert_deliverable(deliverable)
                return {"pack": pack, "publication_safety": safety, "audit_receipt": receipt.as_dict(), "deliverable": deliverable.as_dict()}
            except Exception:
                return {"pack": pack, "publication_safety": safety}

        return _with_student_store(do)

    result = await asyncio.to_thread(build)
    if "__error__" in result:
        body = {"error": result["__error__"]}
        if "__safety__" in result:
            body["publication_safety"] = result["__safety__"]
        return JSONResponse(body, status_code=result["__status__"])
    return result


@app.get("/api/deliverables")
async def deliverables(limit: int = 50, session_id: str = "", action_plan_id: str = ""):
    from src.lingua_viva.deliverables.store import read_deliverables

    bounded = max(1, min(int(limit or 50), 200))
    records = await asyncio.to_thread(read_deliverables, session_id, action_plan_id, bounded)
    return {"deliverables": records, "count": len(records)}


@app.post("/api/audit-receipts/export")
async def audit_receipts_export(payload: dict):
    from src.lingua_viva.audit_receipts.builder import build_receipt

    source_record_ids = payload.get("source_record_ids") if isinstance(payload.get("source_record_ids"), list) else []
    receipt = await asyncio.to_thread(
        build_receipt,
        scope=str(payload.get("scope") or "query"),
        session_id=str(payload.get("session_id") or broadcaster.session_id or ""),
        trace_id=str(payload.get("trace_id") or ""),
        action_plan_id=str(payload.get("action_plan_id") or ""),
        deliverable_id=str(payload.get("deliverable_id") or ""),
        grounding_id=str(payload.get("grounding_id") or ""),
        source_record_ids=[str(item) for item in source_record_ids],
        export_format=str(payload.get("format") or "json"),
    )
    return {"receipt": receipt.as_dict()}


@app.post("/api/governance/verify-pack")
async def governance_verify_pack(payload: dict):
    """Check a pack's seal. Lets an administrator confirm a file they were
    sent is unchanged, rather than taking the seal on faith."""
    from src.lingua_viva.governance import SIGNATURE_MEANING, verify_pack

    pack = payload.get("pack")
    if not isinstance(pack, dict):
        return JSONResponse({"error": "Expected a pack object."}, status_code=400)
    valid = await asyncio.to_thread(verify_pack, pack)
    return {
        "valid": valid,
        "means": SIGNATURE_MEANING,
        "detail": (
            "The pack is unchanged since this computer created it."
            if valid
            else "The seal does not match. This pack was changed, or it came from a different computer."
        ),
    }


@app.get("/api/voice/probe")
async def voice_probe():
    import shutil

    try:
        import faster_whisper  # noqa: F401

        stt_available = True
    except Exception:
        stt_available = False
    return {
        "stt": {
            "available": bool(stt_available and shutil.which("ffmpeg")),
            "provider": "faster-whisper",
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "local_only": True,
        },
        "tts": {
            "rime_configured": bool(_rime_api_key()),
            "student_data_gate": True,
            "local_fallback": True,
        },
    }


@app.post("/api/voice/stt")
async def voice_stt(request: Request):
    audio = await request.body()
    if not audio:
        return JSONResponse({"error": "audio body required"}, status_code=400)
    try:
        from src.lingua_viva.voice_stt import get_stt_provider

        provider = get_stt_provider()
        transcript = await asyncio.to_thread(provider.transcribe, audio)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "available": False}, status_code=503)
    except ModuleNotFoundError:
        return JSONResponse({"error": "faster-whisper is not installed.", "available": False}, status_code=503)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Could not transcribe audio ({type(exc).__name__})."}, status_code=422)
    return {"transcript": transcript, "provider": "faster-whisper", "local_only": True}


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
        return JSONResponse(
            {"error": str(exc), "code": _filemap_error_code(exc)},
            status_code=400,
        )
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
        from src.lingua_viva.google_drive_integration import import_dir as drive_import_dir

        # Hermeticity seam (same pattern as LV_SANITIZER_DATA_DIR / LV_OPS_*):
        # without this override, the demo-file fallback below writes into the
        # operator's REAL ~/.lingua-viva/imports/ when the suite runs, because
        # conftest deliberately doesn't force LV_CONFIG_HOME.
        local_imports = (
            Path(os.environ["LV_LOCAL_IMPORTS_DIR"]).expanduser()
            if os.environ.get("LV_LOCAL_IMPORTS_DIR")
            else lv_home() / "imports"
        )
        seen_paths = {s["file_path"] for s in sources}
        scan_dirs = [
            (local_imports, "local_import"),
            (drive_import_dir(), "google_drive"),
        ]
        for directory, source_type in scan_dirs:
            if not directory.exists():
                continue
            for p in sorted(directory.glob("*")):
                if p.is_file() and p.suffix.lower() in (".txt", ".md", ".pdf"):
                    path_str = str(p)
                    if path_str in seen_paths:
                        continue
                    seen_paths.add(path_str)
                    sources.append({
                        "file_path": path_str,
                        "display_name": p.name,
                        "source_type": source_type,
                        "student_id": None,
                    })

        if not sources:
            demo_path = local_imports / "demo_observation.txt"
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
        result = {
            "subject_line": _strip_parent_output(draft.subject_line, names),
            "body": _strip_parent_output(body, names),
            "home_activities": [_strip_parent_output(item, names) for item in draft.home_activities],
            "review_label": "Review before sending. No AI attribution in final message.",
            "source_citation": "Source: Manuale v1 and local teacher observations.",
        }

        # Gap 1 (SPEC_LV_REMAINING_GAPS_2026-07-29): the same gate the
        # observation export uses, run on the POST-strip text — the words that
        # actually reach the teacher's screen.
        #
        # _strip_parent_output() is best-effort cleanup, not a gate: it does
        # case-sensitive exact replacement, so "Marco" is removed while
        # "marco" or a possessive survives. check_publication_safety()
        # lowercases before matching, so it catches what the stripper missed.
        # Both run — the stripper still fixes what it can, this reports what
        # it could not.
        #
        # Flag, never block. A draft the teacher cannot see is a draft they
        # cannot fix, and the failure mode we care about is a name reaching a
        # parent — which only happens after the teacher presses send.
        from src.lingua_viva.governance import check_publication_safety

        safety = check_publication_safety(
            {
                "subject_line": result["subject_line"],
                "body": result["body"],
                "home_activities": result["home_activities"],
            },
            student_names=names,
        )
        result["publication_safety"] = safety
        if safety["blocked"]:
            result["safety_warnings"] = safety["violations"]
            result["review_required"] = True
        return result

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
        # uuid4, not int(time.time()): two reflections saved within the same
        # second shared a revision_id, and the P0 migration dedupes on it —
        # the second note would be silently dropped (review finding 2).
        "revision_id": f"teacher-reflection-{uuid.uuid4().hex}",
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


@app.get("/api/updates/pending")
async def updates_pending():
    """Parked template updates (SPEC_ONE_BUTTON_UPDATE_2026-07-27 Phase 3).

    Each entry is a shipped template the teacher customized whose new
    version is staged, waiting for a Keep-mine / Take-new decision."""
    from src.lingua_viva.reconcile import downgrade_detected, list_pending

    def build():
        return {
            "pending": list_pending(),
            "downgrade": downgrade_detected(),
            "message": "Your customized versions were preserved.",
        }

    return await asyncio.to_thread(build)


@app.get("/api/updates/diff")
async def updates_diff(path: str):
    from src.lingua_viva.reconcile import pending_diff

    diff = await asyncio.to_thread(pending_diff, path)
    if diff is None:
        return JSONResponse({"error": "No pending update for this path."}, status_code=404)
    return {"path": path, "diff": diff}


@app.post("/api/updates/resolve")
async def updates_resolve(payload: dict):
    """Resolve one parked update: keep_mine or take_new. Take-new archives
    the teacher's version first — nothing is ever destroyed."""
    from src.lingua_viva.reconcile import resolve_pending

    rel = str(payload.get("path") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not rel:
        return JSONResponse({"error": "path is required"}, status_code=400)
    result = await asyncio.to_thread(resolve_pending, rel, action)
    if result.get("status") != "resolved":
        return JSONResponse({"error": result.get("error", "could not resolve")}, status_code=400)
    return result


# Gap 4 (SPEC_LV_REMAINING_GAPS_2026-07-29): these three were honest
# "deferred" stubs — three nav items that did nothing. Each now returns real
# counts from data that already existed. Simple on purpose: a coordinator can
# act on "4 students have no observation this week"; they cannot act on a
# trend line drawn through six points.


@app.get("/api/admin/evidence")
async def admin_evidence(window_days: int = 7):
    """Observation coverage per student (ARON) and per domain."""
    from src.lingua_viva.admin_metrics import evidence_metrics

    window = max(1, min(int(window_days or 7), 90))
    return await asyncio.to_thread(evidence_metrics, window)


@app.get("/api/admin/capacity")
async def admin_capacity(weeks: int = 4):
    """Recorded activity per week. Explicitly NOT a staffing model."""
    from src.lingua_viva.admin_metrics import capacity_metrics

    span = max(1, min(int(weeks or 4), 52))
    return await asyncio.to_thread(capacity_metrics, span)


@app.get("/api/admin/trends")
async def admin_trends(min_cohort: int = 1):
    """Support-tier distribution, withheld below a minimum cohort size."""
    from src.lingua_viva.admin_metrics import trends_metrics

    floor = max(1, min(int(min_cohort or 1), 100))
    return await asyncio.to_thread(trends_metrics, floor)


@app.get("/api/ontology/domains")
async def ontology_domains():
    """List all ontology domains with their node counts (BLT-009 knowledge browser)."""
    try:
        from ontology.engine import OntologyEngine
        engine = OntologyEngine()
        domains = []
        for domain_name, node_ids in sorted(engine.domains.items()):
            domains.append({
                "domain": domain_name,
                "node_count": len(node_ids),
                "nodes": [
                    {"id": n.id, "name": n.name}
                    for nid in node_ids
                    if (n := engine.get_node(nid)) is not None
                ],
            })
        return {"domains": domains, "total_domains": len(domains)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
    """Reports .mc_session status — permanently inactive in this app; only the archived MC CLI
    (archive/mc-engine/mc_cli.py, excluded from the packaged build) ever creates that file.
    See dev/specs/SPEC_LV_SESSION_ROUTE_RECLASSIFY_2026-07-23.md."""
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


@app.post("/api/google-drive/auth/start")
async def google_drive_auth_start():
    """Begin the in-app Google sign-in loopback flow
    (SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A1). Opens the system
    browser backend-side; the UI polls /api/google-drive/status until
    `configured` flips. `auth_url` is returned for a fallback link when
    the browser did not open."""
    from src.lingua_viva.google_drive_integration import DriveConfigError
    from src.lingua_viva.google_drive_oauth import start_signin

    try:
        return await asyncio.to_thread(start_signin)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


@app.post("/api/google-drive/auth/disconnect")
async def google_drive_auth_disconnect():
    """Sign the Google account out: best-effort revoke at Google, then
    delete the locally stored token (spec §A6)."""
    from src.lingua_viva.google_drive_oauth import disconnect

    removed = await asyncio.to_thread(disconnect)
    if removed:
        try:
            from src.lingua_viva.privacy_log import log_event

            log_event("drive_account_disconnected")
        except Exception:
            pass
    return {"disconnected": bool(removed)}


@app.post("/api/google-drive/list")
async def google_drive_list(payload: dict):
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        list_connected_folders,
        list_files,
        mark_folder_checked,
    )

    folder_id = str(payload.get("folder_id") or "")
    try:
        result = await asyncio.to_thread(
            list_files,
            str(payload.get("query") or ""),
            folder_id,
            str(payload.get("page_token") or ""),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError:
        return JSONResponse({"error": "Google Drive could not be reached safely."}, status_code=503)
    if folder_id and any(f.get("id") == folder_id for f in list_connected_folders()):
        await asyncio.to_thread(mark_folder_checked, folder_id)
    return result


@app.get("/api/google-drive/folders")
async def google_drive_folders():
    from src.lingua_viva.google_drive_integration import list_connected_folders

    return {"folders": await asyncio.to_thread(list_connected_folders)}


@app.post("/api/google-drive/folders")
async def google_drive_connect_folder(payload: dict):
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        connect_folder,
    )

    try:
        entry = await asyncio.to_thread(
            connect_folder,
            str(payload.get("link") or ""),
            str(payload.get("name") or ""),
            str(payload.get("purpose") or "unassigned"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    try:
        from src.lingua_viva.privacy_log import log_event

        log_event("drive_folder_connected", query_text=entry.get("name", ""))
    except Exception:
        pass
    return {"connected": entry}


@app.delete("/api/google-drive/folders/{folder_id}")
async def google_drive_disconnect_folder(folder_id: str):
    from src.lingua_viva.google_drive_integration import disconnect_folder

    removed = await asyncio.to_thread(disconnect_folder, folder_id)
    if not removed:
        return JSONResponse({"error": "That folder is not connected."}, status_code=404)
    try:
        from src.lingua_viva.privacy_log import log_event

        log_event("drive_folder_disconnected", query_text=folder_id)
    except Exception:
        pass
    return {"disconnected": folder_id}


@app.post("/api/google-drive/import")
async def google_drive_import(payload: dict):
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        import_files,
    )

    file_ids = payload.get("file_ids")
    if (
        not isinstance(file_ids, list)
        or not file_ids
        or not all(isinstance(item, str) and item.strip() for item in file_ids)
    ):
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
        result = await asyncio.to_thread(
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
    for item in result.get("imported", []):
        try:
            from src.lingua_viva.privacy_log import log_event

            log_event("drive_files_imported", query_text=item.get("name", ""))
        except Exception:
            pass
    return result


@app.post("/api/google-drive/upload")
async def google_drive_upload(payload: dict):
    """Explicitly share deliverables back into the connected Drive folder.

    Accepts either {"student_id": "..."} — materializes that student lens as
    JSON into the export dir and shares it — or {"file_paths": [...]} for
    existing deliverable files (must live inside the Lingua Viva home).
    """
    from src.lingua_viva.google_drive_integration import (
        DriveAuthError,
        DriveConfigError,
        _atomic_write_private_json,
        export_dir,
        prune_student_exports,
        upload_paths,
    )
    from src.lingua_viva.privacy_log import log_event

    folder_id = str(payload.get("folder_id") or "")
    student_id = payload.get("student_id")
    file_paths = payload.get("file_paths")

    if student_id is not None:
        if not isinstance(student_id, str) or not student_id.strip():
            return JSONResponse({"error": "student_id must be a non-empty string"}, status_code=400)
        student_id = student_id.strip()

        def materialize(store):
            lens = store.export_lens(student_id)
            target = export_dir()
            target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            path = target / f"student-lens-{student_id}-{stamp}.json"
            # 0600 from birth — the snapshot is student data (H3 review found
            # the old write_text left it at the default umask).
            _atomic_write_private_json(path, lens)
            return str(path)

        try:
            lens_path = await asyncio.to_thread(_with_student_store, materialize)
        except Exception:
            return JSONResponse({"error": "Student lens could not be exported."}, status_code=400)
        file_paths = [lens_path]
    elif not isinstance(file_paths, list) or not file_paths:
        return JSONResponse(
            {"error": "Provide student_id or a non-empty file_paths list."}, status_code=400
        )

    try:
        result = await asyncio.to_thread(upload_paths, file_paths, folder_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except DriveConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except DriveAuthError:
        return JSONResponse({"error": "Google Drive could not be reached safely."}, status_code=503)

    for item in result.get("uploaded", []):
        try:
            log_event("drive_upload_shared", query_text=item.get("name", ""))
        except Exception:
            pass
    if student_id is not None and result.get("uploaded"):
        # H3: successful share-back prunes older snapshots for this student
        # (3 newest stay). Imports are never pruned — teacher-owned.
        try:
            await asyncio.to_thread(prune_student_exports, student_id)
        except Exception:
            pass

    # Integration loop Stage 4: this is the highest-risk action in the app —
    # data actually leaves the machine — yet it produced no durable record
    # before this. Every successful share now gets a DeliverableRecord (and,
    # when at least one file uploaded, an AuditReceipt) so it shows up next
    # to the observation export in Governance -> Deliverables and receipts.
    # Best-effort: a durable-record failure must never mask a real upload.
    uploaded = result.get("uploaded") or []
    if uploaded:
        try:
            from src.lingua_viva.audit_receipts.builder import build_receipt
            from src.lingua_viva.deliverables.schema import (
                DeliverableLocation,
                DeliverableRecord,
                compute_deliverable_id,
            )
            from src.lingua_viva.deliverables.store import upsert_deliverable

            trace_id = f"drive-upload-{uuid.uuid4().hex[:12]}"
            deliverable_id = compute_deliverable_id(trace_id, "")
            names = ", ".join(item.get("name", "") for item in uploaded if item.get("name"))
            deliverable = DeliverableRecord(
                deliverable_id=deliverable_id,
                session_id=broadcaster.session_id or "",
                trace_id=trace_id,
                type="drive_export",
                title=f"Shared to Drive: {names}" if names else "Shared to Drive",
                status="exported",
                location=DeliverableLocation(kind="drive_file", external_id=folder_id),
                summary=f"{len(uploaded)} file(s) shared to the connected Drive folder.",
            )
            upsert_deliverable(deliverable)
            receipt = build_receipt(
                scope="deliverable",
                session_id=broadcaster.session_id or "",
                trace_id=trace_id,
                deliverable_id=deliverable_id,
            )
            result["deliverable"] = deliverable.as_dict()
            result["audit_receipt"] = receipt.as_dict()
        except Exception:
            pass
    return result


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
        # Provenance is only worth showing if it is measured. Derive it from
        # the model that actually answered rather than asserting "local".
        from src.lingua_viva.reasoning import ReasoningEngine as _NativeReasoner

        answered_externally = _NativeReasoner._is_external_model(
            result.synthesis.model_used or ""
        )
        query_trace = new_trace(
            query_text,
            domain=result.classification.domain,
            model_used=result.synthesis.model_used,
            duration_ms=result.duration_ms,
            token_count=0,
            source_citations=source_citations,
            privacy_events=[],
            external_calls=1 if answered_externally else 0,
            route="external" if answered_externally else "local",
        )
        append_trace(query_trace)
        log_event("query_processed_locally", query_text=query_text)
        try:
            from src.lingua_viva.grounding.build import build_grounding_result

            grounding = build_grounding_result(
                trace={
                    "trace_id": query_trace.trace_id,
                    "session_id": session_id,
                    "model_used": result.synthesis.model_used,
                    "source_citations": source_citations,
                },
                classification=result.classification,
                content=result.synthesis.content,
                query_text=query_text,
                session_id=session_id,
                intent=str(intent or ""),
            ).as_dict()
        except Exception:
            grounding = None
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
                "external_called": answered_externally,
                "duration_ms": result.duration_ms,
                "gap_signals": result.gap_signals,
            },
            "trace_id": query_trace.trace_id,
            "route": "external" if answered_externally else "local",
            "model_used": result.synthesis.model_used,
            "duration_ms": result.duration_ms,
            "source_citation": source_citations[0] if source_citations else "Manuale v1",
            "sources": source_citations,
            "grounding": grounding,
            "external_calls": 1 if answered_externally else 0,
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
