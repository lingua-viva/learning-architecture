"""
Mission Canvas — Web Surface (Dual Surface Architecture)

Embedded web server that syncs with the CLI through a shared session.
Both surfaces see the same pipeline events in real-time.

Architecture:
    MC Process (single Python)
    ├── CLI Loop (stdin/stdout)
    ├── Session (shared state)
    └── FastAPI + WebSocket Server (localhost:7896)

Start: automatically launched as daemon thread when mc session starts.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
import uvicorn
from urllib.parse import urlencode

MC_ROOT = Path(__file__).parent.parent

app = FastAPI(title="Mission Canvas", docs_url=None, redoc_url=None)


class SessionBroadcaster:
    """Manages WebSocket connections and broadcasts pipeline events."""

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

    manifest_path = MC_ROOT / "MANIFEST.yaml"
    if manifest_path.exists():
        parts.append(f"# MANIFEST\n{manifest_path.read_text()[:2000]}")

    core_path = MC_ROOT / "config" / "core.md"
    if core_path.exists():
        parts.append(f"# TIER 1 RULES\n{core_path.read_text()}")

    return "\n---\n".join(parts)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = MC_ROOT / "static" / "index.html"
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
    return FileResponse(MC_ROOT / "static" / "sw.js", media_type="application/javascript")


@app.get("/offline.html", response_class=HTMLResponse)
async def offline_page():
    return FileResponse(MC_ROOT / "static" / "offline.html", media_type="text/html")


@app.get("/icons/{name}")
async def icon_asset(name: str):
    safe_name = Path(name).name
    return FileResponse(MC_ROOT / "static" / "icons" / safe_name)


@app.get("/api/health")
async def health():
    try:
        from src.integrity.health_check import HealthCheck
        hc = HealthCheck()
        result = hc.run()
        return {
            "healthy": result.healthy,
            "score": f"{result.score:.0%}",
            "checks_passed": result.checks_passed,
            "checks_total": result.checks_total,
        }
    except Exception as e:
        return {"healthy": False, "error": str(e)}


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


@app.post("/api/query")
async def query_endpoint(payload: dict):
    """Run a query through the governed pipeline."""
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
        pipeline = Pipeline()
        result = await pipeline.run(
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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "query":
                # Browser sent a query — run through pipeline
                result = await query_endpoint({
                    "query": data.get("query", ""),
                    "intent": data.get("intent"),
                })
                # Result already broadcast by query_endpoint
            elif data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)


# Lazy import to avoid circular deps
Pipeline = None


def _ensure_pipeline():
    global Pipeline
    if Pipeline is None:
        from src.pipeline import Pipeline as P
        Pipeline = P


def start_web_server(port: int = 7896):
    """Start the web server. Called from a daemon thread in mc_cli.py."""
    _ensure_pipeline()
    broadcaster.governance_context = load_governance_context()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    # Standalone/detached launch — e.g. `python3 -m src.web 7893 &` from an
    # installer. Mirrors src/api_server.py's own __main__ pattern; without
    # this, start_web_server() could only ever run as a daemon thread inside
    # `mc session start`'s foreground process, which dies with its parent.
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else 7896
    start_web_server(_port)


FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mission Canvas</title>
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
  <h1>Mission Canvas</h1>
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
  <input type="text" id="query-input" placeholder="Ask Mission Canvas..." autofocus>
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
  div.textContent = `Mission Canvas — ${data.ontology_nodes} nodes, ${data.knowledge_entries} KL entries, ${data.path_records} paths`;
  output.appendChild(div);
});
</script>
</body>
</html>"""
