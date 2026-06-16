# Mission Canvas — Dual Surface Architecture Plan

**Date**: 2026-06-12
**Author**: kiro.design
**Status**: Plan only — no implementation yet
**Goal**: `curl -fsSL https://missioncanvas.ai/install.sh | bash` → CLI session starts + localhost opens in browser, both synced to same session

---

## What We Want

After install completes:
1. **Terminal stays active as an MC session** — user can type `mc research "..."` immediately
2. **Browser opens localhost** — same session, same output, bidirectional
3. **Both surfaces are synced** — action in terminal appears in browser and vice versa
4. **Subsequent launches**: user types `mc` → CLI starts + localhost opens (like `claude`, `kiro-cli`, `codex`)

### The Ideal Experience
- User types in terminal → browser shows it live
- User clicks in browser → terminal reflects the action
- Pipeline steps (CLASSIFY → RETRIEVE → REASON → etc.) visible in BOTH surfaces as they execute
- Session state persists across surfaces — close browser, come back, state is there

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| `mc` CLI | Works | `./mc` → `src/mc_cli.py` |
| Install script | Works (install only, no session start) | `install.sh` |
| Setup script | Works (starts services + opens browser) | `setup.sh` |
| Hub web server | Works (voice interface on :7890) | `runtime/hub/server.mjs` |
| Broker | Works (message bus on :7899) | `runtime/broker/index.mjs` |
| Session system | Works (file-based, `.mc_session`) | `src/session.py` |
| API server | Exists (planned :7891) | Not fully wired |

**Gap**: No shared session between CLI and web. They're separate codepaths. The hub serves a voice interface, not an MC pipeline mirror.

---

## Architecture Options (Researched)

### Option A: FastAPI + WebSocket + xterm.js (Recommended)

**How it works**:
- MC CLI starts a FastAPI server on localhost (e.g., :7891) as a background thread
- Server exposes: `GET /` (web UI), `WS /ws` (WebSocket for live sync)
- Shared session object holds all state (history, pipeline steps, path records)
- CLI reads stdin → session.handle() → prints to terminal + broadcasts via WebSocket
- Browser sends via WebSocket → session.handle() → prints to terminal + broadcasts back

**Why this wins**:
- Python-native (MC is already Python)
- Single process (no IPC, no file sync, no race conditions)
- WebSocket = instant sync, bidirectional
- xterm.js in browser shows terminal output verbatim
- FastAPI is async, lightweight, already a common MC dependency pattern
- Works on Linux/Mac/Windows without platform-specific code

**Dependencies**: `fastapi`, `uvicorn`, `websockets` (all well-maintained, pinnable)

**Effort**: ~200 lines of Python + ~100 lines of HTML/JS

### Option B: Shared State File + SSE

- CLI writes to a NDJSON state file
- Web server watches file, pushes changes via SSE
- Browser receives SSE stream, renders

