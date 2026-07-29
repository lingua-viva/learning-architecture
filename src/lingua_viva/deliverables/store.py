from __future__ import annotations

import json
import os
import threading
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
