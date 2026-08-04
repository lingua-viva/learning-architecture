"""Drive write-back sync queue (T6, SPEC_T6_SYNC_2026-08-04).

A local lens save propagates to the teacher's own Google Drive. The queue is
persistent and offline-first: entries flip to "pushed" only after a confirmed
push, so a crash mid-drain retries safely and nothing is ever dropped.

`drive.push_file` is the frozen T1/T6 seam — while it is unimplemented the
queue holds honestly (the accepted day-one fallback is a local-only loop).
Exports are per-teacher, timestamped files: two teachers can never overwrite
each other's view of a student; merging happens locally through the additive
evidence[] import path, not by clobbering files in Drive.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import drive, vault

QUEUE_RELATIVE = Path("sync") / "queue.json"
OUTBOX_RELATIVE = Path("sync") / "outbox"
FAILED_ATTEMPT_THRESHOLD = 3
BACKOFF_CAP_MINUTES = 30

PROFILE_LABELS = {
    "learning_and_cognition": "Learning and Cognition",
    "communication_and_language": "Communication and Language",
    "executive_functioning": "Executive Functioning",
    "social_skills": "Social Skills",
    "emotional_regulation": "Emotional Regulation",
    "physical_sensory_needs": "Physical/Sensory Needs",
    "attendance_and_engagement": "Attendance and Engagement",
    "strategies_trialed": "Strategies trialed",
    "academic_strengths": "Academic Strengths",
    "personal_strengths": "Personal Strengths",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _queue_path(root: Optional[Path]) -> Path:
    base = root if root is not None else vault.vault_root()
    return base / QUEUE_RELATIVE


def _read_queue(root: Optional[Path]) -> list[dict[str, Any]]:
    path = _queue_path(root)
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_queue(entries: list[dict[str, Any]], root: Optional[Path]) -> None:
    path = _queue_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def enqueue_lens(
    student_id: str,
    *,
    root: Optional[Path] = None,
    destination_ref: str = "lens-exports",
) -> dict[str, Any]:
    """Queue a lens for Drive write-back. One pending entry per student —
    a re-save refreshes the pending entry instead of duplicating it."""
    entries = _read_queue(root)
    for entry in entries:
        if entry.get("student_id") == student_id and entry.get("status") == "pending":
            entry["enqueued_at"] = _now()
            entry["destination_ref"] = destination_ref
            _write_queue(entries, root)
            return entry
    entry = {
        "entry_id": f"SYN-{uuid.uuid4()}",
        "student_id": student_id,
        "enqueued_at": _now(),
        "attempts": 0,
        "last_attempt_at": None,
        "last_error": None,
        "status": "pending",
        "pushed_at": None,
        "destination_ref": destination_ref,
    }
    entries.append(entry)
    _write_queue(entries, root)
    return entry


def _backoff_elapsed(entry: dict[str, Any], now_ts: float) -> bool:
    attempts = int(entry.get("attempts") or 0)
    if attempts == 0:
        return True
    wait_minutes = min(2 ** attempts, BACKOFF_CAP_MINUTES)
    return now_ts - _parse_ts(entry.get("last_attempt_at")) >= wait_minutes * 60


def render_lens_markdown(lens_data: dict[str, Any]) -> str:
    """Teacher-readable Markdown of a lens — what actually lands in Drive.
    Every populated value carries its evidence line; empty categories are
    listed honestly, never filled in."""
    lines = [
        f"# Student lens — {lens_data.get('display_name', 'Unknown student')}",
        "",
        f"Updated: {lens_data.get('updated_at', 'unknown')}",
        "",
    ]
    empty: list[str] = []
    for field_id, label in PROFILE_LABELS.items():
        field = (lens_data.get("profile") or {}).get(field_id) or {}
        value = field.get("value")
        evidence = field.get("evidence") or []
        if value in (None, "", [], {}):
            empty.append(label)
            continue
        lines.append(f"## {label}")
        values = value if isinstance(value, list) else [value]
        for item in values:
            lines.append(f"- {_value_text(item)}")
        for item in evidence:
            source_ref = item.get("source_ref") or {}
            if source_ref.get("type") == "OBSERVATION":
                ref = f"observation {item.get('obs_id') or source_ref.get('obs_id')}"
            else:
                ref = f"document {source_ref.get('source_id')} span {item.get('span_id')}"
            lines.append(f"  - evidence: {ref}, added by {item.get('added_by', 'unknown')}")
        lines.append("")
    if empty:
        lines.append("## No evidence yet")
        for label in empty:
            lines.append(f"- {label}")
        lines.append("")
    return "\n".join(lines)


def _value_text(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v)
    return " ".join(str(value).split())


def _export_filename(lens_data: dict[str, Any], now: str) -> str:
    owner = str(lens_data.get("metadata", {}).get("owner") or "teacher").replace(":", "-")
    stamp = now.replace(":", "").replace("-", "").replace("Z", "")
    return f"lens-{lens_data.get('student_id')}-{owner}-{stamp}.md"


def drain(
    *,
    root: Optional[Path] = None,
    now: Optional[float] = None,
    push: Optional[Callable[..., Any]] = None,
) -> dict[str, int]:
    """One worker pass over the queue. Per-entry failures are recorded, never
    raised — the queue is the source of truth and survives everything."""
    from src.lingua_viva.privacy_log import log_event

    push_file = push if push is not None else drive.push_file
    now_ts = now if now is not None else time.time()
    entries = _read_queue(root)
    pushed = 0
    failed = 0
    for entry in entries:
        if entry.get("status") != "pending":
            continue
        if not _backoff_elapsed(entry, now_ts):
            continue
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        entry["last_attempt_at"] = _now()
        try:
            lens = vault.get_lens(str(entry["student_id"]), root=root)
            rendered = render_lens_markdown(lens.data)
            base = root if root is not None else vault.vault_root()
            outbox = base / OUTBOX_RELATIVE
            outbox.mkdir(parents=True, exist_ok=True)
            local_path = outbox / _export_filename(lens.data, _now())
            local_path.write_text(rendered, encoding="utf-8")
            push_file(local_path, str(entry.get("destination_ref") or "lens-exports"), mime="text/markdown")
            entry["status"] = "pushed"
            entry["pushed_at"] = _now()
            entry["last_error"] = None
            pushed += 1
            try:
                log_event("drive_upload_shared", query_text=str(entry["student_id"]))
            except Exception:
                pass
        except NotImplementedError:
            entry["last_error"] = (
                "Drive write-back is not available in this build yet; the lens "
                "stays queued locally and syncs after the next update."
            )
            failed += 1
        except Exception as error:
            entry["last_error"] = str(error)[:300]
            failed += 1
    _write_queue(entries, root)
    return {
        "pushed": pushed,
        "failed_this_pass": failed,
        "pending": sum(1 for e in entries if e.get("status") == "pending"),
    }


def sync_status(
    student_id: Optional[str] = None,
    *,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    entries = _read_queue(root)
    if student_id is not None:
        relevant = [e for e in entries if e.get("student_id") == student_id]
        pending = [e for e in relevant if e.get("status") == "pending"]
        if not relevant:
            return {"status": "synced", "attempts": 0, "last_error": None}
        if not pending:
            latest = max(relevant, key=lambda e: _parse_ts(e.get("pushed_at")))
            return {"status": "synced", "attempts": latest.get("attempts", 0), "last_error": None,
                    "pushed_at": latest.get("pushed_at")}
        entry = pending[0]
        status = "failed" if int(entry.get("attempts") or 0) >= FAILED_ATTEMPT_THRESHOLD else "pending"
        return {"status": status, "attempts": entry.get("attempts", 0),
                "last_error": entry.get("last_error"), "enqueued_at": entry.get("enqueued_at")}
    pending = [e for e in entries if e.get("status") == "pending"]
    return {
        "pending": len(pending),
        "pushed": sum(1 for e in entries if e.get("status") == "pushed"),
        "failed": sum(
            1 for e in pending if int(e.get("attempts") or 0) >= FAILED_ATTEMPT_THRESHOLD
        ),
    }


_worker: dict[str, Any] = {"thread": None, "stop": None}


def start_worker(interval_seconds: int = 60, *, root: Optional[Path] = None) -> None:
    """Background drain loop. Caller wires this at app startup (T5-or-later)."""
    if _worker["thread"] is not None and _worker["thread"].is_alive():
        return
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_seconds):
            try:
                drain(root=root)
            except Exception:
                pass

    thread = threading.Thread(target=loop, name="lv-sync-worker", daemon=True)
    _worker.update({"thread": thread, "stop": stop})
    thread.start()


def stop_worker() -> None:
    stop = _worker.get("stop")
    if stop is not None:
        stop.set()
    _worker.update({"thread": None, "stop": None})
