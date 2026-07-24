from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request

from src.lingua_viva.config import lv_home


DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SUPPORTED_IMPORT_MIME_TYPES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/vnd.google-apps.document": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
EXTRACTION_SUFFIXES = {".pdf", ".txt", ".md"}
PURPOSES = {
    "student_lens_source",
    "curriculum_unit_source",
    "teacher_artifact_source",
    "unassigned",
}


class DriveConfigError(RuntimeError):
    pass


class DriveAuthError(RuntimeError):
    pass


class DriveTransport(Protocol):
    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        ...

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        ...

    def get_bytes(self, url: str, token: str) -> bytes:
        ...


class UrlLibDriveTransport:
    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        encoded = parse.urlencode(data).encode("utf-8")
        req = request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_bytes(self, url: str, token: str) -> bytes:
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with request.urlopen(req, timeout=30) as response:
            return response.read()


class FixtureDriveTransport:
    """Local fixture transport for served-app verification; never contacts Google."""

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self.data = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {"access_token": "fixture-access-token"}

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        files = self.data.get("files", [])
        if "/files?" in url:
            return {"files": files, "nextPageToken": None}
        file_id = parse.unquote(url.split("/files/", 1)[1].split("?", 1)[0])
        for item in files:
            if item.get("id") == file_id:
                return item
        raise FileNotFoundError(file_id)

    def get_bytes(self, url: str, token: str) -> bytes:
        file_id = parse.unquote(url.split("/files/", 1)[1].split("?", 1)[0])
        for item in self.data.get("files", []):
            if item.get("id") == file_id:
                return str(item.get("content", "")).encode("utf-8")
        raise FileNotFoundError(file_id)


def default_transport() -> DriveTransport:
    fixture = os.environ.get("LV_GOOGLE_DRIVE_MOCK_FIXTURE")
    if fixture:
        return FixtureDriveTransport(fixture)
    return UrlLibDriveTransport()


@dataclass(frozen=True)
class DriveSettings:
    enabled: bool
    client_id: str | None
    client_secret: str | None
    refresh_token: str | None
    root_id: str | None

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.client_id and self.client_secret and self.refresh_token)


def settings_from_env() -> DriveSettings:
    def clean(name: str) -> str | None:
        value = os.environ.get(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    return DriveSettings(
        enabled=os.environ.get("LV_GOOGLE_DRIVE_ENABLED", "").lower() in {"1", "true", "yes", "on"},
        client_id=clean("LV_GOOGLE_CLIENT_ID"),
        client_secret=clean("LV_GOOGLE_CLIENT_SECRET"),
        refresh_token=clean("LV_GOOGLE_REFRESH_TOKEN"),
        root_id=clean("LV_GOOGLE_DRIVE_ROOT_ID"),
    )


def import_dir() -> Path:
    override = os.environ.get("LV_GOOGLE_DRIVE_IMPORT_DIR")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "drive_imports"


def manifest_path() -> Path:
    return import_dir() / "import_manifest.json"


def status(settings: DriveSettings | None = None) -> dict[str, Any]:
    settings = settings or settings_from_env()
    configured = settings.configured
    return {
        "configured": configured,
        "mode": "explicit_import",
        "enabled": settings.enabled,
        "client_id_set": bool(settings.client_id),
        "client_secret_set": bool(settings.client_secret),
        "refresh_token_set": bool(settings.refresh_token),
        "root_id_set": bool(settings.root_id),
        "can_list": configured,
        "can_download": configured,
        "can_upload": False,
        "local_only_after_import": True,
        "setup_message": (
            "Google Drive import is configured for explicit local import."
            if configured
            else "Google Drive import is not configured on this machine."
        ),
    }


def ensure_configured(settings: DriveSettings | None = None) -> DriveSettings:
    settings = settings or settings_from_env()
    if not settings.configured:
        raise DriveConfigError("Google Drive import is not configured on this machine.")
    return settings


def _access_token(settings: DriveSettings, transport: DriveTransport) -> str:
    try:
        payload = transport.post_form(
            TOKEN_URL,
            {
                "client_id": settings.client_id or "",
                "client_secret": settings.client_secret or "",
                "refresh_token": settings.refresh_token or "",
                "grant_type": "refresh_token",
            },
        )
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DriveAuthError("Google Drive authorization failed.") from exc
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise DriveAuthError("Google Drive authorization failed.")
    return token


def _supports(mime_type: str) -> tuple[bool, bool, str | None]:
    suffix = SUPPORTED_IMPORT_MIME_TYPES.get(mime_type)
    if not suffix:
        return False, False, None
    return True, suffix in EXTRACTION_SUFFIXES, suffix


def _file_metadata(item: dict[str, Any]) -> dict[str, Any]:
    mime_type = str(item.get("mimeType") or item.get("mime_type") or "")
    supported_import, supported_extraction, _suffix = _supports(mime_type)
    size_value = item.get("size")
    try:
        size = int(size_value) if size_value not in (None, "") else None
    except (TypeError, ValueError):
        size = None
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "untitled"),
        "mime_type": mime_type,
        "modified_time": item.get("modifiedTime") or item.get("modified_time"),
        "size": size,
        "supported_for_import": supported_import,
        "supported_for_extraction": supported_extraction,
    }


