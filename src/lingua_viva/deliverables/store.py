from __future__ import annotations

import json
import os
import threading
import tempfile
import uuid
import re
from pathlib import Path

from src.lingua_viva.deliverables.schema import DeliverableRecord

_LOCK = threading.Lock()


def _state_root() -> Path:
    env = os.environ.get("LV_STATE_HOME", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".lingua-viva"


def records_path() -> Path:
    path = _state_root() / "deliverables" / "records.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, lines: list[str]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def _load_all() -> dict[str, DeliverableRecord]:
    path = records_path()
    records: dict[str, DeliverableRecord] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = DeliverableRecord.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
        records[record.deliverable_id] = record
    return records


def upsert_deliverable(record: DeliverableRecord) -> DeliverableRecord:
    with _LOCK:
        records = _load_all()
        records[record.deliverable_id] = record
        _atomic_write(records_path(), [json.dumps(r.as_dict(), sort_keys=True) for _id, r in sorted(records.items())])
        return record


def read_deliverable(deliverable_id: str) -> DeliverableRecord | None:
    return _load_all().get(deliverable_id)


def read_deliverables(session_id: str = "", action_plan_id: str = "", limit: int = 50) -> list[dict]:
    records = list(_load_all().values())
    if session_id:
        records = [r for r in records if r.session_id == session_id]
    if action_plan_id:
        records = [r for r in records if r.action_plan_id == action_plan_id]
    records.sort(key=lambda r: r.created_at, reverse=True)
    return [r.as_dict() for r in records[:max(0, int(limit))]]


def snapshots_dir() -> Path:
    """Immutable output revisions alongside the existing deliverables index."""
    path = _state_root() / "deliverables" / "saved"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_snapshot(kind: str, title: str, payload: dict, *, teacher_id: str = "") -> dict:
    from src.lingua_viva.deliverables.schema import now_iso
    from src.lingua_viva.docpipe.vault import _fsync_dir

    identifier = "SAVED-" + uuid.uuid4().hex
    record = {
        "schema_version": "lv.saved-deliverable.v1", "id": identifier,
        "kind": kind, "title": title, "created_at": now_iso(),
        "teacher_id": teacher_id, "payload": payload,
    }
    directory = snapshots_dir()
    destination = directory / (identifier + ".json")
    fd, temporary = tempfile.mkstemp(prefix=".saving-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_dir(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {**{k: v for k, v in record.items() if k != "payload"}, "path": str(destination)}


def read_snapshot(identifier: str) -> dict:
    if not re.fullmatch(r"SAVED-[a-f0-9]{32}", identifier):
        raise FileNotFoundError("Unknown saved work")
    directory = snapshots_dir().resolve()
    candidate = (directory / (identifier + ".json")).resolve()
    if candidate.parent != directory:
        raise FileNotFoundError("Unknown saved work")
    return json.loads(candidate.read_text(encoding="utf-8"))


def list_snapshots() -> tuple[list[dict], int]:
    items, unreadable = [], 0
    for path in snapshots_dir().glob("SAVED-*.json"):
        try:
            record = read_snapshot(path.stem)
            items.append({k: record[k] for k in ("id", "kind", "title", "created_at", "teacher_id")})
        except (OSError, ValueError, KeyError):
            unreadable += 1
    return sorted(items, key=lambda item: item["created_at"], reverse=True), unreadable