**Downside**: One-way (browser can't send back easily), file I/O latency, race conditions.

### Option C: Broker as Middleware

- Both CLI and web connect to the existing broker (:7899)
- Pipeline events broadcast as bus messages
- Browser subscribes via SSE/WebSocket to broker

**Downside**: Adds broker as hard dependency for basic use. Broker is currently optional.

### Option D: Textual Serve (Python TUI in browser)

- Use Textual's `textual serve` to expose terminal UI as web app
- Single codebase renders in both terminal and browser

**Downside**: Locks us into Textual's rendering model. Heavy dependency. Browser experience is "terminal in a box" not a native web UI.

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│                MC Process (single Python)             │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ CLI Loop │───▶│   Session    │◀───│  FastAPI   │  │
│  │  (stdin) │    │  (shared     │    │  WebSocket │  │
│  │          │◀───│   state)     │───▶│  Server    │  │
│  └──────────┘    └──────────────┘    └───────────┘  │
│       │                │                    │        │
│       ▼                ▼                    ▼        │
│   Terminal          Pipeline           Browser       │
│   (stdout)       (8-step exec)      (localhost)      │
└─────────────────────────────────────────────────────┘
```

**Session object holds**:
- `session_id` — unique per session
- `history[]` — all input/output lines
- `pipeline_state` — current step, node, confidence
- `path_records[]` — completed queries
- `active_connections[]` — WebSocket clients

**Event flow**:
1. Input arrives (from CLI stdin OR browser WebSocket)
2. Session dispatches to pipeline
3. Pipeline emits step-by-step events (CLASSIFY done, RETRIEVE done, etc.)
4. Session broadcasts each event to ALL surfaces (print to terminal + send via WS)
5. STORE fires, path record saved
6. Both surfaces show final result

---

## Implementation Plan

### Phase 1: Embedded Web Server (Minimal)

```python
# In mc_cli.py startup:
import threading
from src.web import start_web_server

# Start web server in background thread
web_thread = threading.Thread(target=start_web_server, args=(session,), daemon=True)
web_thread.start()
print(f"  Web UI: http://localhost:7891")
```

New file: `src/web.py` (~150 lines)
- FastAPI app with WebSocket endpoint
- Serves `static/index.html` (xterm.js terminal + pipeline status panel)
- Connects to shared Session object
- Broadcasts pipeline events as they happen

### Phase 2: Install Flow

Update `install.sh` / `setup.sh`:
```bash
# After install completes:
echo "Starting Mission Canvas..."
exec ./mc   # This starts CLI + web server together
```

### Phase 3: `mc` as Session Launcher

When user types `mc` with no arguments:
1. Start/resume session
2. Start web server on :7891
3. Open browser (`xdg-open http://localhost:7891`)
4. Enter interactive CLI loop
5. Both surfaces active until user exits

### Phase 4: PATH Integration

```bash
# install.sh adds to ~/.bashrc or ~/.profile:
export PATH="$HOME/mission-canvas:$PATH"
```

Now `mc` works from anywhere, like `claude` or `kiro-cli`.

---

## Task 2: Auto-Read Steering Files on Session Start

**Problem**: MC must understand itself before processing any query. Users won't know to read steering files manually.

**Solution**: Pipeline Step 0 (SCAN) or session initialization reads governance automatically.

### Implementation

In `src/session.py` or `src/mc_cli.py` startup:

```python
def start_session():
    """Start a new MC session — always reads steering first."""
    session = Session(id=uuid4())

    # Auto-load governance context into session memory
    governance_files = [
        "MANIFEST.yaml",
        "config/core.md",
        "config/governance/",  # all files in dir
    ]
    for f in governance_files:
        session.governance_context += load_file(f)

    # Governance context is injected into every pipeline CONTEXT step (Step 4)
    # It's not a query — it's ambient knowledge the pipeline always has
    return session
```

**Where it lives in the pipeline**:
- NOT as a query that runs through CLASSIFY
- AS ambient context loaded at session start
- INJECTED into Step 4 (CONTEXT) for every subsequent query
- The pipeline always knows what MC is, what its rules are, what it can do

**What gets loaded** (read once per session, cached):
1. `MANIFEST.yaml` — system identity, versions, counts
2. `config/core.md` — 5 immutable rules
3. `config/governance/tier_1.yaml` — never-break rules
4. Ontology node count + domain list (from engine)
5. Current health score (from last health check)

**User experience**: Invisible. User types `mc research "..."` and the pipeline already knows what MC is. No manual step needed.

---

## What NOT to Build

- ❌ Don't replace the hub (voice interface stays separate)
- ❌ Don't require broker for basic CLI+web sync (keep broker optional)
- ❌ Don't use electron or heavy frameworks (plain HTML + xterm.js + WebSocket)
- ❌ Don't sync via files (use in-process shared state)
- ❌ Don't add Textual as a dependency (too heavy, wrong abstraction)

---

## Effort Estimate

| Phase | Files | Lines | Time |
|-------|-------|-------|------|
| Phase 1: Web server | `src/web.py` + `static/index.html` | ~250 | 4 hrs |
| Phase 2: Install flow | `install.sh` edits | ~10 | 30 min |
| Phase 3: `mc` launcher | `mc` + `src/mc_cli.py` edits | ~50 | 2 hrs |
| Phase 4: PATH | `install.sh` append | ~5 | 15 min |
| Task 2: Auto-steering | `src/session.py` edits | ~30 | 1 hr |
| **Total** | | **~345** | **~8 hrs** |

---

## Success Criteria

- [ ] `curl -fsSL https://missioncanvas.ai/install.sh | bash` → ends with active CLI session
- [ ] Browser opens automatically to localhost showing same session
- [ ] Type in terminal → appears in browser instantly
- [ ] Click/type in browser → appears in terminal
- [ ] Pipeline steps visible in both surfaces as they execute
- [ ] `mc` from any terminal starts a session (after PATH is set)
- [ ] Steering files loaded automatically — user never needs to know they exist
- [ ] Session persists if browser is closed and reopened

---

*Plan created 2026-06-12 07:00 PT by kiro.design. Ready for team review before implementation.*
