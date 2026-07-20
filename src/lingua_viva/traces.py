from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ReasoningTrace:
    trace_id: str
    timestamp: str
    query_hash: str
    classification_domain: str
    model_used: str
    duration_ms: int
    token_count: int
    source_citations: list[str] = field(default_factory=list)
    privacy_events: list[str] = field(default_factory=list)
    external_calls: int = 0
    route: str = "local"


def trace_path() -> Path:
    override = os.environ.get("LV_TRACE_PATH")
    if override:
        return Path(override).expanduser()
    from src.lingua_viva.config import lv_home
    return lv_home() / "traces.ndjson"


def hash_query(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def new_trace(
    query: str,
    *,
    domain: str = "general",
    model_used: str = "none",
    duration_ms: int = 0,
    token_count: int = 0,
    source_citations: list[str] | None = None,
    privacy_events: list[str] | None = None,
) -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        query_hash=hash_query(query),
        classification_domain=domain or "general",
        model_used=model_used or "none",
        duration_ms=max(int(duration_ms), 0),
        token_count=max(int(token_count), 0),
        source_citations=source_citations or [],
        privacy_events=privacy_events or [],
        external_calls=0,
        route="local",
    )


def append_trace(trace: ReasoningTrace) -> None:
    path = trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(trace), ensure_ascii=True) + "\n")
    os.chmod(path, 0o600)


def read_traces(limit: int = 20) -> list[ReasoningTrace]:
    path = trace_path()
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []
    traces: list[ReasoningTrace] = []
    for line in lines:
        try:
            data = json.loads(line)
            data["external_calls"] = 0
            data["route"] = "local"
            traces.append(ReasoningTrace(**data))
        except (TypeError, json.JSONDecodeError):
            continue
    traces.sort(key=lambda trace: trace.timestamp, reverse=True)
    return traces[: max(limit, 0)]


def get_trace(trace_id: str) -> Optional[ReasoningTrace]:
    for trace in read_traces(limit=10_000):
        if trace.trace_id == trace_id:
            return trace
    return None


def clear_traces() -> None:
    try:
        trace_path().unlink()
    except FileNotFoundError:
        return
