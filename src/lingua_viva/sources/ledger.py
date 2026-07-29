from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.lingua_viva.sources.schema import SourceObservation, SourceRecord

_WRITE_LOCK = threading.Lock()


def _state_root() -> Path:
    env = os.environ.get("LV_STATE_HOME", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".lingua-viva"


def sources_dir() -> Path:
    path = _state_root() / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def records_path() -> Path:
    return sources_dir() / "source_records.ndjson"


def observations_path() -> Path:
    return sources_dir() / "source_observations.ndjson"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_source_record_id(source_type: str, source_id: str, container: str, record_id: str) -> str:
    digest = hashlib.sha256("|".join([source_type, source_id, container, record_id]).encode()).hexdigest()[:20]
    return f"SRC-{digest}"


def _atomic_write_ndjson(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _append_ndjson(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    os.chmod(path, 0o600)


def _load_all_records() -> dict[str, SourceRecord]:
    path = records_path()
    records: dict[str, SourceRecord] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = SourceRecord.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
        records[record.source_record_id] = record
    return records


def _save_all_records(records: dict[str, SourceRecord]) -> None:
    _atomic_write_ndjson(records_path(), [
        json.dumps(record.as_dict(), sort_keys=True)
        for _id, record in sorted(records.items())
    ])


def append_observation(observation: SourceObservation) -> None:
    _append_ndjson(observations_path(), json.dumps(observation.as_dict(), sort_keys=True))


def _state_changed(existing: Optional[SourceRecord], incoming: SourceRecord) -> bool:
    if existing is None:
        return True
    return (
        existing.content_hash != incoming.content_hash
        or existing.retrieval_scope != incoming.retrieval_scope
        or existing.policy.as_dict() != incoming.policy.as_dict()
        or existing.title != incoming.title
        or existing.uri != incoming.uri
        or existing.student_data != incoming.student_data
    )


def upsert(record: SourceRecord, *, detail: Optional[dict] = None) -> tuple[SourceRecord, bool]:
    with _WRITE_LOCK:
        records = _load_all_records()
        existing = records.get(record.source_record_id)
        changed = _state_changed(existing, record)
        if existing is not None and not changed:
            existing.observed_at = record.observed_at
            records[existing.source_record_id] = existing
            _save_all_records(records)
            return existing, False
        if existing is not None:
            record.created_at = existing.created_at
        records[record.source_record_id] = record
        _save_all_records(records)
        if record.retrieval_scope == "excluded":
            event = "excluded"
        elif existing is None:
            event = "imported" if record.provenance in {"import", "fetch"} else "seen"
        elif existing.content_hash != record.content_hash:
            event = "changed"
        else:
            event = "seen"
        append_observation(SourceObservation(
            observation_id=f"OBS-{uuid.uuid4().hex[:20]}",
            source_record_id=record.source_record_id,
            source_type=record.source_type,
            event=event,
            observed_at=record.observed_at,
            content_hash=record.content_hash,
            detail=dict(detail or {}),
        ))
        return record, True


def read_records(source_type: Optional[str] = None, limit: Optional[int] = None, q: Optional[str] = None) -> list[dict]:
    records = list(_load_all_records().values())
    if source_type:
        records = [r for r in records if r.source_type == source_type]
    if q:
        needle = q.strip().lower()
        records = [r for r in records if needle in r.title.lower() or needle in r.uri.lower() or needle in r.summary.lower()]
    records.sort(key=lambda r: r.observed_at, reverse=True)
    if limit is not None:
        records = records[:max(0, int(limit))]
    return [r.as_dict() for r in records]


def read_observations(source_record_id: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
    path = observations_path()
    if not path.exists():
        return []
    observations: list[SourceObservation] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obs = SourceObservation.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
        if source_record_id and obs.source_record_id != source_record_id:
            continue
        observations.append(obs)
    observations.sort(key=lambda o: o.observed_at, reverse=True)
    if limit is not None:
        observations = observations[:max(0, int(limit))]
    return [o.as_dict() for o in observations]


def counts_by_type() -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in _load_all_records().values():
        if record.retrieval_scope == "excluded":
            continue
        counts[record.source_type] = counts.get(record.source_type, 0) + 1
    return counts


def is_initialized() -> bool:
    return records_path().exists()
