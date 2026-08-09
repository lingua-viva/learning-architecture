from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.lingua_viva.runtime_paths import runtime_data_dir


def review_queue_path() -> Path:
    return runtime_data_dir("ingest_review") / "unattributed.ndjson"


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _key(item: dict[str, Any]) -> str:
    return f"{item.get('drive_id') or ''}|{item.get('source_id') or ''}"


def _append_event(event: dict[str, Any]) -> None:
    path = review_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": f"ingest-review-{uuid.uuid4().hex}",
        "event_at": _now_z(),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_events() -> list[dict[str, Any]]:
    path = review_queue_path()
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def current_items() -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in read_events():
        key = _key(event)
        if not key.strip("|"):
            continue
        state[key] = event
    return state


def list_open_items(teacher_id: str | None = None) -> list[dict[str, Any]]:
    items = [
        item for item in current_items().values()
        if item.get("status") == "open"
        and (not teacher_id or item.get("teacher_id") == teacher_id)
    ]
    return sorted(
        items,
        key=lambda item: str(item.get("queued_at") or item.get("event_at") or ""),
        reverse=True,
    )


def enqueue_unattributed(
    item: dict[str, Any],
    *,
    teacher_id: str,
    folder_id: str,
) -> dict[str, Any]:
    event = {
        "status": "open",
        "queued_at": _now_z(),
        "teacher_id": teacher_id,
        "folder_id": folder_id,
        "drive_id": str(item.get("drive_id") or ""),
        "source_id": str(item.get("source_id") or ""),
        "name": str(item.get("name") or ""),
        "reason": str(item.get("reason") or ""),
        "students_detected": [
            student for student in item.get("students_detected", [])
            if isinstance(student, dict)
        ],
    }
    if not event["drive_id"] or not event["source_id"]:
        raise ValueError("unattributed item requires drive_id and source_id")
    for existing in current_items().values():
        if (
            existing.get("status") == "open"
            and existing.get("drive_id") == event["drive_id"]
        ):
            return existing
    _append_event(event)
    return event


def mark_assigned(
    *,
    source_id: str,
    drive_id: str,
    student_id: str,
    teacher_id: str,
    evidence_id: str,
) -> dict[str, Any]:
    event = {
        "status": "assigned",
        "assigned_at": _now_z(),
        "teacher_id": teacher_id,
        "source_id": source_id,
        "drive_id": drive_id,
        "student_id": student_id,
        "evidence_id": evidence_id,
    }
    _append_event(event)
    return event


def mark_dismissed(
    *,
    source_id: str,
    drive_id: str,
    teacher_id: str,
) -> dict[str, Any]:
    event = {
        "status": "dismissed",
        "dismissed_at": _now_z(),
        "teacher_id": teacher_id,
        "source_id": source_id,
        "drive_id": drive_id,
    }
    _append_event(event)
    return event
