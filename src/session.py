"""
Session Continuity

Allows multiple CLI queries to share the same session context.
5 queries about the same legal matter accumulate paths in one session.

Usage:
    mc session start    — create .mc_session in CWD
    mc session end      — close session, run compaction
    mc session status   — show current session info

When .mc_session exists, all pipeline.run() calls use its session_id.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional


SESSION_FILE = ".mc_session"
MC_ROOT = Path(__file__).parent.parent

# Governance context loaded once per session — injected into every pipeline CONTEXT step.
_governance_context: Optional[str] = None


def load_governance() -> str:
    """Load Tier 1 steering files into ambient context. Called once at session start."""
    parts = []
    manifest = MC_ROOT / "MANIFEST.yaml"
    if manifest.exists():
        parts.append(manifest.read_text()[:2000])
    core = MC_ROOT / "config" / "core.md"
    if core.exists():
        parts.append(core.read_text())
    return "\n---\n".join(parts)


def get_governance_context() -> Optional[str]:
    """Return the cached governance context for this session."""
    return _governance_context


def get_active_session() -> Optional[str]:
    """Get the active session ID from .mc_session file, or None."""
    path = Path(SESSION_FILE)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data.get("session_id")
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def start_session() -> str:
    """Start a new session. Loads governance context and creates .mc_session."""
    global _governance_context
    session_id = str(uuid.uuid4())
    data = {
        "session_id": session_id,
        "started_at": time.time(),
        "query_count": 0,
    }
    Path(SESSION_FILE).write_text(json.dumps(data, indent=2))
    _governance_context = load_governance()
    return session_id


def increment_session() -> None:
    """Increment the query count for the active session."""
    path = Path(SESSION_FILE)
    if path.exists():
        data = json.loads(path.read_text())
        data["query_count"] = data.get("query_count", 0) + 1
        data["last_query_at"] = time.time()
        path.write_text(json.dumps(data, indent=2))


def end_session() -> Optional[dict]:
    """End the active session. Returns session summary."""
    path = Path(SESSION_FILE)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data["ended_at"] = time.time()
    duration = data["ended_at"] - data.get("started_at", data["ended_at"])
    data["duration_seconds"] = round(duration)
    path.unlink()
    return data


def session_status() -> Optional[dict]:
    """Get current session info."""
    path = Path(SESSION_FILE)
    if not path.exists():
        return None
    return json.loads(path.read_text())