def list_files(
    query: str = "",
    folder_id: str = "",
    page_token: str = "",
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> dict[str, Any]:
    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)

    q_parts = ["trashed = false"]
    root = folder_id.strip() or settings.root_id
    if root:
        q_parts.append(f"'{root}' in parents")
    if query.strip():
        safe_query = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        q_parts.append(f"name contains '{safe_query}'")
    params = {
        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size)",
        "pageSize": "25",
        "q": " and ".join(q_parts),
    }
    if page_token.strip():
        params["pageToken"] = page_token.strip()
    url = f"{DRIVE_API}/files?{parse.urlencode(params)}"
    try:
        data = transport.get_json(url, token)
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DriveAuthError("Google Drive list failed.") from exc
    files = [_file_metadata(item) for item in data.get("files", []) if isinstance(item, dict)]
    return {"files": files, "next_page_token": data.get("nextPageToken")}


def _safe_filename(name: str, suffix: str) -> str:
    stem = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .") or "drive-file"
    current_suffix = Path(stem).suffix.lower()
    if current_suffix != suffix:
        stem = f"{Path(stem).stem or 'drive-file'}{suffix}"
    return stem


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _load_manifest() -> dict[str, Any]:
    path = manifest_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    return data if isinstance(data, dict) else {}


def _write_manifest(entries: list[dict[str, Any]]) -> None:
    path = manifest_path()
    existing = _load_manifest()
    existing_entries = existing.get("imports") if isinstance(existing.get("imports"), list) else []
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "imports": [*existing_entries, *entries],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    os.chmod(path, 0o600)


def _download_url(file_id: str, mime_type: str) -> str:
    if mime_type == "application/vnd.google-apps.document":
        return f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}/export?mimeType=text/plain"
    return f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}?alt=media"


def _record_assignment(local_path: Path, purpose: str, assigned_student_id: str | None) -> None:
    from src.lingua_viva.filemap import record_imported_file_assignment

    record_imported_file_assignment(local_path, purpose, assigned_student_id)


def import_files(
    file_ids: list[str],
    purpose: str,
    assigned_student_id: str | None = None,
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
    student_exists: Any = None,
) -> dict[str, Any]:
    if not file_ids or not all(isinstance(item, str) and item.strip() for item in file_ids):
        raise ValueError("file_ids must be a non-empty list of opaque IDs.")
    if purpose not in PURPOSES:
        raise ValueError("Invalid Drive import purpose.")
    if purpose == "student_lens_source":
        if not assigned_student_id:
            raise ValueError("assigned_student_id is required for student_lens_source.")
        if student_exists is not None and not student_exists(assigned_student_id):
            raise ValueError("assigned_student_id is not in the current roster.")

    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    target_dir = import_dir().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []

    for file_id in [item.strip() for item in file_ids]:
        try:
            meta = transport.get_json(
                f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}?fields=id,name,mimeType,modifiedTime,size",
                token,
            )
            file_meta = _file_metadata(meta)
            supported_import, supported_extraction, suffix = _supports(file_meta["mime_type"])
            if not supported_import or not suffix:
                failed.append({
                    "drive_id": file_id,
                    "status": "unsupported_for_import",
                    "message": "This file type is not supported yet.",
                })
                continue
            content = transport.get_bytes(_download_url(file_id, file_meta["mime_type"]), token)
            local_path = _unique_path(target_dir, _safe_filename(file_meta["name"], suffix)).resolve()
            if target_dir not in local_path.parents:
                raise ValueError("Drive filename resolved outside the import cache.")
            local_path.write_bytes(content)
            os.chmod(local_path, 0o600)
            if purpose != "unassigned":
                _record_assignment(local_path, purpose, assigned_student_id)
            item = {
                "drive_id": file_id,
                "name": file_meta["name"],
                "local_path": str(local_path),
                "purpose": purpose,
                "assigned_student_id": assigned_student_id,
                "supported_for_extraction": supported_extraction,
                "status": "imported",
            }
            imported.append(item)
            manifest_entries.append({
                "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "drive_id": file_id,
                "drive_name": file_meta["name"],
                "mime_type": file_meta["mime_type"],
                "modified_time": file_meta.get("modified_time"),
                "local_path": str(local_path),
                "purpose": purpose,
                "assigned_student_id": assigned_student_id,
                "supported_for_extraction": supported_extraction,
                "status": "imported",
            })
        except Exception:
            failed.append({
                "drive_id": file_id,
                "status": "download_failed",
                "message": "This file could not be imported safely.",
            })
    if manifest_entries:
        _write_manifest(manifest_entries)
    return {
        "imported": imported,
        "failed": failed,
        "local_only_after_import": True,
    }
