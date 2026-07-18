from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.lingua_viva.traces import read_traces


@dataclass
class PrivacyEvent:
    timestamp: str
    event_type: str
    detail: str
    query_hash: str = ""


STUDENT_EVENT_TYPES = {"student_name_blocked", "student_data_blocked"}


def privacy_log_path() -> Path:
    override = os.environ.get("LV_PRIVACY_LOG_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".lingua-viva" / "privacy_events.ndjson"


def event_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _generic_detail(event_type: str) -> str:
    details = {
        "student_name_blocked": "Student-identifying text was blocked from output.",
        "student_data_blocked": "Student or family data was kept local.",
        "observation_saved_locally": "Observation saved locally only.",
        "query_processed_locally": "Teacher query processed locally.",
        "ai_attribution_stripped": "AI attribution wording removed from parent draft.",
    }
    return details.get(event_type, "Privacy event recorded locally.")


def make_event(event_type: str, *, detail: str | None = None, query_text: str = "") -> PrivacyEvent:
    return PrivacyEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        detail=detail or _generic_detail(event_type),
        query_hash=event_hash(query_text),
    )


def log_privacy_event(event: PrivacyEvent) -> None:
    event.detail = _generic_detail(event.event_type)
    path = privacy_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
    os.chmod(path, 0o600)


def log_event(event_type: str, *, query_text: str = "") -> PrivacyEvent:
    event = make_event(event_type, query_text=query_text)
    log_privacy_event(event)
    return event


def read_privacy_events(limit: int = 50) -> list[PrivacyEvent]:
    path = privacy_log_path()
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []
    events: list[PrivacyEvent] = []
    for line in lines:
        try:
            data = json.loads(line)
            data["detail"] = _generic_detail(str(data.get("event_type") or ""))
            events.append(PrivacyEvent(**data))
        except (TypeError, json.JSONDecodeError):
            continue
    events.sort(key=lambda event: event.timestamp, reverse=True)
    return events[: max(limit, 0)]


def privacy_summary() -> dict:
    events = read_privacy_events(limit=10_000)
    trace_count = len(read_traces(limit=10_000))
    return {
        "total_queries_local": max(trace_count, sum(1 for event in events if event.event_type == "query_processed_locally")),
        "student_blocks": sum(1 for event in events if event.event_type in STUDENT_EVENT_TYPES),
        "ai_attribution_stripped": sum(1 for event in events if event.event_type == "ai_attribution_stripped"),
        "observations_saved_locally": sum(1 for event in events if event.event_type == "observation_saved_locally"),
        "external_calls": 0,
        "docx_modifications": 0,
    }


def clear_privacy_events() -> None:
    try:
        privacy_log_path().unlink()
    except FileNotFoundError:
        return
