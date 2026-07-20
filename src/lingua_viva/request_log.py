"""Lightweight request-outcome log (MC-lessons §5).

MC could prove zero unhandled 500s across its full firewall history because
it had a longitudinal event log to audit. LV's uvicorn server ran with
log_level="error" — no request log at all. This module is the minimal fix:
one NDJSON line per HTTP response — timestamp, method, path-template,
status. No query content, no request/response bodies, no query strings —
privacy first, same hash-only-or-nothing discipline as traces.py and
privacy_log.py.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RequestEvent:
    timestamp: str
    method: str
    path_template: str
    status: int


def request_log_path() -> Path:
    override = os.environ.get("LV_REQUEST_LOG_PATH")
    if override:
        return Path(override).expanduser()
    from src.lingua_viva.config import lv_home
    return lv_home() / "request_events.ndjson"


def append_request_event(method: str, path_template: str, status: int) -> None:
    event = RequestEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        method=method,
        path_template=path_template,
        status=status,
    )
    path = request_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
    os.chmod(path, 0o600)


def read_request_events(limit: int = 10_000) -> list[RequestEvent]:
    path = request_log_path()
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []
    events: list[RequestEvent] = []
    for line in lines:
        try:
            events.append(RequestEvent(**json.loads(line)))
        except (TypeError, json.JSONDecodeError):
            continue
    return events[-max(limit, 0):]


def count_5xx(events: list[RequestEvent] | None = None) -> int:
    events = events if events is not None else read_request_events()
    return sum(1 for event in events if event.status >= 500)
