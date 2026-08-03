from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.lingua_viva import config

from .contracts import ExtractionRecord, LensRecord, ManifestRecord, SourceRecord
from .validate import validate_file


_ROOT_LOCKS: dict[str, threading.RLock] = {}
_ROOT_LOCKS_GUARD = threading.Lock()


def vault_root() -> Path:
    state_home = os.environ.get("LV_STATE_HOME")
    base = Path(state_home) if state_home else config.lv_home()
    return base / "vault"


def init(*, root: Path | None = None) -> ManifestRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        _ensure_dirs(resolved)
        _ensure_sync_queue(resolved)
        return _rebuild_manifest(resolved)


def put_source(
    source: SourceRecord,
    content: bytes,
    *,
    root: Path | None = None,
) -> SourceRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        _ensure_dirs(resolved)
        _validate_record(source.data, "source")
        if _sha256(content) != source.data["sha256"]:
            raise ValueError("source sha256 does not match original content")
        source_dir = resolved / "sources" / source.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        original_path = source_dir / f"original{source.original_ext}"
        _atomic_write_bytes(original_path, content)
        _atomic_write_json(source_dir / "source.json", source.data)
        _rebuild_manifest(resolved)
        return source


def get_source(source_id: str, *, root: Path | None = None) -> SourceRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        path = resolved / "sources" / source_id / "source.json"
        return SourceRecord(_read_valid_json(path))


def put_extraction(
    extraction: ExtractionRecord,
    *,
    root: Path | None = None,
) -> ExtractionRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        _ensure_dirs(resolved)
        _atomic_write_json(
            resolved / "extracted" / f"{extraction.source_id}.json",
            extraction.data,
        )
        _rebuild_manifest(resolved)
        return extraction


def get_extraction(source_id: str, *, root: Path | None = None) -> ExtractionRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        path = resolved / "extracted" / f"{source_id}.json"
        return ExtractionRecord(_read_valid_json(path))


def get_lens(student_id: str, *, root: Path | None = None) -> LensRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        path = resolved / "lenses" / student_id / "lens.json"
        return LensRecord(_read_valid_json(path))


def put_lens(lens: LensRecord, *, root: Path | None = None) -> LensRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        _ensure_dirs(resolved)
        lens_dir = resolved / "lenses" / lens.student_id
        lens_dir.mkdir(parents=True, exist_ok=True)
        (lens_dir / "observations").mkdir(exist_ok=True)
        _atomic_write_json(lens_dir / "lens.json", lens.data)
        _rebuild_manifest(resolved)
        return lens


def manifest(*, root: Path | None = None) -> ManifestRecord:
    resolved = _root(root)
    with _lock_for(resolved):
        _ensure_dirs(resolved)
        _ensure_sync_queue(resolved)
        manifest_path = resolved / "manifest.json"
        if manifest_path.exists():
            try:
                return ManifestRecord(_read_valid_json(manifest_path))
            except (ValueError, OSError, json.JSONDecodeError):
                pass
        return _rebuild_manifest(resolved)


def _root(root: Path | None = None) -> Path:
    return root if root is not None else vault_root()


def _lock_for(root: Path) -> threading.RLock:
    key = str(root.expanduser().resolve(strict=False))
    with _ROOT_LOCKS_GUARD:
        lock = _ROOT_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _ROOT_LOCKS[key] = lock
        return lock


def _ensure_dirs(root: Path) -> None:
    for relative in ("sources", "extracted", "lenses", "sync"):
        (root / relative).mkdir(parents=True, exist_ok=True)


def _ensure_sync_queue(root: Path) -> None:
    queue = root / "sync" / "queue.json"
    if not queue.exists():
        _atomic_write_raw_json(queue, [])


def _read_valid_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    errors = validate_file(path)
    if errors:
        raise ValueError(f"{path} failed schema validation: {'; '.join(errors)}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _temp_path(path) as tmp:
        _write_json_file(tmp, data)
        errors = validate_file(tmp)
        if errors:
            _safe_unlink(tmp)
            raise ValueError(f"{path} failed schema validation: {'; '.join(errors)}")
        _replace(tmp, path)
        _fsync_dir(path.parent)


def _atomic_write_raw_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _temp_path(path) as tmp:
        _write_json_file(tmp, data)
        _replace(tmp, path)
        _fsync_dir(path.parent)


def _write_json_file(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(tmp, path)
        _fsync_dir(path.parent)
    except Exception:
        _safe_unlink(tmp)
        raise


class _temp_path:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.path: Path | None = None

    def __enter__(self) -> Path:
        fd, raw = tempfile.mkstemp(
            prefix=f".{self.destination.name}.",
            suffix=".tmp",
            dir=self.destination.parent,
        )
        os.close(fd)
        self.path = Path(raw)
        return self.path

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.path is not None:
            _safe_unlink(self.path)


def _replace(tmp: Path, destination: Path) -> None:
    os.replace(tmp, destination)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rebuild_manifest(root: Path) -> ManifestRecord:
    existing = _load_existing_manifest(root / "manifest.json")
    now = _now()
    data = {
        "schema_version": "docpipe.v1",
        "vault_id": existing.get("vault_id") or f"VAULT-{uuid.uuid4()}",
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "sources": _scan_sources(root),
        "extractions": _scan_extractions(root),
        "lenses": _scan_lenses(root),
        "sync": {
            "queue_path": "sync/queue.json",
            "pending_count": _pending_sync_count(root / "sync" / "queue.json"),
        },
    }
    _atomic_write_json(root / "manifest.json", data)
    return ManifestRecord(data)


def _load_existing_manifest(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _scan_sources(root: Path) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source_json in sorted((root / "sources").glob("*/source.json")):
        try:
            data = _read_valid_json(source_json)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        source_id = str(data["source_id"])
        sources[source_id] = {
            "source_id": source_id,
            "source_path": _relative(root, source_json),
            "origin": data["origin"],
            "sha256": data["sha256"],
        }
    return sources


def _scan_extractions(root: Path) -> dict[str, dict[str, str]]:
    extractions: dict[str, dict[str, str]] = {}
    for extraction_json in sorted((root / "extracted").glob("*.json")):
        if extraction_json.name.startswith("."):
            continue
        try:
            data = _read_valid_json(extraction_json)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        source_id = str(data["source_id"])
        extractions[source_id] = {
            "source_id": source_id,
            "extraction_path": _relative(root, extraction_json),
        }
    return extractions


def _scan_lenses(root: Path) -> dict[str, dict[str, str]]:
    lenses: dict[str, dict[str, str]] = {}
    for lens_json in sorted((root / "lenses").glob("*/lens.json")):
        try:
            data = _read_valid_json(lens_json)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        student_id = str(data["student_id"])
        lenses[student_id] = {
            "student_id": student_id,
            "lens_path": _relative(root, lens_json),
            "display_name": str(data["display_name"]),
        }
    return lenses


def _pending_sync_count(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        queue = data.get("queue")
        if isinstance(queue, list):
            return len(queue)
        pending = data.get("pending")
        if isinstance(pending, list):
            return len(pending)
    return 0


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _validate_record(data: dict[str, Any], expected: str) -> None:
    actual = data.get("schema_version")
    expected_version = {
        "source": "docpipe.source.v1",
        "extraction": "docpipe.extraction.v1",
        "lens": "docpipe.lens.v1",
        "manifest": "docpipe.v1",
    }[expected]
    if actual != expected_version:
        raise ValueError(f"expected {expected_version}, got {actual!r}")
